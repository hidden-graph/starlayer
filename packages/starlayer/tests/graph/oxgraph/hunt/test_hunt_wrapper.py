"""Bug hunt on the Oxigraph wrapper (OxGraph / OxDataset). Each test is a minimal reproducer of a confirmed bug and is
``xfail(strict=True)``: when the bug is fixed the test starts to pass and strict mode flags it, so remove the marker then."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph.oxgraph import OxDataset, OxGraph

N = ox.NamedNode
EX = "http://ex/"
A, P, B, C = (N(EX + x) for x in "apbc")
G1, G2 = N(EX + "g1"), N(EX + "g2")
OTHER = "http://other/"


def _ds_with_g1():
    ds = OxDataset()
    ds.graph(G1).add((A, P, B))
    return ds


@pytest.mark.xfail(strict=True, reason="BUG: (s, p, o, g) in view tests graph g, not the view's graph: a triple of another graph is 'contained'")
def test_contains_quad_of_another_graph_on_a_view():
    ds = _ds_with_g1()
    view = ds.graph(G2)
    assert (A, P, B) not in view
    assert (A, P, B, G1) not in view  # True today; quads() on the same view returns nothing for graph G1


@pytest.mark.xfail(strict=True, reason="BUG: view.remove((s, p, o, g)) deletes from graph g although the view is another graph (data loss)")
def test_remove_with_graph_element_does_not_leave_the_view():
    ds = _ds_with_g1()
    ds.graph(G2).remove((A, P, B, G1))
    assert len(ds.graph(G1)) == 1


@pytest.mark.xfail(strict=True, reason="BUG: view.add(Quad in another graph) writes outside the view")
def test_view_add_of_foreign_quad_stays_in_view_or_raises():
    ds = _ds_with_g1()
    ds.graph(G1).clear()
    view = ds.graph(G2)
    try:
        view.add(ox.Quad(A, P, B, G1))
    except (ValueError, TypeError):
        return
    assert len(ds.graph(G1)) == 0


@pytest.mark.xfail(strict=True, reason="BUG: serialize(only_used=True) drops '@prefix :' when the empty prefix is used only as a datatype (^^:dt): output is not parseable")
def test_only_used_keeps_empty_prefix_used_by_datatype():
    g = OxGraph()
    g.bind("", EX)
    g.bind("o", OTHER)
    g.add((N(OTHER + "a"), N(OTHER + "p"), ox.Literal("x", datatype=N(EX + "dt"))))
    text = g.serialize(format="turtle", only_used=True)
    back = OxGraph()
    back.parse(data=text, format="turtle")  # SyntaxError: prefix ':' undeclared
    assert len(back) == 1


@pytest.mark.xfail(strict=True, reason="BUG: used_prefixes() omits the empty prefix when it is used only as a datatype")
def test_used_prefixes_includes_empty_prefix_used_by_datatype():
    g = OxGraph()
    g.bind("", EX)
    g.add((N(OTHER + "a"), N(OTHER + "p"), ox.Literal("x", datatype=N(EX + "dt"))))
    assert ("", EX) in g.used_prefixes()


@pytest.mark.xfail(strict=True, reason="BUG: initBindings with a blank node for a variable that is not projected raises SyntaxError (VALUES fallback); old class answers")
def test_init_bindings_blank_node_unprojected_variable():
    g = OxGraph()
    bn = ox.BlankNode("q")
    g.add((A, P, bn))
    rows = g.query("SELECT ?s WHERE { ?s <http://ex/p> ?x }", initBindings={"x": bn}).bindings
    assert rows == [{"s": A}]


@pytest.mark.xfail(strict=True, reason="BUG: initBindings with a triple term for a variable that is not projected raises SyntaxError (VALUES fallback)")
def test_init_bindings_triple_term_unprojected_variable():
    g = OxGraph()
    tt = ox.Triple(A, P, B)
    g.add((A, N(EX + "t"), tt))
    rows = g.query("SELECT ?s WHERE { ?s <http://ex/t> ?x }", initBindings={"x": tt}).bindings
    assert rows == [{"s": A}]


@pytest.mark.xfail(strict=True, reason="BUG: Result.type of a CONSTRUCT is 'DESCRIBE' when a prefix is named 'describe' (keyword regex runs on the prologue)")
def test_result_type_construct_with_prefix_named_describe():
    g = OxGraph()
    g.add((A, P, B))
    r = g.query("PREFIX describe: <http://ex/> CONSTRUCT { ?s describe:z ?x } WHERE { ?s describe:p ?x }")
    assert r.type == "CONSTRUCT"


@pytest.mark.xfail(strict=True, reason="BUG: value(subject) defaults predicate to rdf:type; rdflib and the old class default to rdf:value (the docstring says 'as in rdflib')")
def test_value_default_predicate_is_rdf_value():
    rdf = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    g = OxGraph()
    g.add((A, N(rdf + "type"), N(EX + "T")))
    g.add((A, N(rdf + "value"), B))
    assert g.value(A) == B


@pytest.mark.xfail(strict=True, reason="BUG: qname() raises ValueError for a non-ASCII local name (valid in Turtle PN_LOCAL; rdflib abbreviates it)")
def test_qname_non_ascii_local_name():
    g = OxGraph()
    g.bind("e", EX)
    assert g.qname(N(EX + "\u00e9")) == "e:\u00e9"


@pytest.mark.xfail(strict=True, reason="BUG: bind() accepts a non-absolute namespace; every later query()/update()/serialize() then raises ValueError")
def test_bind_relative_namespace_does_not_poison_the_graph():
    g = OxGraph()
    g.add((A, P, B))
    try:
        g.bind("x", "relative/ns")
    except ValueError:
        return
    assert len(g.query("SELECT * { ?s ?p ?o }").bindings) == 1


@pytest.mark.xfail(strict=True, reason="BUG: bind() of an invalid prefix name ('bad prefix') makes serialize() write unparseable Turtle (old class raises on spaces)")
def test_bind_invalid_prefix_name_still_serializes_parseable_turtle():
    g = OxGraph()
    g.add((A, P, B))
    try:
        g.bind("bad prefix", EX)
    except (ValueError, KeyError):
        return
    back = OxGraph()
    back.parse(data=g.serialize(format="turtle"), format="turtle")
    assert len(back) == 1


@pytest.mark.xfail(strict=True, reason="BUG: update() WHERE ignores default_union=True: query() sees the union of graphs, INSERT/DELETE WHERE does not (old class sees it)")
def test_update_where_sees_union_like_query():
    ds = OxDataset(default_union=True)
    ds.graph(G1).add((A, P, B))
    assert len(ds.query("SELECT * { ?s <http://ex/p> ?o }").bindings) == 1  # query: union
    ds.update("INSERT { GRAPH <http://ex/out> { ?s <http://ex/z> ?o } } WHERE { ?s <http://ex/p> ?o }")
    assert len(ds.graph(N(EX + "out"))) == 1


@pytest.mark.xfail(strict=True, reason="BUG: OxDataset.copy() drops empty named graphs (copy.copy of the old StarLayerDataset keeps them)")
def test_dataset_copy_keeps_empty_named_graph():
    ds = OxDataset()
    ds.graph(G1)
    assert ds.has_graph(G1)
    assert ds.copy().has_graph(G1)


@pytest.mark.xfail(strict=True, reason="BUG: parse(data=<non-str/bytes>) raises AttributeError ('int' has no attribute 'read') instead of TypeError")
def test_parse_data_wrong_type_is_a_type_error():
    with pytest.raises(TypeError):
        OxGraph().parse(data=5, format="nt")
