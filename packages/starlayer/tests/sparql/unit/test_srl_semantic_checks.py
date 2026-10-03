"""Tests for starlayer.sparql.srl_semantic_checks - SRL §4.2 Well-formedness
Conditions, a cross-referential check that (like
semantic_checks.find_unbound_projected_variables) can't be expressed as a
per-node SHACL shape - see that module's own docstring.
"""

from rdflib import Variable

from starlayer.sparql.srl import parse_ruleset
from starlayer.sparql.srl_semantic_checks import check_ruleset

PREFIX = "PREFIX : <http://example.org/>\n"


def _issues(text):
    return check_ruleset(parse_ruleset(PREFIX + text))


def test_worked_example_is_fully_well_formed():
    text = """
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    RULE { ?x :exposedTo ?v } WHERE { ?x :hasVulnerability ?v . }
    RULE { ?x :exposedTo ?v } WHERE { ?x :dependsOn ?y . ?y :exposedTo ?v . }
    RULE { ?x :status :criticallyExposed }
    WHERE { ?x :exposedTo ?v . ?v :severity ?s . FILTER(?s >= 9.0) }
    RULE { ?x :status :safeToDeploy }
    WHERE { ?x rdf:type :Component . NOT { ?x :status :criticallyExposed } }
    RULE { [] rdf:type :Notification ; :concerns ?x }
    WHERE { ?x :status :criticallyExposed . }
    """
    assert _issues(text) == []


def test_unbound_head_variable():
    issues = _issues("RULE { ?x :p ?unbound } WHERE { ?x :q ?y . }")
    assert len(issues) == 1
    assert issues[0].kind == "unbound_head_variable"
    assert issues[0].variable == Variable("unbound")


def test_unbound_filter_variable():
    issues = _issues("RULE { ?x :p true } WHERE { ?x :q ?y . FILTER(?unbound > 1) }")
    assert len(issues) == 1
    assert issues[0].kind == "unbound_filter_variable"
    assert issues[0].variable == Variable("unbound")


def test_unbound_assignment_expr_variable():
    issues = _issues("RULE { ?x :p ?z } WHERE { ?x :q ?y . SET (?z := ?unbound + 1) }")
    assert any(i.kind == "unbound_assignment_expr_variable" and i.variable == Variable("unbound") for i in issues)


def test_assignment_reusing_existing_variable_is_rejected():
    issues = _issues("RULE { ?x :p ?y } WHERE { ?x :q ?y . SET (?y := ?y + 1) }")
    assert any(i.kind == "reused_assignment_variable" and i.variable == Variable("y") for i in issues)


def test_assignment_binds_variable_for_later_use():
    """A variable introduced by SET(...) is visible to later body elements
    and the head - not itself a violation."""
    text = "RULE { ?x :p ?z } WHERE { ?x :q ?y . SET (?z := ?y + 1) . FILTER(?z > 0) }"
    assert _issues(text) == []


def test_variable_bound_only_inside_negation_is_not_visible_after():
    """§4.2: a negation element's own varsi is empty - a variable first
    bound inside NOT { } does not extend V for what follows, or reach the
    head."""
    issues = _issues("RULE { ?x :p ?y } WHERE { ?x :q true . NOT { ?x :r ?y } }")
    assert any(i.kind == "unbound_head_variable" and i.variable == Variable("y") for i in issues)


def test_negation_body_checked_against_outer_bindings():
    """A negation element's own inner sequence is well-formed given the
    variables already bound before it - a filter inside NOT{} referencing
    an outer-bound variable is fine."""
    text = "RULE { ?x :p true } WHERE { ?x :q ?y . NOT { ?x :r ?y . FILTER(?y > 0) } }"
    assert _issues(text) == []


def test_filter_inside_negation_referencing_unbound_variable_is_rejected():
    """Unlike the previous test, `?unbound` here never appears in any
    triple pattern anywhere in the negation's own body - genuinely
    unbound, not just bound-later."""
    issues = _issues("RULE { ?x :p true } WHERE { ?x :q true . NOT { ?x :r true . FILTER(?unbound > 0) } }")
    assert any(i.kind == "unbound_filter_variable" and i.variable == Variable("unbound") for i in issues)
