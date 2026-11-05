"""Edge cases around the fixes for the bug hunts (the minimal reproducers are in ``hunt/``)."""

from __future__ import annotations

import random

import pyoxigraph as ox
import pytest
from starlayer.graph import interop
from starlayer.graph.oxgraph import StarLayerDataset, StarLayerGraph
from starlayer.graph.oxgraph.pretty import pretty_trig

N = ox.NamedNode
EX = "http://ex/"
A, P, B, C = (N(EX + x) for x in "apbc")
G1, G2 = N(EX + "g1"), N(EX + "g2")
D = ox.DefaultGraph()


# ---- graph views never reach outside themselves -----------------------------------------------------------------------
def test_view_quad_in_its_own_graph_is_contained_and_added():
    ds = StarLayerDataset()
    view = ds.graph(G1)
    view.add(ox.Quad(A, P, B, G1))
    view.add((A, P, C, G1))
    assert (A, P, B, G1) in view and ox.Quad(A, P, B, G1) in view
    assert (A, P, B, G2) not in view and ox.Quad(A, P, B, G2) not in view
    assert len(view) == 2


def test_view_add_of_foreign_quad_raises_but_addn_skips_it():
    ds = StarLayerDataset()
    view = ds.graph(G2)
    with pytest.raises(ValueError):
        view.add(ox.Quad(A, P, B, G1))
    with pytest.raises(ValueError):
        view.add((A, P, B, G1))
    view.addN([(A, P, B, G1), (A, P, C, G2)])
    assert len(ds.graph(G1)) == 0 and len(view) == 1


def test_default_graph_view_does_not_remove_from_named_graph():
    ds = StarLayerDataset()
    ds.graph(G1).add((A, P, B))
    ds.default_graph.remove((A, P, B, G1))
    assert len(ds.graph(G1)) == 1


# ---- only_used keeps a prefix wherever the output uses it -------------------------------------------------------------
@pytest.mark.parametrize(
    "build",
    [
        lambda g: g.add((N("http://o/a"), N("http://o/p"), ox.Literal("x", datatype=N(EX + "dt")))),
        lambda g: g.add((N("http://o/a"), N("http://o/p"), ox.Triple(N(EX + "s"), N("http://o/p"), N("http://o/c")))),
        lambda g: g.add((N("http://o/a"), N("http://o/p"), ox.Triple(N("http://o/s"), N("http://o/p"), ox.Literal("1", datatype=N(EX + "dt"))))),
    ],
    ids=["datatype", "triple-term-subject", "datatype-in-triple-term"],
)
@pytest.mark.parametrize("pretty", [False, True])
def test_only_used_output_always_reparses(build, pretty):
    g = StarLayerGraph()
    g.bind("", EX)
    g.bind("o", "http://o/")
    g.bind("unused", "http://unused/")
    build(g)
    text = g.serialize(format="turtle", only_used=True, pretty=pretty)
    assert "@prefix unused:" not in text and "@prefix : " in text
    back = StarLayerGraph()
    back.parse(data=text, format="turtle")
    assert set(back) == set(g)


def test_a_prefix_inside_a_string_or_iri_is_not_a_use():
    g = StarLayerGraph()
    g.bind("o", "http://o/")
    g.bind("z", "http://z/")
    g.add((N("http://o/a"), N("http://o/p"), ox.Literal("z:text")))
    assert [p for p, _ in g.used_prefixes()] == ["o"]


# ---- initBindings ---------------------------------------------------------------------------------------------------------
def test_init_bindings_blank_node_keeps_projected_columns_and_hides_the_added_one():
    g = StarLayerGraph()
    bn = ox.BlankNode("q")
    g.add((A, P, bn))
    g.add((B, P, ox.BlankNode("other")))
    res = g.query("SELECT DISTINCT ?s WHERE { ?s <http://ex/p> ?x }", initBindings={"x": bn})
    assert [v.value for v in res.vars] == ["s"]
    assert res.bindings == [{"s": A}]
    assert g.query("ASK { ?s <http://ex/p> ?x }", initBindings={"x": bn}).askAnswer is True


def test_init_bindings_blank_node_with_aggregate_is_refused_clearly():
    g = StarLayerGraph()
    bn = ox.BlankNode("q")
    g.add((A, P, bn))
    with pytest.raises(NotImplementedError):
        g.query("SELECT (COUNT(*) AS ?c) WHERE { ?s <http://ex/p> ?x }", initBindings={"x": bn})


def test_init_bindings_triple_term_with_a_blank_node():
    g = StarLayerGraph()
    tt = ox.Triple(A, P, ox.BlankNode("z"))
    g.add((A, N(EX + "t"), tt))
    assert g.query("SELECT ?s WHERE { ?s <http://ex/t> ?x }", initBindings={"x": tt}).bindings == [{"s": A}]


# ---- Result.type -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text, kind",
    [
        ("PREFIX describe: <http://ex/> CONSTRUCT { ?s describe:z ?x } WHERE { ?s describe:p ?x }", "CONSTRUCT"),
        ("BASE <http://ex/> PREFIX select: <http://ex/> DESCRIBE <a>", "DESCRIBE"),
        ("# DESCRIBE\nCONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }", "CONSTRUCT"),
        ("PREFIX d: <http://ex/describe> CONSTRUCT WHERE { ?s ?p 'DESCRIBE' }", "CONSTRUCT"),
    ],
)
def test_result_type_is_the_first_keyword_after_the_prologue(text, kind):
    g = StarLayerGraph()
    g.add((A, P, B))
    assert g.query(text).type == kind


# ---- qname / bind -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("local", ["é", "café", "a%41b", "x:y", "1a", "中文"])
def test_qname_follows_the_turtle_local_name_rules(local):
    g = StarLayerGraph()
    g.bind("e", EX)
    assert g.qname(N(EX + local)) == f"e:{local}"


@pytest.mark.parametrize("bad", ["a.", "-a"])
def test_qname_refuses_a_name_turtle_cannot_write(bad):
    g = StarLayerGraph()
    g.bind("e", EX)
    with pytest.raises(ValueError):
        g.qname(N(EX + bad))


@pytest.mark.parametrize("prefix", ["", "a", "a.b", "éx"])
def test_bind_accepts_valid_prefixes(prefix):
    g = StarLayerGraph()
    g.bind(prefix, EX)
    assert g.prefixes[prefix] == EX


@pytest.mark.parametrize("prefix", ["1x", "a b", "a:", None, 5, "-x", "a."])
def test_bind_rejects_invalid_prefixes(prefix):
    with pytest.raises(ValueError):
        StarLayerGraph().bind(prefix, EX)


@pytest.mark.parametrize("ns", ["", None, "relative/ns", "//host/x", "has space:x", "http://a b/", 5])
def test_bind_rejects_non_iri_namespaces(ns):
    g = StarLayerGraph()
    with pytest.raises(ValueError):
        g.bind("x", ns)
    assert "x" not in g.prefixes


def test_bind_accepts_a_named_node_and_honours_override():
    g = StarLayerGraph()
    g.bind("x", N(EX))
    g.bind("x", "http://other/", override=False)
    assert g.prefixes["x"] == EX


# ---- update() with default_union ---------------------------------------------------------------------------------------------
def test_update_union_sees_the_default_graph_and_named_graphs_and_leaves_no_scratch_graph():
    ds = StarLayerDataset(default_union=True)
    ds.default_graph.add((A, P, B))
    ds.graph(G1).add((B, P, C))
    ds.update("INSERT { GRAPH <http://ex/out> { ?s <http://ex/z> ?o } } WHERE { ?s <http://ex/p> ?o }")
    assert set(ds.graph(N(EX + "out"))) == {(A, N(EX + "z"), B), (B, N(EX + "z"), C)}
    assert {g.value for g in ds.graph_names()} == {EX + "g1", EX + "out"}


def test_update_union_delete_where_and_graph_patterns_and_several_operations():
    ds = StarLayerDataset(default_union=True)
    ds.graph(G1).add((A, P, B))
    ds.graph(G2).add((A, N(EX + "q"), C))
    ds.update(
        "PREFIX e: <http://ex/> "
        "INSERT { <http://ex/r> e:from ?g } WHERE { GRAPH ?g { ?s e:p ?o } } ; "
        "DELETE WHERE { GRAPH <http://ex/g2> { ?s e:q ?o } } ; "
        "INSERT { ?s e:both ?o2 } WHERE { ?s e:p ?o . ?s e:q ?o2 }"
    )
    assert (N(EX + "r"), N(EX + "from"), G1) in ds.default_graph
    assert len(ds.graph(G2)) == 0


def test_update_without_union_and_with_own_dataset_clauses_is_untouched():
    ds = StarLayerDataset(default_union=False)
    ds.graph(G1).add((A, P, B))
    ds.update("INSERT { <http://ex/x> <http://ex/y> ?o } WHERE { ?s <http://ex/p> ?o }")
    assert len(ds.default_graph) == 0  # the default graph is only the default graph
    du = StarLayerDataset(default_union=True)
    du.graph(G1).add((A, P, B))
    du.update("INSERT { <http://ex/x> <http://ex/y> ?o } USING <http://ex/none> WHERE { ?s <http://ex/p> ?o }")
    assert len(du.default_graph) == 0  # the author's own USING wins


def test_update_union_string_that_looks_like_a_keyword_is_not_rewritten():
    ds = StarLayerDataset(default_union=True)
    ds.graph(G1).add((A, P, ox.Literal("a; WHERE { x }")))
    ds.update('INSERT { <http://ex/x> <http://ex/y> "WHERE ; {" } WHERE { ?s <http://ex/p> ?o }')
    assert (N(EX + "x"), N(EX + "y"), ox.Literal("WHERE ; {")) in ds.default_graph


def test_copy_keeps_empty_graph_and_union_flag():
    ds = StarLayerDataset(default_union=False)
    ds.graph(G1)
    c = ds.copy()
    assert c.has_graph(G1) and c.default_union is False


@pytest.mark.parametrize("bad", [5, 1.5, ["a"], object()])
def test_parse_data_of_a_wrong_type_is_a_type_error(bad):
    with pytest.raises(TypeError):
        StarLayerGraph().parse(data=bad, format="nt")


# ---- pretty ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("rest", ["a:b", "_:x", "9:a", "a/b:c", "x%3Ay"])
def test_relative_iri_with_a_colon_before_the_first_slash_reparses(rest):
    iri = N("http://e/" + rest)
    quads = [ox.Quad(iri, N("http://e/p"), iri, D)]
    back = list(ox.parse(pretty_trig(quads, base_iri="http://e/").encode(), format=ox.RdfFormat.TRIG))
    assert set(back) == set(quads)


def test_pretty_rdf11_for_a_dataset_trig_and_with_a_direction_literal():
    ds = StarLayerDataset()
    tt = ox.Triple(A, P, B)
    ds.graph(G1).add((A, N(EX + "t"), tt))
    ds.graph(G1).add((A, N(EX + "l"), ox.Literal("x", language="en", direction=ox.BaseDirection.LTR)))
    text = ds.serialize(format="trig", pretty=True, rdf_version="1.1")
    assert "<<" not in text and "@version" not in text and "dirlang#en--ltr" in text
    back = StarLayerDataset()
    back.parse(data=text, format="trig")
    assert len(back) == 6


def test_pretty_output_is_independent_of_input_order_on_a_larger_graph():
    p, q = N("http://e/p"), N("http://e/q")
    quads = []
    for k in range(12):  # twelve chains of blank nodes of length 6, told apart only by the last literal
        ids = [ox.BlankNode(f"c{k}_{i}") for i in range(6)]
        quads += [ox.Quad(a, p, b, D) for a, b in zip(ids, ids[1:], strict=False)]
        quads += [ox.Quad(ids[-1], q, ox.Literal(str(k)), D), ox.Quad(N("http://e/s"), p, ids[0], D)]
    outs = set()
    for seed in range(8):
        shuffled = list(quads)
        random.Random(seed).shuffle(shuffled)
        outs.add(pretty_trig(shuffled))
    assert len(outs) == 1


# ---- interop --------------------------------------------------------------------------------------------------------------------
def _nested(depth):
    o = N("http://e/leaf")
    for i in range(depth):
        o = ox.Triple(N(f"http://e/s{i % 3}"), P, o)
    return [ox.Quad(N("http://e/a"), P, o, D)]


def test_deeply_nested_triple_term_round_trips():
    quads = _nested(1500)
    basic = interop.to_basic(quads, bnode_prefix="n")
    assert not interop.has_triple_terms(basic) and len(basic) == 1 + 4 * 1500
    assert interop.from_basic(basic) == quads


def test_to_basic_shares_equal_nested_terms_and_keeps_graphs_apart():
    inner = ox.Triple(A, P, B)
    outer = ox.Triple(A, P, inner)
    quads = [ox.Quad(A, P, outer, D), ox.Quad(B, P, outer, D), ox.Quad(A, P, outer, G1), ox.Quad(A, P, inner, D)]
    basic = interop.to_basic(quads, bnode_prefix="n")
    assert len({q.object for q in basic if q.predicate == interop.PF_OBJECT and isinstance(q.object, ox.BlankNode)}) == 2
    assert set(interop.from_basic(basic)) == set(quads)


def test_encode_directions_only_rebuilds_quads_that_change():
    plain = ox.Quad(A, P, ox.Literal("x"), D)
    ltr = ox.Quad(A, P, ox.Literal("x", language="en", direction=ox.BaseDirection.LTR), D)
    out = interop.encode_directions([plain, ltr])
    assert out[0] is plain and out[1] != ltr and out[1].object.direction is None


def test_bind_accepts_rdflib_namespace_classes():
    from rdflib import OWL, Namespace

    g = StarLayerGraph()
    for ns in (OWL, Namespace("http://example.org/"), Namespace(OWL)):
        g.bind("x", ns)
        assert g.prefixes["x"] == str(ns)
    for bad in (None, "", "relative/ns"):
        with pytest.raises(ValueError):
            g.bind("x", bad)
