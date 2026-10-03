"""SRL/SPARQL-RL evaluation engine - `WD-sparql12-rl-20260919
<https://www.w3.org/TR/sparql12-rl/>`_ §4.3 (Rule Dependency),
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

from rdflib import BNode, Graph, Variable
from rdflib.plugins.sparql import algebra
from rdflib.plugins.sparql.evaluate import _ebv, evalBGP
from rdflib.plugins.sparql.sparql import QueryContext, SPARQLError

from . import srl_ast


class SRLEvalError(ValueError):
    """Base class for SRL evaluation errors."""


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
class DependencyEdge:
    source: srl_ast.Rule
    target: srl_ast.Rule
    label: str  # "open" | "closed"


def is_run_once(rule: srl_ast.Rule) -> bool:
    """§4.1/§4.4: a rule is run-once if it has an assignment element
    anywhere in its body, or a blank node anywhere in its head - otherwise
    it is a general rule. (Assignment elements can never occur nested
    inside a negation element - the grammar forbids it, see
    ``srl_ast.NegationElement`` - so a top-level scan of ``rule.body``
    already covers every assignment element that could exist.)"""
    if any(isinstance(e, srl_ast.AssignmentElement) for e in rule.body):
        return True
    return any(_has_blank_node(t) for t in rule.head)


def _has_blank_node(triple: srl_ast.TriplePattern) -> bool:
    return isinstance(triple.subject, BNode) or isinstance(triple.object, BNode)


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
    """
    if isinstance(pattern_term, Variable) or isinstance(template_term, Variable):
        return True
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


def build_dependency_graph(ruleset: srl_ast.RuleSet) -> list[DependencyEdge]:
    """§4.3.2's ``buildDependencyGraph`` algorithm, translated directly."""
    edge_labels: dict[tuple[int, int], str] = {}
    id_to_rule: dict[int, srl_ast.Rule] = {id(r): r for r in ruleset.rules}

    for r1 in ruleset.rules:
        body_dependencies: list[tuple[srl_ast.TriplePattern, str]] = []
        for elt in r1.body:
            if isinstance(elt, srl_ast.NegationElement):
                for inner in elt.inner:
                    if isinstance(inner, srl_ast.TriplePattern):
                        body_dependencies.append((inner, "closed"))
            elif isinstance(elt, srl_ast.TriplePattern):
                body_dependencies.append((elt, "open"))
            # FilterElement / AssignmentElement: no dependency contribution.

        r1_run_once = is_run_once(r1)

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
        DependencyEdge(id_to_rule[r1_id], id_to_rule[r2_id], label)
        for (r1_id, r2_id), label in edge_labels.items()
    ]


# ---------------------------------------------------------------------------
# §4.4 Stratification / §4.4.2 Stratification Algorithm
# ---------------------------------------------------------------------------


def stratify(ruleset: srl_ast.RuleSet) -> list[tuple[list[srl_ast.Rule], list[srl_ast.Rule]]]:
    """§4.4.2's ``stratification`` algorithm, translated directly. Returns
    a sequence of ``(once_rules, general_rules)`` pairs, one per stratum,
    in evaluation order. Raises :class:`StratificationError` if the
    §4.4.1 Stratification Condition is violated (a recursive dependency
    involving a closed edge)."""
    edges = build_dependency_graph(ruleset)
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

    stratum_rules: dict[int, list[srl_ast.Rule]] = {i: [] for i in range(max_stratum + 1)}
    for r in ruleset.rules:
        stratum_rules[stratum[id(r)]].append(r)

    layers: list[tuple[list[srl_ast.Rule], list[srl_ast.Rule]]] = []
    for i in range(max_stratum + 1):
        rules_i = stratum_rules[i]
        once_ids = {id(r) for r in rules_i if is_run_once(r)}
        once = [r for r in rules_i if id(r) in once_ids]
        general = [r for r in rules_i if id(r) not in once_ids]
        layers.append((once, general))
    return layers


# ---------------------------------------------------------------------------
# §6.3/§6.4 Evaluating expressions and a single rule
# ---------------------------------------------------------------------------


def _collect_vars_in_expr(expr, found: set[Variable]) -> None:
    def _visit(node):
        if isinstance(node, Variable):
            found.add(node)
        return None

    algebra.traverse(expr, visitPost=_visit)


def _collect_variables(rule: srl_ast.Rule) -> set[Variable]:
    """Every ``Variable`` used anywhere in ``rule`` (head or body) - needed
    so fresh variables minted for body blank nodes (§6.4) can't collide
    with a variable the rule already uses."""
    found: set[Variable] = set()

    def _triple(t: srl_ast.TriplePattern) -> None:
        for term in (t.subject, t.predicate, t.object):
            if isinstance(term, Variable):
                found.add(term)

    def _element(e: srl_ast.BodyElement) -> None:
        if isinstance(e, srl_ast.TriplePattern):
            _triple(e)
        elif isinstance(e, srl_ast.FilterElement):
            _collect_vars_in_expr(e.expr, found)
        elif isinstance(e, srl_ast.AssignmentElement):
            found.add(e.var)
            _collect_vars_in_expr(e.expr, found)
        elif isinstance(e, srl_ast.NegationElement):
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
    substituted."""
    mapping: dict[BNode, Variable] = {}

    def _sub_term(t):
        if isinstance(t, BNode):
            if t not in mapping:
                mapping[t] = _fresh_variable(used_vars)
            return mapping[t]
        return t

    def _sub_triple(t: srl_ast.TriplePattern) -> srl_ast.TriplePattern:
        return srl_ast.TriplePattern(_sub_term(t.subject), t.predicate, _sub_term(t.object))

    def _sub_element(e: srl_ast.BodyElement) -> srl_ast.BodyElement:
        if isinstance(e, srl_ast.TriplePattern):
            return _sub_triple(e)
        if isinstance(e, srl_ast.NegationElement):
            return srl_ast.NegationElement(inner=[_sub_element(x) for x in e.inner], data=e.data)
        return e  # FilterElement/AssignmentElement: no raw BNode terms to substitute

    return [_sub_element(e) for e in body]


def _eval_triple_run(run: list[srl_ast.TriplePattern], seq: list[dict], g: Graph) -> list[dict]:
    """One ``evalBGP`` call per incoming solution for a maximal consecutive
    run of triple-pattern elements - see module docstring for why this is
    equivalent to (and more efficient than) matching them one at a time."""
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
    """Returns the evaluated value, or ``None`` if evaluation errored -
    matching §6.3's ``evalFunction``/§6.4's "if x is not an error" check
    (``Expr.eval`` catches ``SPARQLError`` internally and returns it as a
    value rather than raising, per rdflib's own source)."""
    ctx = QueryContext(graph=g, initBindings=mu)
    val = expr.eval(ctx)
    if isinstance(val, SPARQLError):
        return None
    return val


def eval_rule_elements(elements: list[srl_ast.BodyElement], seq: list[dict], g: Graph, gd: Graph) -> list[dict]:
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
        elif isinstance(elt, srl_ast.FilterElement):
            seq = [mu for mu in seq if _eval_ebv(elt.expr, mu, g)]
            i += 1
        elif isinstance(elt, srl_ast.AssignmentElement):
            new_seq: list[dict] = []
            for mu in seq:
                val = _eval_expr(elt.expr, mu, g)
                if val is not None:
                    mu2 = dict(mu)
                    mu2[elt.var] = val
                    new_seq.append(mu2)
            seq = new_seq
            i += 1
        elif isinstance(elt, srl_ast.NegationElement):
            inner_g = gd if elt.data else g
            new_seq = []
            for mu in seq:
                neg = eval_rule_elements(elt.inner, [mu], inner_g, gd)
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

    return (_sub(triple.subject), _sub(triple.predicate), _sub(triple.object))


def eval_rule(rule: srl_ast.Rule, g: Graph, gd: Graph) -> set[tuple]:
    """§6.4's ``evalRule``."""
    used_vars = _collect_variables(rule)
    body = _blank_nodes_to_vars(rule.body, used_vars)
    if rule.data:
        seq = eval_rule_elements(body, [{}], gd, gd)
    else:
        seq = eval_rule_elements(body, [{}], g, gd)

    out: set[tuple] = set()
    for mu in seq:
        bnode_map: dict[BNode, BNode] = {}
        for template in rule.head:
            out.add(_subst_head_triple(template, mu, bnode_map))
    return out


# ---------------------------------------------------------------------------
# §6.5 Evaluation of a Rule Set / top-level Infer / Query (§4.1)
# ---------------------------------------------------------------------------


def evaluate_ruleset(base_graph: Graph, ruleset: srl_ast.RuleSet) -> Graph:
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

    Returns ``GI``, the inferred-triples-only graph (never includes a
    triple already present in ``base_graph``, per §6's own stated output
    contract) - not the combined evaluation graph.
    """
    if ruleset.imports:
        raise SRLImportsNotSupportedError(
            "SRL: this implementation does not support IMPORTS - per §4.5, "
            "an implementation without import support MUST reject a rule set "
            "containing IMPORTS statements, rather than silently ignoring them"
        )

    d = Graph()
    for block in ruleset.data:
        for t in block.triples:
            d.add((t.subject, t.predicate, t.object))

    gi = Graph()
    for t in d:
        if t not in base_graph:
            gi.add(t)

    ge = Graph()
    ge += base_graph
    ge += d

    for once_rules, general_rules in stratify(ruleset):
        for rule in once_rules:
            for t in eval_rule(rule, ge, base_graph):
                if t not in ge:
                    gi.add(t)
                    ge.add(t)

        finished = False
        while not finished:
            finished = True
            for rule in general_rules:
                for t in eval_rule(rule, ge, base_graph):
                    if t not in ge:
                        finished = False
                        gi.add(t)
                        ge.add(t)

    return gi


def srl_infer(base_graph: Graph, ruleset: srl_ast.RuleSet) -> Graph:
    """§4.1's top-level ``Infer`` operation - apply full rule-set
    evaluation, producing the inference graph. Alias for
    :func:`evaluate_ruleset` under the spec's own operation name.

    Named ``srl_infer``, not the bare ``infer`` the spec itself uses -
    deliberately, to avoid colliding with ``StarLayerGraph.infer(profile=
    ...)`` (RDF/RDFS/OWL-RL/OWL-DL entailment) when both are imported into
    the same namespace, e.g. ``from starlayer.sparql.srl_eval import *`` alongside
    ``from starlayer.graph import StarLayerGraph`` - a real, easy mix-up
    given how similar the two names and signatures are otherwise."""
    return evaluate_ruleset(base_graph, ruleset)


def srl_query(base_graph: Graph, ruleset: srl_ast.RuleSet, goal_pattern: srl_ast.TriplePattern) -> list[dict]:
    """§4.1's top-level ``Query`` operation, v1: "equivalent to infer +
    matching the goal pattern against base ∪ GI" - the spec's own stated
    equivalence, implemented directly on top of :func:`srl_infer` rather
    than the selective-rule-evaluation optimization it also permits (a
    documented future enhancement, not required for a correct result).
    Returns one ``dict[Variable, term]`` solution per match.

    Named ``srl_query``, not the bare ``query`` the spec itself uses - same
    collision-avoidance reasoning as :func:`srl_infer` above, this time
    against ``StarLayerGraph.query()``/plain rdflib's own ``Graph.query()``.
    """
    gi = evaluate_ruleset(base_graph, ruleset)
    combined = Graph()
    combined += base_graph
    combined += gi

    goal_vars = {
        term
        for term in (goal_pattern.subject, goal_pattern.predicate, goal_pattern.object)
        if isinstance(term, Variable)
    }
    bgp = [(goal_pattern.subject, goal_pattern.predicate, goal_pattern.object)]
    ctx = QueryContext(graph=combined)
    return [{v: binding[v] for v in goal_vars} for binding in evalBGP(ctx, bgp)]
