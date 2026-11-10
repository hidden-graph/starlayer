"""SHACL 1.2 Inference Rules (editor's draft ``shacl12-inference-rules``), native engine.

``apply_rules(data_graph, shapes_graph, ...)`` runs the rules of the shapes graph over the data graph and returns a
``RuleResult``: the inferred triples and an ``InferredView`` (the data graph plus the inferred triples as an overlay).
The caller's data graph is never modified.

Supported (SHACL 1.2 forms only; no SHACL-AF 2017 behaviour, no JS rules, no pySHACL classes):

* ``sh:SPARQLRule`` (``sh:construct``, ``sh:prefixes``, ``$this`` pre-bound for shape rules, no binding for global
  rules) and instances of ``sh:SPARQLRuleTemplate`` (parameters pre-bound by local name);
* ``sh:TripleRule`` (``sh:subject`` / ``sh:predicate`` / ``sh:object`` node expressions, evaluated by
  ``starlayer.shacl_engine.expressions.evaluate_expression``, imported lazily);
* ``sh:rule`` (shape rules), rules with no shape (global rules), ``sh:condition`` (with the ``NodeShape`` + ``rdfs:Class``
  superclass extension), ``sh:deactivated``, ``sh:layer``, ``sh:order`` (order groups), ``sh:runOnce`` (once per focus
  node), ``sh:expectedPredicate`` (derived ``sh:defaultValue`` / ``sh:values`` triples, removed at layer end),
  ``sh:tempTriple`` (removed at the end), ``sh:RuleSet`` / ``sh:hasRule`` / ``sh:includesRuleSet``, ``sh:entailment``
  (``sh:RulesEntailment`` or rule-set IRIs), ``sh:ruleProcessor`` (any value: an unsupported processor is a failure).

The algorithm is the draft's pseudocode: layers ascending; per layer one pass over run-once rules (by order group), then
the iterating rules (by order group) repeated until nothing new is inferred.

Performance note: SPARQL runs on a materialised ``StarLayerGraph`` (base copy plus inferred), built once per
``InferredView`` and kept in step incrementally. A native overlay query (union dataset, or the backend's own
``sparql_query``) is the follow-up.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from starlayer.shacl_engine import xsd_values as xv
from starlayer.shacl_engine.executor import Context
from starlayer.shacl_engine.interface import Solutions, Term
from starlayer.shacl_engine.plan import SH, Plan, ShapeError
from starlayer.shacl_engine.sparql_support import (
    check_query,
    is_true,
    with_prefixes,
)
from starlayer.shacl_engine.terms import (
    RDF,
    RDFS,
    Literal,
    check_graphs,
    engine_view,
    text,
    to_engine,
    with_term_policy,
)
from starlayer.shacl_engine.terms import BlankNode as BNode
from starlayer.shacl_engine.terms import NamedNode as URIRef

Triple = tuple[Term, Term, Term]
_REIFIES = RDF.reifies


class RuleError(ValueError):
    """A rule failed, or the rules graph is ill-formed or needs something unsupported (the rule set fails as a whole)."""


# --------------------------------------------------------------------------------------------------------------------
# The overlay view


class InferredView:
    """A data graph plus inferred triples, as a ``GraphView`` (and ``SparqlCapable``). ``base`` is never modified. Engine
    terms in and out; ``base`` must be an engine-term view."""

    engine_terms = True

    @property
    def preserves_lexical_forms(self) -> bool:
        """The base's: inferred triples are held as terms, so the view is as faithful as its data."""
        return getattr(self.base, "preserves_lexical_forms", True)

    def __init__(self, base: Any) -> None:
        self.base = base
        self._inferred: set[Triple] = set()
        self._index: tuple[dict, dict, dict] = ({}, {}, {})
        self._mat: Any = None

    # -- writes (inferred triples only)
    def add(self, triple: Triple) -> bool:
        """Add an inferred triple; True if it is new to the view (absent from base and from the inferred set)."""
        if triple in self._inferred or triple in self.base:
            return False
        self._inferred.add(triple)
        for idx, term in zip(self._index, triple, strict=True):
            idx.setdefault(term, set()).add(triple)
        if self._mat is not None:
            self._mat.add(triple)
        return True

    def remove(self, triple: Triple) -> None:
        """Remove an inferred triple (a triple of the base cannot be removed)."""
        if triple not in self._inferred:
            return
        self._inferred.discard(triple)
        for idx, term in zip(self._index, triple, strict=True):
            idx[term].discard(triple)
        self._mat = None  # rebuilt lazily on the next query

    @property
    def inferred(self) -> frozenset[Triple]:
        return frozenset(self._inferred)

    # -- GraphView
    def _inferred_matching(self, s: Term | None, p: Term | None, o: Term | None) -> Iterator[Triple]:
        bound = [(idx, t) for idx, t in zip(self._index, (s, p, o), strict=True) if t is not None]
        if not bound:
            yield from list(self._inferred)
            return
        candidates = min((idx.get(t, set()) for idx, t in bound), key=len)
        for tr in list(candidates):
            if (s is None or tr[0] == s) and (p is None or tr[1] == p) and (o is None or tr[2] == o):
                yield tr

    def triples(self, pattern: tuple[Term | None, Term | None, Term | None]) -> Iterator[Triple]:
        s, p, o = pattern
        yield from self.base.triples((s, p, o))
        yield from self._inferred_matching(s, p, o)  # inferred triples are never in base (see add)

    def objects(self, subject: Term | None = None, predicate: Term | None = None) -> Iterator[Term]:
        seen: set = set()
        for _s, _p, o in self.triples((subject, predicate, None)):
            if o not in seen:
                seen.add(o)
                yield o

    def predicates(self, subject: Term | None = None, object: Term | None = None) -> Iterator[Term]:  # noqa: A002
        seen: set = set()
        for _s, p, _o in self.triples((subject, None, object)):
            if p not in seen:
                seen.add(p)
                yield p

    def subjects(self, predicate: Term | None = None, object: Term | None = None) -> Iterator[Term]:  # noqa: A002
        seen: set = set()
        for s, _p, _o in self.triples((None, predicate, object)):
            if s not in seen:
                seen.add(s)
                yield s

    def namespaces(self) -> Iterator[tuple[str, str]]:
        """The base graph's prefixes (report text and report graphs print prefixed names)."""
        return iter(self.base.namespaces())

    def items(self, head: Term) -> Iterator[Term]:
        """The members of the RDF list at ``head``."""
        seen: set = set()
        while head is not None and head != RDF.nil and head not in seen:
            seen.add(head)
            first = next(self.objects(head, RDF.first), None)
            if first is None:
                return
            yield first
            head = next(self.objects(head, RDF.rest), None)

    def predicate_objects(self, subject: Term | None = None) -> Iterator[tuple[Term, Term]]:
        for _s, p, o in self.triples((subject, None, None)):
            yield p, o

    def __contains__(self, triple: Triple) -> bool:
        return triple in self._inferred or triple in self.base

    # -- SPARQL: through the materialised union
    def materialised(self) -> Any:
        """An ``StarLayerGraph`` holding the base and the inferred triples (built once, then kept in step by ``add`` / ``remove``)."""
        if self._mat is None:
            from starlayer.shacl_engine.graphs import new_graph

            mat = new_graph()
            mat.extend(list(self.base.triples((None, None, None))))
            mat.extend(list(self._inferred))
            self._mat = mat
        return self._mat

    def sparql_query(
        self, text: str, init_bindings: Mapping[str, Term] | None = None, custom_functions: Any = None
    ) -> Solutions:
        return self.materialised().sparql_query(text, init_bindings, custom_functions)

    def construct(self, text: str, init_bindings: Mapping[str, Term] | None) -> list[Triple]:
        import pyoxigraph as ox

        raw = self.materialised().engine_view()._run(text, dict(init_bindings or {}), None, None)
        if not isinstance(raw, ox.QueryTriples):
            raise RuleError("sh:construct must be a CONSTRUCT query")
        return [(t.subject, t.predicate, t.object) for t in raw]


_OXIGRAPH_OVERLAY = os.environ.get("STARLAYER_SHACL_OVERLAY", "").strip().lower() == "oxigraph"


def use_oxigraph_overlay(enabled: bool = True) -> None:
    """Opt in (or out) of the Oxigraph-backed overlay (``overlay_oxigraph.OxigraphOverlay``) for inferred triples. The
    default is the Python ``InferredView``; the environment variable ``STARLAYER_SHACL_OVERLAY=oxigraph`` selects the
    Oxigraph one at import time. Experimental: see docs/working/shacl-engine-overlay-oxigraph.md."""
    global _OXIGRAPH_OVERLAY
    _OXIGRAPH_OVERLAY = bool(enabled)


def new_overlay(base: Any) -> InferredView:
    """A fresh overlay over ``base`` (the selected implementation)."""
    if _OXIGRAPH_OVERLAY:
        from starlayer.shacl_engine.overlay_oxigraph import OxigraphOverlay

        return OxigraphOverlay(base)
    return InferredView(base)


# --------------------------------------------------------------------------------------------------------------------
# Rules read from the shapes graph


@dataclass
class Rule:
    node: Term
    types: tuple[Term, ...]
    layer: float
    order: float
    run_once: bool
    shapes: tuple[Term, ...]  # shapes that link the rule with sh:rule (empty: a global rule)
    conditions: tuple[Term, ...]
    expected_predicates: tuple[Term, ...]


@dataclass
class RuleResult:
    """``inferred``: the inferred triples that remain (temporary triples removed). ``view``: data graph + ``inferred``.
    ``failures``: the messages of failed rules (empty on success). ``iterations``: iterating passes taken."""

    inferred: frozenset[Triple]
    view: InferredView
    failures: list[str] = field(default_factory=list)
    iterations: int = 0
    source_rules: tuple[tuple[Triple, Term], ...] = ()  # ``(inferred triple, rule node)``, when asked for (``sh:sourceRule``, Rules 9)

    @property
    def ok(self) -> bool:
        return not self.failures


def _number(graph: Any, node: Term, pred: Term, default: float = 0) -> float:
    values = list(graph.objects(node, pred))
    if len(values) > 1:
        raise RuleError(f"{node!r}: more than one {text(pred)}")
    if not values:
        return default
    v = values[0]
    n = xv.numeric(v)
    if n is None:
        raise RuleError(f"{node!r}: {text(pred)} must be a numeric literal")
    return float(n)


def _boolean(graph: Any, node: Term, pred: Term) -> bool:
    values = list(graph.objects(node, pred))
    if len(values) > 1:
        raise RuleError(f"{node!r}: more than one {text(pred)}")
    return bool(values) and is_true(values[0])


def _closure(graph: Any, start: Iterable[Term], step) -> list[Term]:
    seen: dict = {}
    queue = list(start)
    while queue:
        n = queue.pop()
        if n in seen:
            continue
        seen[n] = None
        queue.extend(step(n))
    return list(seen)


def _rule_classes(graph: Any) -> set[Term]:
    """``sh:Rule`` and everything below it by ``rdfs:subClassOf`` (SPARQLRule, TripleRule, templates, ...)."""
    return set(
        _closure(graph, [SH.Rule, SH.SPARQLRule, SH.TripleRule], lambda c: graph.subjects(RDFS.subClassOf, c))
    )


def all_rule_nodes(graph: Any) -> list[Term]:
    """Every rule of the graph (the default rule set): linked by ``sh:rule`` / ``sh:hasRule`` or an instance of a rule
    class; deterministic order of first discovery."""
    classes = _rule_classes(graph)
    found: dict = {}
    for _s, r in ((s, o) for s, _p, o in graph.triples((None, SH.rule, None))):
        found.setdefault(r, None)
    for _s, _p, r in graph.triples((None, SH.hasRule, None)):
        found.setdefault(r, None)
    for c in classes:
        for r in graph.subjects(RDF.type, c):
            found.setdefault(r, None)
    return list(found)


def rule_set_members(graph: Any, rule_sets: Iterable[Term]) -> list[Term]:
    """Rules of the given rule sets and the sets they include (transitively)."""
    sets = _closure(graph, rule_sets, lambda s: graph.objects(s, SH.includesRuleSet))
    members: dict = {}
    for s in sets:
        if (s, SH.ruleProcessor, None) in graph:  # a rule set that names a processor needs it, and none is available
            raise RuleError(f"{s!r}: sh:ruleProcessor is declared and no custom rule processor is available")
        for r in graph.objects(s, SH.hasRule):
            members.setdefault(r, None)
    return list(members)


def entailment_selection(shapes: Any) -> tuple[bool, list[Term]]:
    """What ``sh:entailment`` on the shapes graph asks of the rules engine: ``(active, rule_sets)``. ``active`` is False
    when no ``sh:RulesEntailment`` nor rule-set IRI is declared. ``sh:RulesEntailment`` means the default rule set (all
    rules); rule-set IRIs select those sets, unless ``sh:RulesEntailment`` is also present (then all run together)."""
    shapes = engine_view(shapes)
    values = [o for _s, _p, o in shapes.triples((None, SH.entailment, None))]
    sets = [v for v in values if (v, RDF.type, SH.RuleSet) in shapes]
    wants_all = SH.RulesEntailment in values
    return bool(wants_all or sets), ([] if wants_all else sets)


def read_rule(graph: Any, node: Term) -> Rule:
    classes = _rule_classes(graph)
    types = tuple(t for t in graph.objects(node, RDF.type) if t in classes)
    if not types:
        raise RuleError(f"{node!r}: a rule needs an rdf:type that is a subclass of sh:Rule")
    for holder in (node, *types):
        if (holder, SH.ruleProcessor, None) in graph:
            raise RuleError(f"{holder!r}: sh:ruleProcessor is declared and no custom rule processor is available")
    return Rule(
        node=node,
        types=types,
        layer=_number(graph, node, SH.layer),
        order=_number(graph, node, SH.order),
        run_once=_boolean(graph, node, SH.runOnce),
        shapes=tuple(dict.fromkeys(graph.subjects(SH.rule, node))),
        conditions=tuple(graph.objects(node, SH.condition)),
        expected_predicates=tuple(graph.objects(node, SH.expectedPredicate)),
    )


# --------------------------------------------------------------------------------------------------------------------
# Execution


def _well_formed(t: Triple) -> bool:
    s, p, o = t
    return isinstance(s, (URIRef, BNode)) and isinstance(p, URIRef) and o is not None


_NOW_TOKEN = re.compile(r"""[#"'<]|(?<![\w:?$])NOW\s*\(\s*\)""", re.IGNORECASE)


def _fix_now(text: str, now: str) -> str:
    """``text`` with every ``NOW()`` call (not inside a comment, string or IRI) replaced by the dateTime literal ``now``."""
    from starlayer.graph.oxgraph.run import _IRI_AT, _STRING_AT

    out: list[str] = []
    i = 0
    while (m := _NOW_TOKEN.search(text, i)) is not None:
        c = m.group()
        if c == "#":
            end = text.find("\n", m.start())
            end = len(text) if end < 0 else end
        elif c in "\"'<":
            token = (_IRI_AT if c == "<" else _STRING_AT).match(text, m.start())
            end = token.end() if token else m.end()
        else:
            out.append(text[i : m.start()])
            out.append(now)
            i = m.end()
            continue
        out.append(text[i:end])
        i = end
    out.append(text[i:])
    return "".join(out)


class _Run:
    def __init__(self, view: InferredView, plan: Plan, max_iterations: int, max_triples: int | None) -> None:
        # Inference Rules 11.1: NOW() returns the same result in all SPARQL rules during the execution of a rule set
        self.now = '"' + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ") + '"^^<http://www.w3.org/2001/XMLSchema#dateTime>'
        self.view = view
        self.plan = plan
        self.shapes = plan.shapes_graph
        self.max_iterations = max_iterations
        self.max_triples = max_triples
        self.done_once: set = set()  # (rule, focus) of run-once rules already executed
        self.derived: set[Triple] = set()  # sh:defaultValue / sh:values triples of the current layer
        self.iterations = 0
        self.source_rules: list[tuple[Triple, Term]] | None = None  # set to a list to record which rule produced each triple

    def run_group(self, ctx: Context, group: list[Rule]) -> list[Triple]:
        """The triples the rules of ``group`` produce over ``ctx`` (every rule of a group reads the same graph)."""
        out: list[Triple] = []
        for rule in group:
            produced = self.execute(ctx, rule)
            if self.source_rules is not None:
                self.source_rules.extend((t, rule.node) for t in produced)
            out.extend(produced)
        return out

    # -- focus nodes
    def _conditions(self, rule: Rule) -> list[Term]:
        out: list[Term] = []
        for cond in rule.conditions:
            if self._deactivated(cond):
                continue
            out.append(cond)
            if self._is_node_shape_class(cond):
                for sup in _closure(
                    self.shapes, self.shapes.objects(cond, RDFS.subClassOf), lambda c: self.shapes.objects(c, RDFS.subClassOf)
                ):
                    if sup != cond and self._is_node_shape_class(sup) and not self._deactivated(sup):
                        out.append(sup)
        return list(dict.fromkeys(out))

    def _deactivated(self, node: Term) -> bool:
        return _boolean(self.shapes, node, SH.deactivated)

    def _is_node_shape_class(self, node: Term) -> bool:
        types = set(self.shapes.objects(node, RDF.type))
        return SH.NodeShape in types and bool(types & {RDFS.Class, SH.ShapeClass})

    def focus_nodes(self, ctx: Context, rule: Rule) -> list[Term]:
        if not rule.shapes:
            return []
        out: dict = {}
        conditions = self._conditions(rule)
        for shape_node in rule.shapes:
            if self._deactivated(shape_node):
                continue
            for n in ctx.shape_focus(ctx.shape(shape_node)):
                if n in out:
                    continue
                try:
                    if all(ctx.conforms(c, n) for c in conditions):
                        out[n] = None
                except ShapeError as exc:
                    raise RuleError(f"{rule.node!r}: sh:condition check failed: {exc}") from exc
        return list(out)

    # -- executing one rule: returns the triples it infers (not yet filtered against the view)
    def execute(self, ctx: Context, rule: Rule) -> list[Triple]:
        focus = self.focus_nodes(ctx, rule)
        if rule.run_once:
            if rule.shapes:
                focus = [f for f in focus if (rule.node, f) not in self.done_once]
                self.done_once.update((rule.node, f) for f in focus)
            else:
                if (rule.node, None) in self.done_once:
                    return []
                self.done_once.add((rule.node, None))
        runs: list[Term | None] = focus if rule.shapes else [None]
        out: list[Triple] = []
        for f in runs:
            if SH.TripleRule in rule.types:
                out.extend(self._triple_rule(ctx, rule, f))
            else:
                out.extend(self._sparql_rule(rule, f))
        return [t for t in out if _well_formed(t)]

    def _sparql_rule(self, rule: Rule, focus: Term | None) -> list[Triple]:
        g = self.shapes
        template = self._template_of(rule)
        holder = rule.node
        bindings: dict[str, Term] = {} if focus is None else {"this": focus}
        constructs = list(g.objects(rule.node, SH.construct))
        if template is not None and (template, SH.construct, None) in g:
            holder = template
            constructs = list(g.objects(template, SH.construct))
            bindings.update(self._template_bindings(rule, template))
        if SH.SPARQLRule not in rule.types and template is None:
            raise RuleError(f"{rule.node!r}: unsupported rule type {sorted(text(t) for t in rule.types)}")
        if len(constructs) != 1 or not isinstance(constructs[0], Literal):
            raise RuleError(f"{rule.node!r}: exactly one string sh:construct is required")
        prefix_holder = holder if (holder, SH.prefixes, None) in g else rule.node
        text = _fix_now(with_prefixes(self.plan, prefix_holder, constructs[0].value), self.now)
        # the same forbidden constructs as for sh:select and sh:ask (SHACL 1.2 SPARQL Extensions, "Pre-binding of Variables"):
        # MINUS, SERVICE (which would send a request from the shapes graph), VALUES / assignment of a pre-bound variable
        try:
            check_query(self.plan, text, bindings, construct=True)
            return self.view.construct(text, bindings)
        except RuleError:
            raise
        except Exception as exc:  # noqa: BLE001  (a query that does not parse or evaluate fails the rule)
            raise RuleError(f"{rule.node!r}: SPARQL rule failed: {exc}") from exc

    def _template_of(self, rule: Rule) -> Term | None:
        """The rule template ``rule`` instantiates: its type, or the nearest superclass of that type (``rdfs:subClassOf``)
        that carries the ``sh:construct``; the first type that is not a built-in rule class when none does."""
        g = self.shapes
        custom = [t for t in rule.types if t not in (SH.SPARQLRule, SH.TripleRule, SH.Rule)]
        for t in custom:
            for c in _closure(g, [t], lambda c: g.objects(c, RDFS.subClassOf)):
                if (c, SH.construct, None) in g:
                    return c
        return custom[0] if custom else None

    def _template_bindings(self, rule: Rule, template: Term) -> dict[str, Term]:
        from starlayer.shacl_engine.components.sparql_components import _parameters

        out: dict[str, Term] = {}
        for pred, name, optional in _parameters(self.shapes, template):
            values = list(self.shapes.objects(rule.node, pred))
            if len(values) > 1:
                raise RuleError(f"{rule.node!r}: more than one value for template parameter {text(pred)}")
            if values:
                out[name] = values[0]
            elif not optional:
                raise RuleError(f"{rule.node!r}: missing value for template parameter {text(pred)}")
        return out

    def _triple_rule(self, ctx: Context, rule: Rule, focus: Term | None) -> list[Triple]:
        evaluate = _evaluator()
        parts: list[list[Term]] = []
        for pred in (SH.subject, SH.predicate, SH.object):
            exprs = list(self.shapes.objects(rule.node, pred))
            if len(exprs) > 1:
                raise RuleError(f"{rule.node!r}: more than one {text(pred)}")
            if exprs:
                try:
                    parts.append(list(evaluate(ctx, exprs[0], focus, None)))
                except Exception as exc:  # noqa: BLE001
                    raise RuleError(f"{rule.node!r}: node expression for {text(pred)} failed: {exc}") from exc
            else:
                parts.append([] if focus is None else [focus])
        return [(s, p, o) for s in parts[0] for p in parts[1] for o in parts[2]]

    # -- sh:expectedPredicate: derived sh:defaultValue / sh:values triples
    def compute_derived(self, ctx: Context, predicates: set[Term]) -> None:
        g = self.shapes
        evaluate = None
        for ps in dict.fromkeys(s for p in predicates for s in g.subjects(SH.path, p)):
            if self._deactivated(ps):
                continue
            pred = next(g.objects(ps, SH.path))
            if not isinstance(pred, URIRef):
                continue
            shape = ctx.shape(ps)
            parents = [s for s in g.subjects(SH.property, ps) if not self._deactivated(s)]
            focus: dict = {}
            for owner in (*parents, ps):
                if owner != ps or shape.targets:
                    for n in ctx.shape_focus(ctx.shape(owner)):
                        focus.setdefault(n, None)
            exprs = list(g.objects(ps, SH["values"]))
            defaults = list(g.objects(ps, SH.defaultValue))
            for n in focus:
                values: list[Term] = []
                for expr in exprs:
                    if isinstance(expr, BNode):
                        evaluate = evaluate or _evaluator()
                        try:
                            values.extend(evaluate(ctx, expr, n, None))
                        except Exception:  # noqa: BLE001  (a failing expression derives no value)
                            continue
                    else:
                        values.append(expr)
                if not values and not any(True for _ in self.view.objects(n, pred)):
                    # Rules 3.8: sh:defaultValue can be a node expression too (Context.value_nodes evaluates it the same way)
                    values = list(dict.fromkeys(ctx._expression_values(tuple(defaults), n)))
                for v in values:
                    t = (n, pred, v)
                    if self.view.add(t):
                        self.derived.add(t)

    def end_layer(self) -> None:
        for t in self.derived:
            self.view.remove(t)
        self.derived = set()

    def add_inferred(self, triples: Iterable[Triple]) -> bool:
        changed = False
        for t in triples:
            if t in self.derived:  # also inferred by a rule: kept (and the rule's own triple counts as new once)
                self.derived.discard(t)
                changed = True
            elif self.view.add(t):
                changed = True
        if self.max_triples is not None and len(self.view.inferred) > self.max_triples:
            raise RuleError(f"more than {self.max_triples} triples inferred")
        return changed

    def delete_temp_triples(self) -> None:
        v = self.view
        reifiers = [s for s, _p, o in v.triples((None, SH.tempTriple, None)) if is_true(o)]
        for r in reifiers:
            for _s, _p, tt in list(v.triples((r, _REIFIES, None))):
                v.remove((tt.subject, tt.predicate, tt.object) if hasattr(tt, "subject") else tt)
            for tr in list(v.triples((r, None, None))):
                v.remove(tr)


def _evaluator():
    try:
        from starlayer.shacl_engine.expressions import evaluate_expression
    except ImportError as exc:
        raise RuleError("sh:TripleRule and node-expression values need starlayer.shacl_engine.expressions") from exc
    return evaluate_expression


def _groups(rules: list[Rule]) -> list[list[Rule]]:
    by: dict[float, list[Rule]] = {}
    for r in rules:
        by.setdefault(r.order, []).append(r)
    return [by[o] for o in sorted(by)]


@with_term_policy
def apply_rules(
    data_graph: Any,
    shapes_graph: Any = None,
    *,
    rule_sets: Iterable[Term] | None = None,
    max_iterations: int = 1000,
    max_triples: int | None = None,
    raise_on_failure: bool = True,
    source_rules: bool = False,
) -> RuleResult:
    """Run the rules of ``shapes_graph`` (default: ``data_graph`` itself) over ``data_graph``.

    ``rule_sets``: IRIs of ``sh:RuleSet`` instances to run (with the sets they include); ``None`` runs the default rule set,
    every rule of the shapes graph. A failing rule fails the whole rule set: ``RuleError`` is raised, or with
    ``raise_on_failure=False`` returned in ``RuleResult.failures`` (``inferred`` is then what was derived so far)."""
    check_graphs((data_graph, "data graph"), (shapes_graph, "shapes graph"))
    data_graph = engine_view(data_graph, "data graph")  # the term-model boundary: rdflib / StarLayer graphs in, an StarLayerGraph copy inside
    shapes = engine_view(shapes_graph, "shapes graph") if shapes_graph is not None else data_graph
    rule_sets = None if rule_sets is None else [to_engine(s) for s in rule_sets]
    view = new_overlay(data_graph)
    plan = Plan(shapes_graph=shapes)
    run = _Run(view, plan, max_iterations, max_triples)
    if source_rules:
        run.source_rules = []
    failures: list[str] = []
    try:
        nodes = all_rule_nodes(shapes) if rule_sets is None else rule_set_members(shapes, rule_sets)
        rules = [r for n in nodes if not _boolean(shapes, n, SH.deactivated) for r in [read_rule(shapes, n)]]
        for layer in sorted({r.layer for r in rules}):
            in_layer = [r for r in rules if r.layer == layer]
            once = [r for r in in_layer if r.run_once]
            iterating = [r for r in in_layer if not r.run_once]
            expected = {p for r in in_layer for p in r.expected_predicates}
            if expected:
                run.compute_derived(Context(data=view, plan=plan), expected)
            for group in _groups(once):
                ctx = Context(data=view, plan=plan)
                run.add_inferred(run.run_group(ctx, group))
            changed = bool(iterating)
            while changed:
                run.iterations += 1
                if run.iterations > max_iterations:
                    raise RuleError(f"rules did not reach a fixpoint within {max_iterations} iterations")
                changed = False
                for group in _groups(iterating):
                    ctx = Context(data=view, plan=plan)
                    if run.add_inferred(run.run_group(ctx, group)):
                        changed = True
            run.end_layer()
        run.delete_temp_triples()
    except (RuleError, ShapeError) as exc:
        if raise_on_failure:
            raise exc if isinstance(exc, RuleError) else RuleError(str(exc)) from exc
        failures.append(str(exc))
    kept = set(view.inferred)  # temporary triples are gone: a rule's record follows its triple
    recorded = tuple(dict.fromkeys((t, rule) for t, rule in (run.source_rules or ()) if t in kept))
    return RuleResult(
        inferred=frozenset(view.inferred),
        view=view,
        failures=failures,
        iterations=run.iterations,
        source_rules=recorded,
    )


def validate_with_rules(data_graph: Any, shapes_graph: Any = None, *, rules: bool | None = None, **options: Any) -> Any:
    """``validate()`` on the evaluation graph (data plus inferred triples). ``rules=None``: run rules when the shapes graph
    declares ``sh:entailment`` (``sh:RulesEntailment`` or rule-set IRIs); ``True`` runs the default rule set; ``False``
    skips. Returns ``(outcome, rule_result_or_None)``; the data graph is not modified."""
    from starlayer.shacl_engine.api import validate

    shapes = shapes_graph if shapes_graph is not None else data_graph
    sets: list[Term] | None = None
    active = bool(rules)
    if rules is None:
        active, sets = entailment_selection(shapes)
        sets = sets or None
    if not active:
        return validate(data_graph, shapes, rules=False), None
    result = apply_rules(data_graph, shapes, rule_sets=sets, **options)
    return validate(result.view, shapes, rules=False), result


__all__ = [
    "InferredView",
    "Rule",
    "RuleError",
    "RuleResult",
    "all_rule_nodes",
    "apply_rules",
    "new_overlay",
    "entailment_selection",
    "read_rule",
    "rule_set_members",
    "use_oxigraph_overlay",
    "validate_with_rules",
]
