"""Tests for SRL §4.2 Well-formedness Conditions.

`parse_ruleset()` does not run the check (a rule set with a problem still loads). `validate_sparql_tree` reports each problem from the
shapes in `srl_shapes.ttl`, a result per offending element (the focus node is that element; the message names the variable), and
running the rule set raises a `FormatError` (kind "srl") from the Python check (`srl_semantic_checks`). These tests go through
`validate_sparql_tree` and `infer()`, the way a real caller would hit them; `test_srl_wellformedness_agreement.py` shows the two agree.
"""

import pytest
from starlayer.errors import FormatError
from starlayer.graph import RDF, StarLayerGraph
from starlayer.sparql import validate_sparql_tree
from starlayer.sparql.srl import parse_ruleset, ruleset_to_tree
from tests.support.srl_wellformedness import findings

PREFIX = "PREFIX : <http://example.org/>\n"


def _assert_well_formed(text):
    """The ruleset loads, and validate_sparql_tree and infer() find nothing wrong with it."""
    ruleset = parse_ruleset(PREFIX + text)
    report = validate_sparql_tree(ruleset_to_tree(ruleset)[0])
    assert report.conforms, report.report_text
    ruleset.infer(StarLayerGraph())


def _classes(tree, node):
    return {o.value.rpartition("#")[2] for o in tree.objects(node, RDF.type)}


def _assert_violation(text, kind, variable, element="TriplePattern"):
    """The rule set loads; validate_sparql_tree has exactly one result of the shape for ``kind`` whose focus node is an ``element`` of the tree
    and whose message names ``variable``; and infer() refuses it."""
    ruleset = parse_ruleset(PREFIX + text)  # it loads
    tree, _root = ruleset_to_tree(ruleset)
    report, rows = findings(tree)
    assert not report.conforms
    ours = [(v, focus) for k, v, focus in rows if k == kind]
    assert len(ours) == 1, rows
    name, focus = ours[0]
    if variable is not None:
        assert name == str(variable)
        assert f"{variable}" in report.report_text  # the message names it
    assert element in _classes(tree, focus)
    with pytest.raises(FormatError) as excinfo:  # and it is not run
        ruleset.infer(StarLayerGraph())
    assert kind in str(excinfo.value) and (variable is None or str(variable) in str(excinfo.value))


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
        "unbound",
    )


def test_unbound_filter_variable():
    _assert_violation(
        "RULE { ?x :p true } WHERE { ?x :q ?y . FILTER(?unbound > 1) }",
        "unbound_filter_variable",
        "unbound",
        element="FilterElement",
    )


def test_unbound_assignment_expr_variable():
    _assert_violation(
        "RULE { ?x :p ?z } WHERE { ?x :q ?y . SET (?z := ?unbound + 1) }",
        "unbound_assignment_expr_variable",
        "unbound",
        element="AssignmentElement",
    )


def test_assignment_reusing_existing_variable_is_rejected():
    _assert_violation(
        "RULE { ?x :p ?y } WHERE { ?x :q ?y . SET (?y := ?y + 1) }",
        "reused_assignment_variable",
        "y",
        element="AssignmentElement",
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
        "y",
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
        "unbound",
        element="FilterElement",
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
    tree, _root = ruleset_to_tree(ruleset)
    report, rows = findings(tree)
    aggregates = [focus for kind, _v, focus in rows if kind == "aggregate_in_expression"]  # (the FILTER body leaves ?n unbound too)
    assert not report.conforms and len(aggregates) == 1
    assert _classes(tree, aggregates[0]) & {"FilterElement", "AssignmentElement"}  # the offending element
    assert "cannot contain an aggregate" in report.report_text
    with pytest.raises(FormatError, match="aggregate_in_expression"):
        ruleset.infer(StarLayerGraph())


# ---- one rule set per condition, breaking only that one: the shape's result, its focus node and its message ----------------


def test_a_filter_before_the_pattern_that_binds_its_variable_is_rejected():
    """Order matters: ``?y`` is bound, but only after the FILTER that uses it."""
    _assert_violation(
        "RULE { ?x :p ?y } WHERE { FILTER(?y > 1) ?x :q ?y }",
        "unbound_filter_variable",
        "y",
        element="FilterElement",
    )


def test_a_set_expression_before_the_pattern_that_binds_its_variable_is_rejected():
    _assert_violation(
        "RULE { ?x :p ?z } WHERE { ?x :q ?y . SET (?z := ?w + 1) ?x :r ?w }",
        "unbound_assignment_expr_variable",
        "w",
        element="AssignmentElement",
    )


def test_a_variable_used_inside_a_negation_may_not_be_used_in_a_triple_pattern_after_it():
    _assert_violation(
        "RULE { ?x :p ?y } WHERE { ?x :q ?y . NOT { ?x :r ?w } ?w :s ?x }",
        "variable_in_use",
        "w",
    )


def test_a_variable_used_inside_a_group_pattern_may_not_be_used_in_a_triple_pattern_after_it():
    _assert_violation(
        "RULE { ?x :p ?y } WHERE { ?x :q ?y . GROUP BY ?x { ?x :r ?o } [ ?n := COUNT(*) ] ?o :s ?x }",
        "variable_in_use",
        "o",
    )


def test_a_triple_pattern_inside_a_negation_may_not_use_a_variable_that_an_earlier_negation_used():
    _assert_violation(
        "RULE { ?x :p ?y } WHERE { ?x :q ?y . NOT { ?x :r ?w } NOT { ?w :s ?x } }",
        "variable_in_use",
        "w",
    )


def test_a_set_variable_that_is_in_use_is_rejected():
    _assert_violation(
        "RULE { ?x :p ?w } WHERE { ?x :q ?y . NOT { ?x :r ?w } SET (?w := 1) }",
        "reused_assignment_variable",
        "w",
        element="AssignmentElement",
    )


def test_a_set_variable_bound_by_the_group_it_follows_is_rejected():
    _assert_violation(
        "RULE { ?x :p ?n } WHERE { GROUP BY ?x { ?x :r ?o } [ ?c := COUNT(*) ] SET (?x := 1) SET (?n := ?c) }",
        "reused_assignment_variable",
        "x",
        element="AssignmentElement",
    )


def test_an_unbound_group_key_is_rejected():
    _assert_violation(
        "RULE { ?x :n ?n } WHERE { ?x :q ?y . GROUP BY ?k { ?x :r ?o } [ ?n := COUNT(*) ] }",
        "group_key_unbound",
        "k",
        element="GroupElement",
    )


def test_a_group_key_bound_only_by_the_group_pattern_is_accepted():
    _assert_well_formed("RULE { ?k :n ?n } WHERE { GROUP BY ?k { ?k :r ?o } [ ?n := COUNT(*) ] }")


def test_an_aggregation_variable_that_is_already_bound_is_rejected():
    _assert_violation(
        "RULE { ?x :n ?y } WHERE { ?x :q ?y . GROUP BY ?x { ?x :r ?o } [ ?y := COUNT(*) ] }",
        "aggregation_variable_in_scope",
        "y",
        element="Aggregation",
    )


def test_an_aggregation_variable_bound_by_the_group_pattern_is_rejected():
    _assert_violation(
        "RULE { :a :n ?o } WHERE { GROUP { ?x :r ?o } [ ?o := COUNT(*) ] }",
        "aggregation_variable_in_scope",
        "o",
        element="Aggregation",
    )


def test_an_aggregation_variable_repeated_in_a_group_is_rejected_at_the_second_one():
    _assert_violation(
        "RULE { :a :n ?n } WHERE { GROUP { ?x :r ?o } [ ?n := COUNT(*) , ?n := SUM(?o) ] }",
        "duplicate_aggregation_variable",
        "n",
        element="Aggregation",
    )


def test_an_aggregation_argument_the_group_does_not_bind_is_rejected():
    _assert_violation(
        "RULE { :a :n ?n } WHERE { GROUP { ?x :r ?o } [ ?n := SUM(?z) ] }",
        "unbound_aggregation_argument",
        "z",
        element="Aggregation",
    )


def test_a_variable_in_a_data_block_is_rejected():
    _assert_violation("DATA { ?x :p :o . }", "variable_in_data", "x")


@pytest.mark.parametrize("position", ["subject", "predicate"])
def test_a_triple_term_as_the_subject_or_predicate_of_a_triple_is_rejected(position):
    """The grammar only lets a triple term be an object, so the tree is edited: the term is moved into the position."""
    from starlayer.sparql._oxterms import NS
    from starlayer.sparql._oxterms import RDF as RDF_NS

    ruleset = parse_ruleset(PREFIX + "RULE { ?x :p ?y } WHERE { ?x :q ?y . ?x :r ?z . FILTER(?z > 1) }")
    tree, _root = ruleset_to_tree(ruleset)
    srl = NS("https://github.com/hidden-graph/starlayer/ns/sparql/srl#")
    sqe = NS("https://github.com/hidden-graph/starlayer/ns/sparql/query-edit#")
    import pyoxigraph as ox

    victim = next(s for s in tree.subjects(srl.predicate, ox.NamedNode("http://example.org/r")))
    term = ox.BlankNode()
    tree.add((term, RDF_NS.type, sqe.TripleTerm))
    for part, value in (("subject", ox.NamedNode("http://example.org/a")), ("predicate", ox.NamedNode("http://example.org/b")), ("object", ox.NamedNode("http://example.org/c"))):
        tree.add((term, sqe[part], value))
    old = next(tree.objects(victim, srl[position]))
    tree.remove((victim, srl[position], old))
    tree.add((victim, srl[position], term))
    report, rows = findings(tree)
    kind = f"triple_term_in_{position}"
    assert not report.conforms
    assert [(k, focus) for k, _v, focus in rows if k == kind] == [(kind, victim)]
    assert f"A triple term cannot be the {position} of a triple" in report.report_text


def test_a_variable_name_above_the_bmp_is_reported_for_each_element_that_holds_it():
    ruleset = parse_ruleset(PREFIX + "RULE { ?s :r ?\U00010000 } WHERE { ?s :p ?\U00010000 }")
    tree, _root = ruleset_to_tree(ruleset)
    report, rows = findings(tree)
    assert not report.conforms
    assert sorted((kind, name) for kind, name, _focus in rows) == [("unsupported_variable_name", "\U00010000")] * 2
    assert "above U+FFFF" in report.report_text


# ---- what is reported besides the §4.2 shapes -----------------------------------------------------------------------------


def test_an_unorderable_rule_set_is_reported_with_the_well_formedness_results_of_the_same_tree():
    ruleset = parse_ruleset(PREFIX + "RULE { ?x :p ?z } WHERE { ?x :q ?y . NOT { ?x :p ?y } }")
    tree, root = ruleset_to_tree(ruleset)
    report, rows = findings(tree)
    assert [kind for kind, _v, _focus in rows] == ["unbound_head_variable"]
    assert not report.conforms
    graph = report.report_graph
    from starlayer.shacl import SH

    ordering = [r for r in graph.subjects(SH.focusNode, root)]
    assert len(ordering) == 1
    assert "stratif" in next(iter(graph.objects(ordering[0], SH.resultMessage))).value.lower()


def test_unresolved_imports_are_a_warning_that_does_not_make_the_report_non_conforming():
    from starlayer.shacl import SH

    ruleset = parse_ruleset(PREFIX + "IMPORTS <http://example.org/lib>\nIMPORTS <http://example.org/other>\nRULE { ?x :p ?y } WHERE { ?x :q ?y }")
    tree, root = ruleset_to_tree(ruleset)
    report = validate_sparql_tree(tree)
    assert report.conforms, report.report_text
    graph = report.report_graph
    warnings_ = list(graph.subjects(SH.resultSeverity, SH.Warning))
    assert len(warnings_) == 2  # one per import IRI
    for result in warnings_:
        assert next(iter(graph.objects(result, SH.focusNode))) == root
        assert next(iter(graph.objects(result, SH.sourceShape))).value.endswith("#UnresolvedImportsShape")
    text = report.report_text
    assert "http://example.org/lib" in text and "http://example.org/other" in text and "covers only the rules in this document" in text


def test_a_rule_set_without_imports_has_no_warning_and_one_with_its_imports_resolved_has_none():
    from starlayer.shacl import SH

    text = PREFIX + "IMPORTS <http://example.org/lib>\nRULE { ?x :p ?y } WHERE { ?x :q ?y }"
    lib = PREFIX + "RULE { ?x :q ?y } WHERE { ?x :r ?y }"
    resolved = parse_ruleset(text, imports_loader=lambda iri: lib)
    for rules in (resolved, parse_ruleset(PREFIX + "RULE { ?x :p ?y } WHERE { ?x :q ?y }")):
        report = validate_sparql_tree(ruleset_to_tree(rules)[0])
        assert report.conforms and not list(report.report_graph.subjects(SH.resultSeverity, SH.Warning))
