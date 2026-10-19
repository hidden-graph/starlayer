"""sqe coverage set: solution modifiers, SELECT *, CONSTRUCT WHERE.

Opt-in (``pytest --sqe-coverage``): each query is parsed to an sqe tree,
decoded and run, and the rows are compared with plain rdflib on the same
data. Unsupported constructs must raise, never be silently dropped.
"""

import pytest
from rdflib import Literal, Namespace
from starlayer.graph import StarLayerGraph
from starlayer.sparql.sqe import (
    sqe_parse_to_tree,
    sqe_tree_to_query,
    sqe_tree_to_text,
    sqe_validate,
)
from tests.sparql.sqe_coverage.test_w3c_through_sqe import assert_no_salg_terms

pytestmark = pytest.mark.sqe_coverage

EX = Namespace("http://x/")
P = "PREFIX ex: <http://x/>\n"


@pytest.fixture(scope="module")
def data():
    g = StarLayerGraph()
    for i in range(12):
        g.add((EX[f"s{i}"], EX.p, Literal(i)))
        g.add((EX[f"s{i}"], EX.q, Literal(f"name{i % 4}")))
    return g


def _rows(graph, query):
    res = graph.query(query)
    if res.type == "CONSTRUCT":
        return sorted(res.graph)
    if res.type == "ASK":
        return res.askAnswer
    return [tuple(r) for r in res]


QUERIES = {
    "distinct": P + "SELECT DISTINCT ?q WHERE { ?s ex:q ?q } ORDER BY ?q",
    "reduced": P + "SELECT REDUCED ?q WHERE { ?s ex:q ?q } ORDER BY ?q",
    "order desc": P + "SELECT ?s WHERE { ?s ex:p ?n } ORDER BY DESC(?n)",
    "order asc explicit": P + "SELECT ?s WHERE { ?s ex:p ?n } ORDER BY ASC(?n)",
    "order expression": P + "SELECT ?s WHERE { ?s ex:p ?n } ORDER BY DESC(?n + 1) ?s",
    "limit": P + "SELECT ?s WHERE { ?s ex:p ?n } ORDER BY ?n LIMIT 3",
    "offset": P + "SELECT ?s WHERE { ?s ex:p ?n } ORDER BY ?n OFFSET 9",
    "limit offset": P + "SELECT ?s WHERE { ?s ex:p ?n } ORDER BY ?n LIMIT 3 OFFSET 4",
    "all together": P + "SELECT DISTINCT ?q WHERE { ?s ex:q ?q } ORDER BY DESC(?q) LIMIT 2 OFFSET 1",
    "select star": P + "SELECT * WHERE { ?s ex:p ?n } ORDER BY ?n LIMIT 2",
    "construct where": P + "CONSTRUCT WHERE { ?s ex:p ?n }",
    "construct limit": P + "CONSTRUCT { ?s ex:r ?n } WHERE { ?s ex:p ?n } ORDER BY ?n LIMIT 2",
}


@pytest.mark.parametrize("name", QUERIES)
def test_modifier_query_matches_rdflib(name, data):
    text = QUERIES[name]
    graph, root = sqe_parse_to_tree(text)
    assert sqe_validate(graph)[0]
    assert_no_salg_terms(graph)
    expected = _rows(data, text)

    decoded = _rows(data, sqe_tree_to_query(graph, root))
    assert decoded == expected

    regenerated = sqe_tree_to_text(graph, root)
    graph2, root2 = sqe_parse_to_tree(regenerated)
    assert _rows(data, sqe_tree_to_query(graph2, root2)) == expected


def test_select_star_and_projection_are_exclusive():
    graph, root = sqe_parse_to_tree(P + "SELECT * WHERE { ?s ex:p ?n }")
    from starlayer.sparql.sqe.vocab import PROJECTION

    graph.add((root, PROJECTION, Literal("x")))
    assert not sqe_validate(graph)[0]


def test_distinct_and_reduced_are_exclusive():
    graph, root = sqe_parse_to_tree(P + "SELECT DISTINCT ?s WHERE { ?s ex:p ?n }")
    from starlayer.sparql.sqe.vocab import REDUCED

    graph.add((root, REDUCED, Literal(True)))
    assert not sqe_validate(graph)[0]


def test_negative_limit_is_rejected():
    graph, root = sqe_parse_to_tree(P + "SELECT ?s WHERE { ?s ex:p ?n } LIMIT 3")
    from starlayer.sparql.sqe.vocab import LIMIT

    graph.set((root, LIMIT, Literal(-1)))
    assert not sqe_validate(graph)[0]
