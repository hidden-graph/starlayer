"""Reading a report: ``ReportResult``, ``ValidationReport.results`` and friends, ``report_results()``, ``diff_reports()``."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl import (
    MetaShaclError,
    ReportDiff,
    ReportResult,
    diff_reports,
    meta_validate,
    report_results,
    validate,
)
from starlayer.shacl.engine.terms import to_engine
from tests.support.terms import RDF, Namespace, lit

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")
PRE = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> . "
)


def graph(turtle: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PRE + turtle, format="turtle12")
    return g


SHAPES = """
ex:S a sh:NodeShape ; sh:targetClass ex:C ;
  sh:closed true ; sh:ignoredProperties ( rdf:type ) ;
  sh:property [ sh:path ex:age ; sh:datatype xsd:integer ; sh:minCount 1 ] ;
  sh:property [ sh:path ex:nick ; sh:severity sh:Warning ; sh:maxLength 3 ] ;
  sh:property [ sh:path ex:note ; sh:severity sh:Info ; sh:maxLength 2 ] .
"""
DATA = 'ex:a a ex:C ; ex:age "x" ; ex:nick "Alexander" . ex:b a ex:C ; ex:note "long" ; ex:extra 1 .'


def run(data: str = DATA, shapes: str | StarLayerGraph = SHAPES):
    """Validate; pass one parsed shapes graph to compare two runs (a blank property shape has a new label in every parse)."""
    if isinstance(shapes, str):
        shapes = graph("@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . " + shapes)
    return validate(graph(data), shacl_graph=shapes)


def test_each_kind_of_result_is_read_into_its_fields():
    report = run()
    by = {(r.focus, r.path, r.component): r for r in report.results}
    age = by[(to_engine(EX.a), to_engine(EX.age), to_engine(SH.DatatypeConstraintComponent))]
    assert age.has_value and age.value == to_engine(lit("x")) and age.severity_name == "Violation"
    assert age.source_constraint is None and age.details == () and age.messages
    nick = by[(to_engine(EX.a), to_engine(EX.nick), to_engine(SH.MaxLengthConstraintComponent))]
    assert nick.severity_name == "Warning"
    note = by[(to_engine(EX.b), to_engine(EX.note), to_engine(SH.MaxLengthConstraintComponent))]
    assert note.severity_name == "Info"
    missing = by[(to_engine(EX.b), to_engine(EX.age), to_engine(SH.MinCountConstraintComponent))]
    assert missing.has_value is False and missing.value is None
    closed = by[(to_engine(EX.b), to_engine(EX.extra), to_engine(SH.ClosedConstraintComponent))]
    assert closed.path == to_engine(EX.extra)
    assert all(isinstance(r, ReportResult) for r in report.results)


def test_a_node_level_result_has_no_path():
    report = run(shapes="ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:nodeKind sh:Literal .", data="ex:a a ex:C .")
    (result,) = report.results
    assert result.path is None and report.node_level(EX.a) == (result,) and report.for_field(EX.a, EX.age) == ()


def test_results_are_sorted_most_severe_first_and_stable_across_calls_and_reparse():
    report = run()
    assert [r.severity_name for r in report.results] == sorted(
        (r.severity_name for r in report.results), key=["Violation", "Warning", "Info"].index
    )
    first = [(r.focus, r.path, r.component) for r in report.results]
    assert first == [(r.focus, r.path, r.component) for r in report_results(report.report_graph)]
    reparsed = StarLayerGraph()
    reparsed.parse(data=report.report_graph.serialize(format="turtle12"), format="turtle12")
    # blank labels change in a re-parse; focus, path and component are named terms here
    assert first == [(r.focus, r.path, r.component) for r in report_results(reparsed)]


def test_for_node_for_field_node_level_and_counts():
    report = run()
    assert {r.focus for r in report.for_node(EX.a)} == {to_engine(EX.a)}
    assert len(report.for_node(EX.a)) == 2
    (age,) = report.for_field(EX.a, EX.age)
    assert age.component == to_engine(SH.DatatypeConstraintComponent)
    assert report.for_field(EX.a, EX.nick)[0].severity_name == "Warning"
    assert report.node_level(EX.b) == ()
    counts = report.counts()
    assert list(counts) == ["Violation", "Warning", "Info", "total"]
    assert counts["total"] == len(report.results) == sum(v for k, v in counts.items() if k != "total")


def test_node_level_results_are_only_those_without_a_path():
    report = run(shapes=SHAPES + " ex:S sh:nodeKind sh:Literal .", data="ex:a a ex:C ; ex:age 1 .")
    assert [r.component for r in report.node_level(EX.a)] == [to_engine(SH.NodeKindConstraintComponent)]
    assert len(report.for_node(EX.a)) >= 1 and all(r.path is None for r in report.node_level(EX.a))


def test_a_nested_result_is_a_detail_and_not_a_top_level_result():
    shapes = """ex:P sh:path ex:age ; sh:datatype xsd:integer .
      ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:node ex:A . ex:A sh:node ex:B . ex:B sh:property ex:P ."""
    report = run('ex:a a ex:C ; ex:age "x" .', shapes)
    (top,) = report.results
    assert top.component == to_engine(SH.NodeConstraintComponent)
    (middle,) = top.details
    assert middle.component == to_engine(SH.NodeConstraintComponent)
    (deepest,) = middle.details
    assert deepest.component == to_engine(SH.DatatypeConstraintComponent) and deepest.path == to_engine(EX.age)
    assert deepest.node not in {r.node for r in report.results}
    assert report.counts() == {"Violation": 1, "total": 1}


def test_member_shape_details_are_one_per_bad_member():
    shapes = "ex:I sh:nodeKind sh:IRI . ex:S a sh:NodeShape ; sh:targetNode ex:l ; sh:property [ sh:path ex:p ; sh:memberShape ex:I ] ."
    (top,) = run('ex:l ex:p ( ex:a "x" "y" ) .', shapes).results
    assert sorted(d.value.value for d in top.details) == ["x", "y"]


def test_deduplicated_collapses_a_property_shape_reached_by_two_targeting_shapes():
    shapes = """ex:P sh:path ex:age ; sh:datatype xsd:integer .
      ex:S1 a sh:NodeShape ; sh:targetClass ex:C ; sh:property ex:P .
      ex:S2 a sh:NodeShape ; sh:targetClass ex:C ; sh:property ex:P ."""
    report = run('ex:a a ex:C ; ex:age "x" .', shapes)
    assert len(report.results) == 2  # the engine reports it once for each targeting shape
    assert len(report.deduplicated()) == 1 and report.deduplicated()[0] == report.results[0]
    assert report.counts()["total"] == 2


def test_deduplicated_keeps_results_that_differ_and_collapses_a_copied_result():
    report = run()
    assert report.deduplicated() == report.results
    g = report.report_graph
    original = report.results[0].node
    import pyoxigraph as ox

    clone = ox.BlankNode()
    for _s, p, o in list(g.triples((original, None, None))):
        g.add((clone, p, o))
    for rep in list(g.subjects(RDF.type, SH.ValidationReport)):
        g.add((rep, to_engine(SH.result), clone))
    again = report_results(g)
    assert len(again) == len(report.results) + 1
    from starlayer.shacl.report_results import deduplicate

    assert len(deduplicate(again)) == len(report.results)


def test_a_different_message_is_not_the_same_mistake_for_deduplicated():
    g = graph("")
    a, b = to_engine(EX.r1), to_engine(EX.r2)
    for node, msg in ((a, "one"), (b, "two")):
        g.add((to_engine(EX.rep), to_engine(RDF.type), to_engine(SH.ValidationReport)))
        g.add((to_engine(EX.rep), to_engine(SH.result), node))
        for p, o in (
            (RDF.type, SH.ValidationResult), (SH.focusNode, EX.a), (SH.sourceShape, EX.S),
            (SH.sourceConstraintComponent, SH.MinCountConstraintComponent), (SH.resultMessage, lit(msg)),
        ):
            g.add((node, to_engine(p), to_engine(o)))
    from starlayer.shacl.report_results import deduplicate

    results = report_results(g)
    assert len(results) == 2 and len(deduplicate(results)) == 2
    assert all(r.severity == to_engine(SH.Violation) for r in results)  # no sh:resultSeverity: a violation


def test_diff_reports_after_fixing_one_value():
    shapes = graph("ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:age ; sh:datatype xsd:integer ] .")
    old = run('ex:a a ex:C ; ex:age "x" . ex:b a ex:C ; ex:age "y" .', shapes)
    new = run('ex:a a ex:C ; ex:age 3 . ex:b a ex:C ; ex:age "y" . ex:c a ex:C ; ex:age "z" .', shapes)
    diff = diff_reports(old, new)
    assert isinstance(diff, ReportDiff)
    assert [r.focus for r in diff.fixed] == [to_engine(EX.a)]
    assert [r.focus for r in diff.unchanged] == [to_engine(EX.b)]
    assert [r.focus for r in diff.added] == [to_engine(EX.c)]
    assert diff.unchanged[0].node in {r.node for r in new.results}  # taken from the new report
    assert diff_reports(old.report_graph, new.report_graph) == diff


def test_diff_reports_counts_a_repeated_result_once():
    shapes = """ex:P sh:path ex:age ; sh:datatype xsd:integer .
      ex:S1 a sh:NodeShape ; sh:targetClass ex:C ; sh:property ex:P .
      ex:S2 a sh:NodeShape ; sh:targetClass ex:C ; sh:property ex:P ."""
    report = run('ex:a a ex:C ; ex:age "x" .', shapes)
    assert len(diff_reports(run("ex:a a ex:C .", shapes), report).added) == 1


def test_report_results_of_a_meta_shacl_error_and_of_meta_validate_with_two_datatypes():
    shapes = graph('ex:S sh:select "not sparql" . ex:T sh:path ex:p ; sh:datatype xsd:integer, xsd:string .')
    with pytest.raises(MetaShaclError) as raised:
        meta_validate(shapes)
    results = report_results(raised.value.report_graph)
    assert results and (to_engine(EX.S), to_engine(SH.select)) in [(r.focus, r.path) for r in results]
    assert any(r.focus == to_engine(EX.T) for r in results)
    assert all(isinstance(r, ReportResult) for r in results)


def test_a_user_defined_severity_shows_its_iri_and_sorts_last():
    shapes = "ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:age ; sh:severity ex:Loud ; sh:minCount 1 ]"
    shapes += " ; sh:property [ sh:path ex:n ; sh:minCount 1 ] ."
    report = run("ex:a a ex:C .", shapes)
    assert [r.severity_name for r in report.results] == ["Violation", "http://example.org/Loud"]
    assert list(report.counts()) == ["Violation", "http://example.org/Loud", "total"]


def test_an_rdflib_graph_is_refused():
    rdflib = pytest.importorskip("rdflib")
    with pytest.raises(TypeError, match="from_rdflib"):
        report_results(rdflib.Graph())


def test_reading_a_report_changes_nothing():
    report = run()
    before = len(report.report_graph)
    report.results, report.for_node(EX.a), report.counts(), report.deduplicated(), diff_reports(report, report)
    report_results(report.report_graph)
    assert len(report.report_graph) == before
