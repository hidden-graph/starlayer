"""SRL evaluation engine - `WD-sparql12-rl-20261014
<https://www.w3.org/TR/sparql12-rl/>`_ (dependency graph updated from the
2026-09-19 draft: WHERE GROUND / NOT GROUND add no dependencies) §4.3 (Rule Dependency),
§4.4 (Stratification), and §6 (Rule Set Evaluation), translated directly
from the spec's own verbatim pseudocode rather than an approximation of it.

**Reuses Oxigraph's SPARQL engine for triple-pattern matching and expression
evaluation, rather than reimplementing SPARQL semantics a second time.** The
evaluation graphs are ``StarLayerGraph`` s (pyoxigraph terms):

- The spec's own §6.1 ``graphMatch``/``compatible``/``merge`` definitions
  are, term for term, SPARQL's basic-graph-pattern join. §6.4's
  ``evalRuleElements`` processes one rule element at a time only because
  that is sufficient to *define* the semantics, not because processing a
  maximal consecutive run of triple-pattern elements as a single
  ``SELECT`` would change the result (join is associative/commutative) -
  this module does the latter: one query per run, joined with the incoming
  solutions.
- §6.3's ``evalFunction``/``EBV`` are SPARQL's expression evaluation and
  effective boolean value: an expression is rendered to SPARQL text
  (``expr_text.render_expression``), evaluated with the solution's
  variables substituted, and ``NOW()`` is replaced by the one instant of the
  rule-set evaluation in progress.

Only the genuinely SRL-specific orchestration is hand-written here: the
dependency graph and stratification algorithms (§4.3.2/§4.4.2, direct
pseudocode translations), the run-once-vs-general/stratum control flow
(§6.5), blank-node-to-fresh-variable body substitution and fresh-blank-
node-per-solution head instantiation (§6.4).
"""

from __future__ import annotations

import dataclasses
import datetime
import itertools
import re
import sys
from contextvars import ContextVar
from dataclasses import dataclass

import pyoxigraph as ox

from . import _srl_ast as srl_ast
from .expr_text import expr_variables
from .parse_sparql import Node
from .srl import SRLError
from .triple_term import TripleTermNode

Variable = ox.Variable
BNode = ox.BlankNode


class SRLEvalError(SRLError):
    """Base class for SRL evaluation errors. Subclasses ``SRLError``
    (``srl.py``) so a caller can catch either "any evaluation failure"
    (this type) or "any SRL failure at all" (``SRLError``, which also
    covers ``SRLParseError``/``SRLDecodeError``)."""


class StratificationError(SRLEvalError):
    """§4.4.1: the rule set's dependency graph has a recursive dependency
    involving a closed dependency - the spec explicitly leaves evaluation
    undefined for this case, so this is raised rather than producing a
    silently-wrong or non-terminating result."""


class SRLImportsNotSupportedError(SRLEvalError):
    """A rule set that still has ``IMPORTS`` was run. §4.5 requires a processor to reject such a rule set, or resolve the imports,
    and never to ignore them. StarLayer resolves imports only through a caller-supplied loader (``imports_loader=``, or
    ``srl.resolve_imports()``), so a run without one is rejected with this error."""


# ---------------------------------------------------------------------------
# §4.3 Rule Dependency / §4.3.2 Dependency Graph Algorithm
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _DependencyEdge:
    source: srl_ast._Rule
    target: srl_ast._Rule
    label: str  # "open" | "closed"


class _Unifier:
    """Unifies a body pattern with a head template (§4.3: the template can
    generate a triple matching the pattern, a variable repeated in either one
    replaced by the same term everywhere). Variables and blank nodes of the
    pattern, and variables of the template, are unification variables, kept
    apart by side; a blank node of a template is a fresh term that equals
    nothing else."""

    def __init__(self) -> None:
        self._parent: dict = {}
        self._const: dict = {}

    def _find(self, key):
        while self._parent.get(key, key) != key:
            key = self._parent[key]
        return key

    def unify(self, pattern_term, template_term) -> bool:
        left = self._key(pattern_term, "p")
        right = self._key(template_term, "t")
        if isinstance(pattern_term, TripleTermNode) and isinstance(template_term, TripleTermNode):
            return all(
                self.unify(pattern_term.get(position), template_term.get(position))
                for position in ("subject", "predicate", "object")
            )
        if isinstance(pattern_term, TripleTermNode) or isinstance(template_term, TripleTermNode):
            # a triple term only equals another triple term, or a variable
            # (not recorded: it may hold variables, and a missed edge is worse than an extra one)
            return left[0] == "v" or right[0] == "v"
        return self._join(left, right)

    @staticmethod
    def _key(term, side):
        if isinstance(term, Variable) or (side == "p" and isinstance(term, BNode)):
            return ("v", side, str(term))
        if isinstance(term, BNode):
            return ("c", ("fresh-bnode", str(term)))
        return ("c", term)

    def _bind(self, var, value) -> bool:
        root = self._find(var)
        if root in self._const:
            return self._const[root] == value
        self._const[root] = value
        return True

    def _join(self, left, right) -> bool:
        if left[0] == "c" and right[0] == "c":
            return left[1] == right[1]
        if left[0] == "c":
            return self._bind(right, left[1])
        if right[0] == "c":
            return self._bind(left, right[1])
        a, b = self._find(left), self._find(right)
        if a == b:
            return True
        if a in self._const and b in self._const and self._const[a] != self._const[b]:
            return False
        self._parent[a] = b
        if a in self._const:
            self._const.setdefault(b, self._const[a])
        return True


def _pattern_matches_template(pattern: srl_ast.TriplePattern, template: srl_ast.TriplePattern) -> bool:
    unifier = _Unifier()
    return (
        unifier.unify(pattern.subject, template.subject)
        and unifier.unify(pattern.predicate, template.predicate)
        and unifier.unify(pattern.object, template.object)
    )


def _merge_label(old: str, new: str) -> str:
    if old == "open" and new == "open":
        return "open"
    return "closed"


def _build_dependency_graph(ruleset: srl_ast.RuleSet) -> list[_DependencyEdge]:
    """§4.3.2's ``buildDependencyGraph`` algorithm, translated directly."""
    edge_labels: dict[tuple[int, int], str] = {}
    id_to_rule: dict[int, srl_ast._Rule] = {id(r): r for r in ruleset.rules}

    for r1 in ruleset.rules:
        # A rule that matches only the base graph (WHERE GROUND) has no dependencies
        # (SRL 2026-10-14 §4.3.1: ``evaldata`` false).
        if not r1.evaldata:
            continue
        body_dependencies: list[tuple[srl_ast.TriplePattern, str]] = []
        for elt in r1.body:
            if isinstance(elt, srl_ast._NegationElement):
                # NOT GROUND matches only the base graph, so it adds no dependency either.
                if not elt.evaldata:
                    continue
                for inner in elt.inner:
                    if isinstance(inner, srl_ast.TriplePattern):
                        body_dependencies.append((inner, "closed"))
            elif isinstance(elt, srl_ast._GroupElement):
                # the triple patterns of a group pattern are closed dependencies (§4.3.2): the group sees every triple its
                # patterns can match, so the rules that produce them finish first
                for inner in elt.pattern:
                    if isinstance(inner, srl_ast.TriplePattern):
                        body_dependencies.append((inner, "closed"))
            elif isinstance(elt, srl_ast.TriplePattern):
                body_dependencies.append((elt, "open"))
            # FilterElement / AssignmentElement: no dependency contribution.

        r1_run_once = r1._is_run_once

        for tp, dep_label in body_dependencies:
            if r1_run_once:
                dep_label = "closed"
            for r2 in ruleset.rules:
                for tt in r2.head:
                    if _pattern_matches_template(tp, tt):
                        key = (id(r1), id(r2))
                        if key in edge_labels:
                            edge_labels[key] = _merge_label(edge_labels[key], dep_label)
                        else:
                            edge_labels[key] = dep_label

    return [
        _DependencyEdge(id_to_rule[r1_id], id_to_rule[r2_id], label)
        for (r1_id, r2_id), label in edge_labels.items()
    ]


# ---------------------------------------------------------------------------
# §4.4 Stratification / §4.4.2 Stratification Algorithm
# ---------------------------------------------------------------------------


def _stratify(ruleset: srl_ast.RuleSet) -> list[tuple[list[srl_ast._Rule], list[srl_ast._Rule]]]:
    """§4.4.2's ``stratification`` algorithm, translated directly.

    Args:
        ruleset: The rule set to stratify.

    Returns:
        A sequence of ``(once_rules, general_rules)`` pairs, one per
        stratum, in evaluation order.

    Raises:
        StratificationError: If the §4.4.1 Stratification Condition is
            violated (a recursive dependency involving a closed edge).
    """
    edges = _build_dependency_graph(ruleset)
    stratum: dict[int, int] = {id(r): 0 for r in ruleset.rules}
    limit = len(ruleset.rules) + 1
    max_stratum = 0

    changed = True
    while changed:
        changed = False
        for edge in edges:
            p, q = id(edge.source), id(edge.target)
            if edge.label == "open":
                if stratum[p] < stratum[q]:
                    stratum[p] = stratum[q]
                    changed = True
            else:  # "closed"
                if stratum[p] <= stratum[q]:
                    x = 1 + stratum[q]
                    if x > limit:
                        raise StratificationError(
                            "SRL: stratification condition violated - a recursive "
                            "dependency involves a closed edge, so this rule set has "
                            "no well-defined evaluation outcome per §4.4.1"
                        )
                    stratum[p] = x
                    max_stratum = max(max_stratum, x)
                    changed = True

    stratum_rules: dict[int, list[srl_ast._Rule]] = {i: [] for i in range(max_stratum + 1)}
    for r in ruleset.rules:
        stratum_rules[stratum[id(r)]].append(r)

    layers: list[tuple[list[srl_ast._Rule], list[srl_ast._Rule]]] = []
    for i in range(max_stratum + 1):
        rules_i = stratum_rules[i]
        once_ids = {id(r) for r in rules_i if r._is_run_once}
        once = [r for r in rules_i if id(r) in once_ids]
        general = [r for r in rules_i if id(r) not in once_ids]
        layers.append((once, general))
    return layers


# ---------------------------------------------------------------------------
# §6.3/§6.4 Evaluating expressions and a single rule
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Triple terms (RDF 1.2) in patterns, templates and DATA blocks
# ---------------------------------------------------------------------------


def _has_triple_term(term) -> bool:
    """True if ``term`` is a triple term (a ``TripleTermNode``)."""
    return isinstance(term, TripleTermNode)


def _term_variables(term) -> list[Variable]:
    """Every variable in ``term``, looking inside triple terms at any depth."""
    if isinstance(term, Variable):
        return [term]
    if isinstance(term, TripleTermNode):
        return [v for part in _triple_term_parts(term) for v in _term_variables(part)]
    return []


def _triple_term_parts(term: TripleTermNode) -> tuple:
    return (term.get("subject"), term.get("predicate"), term.get("object"))


def _triple_uses_triple_terms(t: srl_ast.TriplePattern) -> bool:
    return any(_has_triple_term(x) for x in (t.subject, t.predicate, t.object))


class _InvalidInstance(Exception):
    """A head template instantiated to something that is not a valid RDF 1.2
    triple term (for example a literal as the subject of a triple term). The
    triple is skipped, as ordinary SPARQL ``CONSTRUCT`` skips an invalid triple."""


def _graph_term(term, resolve=None):
    """The graph-storable form of a pattern/template term, as a pyoxigraph term: a ``TripleTermNode`` becomes an ``ox.Triple``
    (recursively); a leaf is a term already. ``resolve`` maps a leaf (variable or blank node) to its value
    (already a pyoxigraph term), and is ``None`` for ground terms (DATA blocks).

    Raises:
        _InvalidInstance: If a triple term would be invalid RDF 1.2.
    """
    if isinstance(term, TripleTermNode):
        s, p, o = (_graph_term(part, resolve) for part in _triple_term_parts(term))
        try:
            return ox.Triple(s, p, o)
        except (TypeError, ValueError) as exc:
            raise _InvalidInstance(str(exc)) from exc
    return resolve(term) if resolve is not None else _ox_term(term)


def _ox_term(term):
    """A ground term of a rule as the pyoxigraph term the evaluation graphs hold (it already is one)."""
    return term


def _pattern_term_text(term) -> str:
    """SPARQL 1.2 text for one pattern term."""
    from starlayer.graph.execution.run import _sparql_term

    if isinstance(term, Variable):
        return "?" + term.value
    if isinstance(term, TripleTermNode):
        s, p, o = (_pattern_term_text(part) for part in _triple_term_parts(term))
        return f"<<( {s} {p} {o} )>>"
    return _sparql_term(_ox_term(term))


_DELTA_GRAPH = ox.NamedNode("urn:starlayer:srl:delta")
"""The named graph, in the evaluation graph's store, that holds the triples the previous round derived (see
``_evaluate_ruleset_at_one_instant``)."""


def _match(run: list[srl_ast.TriplePattern], g, delta_pos: int | None = None) -> list[dict]:
    """Every solution of the basic graph pattern ``run`` against ``g`` (an ``StarLayerGraph``), found by running the pattern as a
    SPARQL 1.2 query. Keys are ``pyoxigraph.Variable`` s, values pyoxigraph terms. With ``delta_pos``, the pattern at that
    position must match the delta graph instead of ``g``'s own triples."""
    patterns = [
        f"{_pattern_term_text(t.subject)} {_pattern_term_text(t.predicate)} {_pattern_term_text(t.object)}" for t in run
    ]
    if delta_pos is not None:
        patterns[delta_pos] = f"GRAPH <{_DELTA_GRAPH.value}> {{ {patterns[delta_pos]} }}"

    def _solutions(body: str) -> list[dict]:
        result = g.query(f"SELECT * WHERE {{ {body} }}")
        return [{Variable(str(name).lstrip("?")): term for name, term in binding.items()} for binding in result.bindings]

    try:
        return _solutions(" . ".join(patterns))
    except RuntimeError as exc:
        # The engine builds <<( "lit" p o )>> while joining a variable bound to a literal into a triple term's subject, and
        # raises. Such a term matches nothing, so join the patterns here instead: each alone never builds one.
        if len(patterns) < 2 or "triple term that is not a valid" not in str(exc):
            raise
    joined: list[dict] = [{}]
    for pattern in patterns:
        matches = _solutions(pattern)
        joined = [{**mu, **m} for mu in joined for m in matches if _compatible(mu, m)]
    return joined


def _compatible(mu1: dict, mu2: dict) -> bool:
    return all(mu1[v] == mu2[v] for v in mu1.keys() & mu2.keys())


def _collect_vars_in_expr(expr, found: set[Variable]) -> None:
    found.update(expr_variables(expr))


def _collect_variables(rule: srl_ast._Rule) -> set[Variable]:
    """Every ``Variable`` used anywhere in ``rule`` (head or body) - needed
    so fresh variables minted for body blank nodes (§6.4) can't collide
    with a variable the rule already uses."""
    found: set[Variable] = set()

    def _triple(t: srl_ast.TriplePattern) -> None:
        for term in (t.subject, t.predicate, t.object):
            found.update(_term_variables(term))

    def _element(e: srl_ast.BodyElement) -> None:
        if isinstance(e, srl_ast.TriplePattern):
            _triple(e)
        elif isinstance(e, srl_ast._FilterElement):
            _collect_vars_in_expr(e.expr, found)
        elif isinstance(e, srl_ast._AssignmentElement):
            found.add(e.var)
            _collect_vars_in_expr(e.expr, found)
        elif isinstance(e, srl_ast._NegationElement):
            for inner in e.inner:
                _element(inner)
        elif isinstance(e, srl_ast._GroupElement):
            found.update(e.keys)
            for agg in e.aggregations:
                found.add(agg.var)
                if agg.argument is not None:
                    found.add(agg.argument)
            for inner in e.pattern:
                _element(inner)

    for t in rule.head:
        _triple(t)
    for e in rule.body:
        _element(e)
    return found


def _fresh_variable(used: set[Variable]) -> Variable:
    n = 0
    while True:
        n += 1
        v = Variable(f"__srl_bn_{n}")
        if v not in used:
            used.add(v)
            return v


def _blank_nodes_to_vars(
    body: list[srl_ast.BodyElement], used_vars: set[Variable]
) -> list[srl_ast.BodyElement]:
    """§6.4: "let B be R.body where each blank node in a triple pattern in
    R.body is replaced by a variable which is not used in the rule. The
    same variable is used for each occurrence of the same blank node, and
    a different variable is used for each different blank node." Blank
    nodes then behave exactly like ordinary (existentially-quantified)
    pattern variables during matching - no special-casing needed once
    substituted.

    Args:
        body: The rule body to substitute blank nodes in.
        used_vars: Variables already used by the rule - extended in place
            with each fresh variable minted.

    Returns:
        ``body`` with every blank node replaced by a fresh variable.
    """
    mapping: dict[BNode, Variable] = {}

    def _sub_term(t):
        if isinstance(t, BNode):
            if t not in mapping:
                mapping[t] = _fresh_variable(used_vars)
            return mapping[t]
        if isinstance(t, TripleTermNode):
            s, p, o = (_sub_term(part) for part in _triple_term_parts(t))
            return TripleTermNode("TripleTerm", subject=s, predicate=p, object=o)
        return t

    def _sub_triple(t: srl_ast.TriplePattern) -> srl_ast.TriplePattern:
        return srl_ast.TriplePattern(_sub_term(t.subject), t.predicate, _sub_term(t.object))

    def _sub_element(e: srl_ast.BodyElement) -> srl_ast.BodyElement:
        if isinstance(e, srl_ast.TriplePattern):
            return _sub_triple(e)
        if isinstance(e, srl_ast._NegationElement):
            return srl_ast._NegationElement(inner=[_sub_element(x) for x in e.inner], evaldata=e.evaldata)
        if isinstance(e, srl_ast._GroupElement):
            return srl_ast._GroupElement(keys=e.keys, pattern=[_sub_element(x) for x in e.pattern], aggregations=e.aggregations)
        return e  # FilterElement/AssignmentElement: no raw BNode terms to substitute

    return [_sub_element(e) for e in body]


def _eval_triple_run(run: list[srl_ast.TriplePattern], seq: list[dict], g, delta_pos: int | None = None) -> list[dict]:
    """One query for a maximal consecutive run of triple-pattern elements, joined with the incoming solutions - see module
    docstring for why this is equivalent to (and more efficient than) matching them one at a time."""
    matches = _match(run, g, delta_pos)
    return [{**mu, **m} for mu in seq for m in matches if _compatible(mu, m)]


_EVAL_STORE = ox.Store()  # expressions here read no graph, so one empty store serves them all
_RENDERED: ContextVar = ContextVar("srl_rendered", default=None)  # id(expr) -> (expr, SPARQL text), for the evaluation in progress


def _with_now(node, now_text: str):
    """``node`` with each ``NOW()`` replaced by the literal of the evaluation instant (a SPARQL engine would read the clock
    once per query, so each solution would see its own instant)."""
    if isinstance(node, Node):
        if node.kind == "Builtin_NOW":
            return ox.Literal(now_text, datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#dateTime"))
        out = type(node)(node.kind, **{k: _with_now(v, now_text) for k, v in node.f.items()})
        out.pos = node.pos
        return out
    if isinstance(node, list):
        return [_with_now(item, now_text) for item in node]
    return node


def _expression_text(expr) -> str:
    """The SPARQL text of an SRL expression, ``NOW()`` fixed to the evaluation instant."""
    from .expr_text import render_expression

    cache = _RENDERED.get()
    if cache is None:
        cache = {}
        _RENDERED.set(cache)
    cached = cache.get(id(expr))
    if cached is not None and cached[0] is expr:
        return cached[1]
    now = _NOW.get() or datetime.datetime.now(datetime.timezone.utc)
    text = render_expression(_with_now(expr, now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")))
    used = expr_variables(expr)
    cache[id(expr)] = (expr, text, used)
    return text


def _has_blank(term) -> bool:
    """A blank node cannot be written in ``VALUES`` (in SPARQL a blank node in a query is a variable, not a stored node)."""
    if isinstance(term, ox.BlankNode):
        return True
    return isinstance(term, ox.Triple) and any(_has_blank(x) for x in (term.subject, term.predicate, term.object))


def _bound(expr, mu: dict) -> tuple[str, str, dict]:
    """``(projection, values, substitutions)`` for ``expr`` under ``mu``. The variables ``expr`` uses that ``mu`` binds go in a
    ``VALUES`` row, so they join like any bound variable: pyoxigraph's ``substitutions=`` turns ``=``, ``!=`` and ``IN`` into
    term identity and loses a variable passed through unchanged. A blank node cannot be written there, so a variable bound to
    one is substituted instead (the engine pre-binds a variable only if the query projects it)."""
    from starlayer.graph.execution.run import _sparql_term

    used = _RENDERED.get()[id(expr)][2]
    names = sorted(var.value for var in used if var in mu)
    written = [n for n in names if not _has_blank(mu[ox.Variable(n)])]
    substituted = [n for n in names if n not in written]
    values = ""
    if written:
        row = " ".join(_sparql_term(mu[ox.Variable(n)]) for n in written)
        values = f"VALUES ({' '.join('?' + n for n in written)}) {{ ({row}) }} "
    return (
        "".join(f"?{name} " for name in substituted),
        values,
        {ox.Variable(name): mu[ox.Variable(name)] for name in substituted},
    )


def _eval_ebv(expr, mu: dict) -> bool:
    """The effective boolean value of ``expr`` under ``mu``; an error (an unbound variable, a type error) is false, as for a
    SPARQL ``FILTER``."""
    text = _expression_text(expr)
    projection, values, substitutions = _bound(expr, mu)
    if not projection and not values:
        return bool(_EVAL_STORE.query(f"ASK {{ FILTER({text}) }}"))
    query = f"SELECT {projection or '*'} WHERE {{ {values}FILTER({text}) }}"
    return any(True for _ in _EVAL_STORE.query(query, substitutions=substitutions or None))


def _eval_expr(expr, mu: dict):
    """Evaluates ``expr`` under solution ``mu``, matching §6.3's ``evalFunction``/§6.4's "if x is not an error" check.

    Args:
        expr: The expression to evaluate.
        mu: The current variable bindings.

    Returns:
        The evaluated value (a pyoxigraph term), or ``None`` if evaluation errored.
    """
    if isinstance(expr, ox.Variable):  # a bound blank node is substituted, and the engine loses a variable passed through
        return mu.get(expr)
    text = _expression_text(expr)
    projection, values, substitutions = _bound(expr, mu)
    target = "__srl_value"
    taken = {var.value for var in _RENDERED.get()[id(expr)][2]}
    while target in taken:  # the rule's own variable may be called that
        target += "_"
    query = f"SELECT {projection}?{target} WHERE {{ {values}BIND({text} AS ?{target}) }}"
    for solution in _EVAL_STORE.query(query, substitutions=substitutions or None):
        value = solution[target]
        if isinstance(value, ox.BlankNode) and value not in mu.values():
            # BNODE(str) names its node by the label, and each evaluation here is its own query, so every solution would get
            # the same node (or one of the data's); the SRL draft wants a different blank node on each call
            return ox.BlankNode()
        return value
    return None


_XSD_INTEGER = ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer")
_SET_FUNCTION = {"SUM": "SUM", "MIN": "MIN", "MAX": "MAX"}


def _aggregate(agg: srl_ast._Aggregation, solutions: list[dict]):
    """§6.4 ``evalAggregate``: the value of one aggregation function over the solutions of one group, or ``None`` for an error.

    ``COUNT(*)`` counts solution mappings (distinct ones with DISTINCT). Otherwise the argument variable's value is taken from each
    solution (without repeats for ``COUNT(DISTINCT ?v)``) and the SPARQL set function is applied: ``COUNT`` counts them, and ``SUM``,
    ``MIN`` and ``MAX`` are computed by the SPARQL engine itself over those values, so numeric promotion and the ORDER BY ordering are
    SPARQL's. An empty group counts 0 and sums to 0; MIN or MAX of nothing, and a SUM of a value that is not a number, are errors."""
    if agg.argument is None:
        n = len({frozenset(mu.items()) for mu in solutions}) if agg.distinct else len(solutions)
        return ox.Literal(str(n), datatype=_XSD_INTEGER)
    values = [mu[agg.argument] for mu in solutions]
    if agg.distinct:
        values = list(dict.fromkeys(values))
    if agg.function == "COUNT":
        return ox.Literal(str(len(values)), datatype=_XSD_INTEGER)
    placeholders: dict = {}
    rows: list[str] = []
    for value in values:
        if isinstance(value, ox.BlankNode):  # a blank node cannot be written in VALUES: stand in an IRI, mapped back below
            placeholders.setdefault(value, ox.NamedNode(f"urn:starlayer:srl-bnode:{len(placeholders)}"))
            value = placeholders[value]
        try:
            rows.append(_pattern_term_text(value))
        except Exception:  # noqa: BLE001  (a term the engine cannot take in a query: the aggregate is an error)
            return None
    text = f"SELECT ({_SET_FUNCTION[agg.function]}(?v) AS ?r) WHERE {{ VALUES ?v {{ {' '.join(rows)} }} }}"
    try:
        solution = next(iter(_EVAL_STORE.query(text)), None)
    except Exception:  # noqa: BLE001
        return None
    result = None if solution is None else solution["r"]
    for blank, stand_in in placeholders.items():
        if result == stand_in:
            return blank
    return result


def _eval_group(group: srl_ast._GroupElement, seq: list[dict], g, gd) -> list[dict]:
    """§6.4, a group element: for each incoming solution μ the group pattern is evaluated from μ restricted to the group keys,
    its solutions are collected into groups by the keys (with no keys there is one group, even with no solutions), and each group
    gives one solution: μ extended with the keys and the aggregation values. A group whose aggregation is an error is dropped."""
    out: list[dict] = []
    for mu in seq:
        start = {k: mu[k] for k in group.keys if k in mu}
        solutions = _eval_rule_elements(group.pattern, [start], g, gd)
        groups: dict[tuple, list[dict]] = {}
        if not group.keys:
            groups[()] = []
        for solution in solutions:
            groups.setdefault(tuple(solution[k] for k in group.keys), []).append(solution)
        for key_values, members in groups.items():
            extension = dict(zip(group.keys, key_values, strict=True))
            for agg in group.aggregations:
                value = _aggregate(agg, members)
                if value is None:
                    break
                extension[agg.var] = value
            else:
                out.append({**mu, **extension})
    return out


def _eval_rule_elements(
    elements: list[srl_ast.BodyElement], seq: list[dict], g, gd, delta_index: int | None = None
) -> list[dict]:
    """§6.4's ``evalRuleElements`` - processes ``elements`` against the
    incoming solution sequence ``seq``, matching ordinary triple-pattern
    runs against ``g`` and any ``DATA``-flagged negation against ``gd``.
    ``delta_index`` is the position in ``elements`` of the one triple pattern that must match the delta graph."""
    seq = list(seq)
    i = 0
    n = len(elements)
    while i < n:
        elt = elements[i]
        if isinstance(elt, srl_ast.TriplePattern):
            start = i
            run: list[srl_ast.TriplePattern] = []
            while i < n and isinstance(elements[i], srl_ast.TriplePattern):
                run.append(elements[i])
                i += 1
            in_run = delta_index is not None and start <= delta_index < i
            seq = _eval_triple_run(run, seq, g, delta_index - start if in_run else None)
        elif isinstance(elt, srl_ast._FilterElement):
            seq = [mu for mu in seq if _eval_ebv(elt.expr, mu)]
            i += 1
        elif isinstance(elt, srl_ast._AssignmentElement):
            new_seq: list[dict] = []
            for mu in seq:
                val = _eval_expr(elt.expr, mu)
                if val is not None:
                    mu2 = dict(mu)
                    mu2[elt.var] = val
                    new_seq.append(mu2)
            seq = new_seq
            i += 1
        elif isinstance(elt, srl_ast._NegationElement):
            inner_g = g if elt.evaldata else gd
            new_seq = []
            for mu in seq:
                neg = _eval_rule_elements(elt.inner, [mu], inner_g, gd)
                if not neg:
                    new_seq.append(mu)
            seq = new_seq
            i += 1
        elif isinstance(elt, srl_ast._GroupElement):
            seq = _eval_group(elt, seq, g, gd)
            i += 1
        else:  # pragma: no cover - srl_ast.BodyElement is exhaustive
            raise TypeError(f"unrecognized rule body element: {elt!r}")
    return seq


def _subst_head_triple(triple: srl_ast.TriplePattern, mu: dict, bnode_map: dict[BNode, ox.BlankNode]) -> tuple:
    """§6.4: ``subst(mu, TT)`` for a head triple template - substitutes
    every variable per ``mu``. A literal blank node in the head is *not* a
    variable, so ``subst`` itself never touches it - but the spec's own
    §6.6 worked-example commentary ("instantiating the head creates a
    fresh blank node") makes clear head blank nodes get a fresh identity
    per solution, the same well-established convention ordinary SPARQL
    CONSTRUCT already uses. ``bnode_map`` is shared across every triple
    template of *one* rule instantiated for *one* solution, so multiple
    head triples referencing the same blank node label (e.g. this
    project's own §6.6 R5 test: ``{ [] a :Notification ; :concerns ?x }``)
    still share one fresh blank node per solution, distinct across
    solutions.

    Args:
        triple: The head triple template to substitute.
        mu: The solution providing variable bindings.
        bnode_map: Blank-node identity shared across every triple template
            of the one rule instantiation this call is part of; extended
            in place with any new blank node minted.

    Returns:
        The substituted ``(subject, predicate, object)`` tuple.

    Raises:
        SRLEvalError: If the head uses a variable not bound in ``mu``.
    """

    def _sub(t):
        if isinstance(t, Variable):
            try:
                return mu[t]
            except KeyError as exc:
                raise SRLEvalError(
                    f"SRL: rule head uses variable {t!r} not bound by its own body - "
                    "the rule is not well-formed per §4.2 (see srl_semantic_checks.py)"
                ) from exc
        if isinstance(t, BNode):
            if t not in bnode_map:
                bnode_map[t] = ox.BlankNode()
            return bnode_map[t]
        return _ox_term(t)

    return tuple(_graph_term(part, _sub) for part in (triple.subject, triple.predicate, triple.object))


def _eval_rule(rule: srl_ast._Rule, g, gd, delta_index: int | None = None) -> set[tuple]:
    """§6.4's ``evalRule``. With ``delta_index``, only the solutions in which the body element at that index (a triple pattern)
    matches the delta graph (see ``_evaluate_ruleset_at_one_instant``)."""
    used_vars = _collect_variables(rule)
    body = _blank_nodes_to_vars(rule.body, used_vars)
    if rule.evaldata:
        seq = _eval_rule_elements(body, [{}], g, gd, delta_index)
    else:
        seq = _eval_rule_elements(body, [{}], gd, gd)

    out: set[tuple] = set()
    for mu in seq:
        bnode_map: dict[BNode, ox.BlankNode] = {}
        for template in rule.head:
            try:
                triple = _subst_head_triple(template, mu, bnode_map)
            except _InvalidInstance:
                continue  # not valid RDF 1.2 (e.g. a literal as a triple term's subject): skipped
            subject, predicate, _object = triple
            if isinstance(subject, (ox.Literal, ox.Triple)) or not isinstance(predicate, ox.NamedNode):
                continue  # a literal subject, or a predicate that is not an IRI, is not a triple: skipped like CONSTRUCT (#96)
            out.add(triple)
    return out


# ---------------------------------------------------------------------------
# §6.5 Evaluation of a Rule Set / top-level Infer / Query (§4.1)
# ---------------------------------------------------------------------------

_NOW: ContextVar = ContextVar("srl_now", default=None)


def flatten_dataset(graph):
    """``graph`` as an ``StarLayerGraph`` the rules are evaluated on: an ``StarLayerGraph`` as it is; an ``StarLayerDataset`` / ``Store`` as the
    union of its graphs. An rdflib graph is a ``TypeError`` (convert it with ``StarLayerGraph.from_rdflib``). Nothing here changes ``graph``."""
    from starlayer.graph.core import StarLayerGraph
    from starlayer.graph.inputs import as_oxigraph
    from starlayer.shacl.engine.graphs import new_graph

    if isinstance(graph, StarLayerGraph):
        return graph
    graph = as_oxigraph(graph, "base graph")
    flat = new_graph()
    # a dataset yields quads; the union of its graphs keeps each triple once, whatever graph it is in
    flat.extend({(item[0], item[1], item[2]) for item in graph})
    return flat


def _default_quads(graph):
    """The triples of ``graph`` as quads of the default graph, ready for ``extend`` of a default-graph ``StarLayerGraph``. A quad is
    handed on as the store made it, so no term is converted on the way (copying 100,000 triples this way takes a third of the
    time of copying them as tuples)."""
    default = ox.DefaultGraph()
    if graph._pattern_graph() == default:
        return graph.quads()
    return (ox.Quad(q.subject, q.predicate, q.object) for q in graph.quads())


def _evaluate_ruleset(base_graph, ruleset: srl_ast.RuleSet):
    """§6.5's rule-set evaluation algorithm, translated directly -
    including its one easy-to-miss subtlety, confirmed against the raw
    spec text (not just the informal prose): every ``evalRule`` call's own
    ``GD`` argument is ``G0``, the *original* base graph passed in here -
    **not** the ruleset's own ``DATA`` blocks unioned in (``GD = G0 ∪ D``
    is a *different*, evaluation-graph-seeding variable in the spec's own
    algorithm, despite the name collision with ``evalRule``'s own ``GD``
    parameter). A ``WHERE GROUND {...}``/``NOT GROUND {...}`` match is
    therefore scoped to the rule set's original ground facts only, not to
    anything any rule (including this one) has already inferred.

    Args:
        base_graph: The graph to run the rule set against (an ``StarLayerGraph``; see :func:`flatten_dataset`).
        ruleset: The rule set to evaluate.

    Returns:
        ``GI``, the inferred-triples-only ``StarLayerGraph`` (never includes a triple
        already present in ``base_graph``, per §6's own stated output
        contract) - not the combined evaluation graph.

    Raises:
        SRLImportsNotSupportedError: If ``ruleset.imports`` is non-empty.
    """
    return _evaluate(base_graph, ruleset).inferred_graph()


def _evaluate(base_graph, ruleset: srl_ast.RuleSet) -> _Evaluation:
    """The rule set run to its end, as the :class:`_Evaluation` that holds the evaluation graph (the base graph and the rule
    set's own data, with everything the rules derived) and, apart, the derived triples."""
    token = _NOW.set(_NOW.get() or datetime.datetime.now(datetime.timezone.utc))
    rendered = _RENDERED.set({})
    try:
        return _evaluate_ruleset_at_one_instant(base_graph, ruleset)
    finally:
        _RENDERED.reset(rendered)
        _NOW.reset(token)


def _evaluate_ruleset_at_one_instant(base_graph, ruleset: srl_ast.RuleSet) -> _Evaluation:
    from starlayer.shacl.engine.graphs import new_graph

    base_graph = flatten_dataset(base_graph)
    if ruleset.imports:
        iris = ", ".join(f"<{iri.value}>" for iri in ruleset.imports)
        raise SRLImportsNotSupportedError(
            f"SRL: this rule set has IMPORTS that are not resolved ({iris}). Pass imports_loader= to infer(), query() or plan() "
            "to resolve them for the call, or resolve them once with srl.resolve_imports() or parse_ruleset(imports_loader=). "
            "A rule set with IMPORTS is never run with its imports ignored (§4.5)."
        )

    d = new_graph()
    for block in ruleset.data:
        for t in block.triples:
            try:
                triple = tuple(_graph_term(part) for part in (t.subject, t.predicate, t.object))
            except _InvalidInstance as exc:
                raise SRLEvalError(f"SRL: a DATA block has an invalid triple term: {exc}") from exc
            if isinstance(triple[0], (ox.Literal, ox.Triple)) or not isinstance(triple[1], ox.NamedNode):
                raise SRLEvalError(f"SRL: a DATA block has a triple that is not an RDF triple (literal subject or non-IRI predicate): {t}")
            d.add(triple)

    evaluation = _Evaluation(base_graph, [t for t in d if t not in base_graph])
    for once_rules, general_rules in _stratify(ruleset):
        for rule in once_rules:
            _derive_once([rule], evaluation)
        _run_to_fixpoint(general_rules, evaluation)

    return evaluation


def _delta_positions(rule: srl_ast._Rule, heads: list[srl_ast.TriplePattern]) -> list[int]:
    """The indexes in ``rule.body`` of the triple patterns that can match a triple one of ``heads`` derives. Only a top-level
    triple pattern can: a negation or group is a closed dependency, so stratification puts what it reads in a lower stratum, and a
    ``DATA`` rule reads the base graph only."""
    if not rule.evaldata:
        return []
    return [
        i
        for i, element in enumerate(rule.body)
        if isinstance(element, srl_ast.TriplePattern) and any(_pattern_matches_template(element, head) for head in heads)
    ]


_CANDIDATE_GRAPH = ox.NamedNode("urn:starlayer:srl:candidate")
_INFERRED_GRAPH = ox.NamedNode("urn:starlayer:srl:inferred")
"""Named graphs in the evaluation graph's store that a run works in: what the rules derived in a round (the candidates), and
everything derived so far. With ``_DELTA_GRAPH`` they are the only graphs ``_Evaluation`` adds to the store."""


def _has_blank_node(term) -> bool:
    if isinstance(term, BNode):
        return True
    return isinstance(term, TripleTermNode) and any(_has_blank_node(part) for part in _triple_term_parts(term))


_NOT_IN_THE_STORE = re.compile(r"(?i)\bBNODE\s*\(")
"""An expression the store would not evaluate as ``_eval_expr`` does: ``BNODE(str)`` names its node by the label, so the store
gives one node to every solution that has the label, where the draft wants a different blank node on each call."""


@dataclass
class _StorePlan:
    """A rule the store can evaluate by itself, as ``INSERT { GRAPH <candidate> { head } } WHERE { body }`` (or, for some rules
    in a pass that needs no rounds, directly into the evaluation graph: see :meth:`direct`)."""

    heads: list[str]  # the head's triples, each written as a template (a blank node has a label of its own for the rule)
    parts: list[tuple[str, int, str]]  # ("triple" | "filter" | "bind" | "not", index in the rule's body, SPARQL text)
    fresh: bool  # every triple of the head has a blank node: every solution gives triples that are not in the graph
    linked: bool  # the head has a variable, so a MINUS can compare a head triple with the graph

    @property
    def head(self) -> str:
        return " ".join(self.heads)

    def _where(self, delta_index: int | None) -> str:
        where = ""
        for kind, index, text in self.parts:
            if kind == "triple":
                where += f"GRAPH <{_DELTA_GRAPH.value}> {{ {text} }} " if index == delta_index else f"{text} . "
            elif kind == "filter":
                where += f"FILTER({text}) "
            elif kind == "bind":
                # a group's filter applies to the whole group, so the one that drops a solution whose assignment is an error
                # (the variable is not bound) must close a group, or a pattern after it that binds the variable would let it pass
                where = f"{{ {where}{text} }} "
            else:
                where += f"FILTER NOT EXISTS {{ {text} }} "
        return where

    def update(self, delta_index: int | None) -> str:
        """The update; with ``delta_index`` the triple pattern at that body index matches the delta graph only."""
        return f"INSERT {{ GRAPH <{_CANDIDATE_GRAPH.value}> {{ {self.head} }} }} WHERE {{ {self._where(delta_index)}}}"

    def direct(self) -> str | None:
        """An update that puts what the rule derives, and is not in the graph yet, in the evaluation graph and the inferred
        graph, or ``None`` when that cannot be told in one update: a rule whose every head triple has a blank node always gives new
        triples (one with a blank node in some of them has the others to check); one with a single head triple has the graph's own
        copies taken away by a ``MINUS`` (which compares nothing if the triple has no variable)."""
        if self.fresh:
            minus = ""
        elif len(self.heads) == 1 and self.linked:
            minus = f"MINUS {{ {self.head} }} "
        else:
            return None
        return f"INSERT {{ {self.head} GRAPH <{_INFERRED_GRAPH.value}> {{ {self.head} }} }} WHERE {{ {self._where(None)}{minus}}}"


def _head_term_text(term, labels: dict) -> str | None:
    """A head term as a template writes it; ``None`` for a blank node inside a triple term, which the store is not given."""
    if isinstance(term, BNode):
        return "_:" + labels.setdefault(term, f"srlb{len(labels)}")
    if _has_blank_node(term):
        return None
    return _pattern_term_text(term)


def _store_plan(rule: srl_ast._Rule) -> _StorePlan | None:
    """The plan for evaluating ``rule`` inside the store, or ``None`` when the rule needs the element-by-element evaluation: the
    store would give a different answer, or this is not worth the risk. The body is read in order and each element must see
    only what the elements before it bound, as ``_eval_rule_elements`` does, whereas a SPARQL group scopes a filter over
    everything in it; so a filter, an assignment's expression, or a negation, may use only variables a triple pattern or an
    assignment before it binds (a negation's variables that nothing else binds are its own). Only triple patterns, filters,
    assignments and negations of plain triple patterns are handled, for a rule that reads the evaluation graph (not ``WHERE
    DATA``). An assignment whose expression is an error drops the solution, as it does in the element-by-element evaluation."""
    if not rule.evaldata:
        return None
    body = _blank_nodes_to_vars(rule.body, _collect_variables(rule))
    in_patterns = {v for e in body if isinstance(e, srl_ast.TriplePattern) for term in (e.subject, e.predicate, e.object) for v in _term_variables(term)}
    in_patterns |= {e.var for e in body if isinstance(e, srl_ast._AssignmentElement)}
    bound: set = set()
    parts: list[tuple[str, int, str]] = []
    for index, element in enumerate(body):
        if isinstance(element, srl_ast.TriplePattern):
            s, p, o = (_pattern_term_text(t) for t in (element.subject, element.predicate, element.object))
            parts.append(("triple", index, f"{s} {p} {o}"))
            bound.update(v for t in (element.subject, element.predicate, element.object) for v in _term_variables(t))
        elif isinstance(element, srl_ast._FilterElement):
            text = _expression_text(element.expr)
            if "EXISTS" in text.upper() or not set(expr_variables(element.expr)) <= bound:
                return None
            parts.append(("filter", index, text))
        elif isinstance(element, srl_ast._AssignmentElement):
            text = _expression_text(element.expr)
            if "EXISTS" in text.upper() or _NOT_IN_THE_STORE.search(text) or element.var in bound or not set(expr_variables(element.expr)) <= bound:
                return None
            parts.append(("bind", index, f"BIND({text} AS ?{element.var.value}) FILTER(BOUND(?{element.var.value}))"))
            bound.add(element.var)
        elif isinstance(element, srl_ast._NegationElement):
            if not element.evaldata or not all(isinstance(i, srl_ast.TriplePattern) for i in element.inner) or not element.inner:
                return None
            inner_vars = {v for i in element.inner for t in (i.subject, i.predicate, i.object) for v in _term_variables(t)}
            if not (inner_vars & in_patterns) <= bound:
                return None
            inner = " . ".join(
                " ".join(_pattern_term_text(t) for t in (i.subject, i.predicate, i.object)) for i in element.inner
            )
            parts.append(("not", index, inner))
        else:
            return None
    if not any(kind == "triple" for kind, _, _ in parts):
        return None
    heads = []
    labels: dict = {}
    head_variables: set = set()
    with_blank = []
    for template in rule.head:
        terms = (template.subject, template.predicate, template.object)
        with_blank.append(any(_has_blank_node(t) for t in terms))
        texts = [_head_term_text(t, labels) for t in terms]
        variables = {v for t in terms for v in _term_variables(t)}
        if None in texts or not variables <= bound:
            return None  # the element-by-element evaluation raises for the unbound variable
        head_variables |= variables
        heads.append(" ".join(texts) + " .")
    return _StorePlan(heads, parts, all(with_blank), bool(head_variables))


_MINUS_FROM = 12
"""A round whose candidates are more than 1 in ``_MINUS_FROM`` of the graph's triples removes the ones the graph has with a
``MINUS`` update (one scan of the graph, about a third of a microsecond per triple); a smaller round checks each candidate in
Python (about 4 microseconds each, against 10 to 20 for ``FILTER NOT EXISTS``, which Oxigraph runs once per candidate). Measured
on pyoxigraph 0.5.13, graphs of 1,000 to 60,000 triples."""


def _count(store, graph: ox.NamedNode | None = None) -> int:
    """How many triples ``graph`` has (the default graph if none is given)."""
    pattern = "?s ?p ?o" if graph is None else f"GRAPH <{graph.value}> {{ ?s ?p ?o }}"
    (row,) = store.query(f"SELECT (COUNT(*) AS ?n) WHERE {{ {pattern} }}")
    return int(row["n"].value)


class _Evaluation:
    """One run of a rule set. ``ge`` is the evaluation graph: the base graph, the rule set's own data and what the rules have
    derived; ``base`` is the base graph (what ``WHERE GROUND`` reads). The store behind ``ge`` also holds, in named graphs, every
    triple derived so far (``_INFERRED_GRAPH``) and the work of the round in progress (``_CANDIDATE_GRAPH``, ``_DELTA_GRAPH``),
    so the rules can run in the store (see ``_run_to_fixpoint``) and the base graph is copied once, in."""

    def __init__(self, base_graph, data: list[tuple]):
        """``data`` is the triples of the rule set's own DATA blocks that the base graph does not have."""
        from starlayer.shacl.engine.graphs import new_graph

        self.base = base_graph
        self.ge = new_graph()
        self.store = self.ge.as_store()  # written to directly: the graph is this run's own, and the wrapper would look at each quad
        self.store.extend(_default_quads(base_graph))
        self.store.extend(ox.Quad(*t) for t in data)
        self._size: int | None = len(self.store)
        self.store.extend(ox.Quad(*t, _INFERRED_GRAPH) for t in data)

    @property
    def size(self) -> int:
        """The number of triples in the evaluation graph (counted again only after the store has changed it unseen)."""
        if self._size is None:
            self._size = _count(self.store)
        return self._size

    def forget_size(self) -> None:
        self._size = None

    def refresh(self) -> None:
        """The store changes under ``ge``'s wrapper; whatever the wrapper kept about the union is stale."""
        self.ge.as_store()

    def insert_directly(self, plan: _StorePlan) -> bool:
        """Run ``plan`` as one update into the evaluation graph and the inferred graph; ``False`` if the plan has no such form or
        the engine cannot evaluate it (nothing is changed then)."""
        text = plan.direct()
        if text is None:
            return False
        self.refresh()
        try:
            self.store.update(text)
        except RuntimeError:
            return False  # the engine cannot evaluate this one (see ``_match``)
        self.forget_size()
        return True

    def commit(self, delta: bool) -> int:
        """Keep the candidates that are not in the evaluation graph yet: they go in the graph and the inferred graph, and, with
        ``delta``, become the delta graph (the previous one is dropped). With ``delta`` it returns how many there were (0 is the
        fixpoint).

        Up to ``size / _MINUS_FROM`` candidates are read and checked in Python; reading one more than that shows the round is
        large, and a ``MINUS`` update does it. (Reading them is how a small round is told from a large one: a count would be a query
        of its own, a quarter of a millisecond, which a chain of hundreds of tiny rounds pays each time.)"""
        store = self.store
        limit = self.size // _MINUS_FROM if _MINUS_FROM else sys.maxsize - 1  # (0 is never MINUS, which the tests use)
        rows = list(itertools.islice(store.quads_for_pattern(None, None, None, _CANDIDATE_GRAPH), limit + 1))
        if not rows:
            if delta:
                store.clear_graph(_DELTA_GRAPH)
            return 0
        if len(rows) <= limit:
            fresh = []
            for q in rows:
                triple = ox.Quad(q.subject, q.predicate, q.object)
                if triple not in store:
                    fresh.append(triple)
            store.clear_graph(_CANDIDATE_GRAPH)
            if delta:
                store.clear_graph(_DELTA_GRAPH)
            store.extend(
                itertools.chain(
                    fresh,
                    (ox.Quad(q.subject, q.predicate, q.object, _INFERRED_GRAPH) for q in fresh),
                    (ox.Quad(q.subject, q.predicate, q.object, _DELTA_GRAPH) for q in fresh) if delta else (),
                )
            )
            self._size = self.size + len(fresh)
            return len(fresh)
        cand, inf, new = (f"<{g.value}>" for g in (_CANDIDATE_GRAPH, _INFERRED_GRAPH, _DELTA_GRAPH))
        targets = f"?s ?p ?o . GRAPH {inf} {{ ?s ?p ?o }}" + (f" GRAPH {new} {{ ?s ?p ?o }}" if delta else "")
        store.update(
            (f"CLEAR SILENT GRAPH {new}; " if delta else "")
            + f"INSERT {{ {targets} }} WHERE {{ GRAPH {cand} {{ ?s ?p ?o }} MINUS {{ ?s ?p ?o }} }}; CLEAR SILENT GRAPH {cand}"
        )
        if delta:
            added = _count(store, _DELTA_GRAPH)
            self._size = self.size + added
            return added
        self.forget_size()
        return len(rows)

    def clear_scratch(self) -> None:
        for graph in (_CANDIDATE_GRAPH, _DELTA_GRAPH):
            self.store.clear_graph(graph)

    def inferred_graph(self):
        """Everything the rules derived, as a graph of its own (never a triple the base graph has)."""
        from starlayer.graph.core import StarLayerGraph

        gi = StarLayerGraph(prefixes={})  # the caller binds the prefixes it wants on the result
        gi.as_store().extend([ox.Quad(q.subject, q.predicate, q.object) for q in self.store.quads_for_pattern(None, None, None, _INFERRED_GRAPH)])
        gi.as_store()  # (the wrapper hears of the write)
        return gi


def _derive_into_candidates(rule: srl_ast._Rule, plan: _StorePlan | None, position: int | None, evaluation: _Evaluation) -> None:
    """Put what ``rule`` derives (with its pattern at ``position`` restricted to the delta graph, if given) in the candidate graph."""
    if plan is not None:
        try:
            evaluation.store.update(plan.update(position))
            return
        except RuntimeError:
            pass  # the engine cannot evaluate this one (see ``_match``): do it element by element
    derived = _eval_rule(rule, evaluation.ge, evaluation.base, position)
    if derived:
        evaluation.store.extend(ox.Quad(*t, _CANDIDATE_GRAPH) for t in derived)


def _derive_once(rules: list[srl_ast._Rule], evaluation: _Evaluation, plans: dict | None = None) -> None:
    """One pass of ``rules`` over the evaluation graph, with nothing to repeat: a rule that ``_StorePlan.direct`` can express
    writes its new triples in the store at once; the others go through the candidate graph. Used for the run-once rules (each
    sees what the one before it derived) and for the general rules of a stratum that no rule of the stratum feeds."""
    evaluation.refresh()
    pending = False
    for rule in rules:
        plan = plans[id(rule)] if plans is not None else _store_plan(rule)
        if plan is not None and evaluation.insert_directly(plan):
            continue
        _derive_into_candidates(rule, plan, None, evaluation)
        pending = True
    if pending:
        evaluation.commit(delta=False)


def _closure_of(rules: list[srl_ast._Rule], positions: dict) -> tuple[srl_ast._Rule, str] | None:
    """When the one rule of a stratum that repeats is a closure Oxigraph computes by itself, that rule and the update that derives
    everything it would in the rounds, into the candidate graph; otherwise ``None``. The shapes, with ``q`` and ``p`` IRIs and
    ``x``, ``y``, ``z`` three different variables, and the rule's body exactly two triple patterns:

    - ``q(x, z) <- q(x, y), q(y, z)``, or the same with the patterns the other way round: ``?x q+ ?z``;
    - ``q(x, z) <- q(x, y), p(y, z)``: what ``q`` has, followed by ``p`` any number of times;
    - ``q(x, z) <- p(x, y), q(y, z)``: ``p`` any number of times, followed by what ``q`` has.

    Every other rule of the stratum must have no pattern a head of the stratum can feed (``positions`` is empty for it), so nothing
    in the stratum changes what it derives and they can run once before; a rule that derives ``p`` is one of them, and the
    closure then follows the ``p`` triples it made."""
    repeating = [rule for rule in rules if positions[id(rule)]]
    if len(repeating) != 1:
        return None
    (rule,) = repeating
    if not rule.evaldata or len(rule.head) != 1 or len(rule.body) != 2 or not all(isinstance(e, srl_ast.TriplePattern) for e in rule.body):
        return None
    head = rule.head[0]
    q = head.predicate
    if not isinstance(q, ox.NamedNode) or not isinstance(head.subject, Variable) or not isinstance(head.object, Variable):
        return None
    x, z = head.subject, head.object
    first, second = rule.body
    if any(not isinstance(t.predicate, ox.NamedNode) or not isinstance(t.subject, Variable) or not isinstance(t.object, Variable) for t in (first, second)):
        return None
    iri = _pattern_term_text
    for left, right in ((first, second), (second, first)):
        y = left.object
        if left.subject != x or right.subject != y or right.object != z or len({x, y, z}) != 3:
            continue
        if left.predicate == q and right.predicate == q:
            where = f"{iri(x)} {iri(q)}+ {iri(z)}"
        elif left.predicate == q and right.predicate != q:
            where = f"{iri(x)} {iri(q)} {iri(y)} . {iri(y)} {iri(right.predicate)}* {iri(z)}"
        else:
            continue
        return rule, f"INSERT {{ GRAPH <{_CANDIDATE_GRAPH.value}> {{ {iri(x)} {iri(q)} {iri(z)} }} }} WHERE {{ {where} }}"
    # p(x, y), q(y, z): the pattern with the head's subject is the p one
    for left, right in ((first, second), (second, first)):
        y = left.object
        if left.subject == x and right.subject == y and right.object == z and len({x, y, z}) == 3 and right.predicate == q and left.predicate != q:
            where = f"{iri(y)} {iri(q)} {iri(z)} . {iri(x)} {iri(left.predicate)}* {iri(y)}"
            return rule, f"INSERT {{ GRAPH <{_CANDIDATE_GRAPH.value}> {{ {iri(x)} {iri(q)} {iri(z)} }} }} WHERE {{ {where} }}"
    return None


def _run_to_fixpoint(rules: list[srl_ast._Rule], evaluation: _Evaluation) -> None:
    """The general rules of one stratum, repeated until no round derives a new triple.

    The first round evaluates every rule in full. After that a rule can only give a new solution if one of its triple patterns
    matches a triple the previous round derived, so each later round runs it once per such pattern, with that pattern restricted to
    the delta graph (the previous round's triples, kept in a named graph of the evaluation graph's store, so Oxigraph does the
    join) and the rest of the body matched against everything. A rule with no such pattern cannot change after the first round, so
    a stratum in which no rule has one takes the one pass (``_derive_once``). The result is the same set as re-evaluating every
    rule in full each round; the work per round is proportional to the delta, not to the graph.

    A round does its work in the store: a rule ``_store_plan`` accepts is one ``INSERT ... WHERE`` into the candidate graph, and
    the new triples are what the candidates have that the graph has not, found by one more update, so no triple is made into a
    Python object on the way. Every rule in a round reads the graph as it was at the start of the round. A rule the store cannot
    evaluate by itself is evaluated element by element and its triples are put in the candidate graph."""
    heads = [head for rule in rules for head in rule.head]
    positions = {id(rule): _delta_positions(rule, heads) for rule in rules}
    plans = {id(rule): _store_plan(rule) for rule in rules}
    try:
        if not any(positions.values()):
            _derive_once(rules, evaluation, plans)
            return
        closure = _closure_of(rules, positions)
        if closure is not None:
            rule, update = closure
            _derive_once([r for r in rules if r is not rule], evaluation, plans)
            evaluation.refresh()
            try:
                evaluation.store.update(update)
            except RuntimeError:
                pass  # the engine cannot evaluate this one: the rounds do it
            else:
                evaluation.commit(delta=False)
                return
        first = True
        while True:
            evaluation.refresh()  # the evaluation graph changes under its wrapper; whatever it kept about the union is stale
            for rule in rules:
                for position in [None] if first else positions[id(rule)]:
                    _derive_into_candidates(rule, plans[id(rule)], position, evaluation)
            if not evaluation.commit(delta=True):
                break
            first = False
    finally:
        evaluation.clear_scratch()


def _srl_infer(base_graph, ruleset: srl_ast.RuleSet):
    """§4.1's top-level ``Infer`` operation - apply full rule-set
    evaluation, producing the inference graph. Alias for
    :func:`_evaluate_ruleset` under the spec's own operation name.

    Private: the one real public API is ``RuleSet.infer()``/``.query()``
    (``_srl_ast.py``), which delegate to this function and ``_srl_query``
    below respectively. Kept as a separate function from
    ``_evaluate_ruleset`` only to carry the spec's own ``Infer`` name for
    anyone reading this file against the spec text side by side.

    Args:
        base_graph: The graph to run the rule set against.
        ruleset: The rule set to evaluate.

    Returns:
        The inferred-triples-only ``StarLayerGraph``.
    """
    return _evaluate_ruleset(base_graph, ruleset)


def _rules_for_goal(ruleset: srl_ast.RuleSet, goal_pattern: srl_ast.TriplePattern) -> srl_ast.RuleSet:
    """The part of ``ruleset`` that can change the answer to ``goal_pattern``: the rules with a head template the goal can match,
    and every rule those depend on, followed on (§4.1 allows an implementation to evaluate only what a query needs).

    The set is closed under dependencies, so each rule in it has the stratum, and the open or closed dependencies, it has in the
    whole rule set. The whole rule set is still stratified, so one that ``infer()`` rejects is rejected here too.
    """
    _stratify(ruleset)
    depends_on: dict[int, list[int]] = {}
    for edge in _build_dependency_graph(ruleset):
        depends_on.setdefault(id(edge.source), []).append(id(edge.target))
    by_id = {id(r): r for r in ruleset.rules}
    needed = {id(r) for r in ruleset.rules if any(_pattern_matches_template(goal_pattern, head) for head in r.head)}
    queue = list(needed)
    while queue:
        for dependency in depends_on.get(queue.pop(), ()):
            if dependency not in needed:
                needed.add(dependency)
                queue.append(dependency)
    if len(needed) == len(by_id):
        return ruleset
    return dataclasses.replace(ruleset, rules=[r for r in ruleset.rules if id(r) in needed])


def _match_goal(combined, goal_pattern: srl_ast.TriplePattern) -> list[dict]:
    """The solutions of ``goal_pattern`` on ``combined`` (the base graph and the inferred triples), one per match."""
    goal_vars = {
        v for term in (goal_pattern.subject, goal_pattern.predicate, goal_pattern.object) for v in _term_variables(term)
    }
    return [{v: m[v] for v in goal_vars if v in m} for m in _match([goal_pattern], combined)]


def _srl_query(base_graph, ruleset: srl_ast.RuleSet, goal_pattern: srl_ast.TriplePattern) -> list[dict]:
    """§4.1's top-level ``Query`` operation: the rules the goal depends on (:func:`_rules_for_goal`) are run on the base graph and
    the goal pattern is matched against the base graph and what they derived, the same answer as ``infer`` and a match of the goal
    against base ∪ GI (the spec's stated equivalence) from less work.

    Private: the one real public API is ``RuleSet.infer()``/``.query()`` (``_srl_ast.py``); this function is the plumbing
    ``RuleSet.query()`` delegates to.

    Args:
        base_graph: The graph to run the rule set against.
        ruleset: The rule set to evaluate.
        goal_pattern: The triple pattern to match against the union of
            ``base_graph`` and the inferred triples.

    Returns:
        One ``dict[Variable, term]`` solution per match, the terms pyoxigraph terms.
    """
    base_graph = flatten_dataset(base_graph)
    # the evaluation graph is the base graph and the inferred triples already
    return _match_goal(_evaluate(base_graph, _rules_for_goal(ruleset, goal_pattern)).ge, goal_pattern)


class Materialization:
    """The triples a rule set derives from a graph, kept: ask goals of it as often as you like without running the rules again.

    ``ruleset.materialize(graph)`` makes one. It is a snapshot: it does not change when ``graph`` does, ``stale`` says that it
    would, and ``refresh()`` runs the rules again. It holds the base graph and the derived triples in memory until ``close()`` (or
    the object) goes. A rule set with a blank node in a head, or a function such as ``UUID()``, derives different nodes each run, so a
    kept result keeps the ones it made.
    """

    def __init__(self, ruleset: srl_ast.RuleSet, base_graph, *, inference=None, imports_loader=None):
        self.ruleset = ruleset
        self._source = base_graph
        self._inference = inference
        self._imports_loader = imports_loader
        self._evaluation: _Evaluation | None = None
        self._inferred = None
        self._watch = None
        self._stamp = None
        self.refresh()

    def refresh(self) -> None:
        """Run the rules again on the graph as it is now, replacing what was kept."""
        stamp = self._stamp_now()  # taken first: a write that lands while the rules run makes the result stale
        base = flatten_dataset(self._source)
        if self._inference is not None:
            base = base.infer(entailment=self._inference, mode="full")
        self._evaluation = _evaluate(base, self.ruleset._with_imports_resolved(self._imports_loader))
        self._inferred = None
        self._stamp = stamp

    def _stamp_now(self):
        """What identifies the state of the graph: the write count of its store (every graph and dataset on that store counts, and no
        other store), or, for a source that is not on a store of its own, the count of every write made through StarLayer."""
        from starlayer.graph.execution import union

        store = self._source if isinstance(self._source, ox.Store) else getattr(self._source, "store", None)
        if isinstance(store, ox.Store):
            if self._watch is None:
                self._watch = union.version_of(store)  # held, so the count it keeps is the one a later write adds to
            return self._watch.stamp()
        return ("every store", union.current())

    @property
    def stale(self) -> bool:
        """True once something has been written to the store of the graph through StarLayer since the rules were run (a write to
        another graph of that store counts, a write to another store does not). A write made on a raw store reference needs
        ``union.touch()`` to be seen."""
        return self._stamp != self._stamp_now()

    @property
    def inferred(self):
        """The derived triples as a graph (never a triple the base graph has), with the prefixes ``RuleSet.infer`` gives."""
        evaluation = self._open()
        if self._inferred is None:
            self._inferred = self.ruleset._with_own_prefixes(self.ruleset._with_prefixes_of(evaluation.inferred_graph(), self._source))
        return self._inferred

    def query(self, goal_pattern: str) -> list[dict]:
        """The solutions of ``goal_pattern`` (one triple pattern in SPARQL syntax, as for ``RuleSet.query``) on the base graph and
        the kept triples, without running a rule."""
        goal = self.ruleset._goal_pattern(goal_pattern, self._source)
        return _match_goal(self._open().ge, goal)

    def close(self) -> None:
        """Drop the kept triples and the copy of the base graph. ``refresh()`` makes them again."""
        self._evaluation = None
        self._inferred = None

    def _open(self) -> _Evaluation:
        if self._evaluation is None:
            raise ValueError("this Materialization is closed; refresh() runs the rules again")
        return self._evaluation
