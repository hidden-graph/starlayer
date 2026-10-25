"""SRL evaluation engine - `WD-sparql12-rl-20261014
<https://www.w3.org/TR/sparql12-rl/>`_ (dependency graph updated from the
2026-09-19 draft: WHERE DATA / NOT DATA add no dependencies) §4.3 (Rule Dependency),
§4.4 (Stratification), and §6 (Rule Set Evaluation), translated directly
from the spec's own verbatim pseudocode rather than an approximation of it.

**Reuses rdflib's own real machinery for triple-pattern matching and
expression evaluation, rather than reimplementing SPARQL semantics a
second time** (see ``packages/sparql/CLAUDE.md``'s SRL entry and this
project's implementation plan for the full reasoning):

- The spec's own §6.1 ``graphMatch``/``compatible``/``merge`` definitions
  are, term for term, exactly rdflib's own BGP-join semantics -
  ``rdflib.plugins.sparql.evaluate.evalBGP(ctx, bgp)`` (confirmed live by
  reading its source) already does this, given a ``QueryContext`` whose
  ``initBindings`` carries the incoming solution. §6.4's
  ``evalRuleElements`` processes one rule element at a time only because
  that is sufficient to *define* the semantics, not because processing a
  maximal consecutive run of triple-pattern elements as a single
  ``evalBGP`` call would change the result (join is associative/
  commutative) - this module does the latter, for one ``evalBGP`` call per
  incoming solution per run instead of one per triple pattern.
- §6.3's ``evalFunction``/``EBV`` are exactly rdflib's own expression-tree
  evaluation (``Expr.eval(ctx)``) and ``rdflib.plugins.sparql.evaluate
  ._ebv`` - reused directly, since ``srl.py`` already builds
  ``filter.expr``/``assign.expr`` as real rdflib ``Expr`` trees (see that
  module's docstring).

Only the genuinely SRL-specific orchestration is hand-written here: the
dependency graph and stratification algorithms (§4.3.2/§4.4.2, direct
pseudocode translations), the run-once-vs-general/stratum control flow
(§6.5), blank-node-to-fresh-variable body substitution and fresh-blank-
node-per-solution head instantiation (§6.4).
"""

from __future__ import annotations

from dataclasses import dataclass

from rdflib import BNode, Graph, Literal, URIRef, Variable
from rdflib.plugins.sparql import algebra
from rdflib.plugins.sparql.evaluate import _ebv, evalBGP
from rdflib.plugins.sparql.sparql import QueryContext, SPARQLError

from . import _srl_ast as srl_ast
from .srl import SRLError
from .triple_term import TripleTermNode


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


def _terms_compatible(pattern_term, template_term) -> bool:
    """Could ``template_term`` (from a rule head's triple template) and
    ``pattern_term`` (from a rule body's triple pattern) refer to the same
    RDF term? A variable on either side is compatible with anything;
    otherwise the two ground terms must be equal.

    Deliberately conservative (a documented, safe simplification, not a
    bug): this checks each subject/predicate/object *position*
    independently, without also requiring that a variable repeated across
    two positions of the *same* pattern/template be replaced by the same
    term on both sides. That refinement would only ever narrow whether a
    match is reported - never widen it - so omitting it can produce a
    dependency edge the spec's own stricter reading wouldn't, but never
    misses a real one. The spec's own §4.3.2 is explicit that "conformance
    depends on producing a dependency graph that meets the definitions...
    not on the use of this procedure" - an extra, spurious edge only costs
    a coarser (still correct) stratification, never a wrong inferred
    graph, since every genuine dependency is still found.

    Args:
        pattern_term: A term from a rule body's triple pattern.
        template_term: A term from a rule head's triple template.

    Returns:
        True if the two terms could refer to the same RDF term.
    """
    # A blank node in a body pattern behaves like a variable (§4.3.1, §6.4).
    if isinstance(pattern_term, (Variable, BNode)) or isinstance(template_term, Variable):
        return True
    if isinstance(pattern_term, TripleTermNode) or isinstance(template_term, TripleTermNode):
        if not (isinstance(pattern_term, TripleTermNode) and isinstance(template_term, TripleTermNode)):
            return False
        return all(
            _terms_compatible(pattern_term.get(position), template_term.get(position))
            for position in ("subject", "predicate", "object")
        )
    return pattern_term == template_term


def _pattern_matches_template(pattern: srl_ast.TriplePattern, template: srl_ast.TriplePattern) -> bool:
    return (
        _terms_compatible(pattern.subject, template.subject)
        and _terms_compatible(pattern.predicate, template.predicate)
        and _terms_compatible(pattern.object, template.object)
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


def _ruleset_uses_triple_terms(ruleset: srl_ast.RuleSet) -> bool:
    """True if any rule (head or body, including inside a negation) or DATA
    block mentions a triple term - such a rule set is evaluated over a
    ``StarLayerGraph``, which can hold them."""

    def _element(e) -> bool:
        if isinstance(e, srl_ast.TriplePattern):
            return _triple_uses_triple_terms(e)
        if isinstance(e, srl_ast._NegationElement):
            return any(_element(x) for x in e.inner)
        return False

    return any(
        any(_triple_uses_triple_terms(t) for t in rule.head) or any(_element(e) for e in rule.body)
        for rule in ruleset.rules
    ) or any(_triple_uses_triple_terms(t) for block in ruleset.data for t in block.triples)


class _InvalidInstance(Exception):
    """A head template instantiated to something that is not a valid RDF 1.2
    triple term (for example a literal as the subject of a triple term). The
    triple is skipped, as ordinary SPARQL ``CONSTRUCT`` skips an invalid triple."""


def _graph_term(term, resolve=None):
    """The graph-storable form of a pattern/template term: a ``TripleTermNode``
    becomes a ``starlayer.graph`` ``TripleTerm`` (recursively); every other term is
    returned unchanged. ``resolve`` maps a leaf (variable or blank node) to its
    value, and is ``None`` for ground terms (DATA blocks).

    Raises:
        _InvalidInstance: If a triple term would be invalid RDF 1.2.
    """
    from starlayer.graph.model.triple import TripleTerm

    if isinstance(term, TripleTermNode):
        s, p, o = (_graph_term(part, resolve) for part in _triple_term_parts(term))
        try:
            return TripleTerm(s, p, o)
        except ValueError as exc:
            raise _InvalidInstance(str(exc)) from exc
    return resolve(term) if resolve is not None else term


def _pattern_term_text(term) -> str:
    """SPARQL 1.2 text for one pattern term, for matching a triple pattern that
    contains a triple term by running it as a query against the graph."""
    from starlayer.graph.backends.native import sparql_term

    if isinstance(term, Variable):
        return "?" + str(term)
    if isinstance(term, TripleTermNode):
        s, p, o = (_pattern_term_text(part) for part in _triple_term_parts(term))
        return f"<<( {s} {p} {o} )>>"
    return sparql_term(term, skolemize_bnodes=False)


def _match_with_query(run: list[srl_ast.TriplePattern], g: Graph) -> list[dict]:
    """Every solution of the basic graph pattern ``run`` against ``g`` (a
    ``StarLayerGraph``), found by running the pattern as a SPARQL 1.2 query. Used
    for a run of triple patterns that contains a triple term, which rdflib's own
    ``evalBGP`` cannot match."""
    body = " . ".join(
        f"{_pattern_term_text(t.subject)} {_pattern_term_text(t.predicate)} {_pattern_term_text(t.object)}"
        for t in run
    )
    result = g.query(f"SELECT * WHERE {{ {body} }}")
    return [dict(binding) for binding in result.bindings]


def _compatible(mu1: dict, mu2: dict) -> bool:
    return all(mu1[v] == mu2[v] for v in mu1.keys() & mu2.keys())


def _collect_vars_in_expr(expr, found: set[Variable]) -> None:
    def _visit(node):
        if isinstance(node, Variable):
            found.add(node)
        return None

    algebra.traverse(expr, visitPost=_visit)


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


def _eval_triple_run(run: list[srl_ast.TriplePattern], seq: list[dict], g: Graph) -> list[dict]:
    """One ``evalBGP`` call per incoming solution for a maximal consecutive
    run of triple-pattern elements - see module docstring for why this is
    equivalent to (and more efficient than) matching them one at a time."""
    if any(_triple_uses_triple_terms(t) for t in run):
        # a pattern with a triple term is matched once, then joined with the incoming solutions
        matches = _match_with_query(run, g)
        return [{**mu, **m} for mu in seq for m in matches if _compatible(mu, m)]
    bgp = [(t.subject, t.predicate, t.object) for t in run]
    run_vars = {term for t in run for term in (t.subject, t.predicate, t.object) if isinstance(term, Variable)}
    out: list[dict] = []
    for mu in seq:
        ctx = QueryContext(graph=g, initBindings=mu)
        for binding in evalBGP(ctx, bgp):
            merged = dict(mu)
            for v in run_vars:
                merged[v] = binding[v]
            out.append(merged)
    return out


def _eval_ebv(expr, mu: dict, g: Graph) -> bool:
    ctx = QueryContext(graph=g, initBindings=mu)
    return _ebv(expr, ctx)


def _eval_expr(expr, mu: dict, g: Graph):
    """Evaluates ``expr`` under solution ``mu`` against graph ``g``,
    matching §6.3's ``evalFunction``/§6.4's "if x is not an error" check
    (``Expr.eval`` catches ``SPARQLError`` internally and returns it as a
    value rather than raising, per rdflib's own source).

    Args:
        expr: The rdflib expression to evaluate.
        mu: The current variable bindings.
        g: The graph to evaluate against.

    Returns:
        The evaluated value, or ``None`` if evaluation errored.
    """
    ctx = QueryContext(graph=g, initBindings=mu)
    val = expr.eval(ctx)
    if isinstance(val, SPARQLError):
        return None
    return val


def _eval_rule_elements(elements: list[srl_ast.BodyElement], seq: list[dict], g: Graph, gd: Graph) -> list[dict]:
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
            seq = [mu for mu in seq if _eval_ebv(elt.expr, mu, g)]
            i += 1
        elif isinstance(elt, srl_ast._AssignmentElement):
            new_seq: list[dict] = []
            for mu in seq:
                val = _eval_expr(elt.expr, mu, g)
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


def _subst_head_triple(triple: srl_ast.TriplePattern, mu: dict, bnode_map: dict[BNode, BNode]) -> tuple:
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
                bnode_map[t] = BNode()
            return bnode_map[t]
        return t

    return tuple(_graph_term(part, _sub) for part in (triple.subject, triple.predicate, triple.object))


def _eval_rule(rule: srl_ast._Rule, g: Graph, gd: Graph) -> set[tuple]:
    """§6.4's ``evalRule``."""
    used_vars = _collect_variables(rule)
    body = _blank_nodes_to_vars(rule.body, used_vars)
    if rule.evaldata:
        seq = _eval_rule_elements(body, [{}], g, gd)
    else:
        seq = _eval_rule_elements(body, [{}], gd, gd)

    out: set[tuple] = set()
    for mu in seq:
        bnode_map: dict[BNode, BNode] = {}
        for template in rule.head:
            try:
                triple = _subst_head_triple(template, mu, bnode_map)
            except _InvalidInstance:
                continue  # not valid RDF 1.2 (e.g. a literal as a triple term's subject): skipped
            subject, predicate, _object = triple
            if isinstance(subject, Literal) or not isinstance(predicate, URIRef):
                continue  # a literal subject, or a predicate that is not an IRI, is not a triple: skipped like CONSTRUCT (#96)
            out.add(triple)
    return out


# ---------------------------------------------------------------------------
# §6.5 Evaluation of a Rule Set / top-level Infer / Query (§4.1)
# ---------------------------------------------------------------------------


def _is_starlayer_graph(graph) -> bool:
    from starlayer.graph import StarLayerGraph

    return isinstance(graph, StarLayerGraph)


def _new_graph(use_starlayer: bool):
    if use_starlayer:
        from starlayer.graph import StarLayerGraph

        return StarLayerGraph()
    return Graph()


def _add_all(dst, src) -> None:
    for triple in src:
        dst.add(triple)


def _as_graph_kind(graph, use_starlayer: bool):
    """``graph`` itself, or a ``StarLayerGraph`` copy of it if one is needed and it is not one."""
    if use_starlayer and not _is_starlayer_graph(graph):
        copy = _new_graph(True)
        _add_all(copy, graph)
        return copy
    return graph


def _evaluate_ruleset(base_graph: Graph, ruleset: srl_ast.RuleSet) -> Graph:
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
        base_graph: The graph to run the rule set against.
        ruleset: The rule set to evaluate.

    Returns:
        ``GI``, the inferred-triples-only graph (never includes a triple
        already present in ``base_graph``, per §6's own stated output
        contract) - not the combined evaluation graph.

    Raises:
        SRLImportsNotSupportedError: If ``ruleset.imports`` is non-empty.
    """
    if ruleset.imports:
        raise SRLImportsNotSupportedError(
            "SRL: this implementation does not support IMPORTS - per §4.5, "
            "an implementation without import support MUST reject a rule set "
            "containing IMPORTS statements, rather than silently ignoring them"
        )

    # A StarLayerGraph can hold RDF 1.2 triple terms; a plain Graph cannot. Use one when
    # the rule set mentions a triple term or the base graph is already a StarLayerGraph.
    use_starlayer = _ruleset_uses_triple_terms(ruleset) or _is_starlayer_graph(base_graph)
    base_graph = _as_graph_kind(base_graph, use_starlayer)

    d = _new_graph(use_starlayer)
    for block in ruleset.data:
        for t in block.triples:
            try:
                d.add(tuple(_graph_term(part) for part in (t.subject, t.predicate, t.object)))
            except _InvalidInstance as exc:
                raise SRLEvalError(f"SRL: a DATA block has an invalid triple term: {exc}") from exc

    gi = _new_graph(use_starlayer)
    for t in d:
        if t not in base_graph:
            gi.add(t)

    ge = _new_graph(use_starlayer)
    _add_all(ge, base_graph)
    _add_all(ge, d)

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


def _srl_infer(base_graph: Graph, ruleset: srl_ast.RuleSet) -> Graph:
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
        The inferred-triples-only graph.
    """
    return _evaluate_ruleset(base_graph, ruleset)


def _srl_query(base_graph: Graph, ruleset: srl_ast.RuleSet, goal_pattern: srl_ast.TriplePattern) -> list[dict]:
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
        One ``dict[Variable, term]`` solution per match.
    """
    gi = _evaluate_ruleset(base_graph, ruleset)
    use_starlayer = _is_starlayer_graph(gi) or _triple_uses_triple_terms(goal_pattern)
    combined = _new_graph(use_starlayer)
    _add_all(combined, base_graph)
    _add_all(combined, gi)

    goal_vars = {
        v for term in (goal_pattern.subject, goal_pattern.predicate, goal_pattern.object) for v in _term_variables(term)
    }
    if _triple_uses_triple_terms(goal_pattern):
        return [{v: m[v] for v in goal_vars if v in m} for m in _match_with_query([goal_pattern], combined)]
    bgp = [(goal_pattern.subject, goal_pattern.predicate, goal_pattern.object)]
    ctx = QueryContext(graph=combined)
    return [{v: binding[v] for v in goal_vars} for binding in evalBGP(ctx, bgp)]
