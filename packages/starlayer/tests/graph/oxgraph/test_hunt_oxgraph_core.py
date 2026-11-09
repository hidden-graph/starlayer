"""Regression tests for the oxgraph-core bug hunt (StarLayerGraph / StarLayerDataset wrapper)."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph import StarLayerDataset, StarLayerGraph  # noqa: F401

N = ox.NamedNode


def ex(x: str) -> ox.NamedNode:
    return N("http://ex/" + x)


def _out(ds, name="out"):
    return len(list(ds.store.quads_for_pattern(None, None, None, ex(name))))


# ---- default_union update(): prologue must not switch off the union rewrite ---------------------------------------------
@pytest.mark.parametrize(
    "prologue",
    ["PREFIX e: <http://ex/> ", 'VERSION "1.2" ', 'VERSION "1.2"\nPREFIX e: <http://ex/>\nBASE <http://ex/> ', "BASE <http://ex/> "],
)
def test_union_update_with_prologue_reads_union(prologue):
    ds = StarLayerDataset(default_union=True)
    ds.graph(ex("g1")).add((ex("a"), ex("p"), ex("b")))
    ds.update(prologue + "INSERT { GRAPH <http://ex/out> { ?s ?p ?o } } WHERE { ?s ?p ?o }")
    assert _out(ds) == 1


def test_union_update_second_operation_after_prologue():
    ds = StarLayerDataset(default_union=True)
    ds.graph(ex("g1")).add((ex("a"), ex("p"), ex("b")))
    ds.update(
        "PREFIX e: <http://ex/> INSERT { GRAPH e:out { ?s ?p ?o } } WHERE { ?s ?p ?o } ; "
        "INSERT { GRAPH <http://ex/out2> { ?s ?p ?o } } WHERE { ?s ?p ?o }"
    )
    assert _out(ds) == 1
    assert _out(ds, "out2") == 1


# ---- blank-node-named graphs are part of the union ----------------------------------------------------------------------
def test_union_update_sees_blank_node_graph():
    ds = StarLayerDataset(default_union=True)
    ds.store.add(ox.Quad(ex("a"), ex("p"), ex("b"), ox.BlankNode("g")))
    ds.update("INSERT { GRAPH <http://ex/out> { ?s ?p ?o } } WHERE { ?s ?p ?o }")
    assert _out(ds) == 1


def test_union_update_blank_graph_into_default():
    ds = StarLayerDataset(default_union=True)
    ds.graph(ox.BlankNode("g")).add((ex("a"), ex("p"), ex("b")))
    ds.update("INSERT { ?s <http://ex/q> ?o } WHERE { ?s <http://ex/p> ?o }")
    assert len(list(ds.store.quads_for_pattern(None, ex("q"), None, ox.DefaultGraph()))) == 1
    assert not [q for q in ds.store if "union-default" in str(q.graph_name)]


# ---- malformed DELETE WHERE ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["DELETE WHERE", "DELETE WHERE ?x"])
def test_union_update_malformed_delete_where_is_syntax_error(text):
    for union in (False, True):
        ds = StarLayerDataset(default_union=union)
        ds.graph(ex("g1")).add((ex("a"), ex("b"), ex("c")))
        with pytest.raises(SyntaxError):
            ds.update(text)


# ---- a query own FROM clause is honoured on a default_union dataset ----
@pytest.mark.parametrize("overlap", [False, True])
def test_query_from_clause_on_union_dataset(overlap):
    ds = StarLayerDataset()
    ds.graph("urn:g1").add((N("urn:a"), N("urn:p"), N("urn:b")))
    ds.add((N("urn:a"), N("urn:p"), N("urn:c")))
    if overlap:
        ds.graph("urn:g2").add((N("urn:a"), N("urn:p"), N("urn:b")))
    got = sorted(r[0].value for r in ds.query("SELECT ?o FROM <urn:g1> WHERE { ?s <urn:p> ?o }"))
    assert got == ["urn:b"]
    got = sorted(r[0].value for r in ds.query("PREFIX from: <urn:> SELECT ?o WHERE { ?s <urn:p> ?o }"))
    assert got == ["urn:b", "urn:c"]


# ---- objects / subjects / predicates agree between a graph and a union dataset ----
def test_term_readers_graph_vs_union_dataset():
    triples = [(ex("a"), ex("p"), ex("b")), (ex("a"), ex("p"), ex("c")), (ex("d"), ex("p"), ex("b"))]
    g = StarLayerGraph()
    g.extend(triples)
    d = StarLayerDataset()
    d.extend(triples)
    for name, args in [("subjects", (ex("p"),)), ("objects", (None, ex("p"))), ("predicates", (ex("a"),))]:
        assert sorted(map(str, getattr(g, name)(*args))) == sorted(map(str, getattr(d, name)(*args)))
    assert len(list(d.subjects(ex("p")))) == 3
    assert len(list(d.subjects(ex("p"), unique=True))) == 2
    d.graph(ex("g2")).add(triples[0])
    assert len(list(d.subjects(ex("p")))) == 3


# ---- blank-node initBinding on a variable that is not projected ----
B = ox.BlankNode("b1")


def _bgraph():
    g = StarLayerGraph()
    g.add((B, ex("p"), ox.Literal("5")))
    return g


@pytest.mark.parametrize("var", ["count", "min", "max", "sum", "sample"])
def test_blank_binding_variable_named_like_aggregate(var):
    rows = list(_bgraph().query(f"SELECT ?{var} WHERE {{ ?x <http://ex/p> ?{var} }}", initBindings={"x": B}))
    assert len(rows) == 1


def test_blank_binding_prefix_named_select():
    q = "PREFIX select: <http://ex/> SELECT ?v WHERE { ?x select:p ?v }"
    assert len(list(_bgraph().query(q, initBindings={"x": B}))) == 1


def test_blank_binding_select_star_unmentioned_variable():
    g = StarLayerGraph()
    g.add((ex("a"), ex("p"), ex("b")))
    q = "SELECT * WHERE { ?s ?p ?o }"
    assert len(list(g.query(q, initBindings={"unused": ox.BlankNode("x")}))) == 1


# ---- Result.type of DESCRIBE with a '#' in a PREFIX IRI ----------------------------------------------------------------
def test_describe_type_with_hash_in_prefix_iri():
    g = StarLayerGraph()
    g.add((ex("a"), ex("p"), ex("b")))
    assert g.query("PREFIX e: <http://ex.org/#> DESCRIBE <http://ex/a>").type == "DESCRIBE"
    assert g.query("# \"quote\n DESCRIBE <http://ex/a>").type == "DESCRIBE"
    assert g.query("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o } # DESCRIBE").type == "CONSTRUCT"


# ---- VERSION "1.1" conformance check ignores strings, IRIs and comments -------------------------------------------------
def test_version_warning_ignores_dashes_and_tilde_in_strings():
    import warnings

    g = StarLayerGraph()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        g.query('VERSION "1.1" SELECT * { ?s ?p "a--b" }')
        g.query('VERSION "1.1" SELECT * { ?s ?p ?o FILTER(CONTAINS(?o, "x~y")) }')
        g.query('VERSION "1.1" SELECT * { ?s <http://x/a~b--c> ?o } # ~ --')
    assert [x for x in w if "onformance" in x.category.__name__] == []
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        g.query('VERSION "1.1" SELECT * { ?s ?p "a"@en--ltr }')
    assert [x for x in w if "onformance" in x.category.__name__]


# ---- parse(source="file:///...") ------------------------------------------------------------------------------------------
def test_parse_file_url(tmp_path):
    p = tmp_path / "a b.ttl"
    p.write_text("<http://x/a> <http://x/b> <http://x/c> .\n")
    assert len(StarLayerGraph().parse(str(p))) == 1
    assert len(StarLayerGraph().parse(p.as_uri())) == 1


# ---- serialize(destination, encoding=...) --------------------------------------------------------------------------------
def test_serialize_encoding(tmp_path):
    import io

    g = StarLayerGraph()
    g.add((ex("a"), ex("p"), ox.Literal("café")))
    s = io.StringIO()
    g.serialize(s, format="nt", encoding="latin-1")
    assert "café" in s.getvalue()
    p = tmp_path / "o.nt"
    g.serialize(p, format="nt", encoding="latin-1")
    assert "café".encode("latin-1") in p.read_bytes()
    b = io.BytesIO()
    g.serialize(b, format="nt")
    assert "café".encode() in b.getvalue()


# ---- pretty TriG of a named-graph view keeps the graph name ----------------------------------------------------------------
def test_pretty_trig_of_named_graph_view_keeps_graph_name():
    ds = StarLayerDataset()
    view = ds.graph(N("http://g/1"))
    view.add((ex("a"), ex("b"), ex("c")))

    def graphs(text):
        h = StarLayerDataset()
        h.parse(data=text, format="trig")
        return sorted(str(q.graph_name) for q in h.store)

    assert graphs(view.serialize(format="trig", pretty=True)) == graphs(view.serialize(format="trig")) == ["<http://g/1>"]
    assert "a b c" not in view.serialize(format="turtle", pretty=True)  # a triple format still works
    ds.add((ex("x"), ex("y"), ex("z")))
    assert graphs(ds.serialize(format="trig", pretty=True)) == ["<http://g/1>", "DEFAULT"]


# ---- derive_shape -----------------------------------------------------------------------------------------------------------
_TTL = "@prefix : <http://ex.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"


def _ttl(text):
    g = StarLayerGraph()
    g.parse(data=_TTL + text, format="turtle")
    return g


def test_derive_shape_ill_formed_typed_literal():
    g = StarLayerGraph()
    g.add((ex("a"), ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), ex("C")))
    g.add((ex("a"), ex("p"), ox.Literal("abc", datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer"))))
    assert len(g.derive_shape()) > 0


def test_derive_shape_template_plain_beside_language_tagged():
    old = _ttl(':n1 a :C ; :p "a"@en .')
    new = _ttl(':n1 a :C ; :p "a"@en, "plain" .')
    assert len(new.derive_shape(old.derive_shape())) > 0


@pytest.mark.parametrize("pred,val", [("maxExclusive", 2), ("minExclusive", 9)])
def test_derive_shape_template_exclusive_bound_violated(pred, val):
    data = _ttl(":a a :C ; :n 5 .")
    tpl = _ttl(f":S a sh:NodeShape ; sh:targetClass :C ; sh:property [ sh:path :n ; sh:{pred} {val} ] .")
    assert len(data.derive_shape(tpl)) > 0


def test_derive_shape_template_target_node_and_nested_node():
    data = _ttl(':a a :C ; :p "x" .')
    tpl = _ttl(":S a sh:NodeShape ; sh:targetNode :a ; sh:property [ sh:path :p ; sh:minCount 3 ] .")
    assert len(data.derive_shape(tpl)) > 0
    nested = _ttl(":S a sh:NodeShape ; sh:targetClass :C ; sh:node :T . :T a sh:NodeShape ; sh:property [ sh:path :p ; sh:minCount 3 ] .")
    assert len(data.derive_shape(nested)) > 0


def test_derive_shape_subclass_hierarchy():
    g = _ttl(':Dog rdfs:subClassOf :Animal . :rex a :Dog ; :barks "yes" . :cat1 a :Animal ; :name "Tom" .')
    assert len(g.derive_shape()) > 0


# ---- has_triple_term: an impossible pattern is False --------------------------------------------------------------------
def test_has_triple_term_impossible_pattern_is_false():
    g = StarLayerGraph()
    g.add((ex("a"), ex("b"), ex("c")))
    assert g.has_triple_term(ox.Literal("x"), ex("b"), ex("c")) is False
    assert g.has_triple_term(ex("a"), ox.BlankNode("p"), ex("c")) is False


# ---- resolve_imports(mode="delta", target_graph=...) --------------------------------------------------------------------
def test_resolve_imports_delta_fills_target_graph():
    owl_imports = N("http://www.w3.org/2002/07/owl#imports")
    main = StarLayerGraph()
    main.add((N("http://x/onto"), owl_imports, N("http://x/other")))
    other = StarLayerGraph()
    other.add((N("http://x/other"), N("http://x/p"), N("http://x/o")))
    target = StarLayerGraph()
    res = main.resolve_imports(loader=lambda iri: other, mode="delta", target_graph=target)
    assert res is target
    assert (N("http://x/other"), N("http://x/p"), N("http://x/o")) in target
