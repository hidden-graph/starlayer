"""SRL evaluation engine - `WD-sparql12-rl-20261014
<https://www.w3.org/TR/sparql12-rl/>`_ (dependency graph updated from the
2026-09-19 draft: WHERE DATA / NOT DATA add no dependencies) §4.3 (Rule Dependency),
§4.4 (Stratification), and §6 (Rule Set Evaluation), translated directly
from the spec's own verbatim pseudocode rather than an approximation of it.

**Reuses Oxigraph's SPARQL engine for triple-pattern matching and expression
evaluation, rather than reimplementing SPARQL semantics a second time.** The
evaluation graphs are ``StarLayerGraph`` s (pyoxigraph terms; an rdflib or old-style
graph argument is copied in, the result converted back):

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

import datetime
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
    """§4.5: ``IMPORTS`` support is optional for SRL processors, but an
    implementation that does not support it MUST reject a rule set
    containing ``IMPORTS`` statements with an error - this project does
    not yet resolve imports, so this is that required hard rejection."""


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
        # A rule that matches only the base graph (WHERE DATA) has no dependencies
        # (SRL 2026-10-14 §4.3.1: ``evaldata`` false).
        if not r1.evaldata:
            continue
        body_dependencies: list[tuple[srl_ast.TriplePattern, str]] = []
        for elt in r1.body:
            if isinstance(elt, srl_ast._NegationElement):
                # NOT DATA matches only the base graph, so it adds no dependency either.
                if not elt.evaldata:
                    continue
                for inner in elt.inner:
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
    from starlayer.graph.oxgraph.run import _sparql_term

    if isinstance(term, Variable):
        return "?" + term.value
    if isinstance(term, TripleTermNode):
        s, p, o = (_pattern_term_text(part) for part in _triple_term_parts(term))
        return f"<<( {s} {p} {o} )>>"
    return _sparql_term(_ox_term(term))


def _match(run: list[srl_ast.TriplePattern], g) -> list[dict]:
    """Every solution of the basic graph pattern ``run`` against ``g`` (an ``StarLayerGraph``), found by running the pattern as a
    SPARQL 1.2 query. Keys are ``pyoxigraph.Variable`` s, values pyoxigraph terms."""
    patterns = [
        f"{_pattern_term_text(t.subject)} {_pattern_term_text(t.predicate)} {_pattern_term_text(t.object)}" for t in run
    ]

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
        return e  # FilterElement/AssignmentElement: no raw BNode terms to substitute

    return [_sub_element(e) for e in body]


def _eval_triple_run(run: list[srl_ast.TriplePattern], seq: list[dict], g) -> list[dict]:
    """One query for a maximal consecutive run of triple-pattern elements, joined with the incoming solutions - see module
    docstring for why this is equivalent to (and more efficient than) matching them one at a time."""
    matches = _match(run, g)
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
    from starlayer.graph.oxgraph.run import _sparql_term

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


def _eval_rule_elements(elements: list[srl_ast.BodyElement], seq: list[dict], g, gd) -> list[dict]:
    """§6.4's ``evalRuleElements`` - processes ``elements`` against the
    incoming solution sequence ``seq``, matching ordinary triple-pattern
    runs against ``g`` and any ``DATA``-flagged negation against ``gd``."""
    seq = list(seq)
    i = 0
    n = len(elements)
    while i < n:
        elt = elements[i]
        if isinstance(elt, srl_ast.TriplePattern):
            run: list[srl_ast.TriplePattern] = []
            while i < n and isinstance(elements[i], srl_ast.TriplePattern):
                run.append(elements[i])
                i += 1
            seq = _eval_triple_run(run, seq, g)
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


def _eval_rule(rule: srl_ast._Rule, g, gd) -> set[tuple]:
    """§6.4's ``evalRule``."""
    used_vars = _collect_variables(rule)
    body = _blank_nodes_to_vars(rule.body, used_vars)
    if rule.evaldata:
        seq = _eval_rule_elements(body, [{}], g, gd)
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
    union of its graphs; an rdflib graph (or, for a dataset, its default graph or the union of all graphs) copied in by the
    rdflib bridge (rdflib is then needed). Nothing here changes ``graph``."""
    from starlayer.graph.oxgraph import _rdflib_bridge as _ox
    from starlayer.graph.oxgraph.core import StarLayerGraph
    from starlayer.shacl_engine.graphs import new_graph

    if isinstance(graph, StarLayerGraph):
        return graph
    flat = new_graph()
    if _ox.is_oxigraph_input(graph):
        # a Store yields quads; the union of its graphs keeps each triple once, whatever graph it is in
        flat.extend({(item[0], item[1], item[2]) for item in graph})
        return flat
    from starlayer._optional import require_rdflib

    require_rdflib("Running SRL rules on an rdflib graph")
    from rdflib import ConjunctiveGraph, Dataset

    triples = graph.triples((None, None, None)) if isinstance(graph, (Dataset, ConjunctiveGraph)) else iter(graph)
    flat.extend((_ox.from_rdflib_term(s), _ox.from_rdflib_term(p), _ox.from_rdflib_term(o)) for s, p, o in triples)
    return flat


def to_foreign(inferred, original):
    """The inferred graph for a caller that did not pass an Oxigraph graph: rdflib terms in a graph of the caller's own class
    when that is an rdflib ``Graph`` subclass (the old-style graph, which can hold triple terms), otherwise a plain
    ``rdflib.Graph``. A result that holds a triple term, which a plain ``rdflib.Graph`` cannot hold, is returned as the
    ``StarLayerGraph`` it is."""
    from starlayer._optional import require_rdflib

    require_rdflib("Returning the inferred triples as an rdflib graph")
    from rdflib import ConjunctiveGraph, Dataset, Graph

    from starlayer.graph.oxgraph._rdflib_bridge import to_rdflib_term

    triples = list(inferred)
    cls = type(original)
    holds_triple_terms = cls not in (Graph, Dataset, ConjunctiveGraph) and isinstance(original, Graph) and not isinstance(
        original, (Dataset, ConjunctiveGraph)
    )
    if not holds_triple_terms and any(isinstance(t, ox.Triple) for triple in triples for t in triple):
        return inferred
    out = cls() if holds_triple_terms else Graph()
    for s, p, o in triples:
        out.add((to_rdflib_term(s), to_rdflib_term(p), to_rdflib_term(o)))
    return out


def _evaluate_ruleset(base_graph, ruleset: srl_ast.RuleSet):
    """§6.5's rule-set evaluation algorithm, translated directly -
    including its one easy-to-miss subtlety, confirmed against the raw
    spec text (not just the informal prose): every ``evalRule`` call's own
    ``GD`` argument is ``G0``, the *original* base graph passed in here -
    **not** the ruleset's own ``DATA`` blocks unioned in (``GD = G0 ∪ D``
    is a *different*, evaluation-graph-seeding variable in the spec's own
    algorithm, despite the name collision with ``evalRule``'s own ``GD``
    parameter). A ``WHERE DATA {...}``/``NOT DATA {...}`` match is
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
    token = _NOW.set(_NOW.get() or datetime.datetime.now(datetime.timezone.utc))
    rendered = _RENDERED.set({})
    try:
        return _evaluate_ruleset_at_one_instant(base_graph, ruleset)
    finally:
        _RENDERED.reset(rendered)
        _NOW.reset(token)


def _evaluate_ruleset_at_one_instant(base_graph, ruleset: srl_ast.RuleSet):
    from starlayer.shacl_engine.graphs import new_graph

    base_graph = flatten_dataset(base_graph)
    if ruleset.imports:
        raise SRLImportsNotSupportedError(
            "SRL: this implementation does not support IMPORTS - per §4.5, "
            "an implementation without import support MUST reject a rule set "
            "containing IMPORTS statements, rather than silently ignoring them"
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

    from starlayer.graph.oxgraph.core import StarLayerGraph

    gi = StarLayerGraph(prefixes={})  # the caller binds the prefixes it wants on the result
    for t in d:
        if t not in base_graph:
            gi.add(t)

    ge = new_graph()
    ge.extend(list(base_graph))
    ge.extend(list(d))

    for once_rules, general_rules in _stratify(ruleset):
        for rule in once_rules:
            for t in _eval_rule(rule, ge, base_graph):
                if t not in ge:
                    gi.add(t)
                    ge.add(t)

        finished = False
        while not finished:
            finished = True
            for rule in general_rules:
                for t in _eval_rule(rule, ge, base_graph):
                    if t not in ge:
                        finished = False
                        gi.add(t)
                        ge.add(t)

    return gi


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


def _srl_query(base_graph, ruleset: srl_ast.RuleSet, goal_pattern: srl_ast.TriplePattern) -> list[dict]:
    """§4.1's top-level ``Query`` operation, v1: "equivalent to infer +
    matching the goal pattern against base ∪ GI" - the spec's own stated
    equivalence, implemented directly on top of :func:`_srl_infer` rather
    than the selective-rule-evaluation optimization it also permits (a
    documented future enhancement, not required for a correct result).

    Private: the one real public API is ``RuleSet.infer()``/``.query()``
    (``_srl_ast.py``); this function is the plumbing ``RuleSet.query()``
    delegates to.

    Args:
        base_graph: The graph to run the rule set against.
        ruleset: The rule set to evaluate.
        goal_pattern: The triple pattern to match against the union of
            ``base_graph`` and the inferred triples.

    Returns:
        One ``dict[Variable, term]`` solution per match, the terms pyoxigraph terms.
    """
    from starlayer.shacl_engine.graphs import new_graph

    base_graph = flatten_dataset(base_graph)
    gi = _evaluate_ruleset(base_graph, ruleset)
    combined = new_graph()
    combined.extend(list(base_graph))
    combined.extend(list(gi))

    goal_vars = {
        v for term in (goal_pattern.subject, goal_pattern.predicate, goal_pattern.object) for v in _term_variables(term)
    }
    return [{v: m[v] for v in goal_vars if v in m} for m in _match([goal_pattern], combined)]
