"""An explicit GROUP BY over no solutions gives no rows; an implicit group still gives its one row."""

from rdflib import Literal
from starlayer.graph import StarLayerGraph


def test_explicit_group_by_over_nothing_gives_no_rows():
    graph = StarLayerGraph()
    query = "SELECT ?n (COUNT(?n) AS ?c) { ?s <http://x/p> ?n FILTER(false) } GROUP BY ?n"
    assert list(graph.query(query)) == []


def test_implicit_group_over_nothing_still_gives_one_row():
    graph = StarLayerGraph()
    rows = list(graph.query("SELECT (COUNT(?n) AS ?c) { ?s <http://x/p> ?n FILTER(false) }"))
    assert len(rows) == 1 and rows[0][0] == Literal(0)
