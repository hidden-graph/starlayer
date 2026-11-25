"""``sqe_validate`` also checks that Oxigraph accepts each query of a tree that conforms to the shapes."""

from starlayer.shacl.engine.terms import SH
from starlayer.sparql.check import check_query
from starlayer.sparql.sqe import sqe_parse_to_tree, sqe_validate

GOOD = "SELECT ?x WHERE { ?x <urn:p> ?y }"
REJECTED = "SELECT ?x WHERE { ?x <urn:p> ?y } ORDER BY <urn:nope>(?y)"  # in the grammar and the shapes; Oxigraph has no function <urn:nope>
SERVICE = "SELECT ?x WHERE { SERVICE <http://127.0.0.1:1/sparql> { ?x <urn:p> ?y } }"


def _messages(report):
    return [m.value for m in report.report_graph.objects(None, SH.resultMessage)]


def test_a_good_tree_still_conforms():
    tree, _ = sqe_parse_to_tree(GOOD)
    report = sqe_validate(tree)
    assert report.conforms and "Conforms: True" in report.report_text


def test_a_tree_that_conforms_to_the_shapes_but_oxigraph_rejects_does_not_conform():
    from starlayer.sparql.sqe.shapes import _validate_shapes

    tree, root = sqe_parse_to_tree(REJECTED)
    assert _validate_shapes(tree).conforms
    report = sqe_validate(tree)
    assert not report.conforms
    (result,) = report.results
    assert result.focus == root and str(result.severity) == str(SH.Violation)
    (message,) = _messages(report)
    assert "Oxigraph rejects" in message and "urn:nope" in message
    assert "Conforms: False" in report.report_text and "urn:nope" in report.report_text
    assert check_query(REJECTED).errors[0].message in message


def test_two_queries_in_one_graph_only_the_rejected_one_is_reported():
    tree, first = sqe_parse_to_tree(GOOD)
    _, second = sqe_parse_to_tree(REJECTED, tree_graph=tree)
    report = sqe_validate(tree)
    assert not report.conforms
    assert [r.focus for r in report.results] == [second] and first != second


def test_a_query_with_service_is_not_run():
    tree, _ = sqe_parse_to_tree(SERVICE)
    assert sqe_validate(tree).conforms


def test_a_broken_tree_is_reported_by_the_shapes_only():
    from starlayer.sparql.parse_sparql import sparql_to_tree

    tree, _ = sparql_to_tree("SELECT ?x WHERE { ?a <urn:p> ?y }")
    report = sqe_validate(tree)
    assert not report.conforms and all("Oxigraph" not in m for m in _messages(report))


def test_check_query_reports_the_engine_once():
    check = check_query(REJECTED)
    assert [p.kind for p in check.problems].count("engine") == 1
