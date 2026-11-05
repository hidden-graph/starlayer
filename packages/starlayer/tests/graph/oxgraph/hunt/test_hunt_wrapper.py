"""Bug hunt on the Oxigraph wrapper (StarLayerGraph / StarLayerDataset): minimal reproducers of confirmed bugs, kept as regression tests."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph.oxgraph import StarLayerDataset, StarLayerGraph

N = ox.NamedNode
EX = "http://ex/"
A, P, B, C = (N(EX + x) for x in "apbc")
G1, G2 = N(EX + "g1"), N(EX + "g2")
OTHER = "http://other/"


def _ds_with_g1():
    ds = StarLayerDataset()
    ds.graph(G1).add((A, P, B))
    return ds


def test_contains_quad_of_another_graph_on_a_view():
    ds = _ds_with_g1()
    view = ds.graph(G2)
    assert (A, P, B) not in view
    assert (A, P, B, G1) not in view  # True today; quads() on the same view returns nothing for graph G1


def test_remove_with_graph_element_does_not_leave_the_view():
    ds = _ds_with_g1()
    ds.graph(G2).remove((A, P, B, G1))
    assert len(ds.graph(G1)) == 1


def test_view_add_of_foreign_quad_stays_in_view_or_raises():
    ds = _ds_with_g1()
    ds.graph(G1).clear()
    view = ds.graph(G2)
    try:
        view.add(ox.Quad(A, P, B, G1))
    except (ValueError, TypeError):
        return
    assert len(ds.graph(G1)) == 0


def test_only_used_keeps_empty_prefix_used_by_datatype():
    g = StarLayerGraph()
    g.bind("", EX)
    g.bind("o", OTHER)
    g.add((N(OTHER + "a"), N(OTHER + "p"), ox.Literal("x", datatype=N(EX + "dt"))))
    text = g.serialize(format="turtle", only_used=True)
    back = StarLayerGraph()
    back.parse(data=text, format="turtle")  # SyntaxError: prefix ':' undeclared
    assert len(back) == 1


def test_used_prefixes_includes_empty_prefix_used_by_datatype():
    g = StarLayerGraph()
    g.bind("", EX)
    g.add((N(OTHER + "a"), N(OTHER + "p"), ox.Literal("x", datatype=N(EX + "dt"))))
    assert ("", EX) in g.used_prefixes()


def test_init_bindings_blank_node_unprojected_variable():
    g = StarLayerGraph()
    bn = ox.BlankNode("q")
    g.add((A, P, bn))
    rows = g.query("SELECT ?s WHERE { ?s <http://ex/p> ?x }", initBindings={"x": bn}).bindings
    assert rows == [{"s": A}]


def test_init_bindings_triple_term_unprojected_variable():
    g = StarLayerGraph()
    tt = ox.Triple(A, P, B)
    g.add((A, N(EX + "t"), tt))
    rows = g.query("SELECT ?s WHERE { ?s <http://ex/t> ?x }", initBindings={"x": tt}).bindings
    assert rows == [{"s": A}]


def test_result_type_construct_with_prefix_named_describe():
    g = StarLayerGraph()
    g.add((A, P, B))
    r = g.query("PREFIX describe: <http://ex/> CONSTRUCT { ?s describe:z ?x } WHERE { ?s describe:p ?x }")
    assert r.type == "CONSTRUCT"


def test_value_default_predicate_is_rdf_value():
    rdf = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    g = StarLayerGraph()
    g.add((A, N(rdf + "type"), N(EX + "T")))
    g.add((A, N(rdf + "value"), B))
    assert g.value(A) == B


def test_qname_non_ascii_local_name():
    g = StarLayerGraph()
    g.bind("e", EX)
    assert g.qname(N(EX + "\u00e9")) == "e:\u00e9"


def test_bind_relative_namespace_does_not_poison_the_graph():
    g = StarLayerGraph()
    g.add((A, P, B))
    try:
        g.bind("x", "relative/ns")
    except ValueError:
        return
    assert len(g.query("SELECT * { ?s ?p ?o }").bindings) == 1


def test_bind_invalid_prefix_name_still_serializes_parseable_turtle():
    g = StarLayerGraph()
    g.add((A, P, B))
    try:
        g.bind("bad prefix", EX)
    except (ValueError, KeyError):
        return
    back = StarLayerGraph()
    back.parse(data=g.serialize(format="turtle"), format="turtle")
    assert len(back) == 1


def test_update_where_sees_union_like_query():
    ds = StarLayerDataset(default_union=True)
    ds.graph(G1).add((A, P, B))
    assert len(ds.query("SELECT * { ?s <http://ex/p> ?o }").bindings) == 1  # query: union
    ds.update("INSERT { GRAPH <http://ex/out> { ?s <http://ex/z> ?o } } WHERE { ?s <http://ex/p> ?o }")
    assert len(ds.graph(N(EX + "out"))) == 1


def test_dataset_copy_keeps_empty_named_graph():
    ds = StarLayerDataset()
    ds.graph(G1)
    assert ds.has_graph(G1)
    assert ds.copy().has_graph(G1)


def test_parse_data_wrong_type_is_a_type_error():
    with pytest.raises(TypeError):
        StarLayerGraph().parse(data=5, format="nt")
