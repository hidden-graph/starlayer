"""Tests for starlayer.sparql.srl_semantic_checks - SRL §4.2 Well-formedness
Conditions, a cross-referential check that can't be expressed as a
per-node SHACL shape - see that module's own docstring.

`parse_ruleset()` does not run this check (a rule set with a problem still loads). `srl_validate` reports each issue as a
violation, and running the rule set raises a `FormatError` (kind "srl"); these tests go through `srl_validate`
and `infer()`, the way a real caller would hit it.
"""

import pytest
from rdflib import Variable
from starlayer.errors import FormatError
from starlayer.graph import StarLayerGraph
from starlayer.sparql.srl import parse_ruleset, ruleset_to_tree, srl_validate

PREFIX = "PREFIX : <http://example.org/>\n"


def _assert_well_formed(text):
    """The ruleset loads, and srl_validate and infer() find nothing wrong with it."""
    ruleset = parse_ruleset(PREFIX + text)
    report = srl_validate(ruleset_to_tree(ruleset)[0])
    assert report.conforms, report.report_text
    ruleset.infer(StarLayerGraph())


def _assert_violation(text, kind, variable):
    ruleset = parse_ruleset(PREFIX + text)  # it loads
    report = srl_validate(ruleset_to_tree(ruleset)[0])
    assert not report.conforms
    assert kind in report.report_text
    assert str(variable) in report.report_text
    with pytest.raises(FormatError) as excinfo:  # and it is not run
        ruleset.infer(StarLayerGraph())
    assert kind in str(excinfo.value) and str(variable) in str(excinfo.value)


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
    _assert_well_formed(text)


def test_unbound_head_variable():
    _assert_violation(
        "RULE { ?x :p ?unbound } WHERE { ?x :q ?y . }",
        "unbound_head_variable",
        Variable("unbound"),
    )


def test_unbound_filter_variable():
    _assert_violation(
        "RULE { ?x :p true } WHERE { ?x :q ?y . FILTER(?unbound > 1) }",
        "unbound_filter_variable",
        Variable("unbound"),
    )


def test_unbound_assignment_expr_variable():
    _assert_violation(
        "RULE { ?x :p ?z } WHERE { ?x :q ?y . SET (?z := ?unbound + 1) }",
        "unbound_assignment_expr_variable",
        Variable("unbound"),
    )


def test_assignment_reusing_existing_variable_is_rejected():
    _assert_violation(
        "RULE { ?x :p ?y } WHERE { ?x :q ?y . SET (?y := ?y + 1) }",
        "reused_assignment_variable",
        Variable("y"),
    )


def test_assignment_binds_variable_for_later_use():
    """A variable introduced by SET(...) is visible to later body elements
    and the head - not itself a violation."""
    text = "RULE { ?x :p ?z } WHERE { ?x :q ?y . SET (?z := ?y + 1) . FILTER(?z > 0) }"
    _assert_well_formed(text)


def test_variable_bound_only_inside_negation_is_not_visible_after():
    """§4.2: a negation element's own varsi is empty - a variable first
    bound inside NOT { } does not extend V for what follows, or reach the
    head."""
    _assert_violation(
        "RULE { ?x :p ?y } WHERE { ?x :q true . NOT { ?x :r ?y } }",
        "unbound_head_variable",
        Variable("y"),
    )


def test_negation_body_checked_against_outer_bindings():
    """A negation element's own inner sequence is well-formed given the
    variables already bound before it - a filter inside NOT{} referencing
    an outer-bound variable is fine."""
    text = "RULE { ?x :p true } WHERE { ?x :q ?y . NOT { ?x :r ?y . FILTER(?y > 0) } }"
    _assert_well_formed(text)


def test_filter_inside_negation_referencing_unbound_variable_is_rejected():
    """Unlike the previous test, `?unbound` here never appears in any
    triple pattern anywhere in the negation's own body - genuinely
    unbound, not just bound-later."""
    _assert_violation(
        "RULE { ?x :p true } WHERE { ?x :q true . NOT { ?x :r true . FILTER(?unbound > 0) } }",
        "unbound_filter_variable",
        Variable("unbound"),
    )


@pytest.mark.parametrize(
    "body",
    [
        "?x :p ?y . SET(?n := COUNT(?y))",
        "?x :p ?y . FILTER(COUNT(?y) > 1)",
        "?x :p ?y . SET(?n := SUM(?y) + 1)",
    ],
)
def test_aggregate_inside_filter_or_set_is_reported_by_validate_and_not_run(body):
    """Aggregation is a separate rule element in SRL (still an open issue), never a
    function inside FILTER or SET - rejected here rather than crashing at infer()."""
    ruleset = parse_ruleset(f"PREFIX : <http://example.org/>\nRULE {{ ?x :n ?n }} WHERE {{ {body} }}")
    assert "aggregate_in_expression" in srl_validate(ruleset_to_tree(ruleset)[0]).report_text
    with pytest.raises(FormatError, match="aggregate_in_expression"):
        ruleset.infer(StarLayerGraph())
