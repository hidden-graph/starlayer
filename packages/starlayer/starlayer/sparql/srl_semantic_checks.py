"""SRL §4.2 "Well-formedness Conditions" - e.g. ``SET(...)`` must
not reuse an already-bound variable, and every filter/assignment/head
variable must be bound - as a function over the decoded ``srl_ast`` tree.

This is the check that *runs* a rule set: running or planning one (``_require_well_formed``) raises a ``FormatError`` (kind
``"srl"``) for a breach - without that, a rule set violating the "SET(...) must not reuse an already-bound variable" condition
would evaluate with zero error, just silently rebinding the variable to the wrong value. ``parse_ruleset()`` does not run it (a
rule set with a problem still loads, so it can be fixed).

The same conditions are also SHACL shapes in ``starontology/srl/srl_shapes.ttl`` (``srl:UnboundHeadVariableShape`` and the
rest, one per ``kind`` below), and ``validate_sparql_tree`` reports those: each result's focus node is the offending element, which
this function cannot give (it names a rule). Both are kept on purpose. A SPARQL constraint costs about 0.5 to 5 ms per element
(a 40-rule set took about 0.5 s to check; this function takes under a millisecond), which is too much to pay on every
``infer()``. ``tests/sparql/unit/test_srl_wellformedness_agreement.py`` proves the two agree (every §4.2 negative case of the
conformance suite and a seeded set of random rule sets); change one and the other.

Implements the spec's own formalism directly and verbatim (not an
approximation): for a sequence of rule elements given initial variables V0
and initial in-use variables U0, ``inScope`` is V0 plus every variable
contributed by the elements before position i, and ``inUse`` is U0 plus the
variables used inside a negation or group pattern that are not in scope
outside it (a name in use may not be set again, which is the rule that
variable names are not reused in a rule; SPARQL-RL draft of 2026-11-10). A
rule is well-formed iff its body is a well-formed sequence (V0 and U0 empty)
and every variable in a head triple template is in the body's final
``inScope``. See each check function's docstring for the exact
per-element-kind condition it enforces.
"""

from __future__ import annotations

from dataclasses import dataclass

import pyoxigraph as ox

from starlayer.errors import ExecutionError, FormatError

from . import _srl_ast as srl_ast
from .expr_text import expr_nodes, expr_variables
from .parse_sparql import _AGGS, _EXISTS_KINDS, Node
from .triple_term import TripleTermNode

Variable = ox.Variable


@dataclass(frozen=True)
class _SRLWellFormednessIssue:
    rule: srl_ast._Rule | None  # None for an issue in a rule set's DATA block
    kind: str  # "unbound_filter_variable" | "unbound_assignment_expr_variable"
    # | "reused_assignment_variable" | "unbound_head_variable" | "aggregate_in_expression"
    # | "triple_term_in_subject" | "triple_term_in_predicate" | "variable_in_data" | "unsupported_variable_name"
    # | "variable_in_use" | "group_key_unbound" | "aggregation_variable_in_scope" | "duplicate_aggregation_variable" | "unbound_aggregation_argument"
    variable: Variable | None  # None when the issue is not about one variable
    context: str


def _term_vars(term) -> set[Variable]:
    """Variables in ``term``, looking inside triple terms at any depth."""
    if isinstance(term, Variable):
        return {term}
    if isinstance(term, TripleTermNode):
        return set().union(*(_term_vars(term.get(part)) for part in ("subject", "predicate", "object")))
    return set()


def _triple_vars(triple: srl_ast.TriplePattern) -> set[Variable]:
    return _term_vars(triple.subject) | _term_vars(triple.predicate) | _term_vars(triple.object)


def _expr_vars(expr) -> set[Variable]:
    """Every variable anywhere in an expression tree."""
    return expr_variables(expr)


def _has_aggregate(expr) -> bool:
    """True if an aggregate node (COUNT, SUM, ...) or an ``EXISTS`` / ``NOT EXISTS`` occurs anywhere in ``expr``.
    Aggregation is a separate rule element in SRL (``GROUP``), never a function inside ``FILTER`` or ``SET``; use a
    ``NOT { ... }`` negation element instead of ``NOT EXISTS``."""
    # EXISTS needs a graph pattern the rule evaluator does not run: reject it here rather than crash later (#96)
    return any(
        isinstance(n, Node) and (n.kind in _AGGS or n.kind in _EXISTS_KINDS)
        for n in expr_nodes(expr)
    )


def _check_sequence(
    elements: list[srl_ast.BodyElement],
    v0: set[Variable],
    u0: set[Variable],
    rule: srl_ast._Rule,
    issues: list[_SRLWellFormednessIssue],
) -> tuple[set[Variable], set[Variable]]:
    """Checks ``elements`` as a well-formed sequence given initial variables ``v0`` and initial in-use variables ``u0``, per the
    spec's own §4.2 definition (``inScope`` and ``inUse``).

    A variable is *in scope* when it has a value at that point; it is *in use* when the rule has used it where its value is not
    visible (inside a negation or a group pattern, or a variable that was in scope before a group and is not one of its keys).
    A name that is in use may not be set again, by a later element or inside a negation or group.

    Args:
        elements: The body elements to check, in sequence order.
        v0: The variables in scope before ``elements`` begins.
        u0: The variables already in use before ``elements`` begins.
        rule: The enclosing rule, attached to any issue found.
        issues: Violations found are appended here.

    Returns:
        ``(inScope, inUse)`` after the whole sequence.
    """
    scope = set(v0)
    use = set(u0)
    for elt in elements:
        if isinstance(elt, srl_ast.TriplePattern):
            variables = _triple_vars(elt)
            for v in sorted(variables & use, key=lambda x: x.value):
                issues.append(_SRLWellFormednessIssue(rule, "variable_in_use", v, "triple pattern"))
            scope |= variables
        elif isinstance(elt, srl_ast._FilterElement):
            for v in _expr_vars(elt.expr) - scope:
                issues.append(_SRLWellFormednessIssue(rule, "unbound_filter_variable", v, "FILTER"))
            if _has_aggregate(elt.expr):
                issues.append(_SRLWellFormednessIssue(rule, "aggregate_in_expression", None, "FILTER"))
        elif isinstance(elt, srl_ast._AssignmentElement):
            for v in _expr_vars(elt.expr) - scope:
                issues.append(_SRLWellFormednessIssue(rule, "unbound_assignment_expr_variable", v, "SET(...)"))
            if _has_aggregate(elt.expr):
                issues.append(_SRLWellFormednessIssue(rule, "aggregate_in_expression", None, "SET(...)"))
            if elt.var in scope or elt.var in use:
                issues.append(_SRLWellFormednessIssue(rule, "reused_assignment_variable", elt.var, "SET(...)"))
            scope = scope | {elt.var}
        elif isinstance(elt, srl_ast._NegationElement):
            # The body is a well-formed sequence given the variables in scope and in use here. What it binds is not in scope
            # afterwards, but it is in use: no later element may set it.
            inner_scope, inner_use = _check_sequence(elt.inner, scope, use, rule, issues)
            use = use | ((inner_scope | inner_use) - scope)
        elif isinstance(elt, srl_ast._GroupElement):
            scope, use = _check_group(elt, scope, use, rule, issues)
        else:  # pragma: no cover - srl_ast.BodyElement is exhaustive
            raise ExecutionError(f"unrecognized rule body element: {elt!r}", kind="internal", context="srl: well-formedness check")
    return scope, use


def _check_group(
    group: srl_ast._GroupElement,
    v_in: set[Variable],
    u_in: set[Variable],
    rule: srl_ast._Rule,
    issues: list[_SRLWellFormednessIssue],
) -> tuple[set[Variable], set[Variable]]:
    """§4.2 for a group element ``GRP``, with ``V_in`` and ``U_in`` the variables in scope and in use before it. The group pattern
    sees only the keys that are already bound (``GK_in = GRP.keys ∩ V_in``); the other variables in scope before the group are in
    use inside it (``GU_in = U_in ∪ (V_in − GRP.keys)``), so the pattern may not reuse them. It is a well-formed sequence given
    those; every group key is in scope after it; no aggregation variable is in ``V_in ∪ U_in`` or in scope or in use in the
    pattern and none is repeated; an aggregation argument that is a variable is in scope in the pattern.

    Returns the variables in scope and in use after the group: scope is ``V_in ∪ GRP.keys ∪ aggVars`` (what the pattern binds
    beyond the keys is not in scope after it, but it is in use)."""
    keys = set(group.keys)
    pattern_scope, pattern_use = _check_sequence(group.pattern, keys & v_in, u_in | (v_in - keys), rule, issues)
    for key in group.keys:
        if key not in pattern_scope:
            issues.append(_SRLWellFormednessIssue(rule, "group_key_unbound", key, "GROUP BY"))
    seen: set[Variable] = set()
    for agg in group.aggregations:
        if agg.var in pattern_scope or agg.var in pattern_use or agg.var in v_in or agg.var in u_in:
            issues.append(_SRLWellFormednessIssue(rule, "aggregation_variable_in_scope", agg.var, "GROUP aggregation"))
        if agg.var in seen:
            issues.append(_SRLWellFormednessIssue(rule, "duplicate_aggregation_variable", agg.var, "GROUP aggregation"))
        seen.add(agg.var)
        if agg.argument is not None and agg.argument not in pattern_scope:
            issues.append(_SRLWellFormednessIssue(rule, "unbound_aggregation_argument", agg.argument, "GROUP aggregation"))
    scope = v_in | keys | {agg.var for agg in group.aggregations}
    return scope, u_in | ((pattern_scope | pattern_use) - scope)


def _triples_of(rule: srl_ast._Rule) -> list[srl_ast.TriplePattern]:
    """Every triple pattern or template in ``rule``: head, body and negation bodies."""
    found = list(rule.head)

    def _element(e) -> None:
        if isinstance(e, srl_ast.TriplePattern):
            found.append(e)
        elif isinstance(e, srl_ast._NegationElement):
            for inner in e.inner:
                _element(inner)
        elif isinstance(e, srl_ast._GroupElement):
            for inner in e.pattern:
                _element(inner)

    for e in rule.body:
        _element(e)
    return found


def _check_triple_term_positions(
    rule: srl_ast._Rule | None, triples: list[srl_ast.TriplePattern], issues: list[_SRLWellFormednessIssue]
) -> None:
    """RDF 1.2: a triple term is only ever legal as the object of a triple, never
    as its subject or predicate."""
    def _inside(term, context: str) -> None:
        # a triple term nested in an object is itself a triple: the same two positions apply to it
        if isinstance(term, TripleTermNode):
            for position in ("subject", "predicate"):
                if isinstance(term.get(position), TripleTermNode):
                    issues.append(_SRLWellFormednessIssue(rule, "triple_term_in_" + position, None, context))
            _inside(term.get("object"), context)

    for t in triples:
        for position, term in (("subject", t.subject), ("predicate", t.predicate)):
            if isinstance(term, TripleTermNode):
                issues.append(
                    _SRLWellFormednessIssue(rule, "triple_term_in_" + position, None, "triple pattern")
                )
        _inside(t.object, "triple term")


def _check_variable_names(rule: srl_ast._Rule, issues: list[_SRLWellFormednessIssue]) -> None:
    """The grammar allows U+10000 to U+EFFFF in a variable name (PN_CHARS_BASE), but the engine the rules run on does not
    accept such a name in its SPARQL text, so a rule using one is refused here rather than failing at ``infer()``."""
    names: set[Variable] = set()

    def _element(e) -> None:
        if isinstance(e, srl_ast.TriplePattern):
            names.update(_triple_vars(e))
        elif isinstance(e, srl_ast._FilterElement):
            names.update(_expr_vars(e.expr))
        elif isinstance(e, srl_ast._AssignmentElement):
            names.add(e.var)
            names.update(_expr_vars(e.expr))
        elif isinstance(e, srl_ast._NegationElement):
            for inner in e.inner:
                _element(inner)
        elif isinstance(e, srl_ast._GroupElement):
            names.update(e.keys)
            for agg in e.aggregations:
                names.add(agg.var)
                if agg.argument is not None:
                    names.add(agg.argument)
            for inner in e.pattern:
                _element(inner)

    for template in rule.head:
        names.update(_triple_vars(template))
    for e in rule.body:
        _element(e)
    for v in sorted(names, key=lambda x: x.value):
        if any(ord(c) > 0xFFFF for c in v.value):
            issues.append(_SRLWellFormednessIssue(rule, "unsupported_variable_name", v, "variable name above U+FFFF"))


def _check_rule(rule: srl_ast._Rule) -> list[_SRLWellFormednessIssue]:
    """§4.2: is ``rule`` a well-formed rule? Its body must be a well-formed
    sequence given V0 = the empty set, and every variable in a head triple
    template must be in the body's own ``Vall``."""
    issues: list[_SRLWellFormednessIssue] = []
    _check_triple_term_positions(rule, _triples_of(rule), issues)
    _check_variable_names(rule, issues)
    v_all, _ = _check_sequence(rule.body, set(), set(), rule, issues)
    for template in rule.head:
        for v in _triple_vars(template):
            if v not in v_all:
                issues.append(_SRLWellFormednessIssue(rule, "unbound_head_variable", v, "rule head"))
    return issues


def _check_ruleset(ruleset: srl_ast.RuleSet) -> list[_SRLWellFormednessIssue]:
    """§4.2: ``ruleset`` is well-formed iff every rule in it is - the
    per-rule issues found, flattened across all rules (empty list means
    the whole rule set is well-formed)."""
    issues: list[_SRLWellFormednessIssue] = []
    for rule in ruleset.rules:
        issues.extend(_check_rule(rule))
    for block in ruleset.data:
        _check_triple_term_positions(None, block.triples, issues)
        # a DATA block holds ground facts: the grammar (§7.6) does not allow a variable in one
        for t in block.triples:
            for v in sorted(_term_vars(t.subject) | _term_vars(t.predicate) | _term_vars(t.object), key=lambda x: x.value):
                issues.append(_SRLWellFormednessIssue(None, "variable_in_data", v, "DATA block"))
    return issues


def _describe(issue: _SRLWellFormednessIssue) -> str:
    """One issue as text: its kind, the variable and where it was found."""
    if issue.variable is not None:
        return f"{issue.kind} ({issue.variable} in {issue.context})"
    return f"{issue.kind} (in {issue.context})"


def _problem_text(issues: list[_SRLWellFormednessIssue]) -> str:
    """The issues of ``_check_ruleset`` as one message."""
    return "SRL: rule set is not well-formed per §4.2: " + "; ".join(_describe(i) for i in issues)


def _require_well_formed(ruleset: srl_ast.RuleSet) -> None:
    """Raise a ``FormatError`` (kind ``"srl"``) if ``ruleset`` breaks a §4.2 condition: a rule set that loads is not run."""
    issues = _check_ruleset(ruleset)
    if issues:
        text = _problem_text(issues)
        raise FormatError(text, kind="srl", why=text, context="rule set")
