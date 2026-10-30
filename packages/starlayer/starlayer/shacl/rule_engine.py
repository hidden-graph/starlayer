"""The rule execution algorithm of SHACL 1.2 Inference Rules, section 8.

pySHACL runs each rule's own fixpoint inside ``SHACLRule.apply()``, one shape after another, and adds the triples a rule
infers before the next rule looks. The specification works the other way round: all rules of a layer take part in one
iteration, rules of the same ``sh:order`` read the same graph, and what they infer becomes visible together. That cannot be
expressed by wrapping ``apply()``, so this module takes the rules' candidate triples and decides itself when they are added.

For each layer, in ascending order (default 0):

1. the expected derived triples of the layer's rules are computed once (``derive``);
2. the ``sh:runOnce`` rules run in one iteration;
3. the other rules run in iterations until one adds nothing (one iteration when the executor does not iterate);
4. the derived triples are removed again, except those a rule also inferred.

An iteration visits the ``sh:order`` groups in ascending order. The rules of a group are all evaluated against the graph as it
stood before the group, and then their triples are added together, so a rule never sees what another rule of its own group
inferred in the same iteration. Deactivated rules are ignored. A failing rule (a bad query, a failing node expression, a
rule type this engine cannot run) raises.

The two rule types are executed the way pySHACL's classes do (``sh:construct`` with ``$this`` pre-bound; node expressions
for the three terms, a missing one defaulting to the focus node), without adding anything to the graph. A *global* rule is one
no shape refers to: it runs once per iteration with no focus node.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

import rdflib
from rdflib import BNode, Literal, URIRef
from rdflib.namespace import Namespace

SH = Namespace("http://www.w3.org/ns/shacl#")
RDF_TYPE = rdflib.RDF.type
SUBCLASS_OF = rdflib.RDFS.subClassOf

SPARQL_RULE = "sparql"
TRIPLE_RULE = "triple"


@dataclass(eq=False)
class EngineRule:
    """One rule as the engine sees it: when it runs (layer, run-once, order) and how to get its triples.

    ``source`` is pySHACL's rule object for a rule a shape refers to. A global rule has no source: ``kind`` says what it is,
    ``query`` is the ``sh:construct`` text with its prefixes in front, ``terms`` the ``(subject, predicate, object)``
    expressions of a triple rule. ``shape`` is anything with the ``sg`` (pySHACL's shapes graph) the rule was read from."""

    node: Any
    shape: Any
    layer: Decimal = Decimal(0)
    order: Decimal = Decimal(0)
    run_once: bool = False
    deactivated: bool = False
    index: int = 0
    kind: str | None = None
    source: Any = None
    query: str | None = None
    terms: tuple[Any, Any, Any] | None = None
    bindings: dict[str, Any] = field(default_factory=dict)  # the parameter values of an instance of a rule template


def number(sg: Any, node: Any, predicate: Any, name: str) -> Decimal:
    """The value of ``predicate`` on ``node`` (an ``xsd:integer``, ``xsd:decimal`` or float literal), 0 when absent."""
    from pyshacl.errors import RuleLoadError

    values = list(sg.objects(node, predicate))
    if not values:
        return Decimal(0)
    if len(values) > 1:
        raise RuleLoadError(
            f"A SHACL Rule can have only one {name} property.", "https://www.w3.org/TR/shacl12-inference-rules/"
        )
    value = values[0].value if isinstance(values[0], Literal) else None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise RuleLoadError(
            f"A SHACL Rule's {name} must be an xsd:decimal or xsd:integer literal, got {values[0].n3()}.",
            "https://www.w3.org/TR/shacl12-inference-rules/",
        )
    try:
        return Decimal(str(value)) if isinstance(value, float) else Decimal(value)
    except (InvalidOperation, ValueError) as error:  # NaN, infinity
        raise RuleLoadError(
            f"A SHACL Rule's {name} must be a finite number, got {values[0].n3()}.",
            "https://www.w3.org/TR/shacl12-inference-rules/",
        ) from error


def flag(sg: Any, node: Any, predicate: Any) -> bool:
    """Whether ``predicate`` on ``node`` is the literal true."""
    return any(isinstance(v, Literal) and bool(v.value) for v in sg.objects(node, predicate))


def _local_name(iri: Any) -> str:
    text = str(iri)
    return text[max(text.rfind("#"), text.rfind("/")) + 1 :]


def _superclasses(graph: Any, node: Any) -> set:
    """``node`` and everything it is a ``rdfs:subClassOf``, transitively."""
    seen, pending = {node}, [node]
    while pending:
        for parent in graph.objects(pending.pop(), SUBCLASS_OF):
            if parent not in seen:
                seen.add(parent)
                pending.append(parent)
    return seen


def template_of(graph: Any, node: Any) -> Any | None:
    """The ``sh:SPARQLRuleTemplate`` ``node`` is an instance of (directly or through a subclass), or None. Inference Rules 12:
    a template is a class and its instances are the rules. An instance of two templates is a failure."""
    from pyshacl.errors import RuleLoadError

    templates = {
        candidate
        for type_ in graph.objects(node, RDF_TYPE)
        for candidate in _superclasses(graph, type_)
        if (candidate, RDF_TYPE, SH.SPARQLRuleTemplate) in graph
    }
    if len(templates) > 1:
        raise RuleLoadError(
            f"The rule {node.n3()} is an instance of more than one SPARQL rule template.",
            "https://www.w3.org/TR/shacl12-inference-rules/#sparql-rule-templates",
        )
    return next(iter(templates)) if templates else None


def template_construct(graph: Any, template: Any) -> str:
    """The ``sh:construct`` of a template: exactly one ``xsd:string`` literal."""
    from pyshacl.errors import RuleLoadError

    values = list(graph.objects(template, SH.construct))
    if len(values) != 1 or not isinstance(values[0], Literal):
        raise RuleLoadError(
            f"The SPARQL rule template {template.n3()} must have exactly one sh:construct, a string.",
            "https://www.w3.org/TR/shacl12-inference-rules/#sparql-rule-templates",
        )
    return str(values[0])


def template_bindings(graph: Any, node: Any, template: Any) -> dict[str, Any]:
    """The pre-bound variables of an instance: one per parameter of ``template``, named after the local name of its ``sh:path``
    (SPARQL Extensions 4.2.1), valued by what ``node`` has for that property. A required parameter without a value, or with
    several, is a failure (Inference Rules 12 gives the first; one value per run is this engine's reading of the second);
    an absent optional parameter is left unbound."""
    from pyshacl.errors import RuleLoadError

    where = "https://www.w3.org/TR/shacl12-inference-rules/#sparql-rule-templates"
    bindings: dict[str, Any] = {}
    for parameter in graph.objects(template, SH.parameter):
        paths = list(graph.objects(parameter, SH.path))
        if len(paths) != 1 or not isinstance(paths[0], URIRef):
            raise RuleLoadError(f"A parameter of the SPARQL rule template {template.n3()} needs exactly one IRI sh:path.", where)
        values = list(graph.objects(node, paths[0]))
        optional = flag(graph, parameter, SH.optional)
        if not values:
            if not optional:
                raise RuleLoadError(
                    f"The rule {node.n3()} has no value for the required parameter {paths[0].n3()} of its template {template.n3()}.", where
                )
            continue
        if len(values) > 1:
            raise RuleLoadError(f"The rule {node.n3()} has several values for the parameter {paths[0].n3()}; it takes one.", where)
        bindings[_local_name(paths[0])] = values[0]
    return bindings


def from_shape_rule(rule: Any, index: int) -> EngineRule:
    """Wrap one of pySHACL's rule objects (what ``gather_rules`` returns for ``sh:rule``). An instance of a rule template comes
    here as a SPARQL rule (the template's query is put on it for ``gather_rules``) and gets its parameter values."""
    sg = rule.shape.sg
    template = template_of(sg.graph, rule.node)
    return EngineRule(
        node=rule.node,
        shape=rule.shape,
        layer=number(sg, rule.node, SH.layer, "sh:layer"),
        order=rule.order,
        run_once=flag(sg, rule.node, SH.runOnce),
        deactivated=rule.deactivated,
        index=index,
        source=rule,
        bindings=template_bindings(sg.graph, rule.node, template) if template is not None else {},
    )


def well_formed(triple: tuple) -> bool:
    """A subject is an IRI, blank node or triple term; a predicate is an IRI (Inference Rules 11.2: skip the rest)."""
    subject, predicate, _object = triple
    return (
        isinstance(predicate, URIRef)
        and not isinstance(subject, Literal)
        and (isinstance(subject, (URIRef, BNode)) or hasattr(subject, "subject"))
    )


def target_graph(graph: Any) -> Any:
    """Where inferred triples go: the default graph of a dataset, otherwise the graph itself."""
    return graph.default_graph if isinstance(graph, rdflib.Dataset) else graph


def _focus_nodes(rule: EngineRule, graph: Any, executor: Any, focus_nodes: Any, done: set, targets: Any = None) -> list:
    """The focus nodes a shape rule runs for now (pySHACL's rules: the shape's targets, narrowed by the executor and the
    rule's conditions). A run-once rule skips a node it already ran for, even through another shape.

    ``targets(graph)`` gives the targets that pySHACL does not know (implicit class targets, ``sh:targetWhere``, node expressions)
    against the graph as it is now: pySHACL reads them from triples written before any rule ran, so a rule that adds the instances
    of a class would otherwise never reach the shape that targets it (GitHub issue #182)."""
    prule = rule.source
    focus_list = list(focus_nodes) if focus_nodes is not None else list(prule.shape.focus_nodes(graph))
    if focus_nodes is None and targets is not None:
        known = set(focus_list)
        focus_list += [n for n in sorted(targets(graph).get(prule.shape.node, ()), key=str) if n not in known]
    if executor.focus_nodes is not None and len(executor.focus_nodes) > 0:
        focus_list = [f for f in focus_list if isinstance(f, URIRef) and f in executor.focus_nodes]
    if rule.run_once:
        focus_list = [f for f in focus_list if (rule.node, f) not in done]
    applicable = prule.filter_conditions(focus_list, graph)
    if rule.run_once:
        done.update((rule.node, f) for f in applicable)
    return applicable


def _triple_candidates(rule: EngineRule, graph: Any, focus_list: Iterable[Any]) -> list[tuple]:
    import pyshacl.rules.triple as triple_module

    evaluate = triple_module.nodes_from_node_expression  # looked up now: the shnex: patch replaces it
    sg = rule.shape.sg
    s_expr, p_expr, o_expr = rule.terms if rule.terms is not None else (rule.source.s, rule.source.p, rule.source.o)
    candidates: list[tuple] = []
    for focus in focus_list:
        s_set = evaluate(s_expr, focus, graph, sg)
        p_set = evaluate(p_expr, focus, graph, sg)
        o_set = evaluate(o_expr, focus, graph, sg)
        candidates.extend(t for t in itertools.product(s_set, p_set, o_set) if well_formed(t))
    return candidates


_TT_PREFIX = "urn:starlayer:tt:"
_SUPPORT_PREDICATES = {rdflib.RDF.subject, rdflib.RDF.predicate, rdflib.RDF.object}


def _without_support_triples(triples: Iterable[tuple]) -> list[tuple]:
    """A CONSTRUCT result on an adapter-encoded graph comes back re-encoded with the support triples of the triple terms the adapter knows
    (``tt:HASH rdf:subject ...``), whether or not the query built any. They belong to the encoding, not to what a rule infers: dropped here,
    they would otherwise be counted as inferred and credited to the rule (GitHub issue #167)."""
    return [
        t for t in triples if not (t[1] in _SUPPORT_PREDICATES and isinstance(t[0], URIRef) and str(t[0]).startswith(_TT_PREFIX))
    ]


def _sparql_candidates(rule: EngineRule, graph: Any, focus_list: Iterable[Any]) -> list[tuple]:
    from pyshacl.errors import ReportableRuntimeError
    from pyshacl.helper import get_query_helper_cls

    prule = rule.source
    bind_this = get_query_helper_cls().bind_this_regex
    candidates: list[tuple] = []
    for focus in focus_list:
        for construct in prule._constructs:
            bindings = {"this": focus} if bind_this.search(construct) else {}
            bindings.update(rule.bindings)
            results = graph.query(prule._qh.apply_prefixes(construct), initBindings=bindings)
            if results.type != "CONSTRUCT":
                raise ReportableRuntimeError("Query executed by a SHACL SPARQLRule must be CONSTRUCT query.")
            if results.graph is None:
                raise ReportableRuntimeError("Query executed by a SHACL SPARQLRule did not return a Graph.")
            candidates.extend(_without_support_triples(tuple(t) for t in results.graph))
    return candidates


def _global_sparql_candidates(rule: EngineRule, graph: Any) -> list[tuple]:
    from pyshacl.errors import RuleLoadError

    where = "https://www.w3.org/TR/shacl12-inference-rules/#sparql-rules"
    try:
        result = graph.query(rule.query, initBindings=rule.bindings or None)
        if result.type != "CONSTRUCT":
            raise RuleLoadError(
                f"Query executed by the sh:SPARQLRule {rule.node.n3()} must be a CONSTRUCT query, not {result.type}.", where
            )
        return _without_support_triples(tuple(t) for t in result)
    except RuleLoadError:
        raise
    except Exception as error:
        raise RuleLoadError(
            f"The sh:construct query of the sh:SPARQLRule {rule.node.n3()} could not be run: "
            f"{type(error).__name__}: {error}",
            where,
        ) from error


def candidates(rule: EngineRule, graph: Any, executor: Any, focus_nodes: Any, done: set, targets: Any = None) -> list[tuple]:
    """The triples ``rule`` produces from ``graph`` as it is now. Nothing is added."""
    from pyshacl.errors import RuleLoadError
    from pyshacl.rules.sparql import SPARQLRule
    from pyshacl.rules.triple import TripleRule

    if rule.source is None:  # a global rule: no focus node
        if rule.kind == SPARQL_RULE:
            return _global_sparql_candidates(rule, graph)
        return _triple_candidates(rule, graph, [None])
    focus_list = _focus_nodes(rule, graph, executor, focus_nodes, done, targets)
    if not focus_list:
        return []
    if isinstance(rule.source, TripleRule):
        return _triple_candidates(rule, graph, focus_list)
    if isinstance(rule.source, SPARQLRule):
        return _sparql_candidates(rule, graph, focus_list)
    raise RuleLoadError(
        f"The rule {rule.node.n3()} is of a type this engine does not run; only sh:TripleRule and sh:SPARQLRule are supported.",
        "https://www.w3.org/TR/shacl12-inference-rules/#execution",
    )


@dataclass
class _Layer:
    graph: Any
    executor: Any
    focus_nodes: Any
    record: Callable[[Any, tuple, Any], None] | None
    targets: Any = None
    derived: set = field(default_factory=set)
    kept: set = field(default_factory=set)  # derived triples a rule inferred as well
    done: set = field(default_factory=set)

    def iteration(self, rules: list[EngineRule]) -> int:
        """One pass over ``rules`` by ascending ``sh:order``; the rules of one order are evaluated before any is added."""
        added = 0
        for _order, group in itertools.groupby(sorted(rules, key=lambda r: (r.order, r.index)), key=lambda r: r.order):
            fresh: dict[tuple, list[EngineRule]] = {}
            for rule in list(group):
                for triple in dict.fromkeys(candidates(rule, self.graph, self.executor, self.focus_nodes, self.done, self.targets)):
                    if triple in self.derived:
                        self.kept.add(triple)
                    if triple not in self.graph:
                        fresh.setdefault(triple, []).append(rule)
            where = target_graph(self.graph)
            for triple, producers in fresh.items():
                where.add(triple)
                if self.record is not None:
                    for rule in producers:
                        self.record(self.graph, triple, rule.node)
            added += len(fresh)
        return added


def run(
    rules: Iterable[EngineRule],
    graph: Any,
    executor: Any,
    *,
    focus_nodes: Any = None,
    derive: Callable[[list[EngineRule], Any], Iterable[tuple]] | None = None,
    record: Callable[[Any, tuple, Any], None] | None = None,
    targets: Callable[[Any], dict] | None = None,
) -> int:
    """Run ``rules`` against ``graph`` and add what they infer. Returns the number of triples added.

    ``derive(layer_rules, graph)`` adds the expected derived triples of a layer and returns them; ``record(graph, triple,
    rule_node)`` is told which rule inferred each triple that was new. ``targets(graph)`` resolves the targets pySHACL does not know (see
    ``_focus_nodes``)."""
    from pyshacl.errors import ReportableRuntimeError
    from pyshacl.rules import RULES_ITERATE_LIMIT

    layers: dict[Decimal, list[EngineRule]] = {}
    for rule in rules:
        if not rule.deactivated:
            layers.setdefault(rule.layer, []).append(rule)
    done: set = set()
    total = 0
    for layer_number in sorted(layers):
        in_layer = layers[layer_number]
        layer = _Layer(graph, executor, focus_nodes, record, targets=targets, done=done)
        if derive is not None:
            layer.derived = set(derive(in_layer, graph))
        try:
            total += layer.iteration([r for r in in_layer if r.run_once])
            iterating = [r for r in in_layer if not r.run_once]
            limit = int(RULES_ITERATE_LIMIT)
            while iterating:
                if limit < 1:
                    raise ReportableRuntimeError(
                        f"SHACL Shape Rule iteration exceeded iteration limit of {RULES_ITERATE_LIMIT}."
                    )
                limit -= 1
                added = layer.iteration(iterating)
                total += added
                if added == 0 or not executor.iterate_rules:
                    break
        finally:
            for triple in layer.derived - layer.kept:
                graph.remove(triple)
    return total
