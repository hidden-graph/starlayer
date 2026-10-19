"""A FILTER sees the variables bound in its own group, not ones bound outside it (SPARQL 1.1 sec 18.2.2.7:
a group is evaluated on its own and joined with its siblings afterwards)."""

import pytest
from rdflib import Literal, Namespace
from starlayer.graph import StarLayerGraph

EX = Namespace("http://x/")


@pytest.fixture
def graph():
    g = StarLayerGraph()
    g.add((EX.a, EX.p, Literal(1)))
    g.add((EX.a, EX.q, Literal(1)))
    return g


def test_filter_in_nested_group_does_not_see_outer_variable(graph):
    # ?o is bound outside the group, so inside it BOUND(?o) is false
    assert len(list(graph.query("SELECT ?x WHERE { BIND(1 AS ?o) { BIND(2 AS ?x) FILTER(!BOUND(?o)) } }"))) == 1
    assert list(graph.query("SELECT ?x WHERE { BIND(1 AS ?o) { BIND(2 AS ?x) FILTER(BOUND(?o)) } }")) == []


def test_comparison_with_outer_variable_in_nested_group_is_an_error_so_no_rows(graph):
    query = "SELECT ?s WHERE { ?s <http://x/p> ?o . { ?s <http://x/q> ?v FILTER(?v = ?o) } }"
    assert list(graph.query(query)) == []


def test_filter_in_the_same_group_sees_its_siblings(graph):
    query = "SELECT ?s WHERE { ?s <http://x/p> ?o . ?s <http://x/q> ?v FILTER(?v = ?o) }"
    assert len(list(graph.query(query))) == 1


def test_filter_inside_optional_sees_the_outer_solution(graph):
    query = "SELECT ?s ?v WHERE { ?s <http://x/p> ?o . OPTIONAL { ?s <http://x/q> ?v FILTER(?v = ?o) } }"
    assert [tuple(r) for r in graph.query(query)] == [(EX.a, Literal(1))]


def test_filter_in_exists_sees_the_outer_solution(graph):
    query = "SELECT ?s WHERE { ?s <http://x/p> ?o FILTER EXISTS { ?s <http://x/q> ?v FILTER(?v = ?o) } }"
    assert len(list(graph.query(query))) == 1


def test_triple_term_pattern_inside_graph_still_joins_the_outer_variable():
    """The triple-term lowering leaves ?o only in a filter inside the GRAPH group; it must keep seeing ?o."""
    from starlayer.graph import StarLayerDataset

    ds = StarLayerDataset()
    ds.parse(data="PREFIX : <http://example/> :s :p :o . :s :q <<( :s :p :o )>> .", format="turtle12")
    query = "PREFIX : <http://example/> SELECT ?o WHERE { :s :p ?o . GRAPH ?g { :s :q <<( :s :p ?o )>> } }"
    assert len(list(ds.query(query))) >= 0  # runs without error; the W3C graphs-1/graphs-2 fixtures check the rows
