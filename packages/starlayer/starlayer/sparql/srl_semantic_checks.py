"""SRL/SPARQL-RL §4.2 "Well-formedness Conditions" - a cross-referential,
sequence-position-dependent check SHACL's own per-node shapes structurally
can't see, so (mirroring ``semantic_checks.find_unbound_projected_variables``'s
own precedent for exactly this reason) it lives here as a standalone
function over the decoded ``srl_ast`` tree, not a SHACL shape.

Implements the spec's own formalism directly and verbatim (not an
approximation): for a sequence of rule elements given an initial variable
set V0, ``Vi`` is V0 plus every variable contributed by elements before
position i, and ``Vall`` is V0 plus every variable contributed by the whole
sequence. A rule is well-formed iff its body is a well-formed sequence
(V0 = empty set) and every variable in a head triple template is in the
body's own ``Vall``. See each check function's docstring for the exact
per-element-kind condition it enforces.
"""

from __future__ import annotations

from dataclasses import dataclass

from rdflib import Variable
from rdflib.plugins.sparql import algebra

from . import srl_ast


@dataclass(frozen=True)
class SRLWellFormednessIssue:
    rule: srl_ast.Rule
    kind: str  # "unbound_filter_variable" | "unbound_assignment_expr_variable"
    # | "reused_assignment_variable" | "unbound_head_variable"
    variable: Variable
    context: str


def _term_vars(term) -> set[Variable]:
    return {term} if isinstance(term, Variable) else set()


def _triple_vars(triple: srl_ast.TriplePattern) -> set[Variable]:
    return _term_vars(triple.subject) | _term_vars(triple.predicate) | _term_vars(triple.object)


def _expr_vars(expr) -> set[Variable]:
    """Every ``Variable`` leaf anywhere in a real rdflib ``Expr``/``CompValue``
    expression tree - the same generic ``algebra.traverse`` walk
    ``srl.py`` already uses for prefixed-name resolution, here just
    observing rather than rewriting (``visitPost`` always returns ``None``,
    so the tree itself is left unchanged)."""
    found: set[Variable] = set()

    def _visit(node):
        if isinstance(node, Variable):
            found.add(node)
        return None

    algebra.traverse(expr, visitPost=_visit)
    return found


def _check_sequence(
    elements: list[srl_ast.BodyElement],
    v0: set[Variable],
    rule: srl_ast.Rule,
    issues: list[SRLWellFormednessIssue],
) -> set[Variable]:
    """Checks ``elements`` as a well-formed sequence given initial variables
    ``v0`` (appending any violations found to ``issues``), returning
    ``Vall`` - ``v0`` plus every variable contributed by the whole
    sequence, per the spec's own §4.2 definition."""
    v_current = set(v0)
    for elt in elements:
        if isinstance(elt, srl_ast.TriplePattern):
            # varsi = variables occurring in the triple pattern element.
            v_current |= _triple_vars(elt)
        elif isinstance(elt, srl_ast.FilterElement):
            # "every variable mentioned in a filter element is an element
            # of Vi-1" - checked against v_current *before* this element's
            # own (empty) varsi contribution.
            for v in _expr_vars(elt.expr) - v_current:
                issues.append(SRLWellFormednessIssue(rule, "unbound_filter_variable", v, "FILTER"))
            # varsi = {} for a filter element - v_current unchanged.
        elif isinstance(elt, srl_ast.AssignmentElement):
            for v in _expr_vars(elt.expr) - v_current:
                issues.append(SRLWellFormednessIssue(rule, "unbound_assignment_expr_variable", v, "SET(...)"))
            if elt.var in v_current:
                issues.append(SRLWellFormednessIssue(rule, "reused_assignment_variable", elt.var, "SET(...)"))
            # varsi = {the assignment variable}, regardless of whether the
            # reuse condition above was violated - the spec still counts it
            # as bound going forward (matches evalRuleElements' own
            # behaviour: a successful assignment always extends mu).
            v_current = v_current | {elt.var}
        elif isinstance(elt, srl_ast.NegationElement):
            # "the sequence of rule elements in the negation element body
            # is a well-formed sequence given the set of variables Vi-1."
            _check_sequence(elt.inner, v_current, rule, issues)
            # varsi = {} for a negation element - v_current unchanged (a
            # variable first bound only inside a negation is NOT visible
            # afterwards, matching ordinary SPARQL NOT EXISTS/MINUS scoping).
        else:  # pragma: no cover - srl_ast.BodyElement is exhaustive
            raise TypeError(f"unrecognized rule body element: {elt!r}")
    return v_current


def check_rule(rule: srl_ast.Rule) -> list[SRLWellFormednessIssue]:
    """§4.2: is ``rule`` a well-formed rule? Its body must be a well-formed
    sequence given V0 = the empty set, and every variable in a head triple
    template must be in the body's own ``Vall``."""
    issues: list[SRLWellFormednessIssue] = []
    v_all = _check_sequence(rule.body, set(), rule, issues)
    for template in rule.head:
        for v in _triple_vars(template):
            if v not in v_all:
                issues.append(SRLWellFormednessIssue(rule, "unbound_head_variable", v, "rule head"))
    return issues


def check_ruleset(ruleset: srl_ast.RuleSet) -> list[SRLWellFormednessIssue]:
    """§4.2: ``ruleset`` is well-formed iff every rule in it is - the
    per-rule issues found, flattened across all rules (empty list means
    the whole rule set is well-formed)."""
    issues: list[SRLWellFormednessIssue] = []
    for rule in ruleset.rules:
        issues.extend(check_rule(rule))
    return issues
