"""Behaviour tests of every public method of ``OxGraph`` / ``OxDataset`` / ``Result`` / the reifier helpers."""

from __future__ import annotations

import io

import pyoxigraph as ox
import pytest
from starlayer.graph.oxgraph import (
    OxDataset,
    OxGraph,
    as_store,
    config,
    reification,
    set_default_prefixes,
)

N = ox.NamedNode
EX = "http://example.org/"
A, B, C, D = (N(EX + x) for x in "abcd")
P, Q = N(EX + "p"), N(EX + "q")
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


def L(v, **kw):
    return ox.Literal(v, **kw)


@pytest.fixture
def g():
    g = OxGraph()
    g.add((A, P, B))
    g.add((A, P, L("x")))
    g.add((A, Q, C))
    g.add((B, P, C))
    return g


# ---- construction, store access ---------------------------------------------------------------------------------
def test_store_access_and_as_store(g):
    assert isinstance(g.store, ox.Store)
    assert as_store(g) is g.store and as_store(g.store) is g.store
    assert as_store(OxDataset(g.store)) is g.store
    with pytest.raises(TypeError):
        as_store(42)


def test_store_and_path_exclusive(tmp_path):
    with pytest.raises(ValueError):
        OxGraph(store=ox.Store(), path=tmp_path / "x")


def test_graph_shares_store_with_dataset():
    ds = OxDataset()
    ds.graph(A).add((B, P, C))
    assert (B, P, C) in OxGraph(ds.store, identifier=A)
    assert (B, P, C) not in OxGraph(ds.store)


# ---- add / addN / remove / contains / len / iter ------------------------------------------------------------------
def test_add_len_contains_iter(g):
    assert len(g) == 4
    assert (A, P, B) in g and (A, P, D) not in g
    assert set(g) == {(A, P, B), (A, P, L("x")), (A, Q, C), (B, P, C)}
    assert g.add((A, P, B)) is g and len(g) == 4  # a set, and add returns the graph


def test_add_accepts_triple_term_objects_and_tuples():
    g = OxGraph()
    tt = ox.Triple(A, P, B)
    g.add((C, N(RDF + "reifies"), tt))
    g.add((C, Q, (A, P, B)))  # a 3-tuple is a triple term
    assert (C, Q, tt) in g and len(g) == 2


def test_extend_and_addN():
    g = OxGraph()
    g.extend([(A, P, B), (A, P, C)])
    assert len(g) == 2
    g.addN([(B, P, C, g.identifier), (C, P, D, N(EX + "other"))])  # only quads for this graph
    assert len(g) == 3 and (C, P, D) not in g


def test_remove_exact_and_wildcards(g):
    g.remove((A, P, B))
    assert (A, P, B) not in g and len(g) == 3
    g.remove((A, None, None))
    assert len(g) == 1
    g.remove((None, None, None))
    assert len(g) == 0


def test_contains_with_literal_subject_is_false_not_error(g):
    assert (L("x"), P, B) not in g
    assert list(g.triples((L("x"), None, None))) == []
    assert list(g.triples((None, L("x"), None))) == []


def test_triples_patterns(g):
    assert len(list(g.triples((None, None, None)))) == 4
    assert len(list(g.triples((A, None, None)))) == 3
    assert len(list(g.triples((None, P, None)))) == 3
    assert len(list(g.triples((None, None, C)))) == 2
    assert list(g.triples((A, Q, C))) == [(A, Q, C)]
    assert list(g.triples()) == list(g)


def test_quads_on_graph_view_carry_the_graph_name(g):
    qs = list(g.quads((A, None, None)))
    assert len(qs) == 3 and all(q.graph_name == ox.DefaultGraph() for q in qs)
    assert list(g.quads((A, None, None, N(EX + "elsewhere")))) == []


def test_convenience_readers(g):
    assert set(g.objects(A, P)) == {B, L("x")}
    assert set(g.subjects(P, C)) == {B}
    assert set(g.predicates(A, C)) == {Q}
    assert set(g.predicate_objects(A)) == {(P, B), (P, L("x")), (Q, C)}
    assert set(g.subject_objects(Q)) == {(A, C)}
    assert set(g.subject_predicates(C)) == {(A, Q), (B, P)}
    assert list(g.objects(A, P, unique=True)).count(B) == 1


def test_value():
    g = OxGraph()
    g.add((A, N(RDF + "type"), B))
    g.add((A, P, C))
    g.add((A, P, D))
    assert g.value(A) == B  # predicate defaults to rdf:type
    assert g.value(A, P, None) in (C, D)
    assert g.value(None, P, C) == A
    assert g.value(B, P, None, default="none") == "none"
    with pytest.raises(ValueError):
        g.value(A, P, None, any=False)
    with pytest.raises(ValueError):
        g.value(A, P, C)


def test_items_reads_a_list():
    g = OxGraph()
    g.parse(data="@prefix : <http://example.org/> . :s :p (1 :a 'x') . :t :p () .")
    head = g.value(N(EX + "s"), P, None)
    assert list(g.items(head)) == [L("1", datatype=N("http://www.w3.org/2001/XMLSchema#integer")), A, L("x")]
    assert list(g.items(g.value(N(EX + "t"), P, None))) == []


def test_items_rejects_cycles_and_broken_lists():
    g = OxGraph()
    b1, b2 = ox.BlankNode("b1"), ox.BlankNode("b2")
    for h, t in ((b1, b2), (b2, b1)):
        g.add((h, N(RDF + "first"), A))
        g.add((h, N(RDF + "rest"), t))
    with pytest.raises(ValueError, match="cycle"):
        list(g.items(b1))
    g2 = OxGraph()
    g2.add((b1, N(RDF + "first"), A))
    with pytest.raises(ValueError, match="well-formed"):
        list(g2.items(b1))


def test_clear_and_copy(g):
    g.bind("ex", EX)
    c = g.copy()
    assert c is not g and c.store is not g.store and set(c) == set(g) and c.prefixes == {"ex": EX}
    c.prefixes["zz"] = "http://z/"
    assert "zz" not in g.prefixes
    g.clear()
    assert len(g) == 0 and len(c) == 4


def test_eq_is_identity_only(g):
    assert g == g and g != g.copy() and hash(g) == hash(g)


def test_rdflib_terms_are_converted_on_the_way_in():
    from rdflib import Literal, URIRef

    g = OxGraph()
    g.add((URIRef(EX + "a"), URIRef(EX + "p"), Literal("v")))
    assert (A, P, L("v")) in g
    assert (URIRef(EX + "a"), URIRef(EX + "p"), Literal("v")) in g


# ---- dataset ------------------------------------------------------------------------------------------------------
def test_dataset_graph_management():
    ds = OxDataset()
    ds.add((A, P, B))
    ds.graph(C).add((B, P, D))
    ds.graph("http://example.org/e")  # created empty, IRI string accepted
    assert ds.graph_names() == [C, N(EX + "e")] or set(ds.graph_names()) == {C, N(EX + "e")}
    gs = ds.graphs()
    assert gs[0].identifier == ox.DefaultGraph() and len(gs) == 3
    assert ds.has_graph(C) and not ds.has_graph(D) and ds.has_graph(None)
    assert len(ds) == 2  # union, as a set
    assert {q.graph_name for q in ds.quads((None, None, None))} == {ox.DefaultGraph(), C}
    assert len(list(ds.quads((None, None, None, C)))) == 1
    ds.remove_graph(C)
    assert not ds.has_graph(C) and len(ds) == 1
    ds.clear()
    assert len(ds) == 0 and ds.graph_names() == []


def test_dataset_union_counts_a_triple_once():
    ds = OxDataset()
    ds.add((A, P, B))
    ds.graph(C).add((A, P, B))
    assert len(ds) == 1 and len(list(ds.triples())) == 1 and len(list(ds.quads())) == 2
    assert (A, P, B) in ds and (A, P, B, C) in ds and (A, P, B, D) not in ds
    ds2 = OxDataset(store=ds.store, default_union=False)
    assert len(ds2) == 1 and not ds2.default_union
    only_named = OxDataset(default_union=False)
    only_named.graph(C).add((A, P, B))
    assert len(only_named) == 0 and OxDataset(store=only_named.store).triples((None, None, None)) is not None


def test_dataset_add_quad_and_remove_in_graph():
    ds = OxDataset()
    ds.add((A, P, B, C))
    assert (A, P, B) in ds.graph(C) and (A, P, B) not in ds.graph(None)
    ds.remove((A, P, B, C))
    assert len(ds) == 0


# ---- parse ---------------------------------------------------------------------------------------------------------
TTL = "@prefix ex: <http://example.org/> . ex:a ex:p ex:b , 'x'@en , 4 ."


@pytest.mark.parametrize("fmt", ["turtle", "turtle12", "ttl"])
def test_parse_turtle_names(fmt):
    g = OxGraph().parse(data=TTL, format=fmt)
    assert len(g) == 3 and g.prefixes == {"ex": EX}


def test_parse_turtle12_syntax_and_lexical_forms_as_written():
    g = OxGraph()
    g.parse(data='@prefix : <http://example.org/> . :a :p <<( :b :q :c )>> ; :r "t"@en--rtl . << :a :p :b >> :s 1 .')
    objs = {o for _, _, o in g}
    assert ox.Triple(B, Q, C) in objs
    assert any(isinstance(o, ox.Literal) and o.direction == ox.BaseDirection.RTL for o in objs)
    assert any(p == N(RDF + "reifies") for _, p, _ in g)


def test_parse_formats_round_trip():
    src = OxDataset()
    src.parse(data=TTL)
    src.graph(C).add((B, P, D))
    for fmt in ("trig", "nq", "nquads"):
        back = OxDataset().parse(data=src.serialize(format=fmt), format=fmt)
        assert set(back.quads()) == set(src.quads())
    flat = OxGraph().parse(data=TTL)
    for fmt in ("nt", "xml", "rdf-xml", "turtle", "n3", "jsonld"):
        back = OxGraph().parse(data=flat.serialize(format=fmt), format=fmt)
        assert set(back) == set(flat), fmt


def test_parse_sources(tmp_path):
    f = tmp_path / "x.ttl"
    f.write_text(TTL)
    assert len(OxGraph().parse(str(f))) == 3  # source path, format guessed from the extension
    assert len(OxGraph().parse(source=f)) == 3
    assert len(OxGraph().parse(file=str(f), format="turtle")) == 3
    with open(f, "rb") as fh:
        assert len(OxGraph().parse(file=fh)) == 3
    assert len(OxGraph().parse(data=TTL.encode())) == 3
    with pytest.raises(ValueError):
        OxGraph().parse()
    with pytest.raises(ValueError):
        OxGraph().parse(data=TTL, file=str(f))


def test_parse_base_and_unknown_format():
    g = OxGraph().parse(data="<a> <http://example.org/p> <b> .", format="turtle", base="http://example.org/")
    assert (A, P, B) in g
    with pytest.raises(ValueError, match="unknown RDF format"):
        OxGraph().parse(data="", format="trix")


def test_parse_syntax_error_leaves_graph_unchanged():
    g = OxGraph().parse(data=TTL)
    with pytest.raises(SyntaxError):
        g.parse(data="<a> <b> <c> . broken")
    assert len(g) == 3


def test_parse_blank_nodes_are_scoped_per_document():
    g = OxGraph()
    doc = "_:b <http://example.org/p> \"1\" ."
    g.parse(data=doc, format="nt")
    g.parse(data=doc, format="nt")
    assert len(g) == 2
    h = OxGraph()
    h.parse(data=doc, format="nt", rename_blank_nodes=False)
    h.parse(data=doc, format="nt", rename_blank_nodes=False)
    assert len(h) == 1


def test_parse_into_named_graph_view_and_quad_documents():
    ds = OxDataset()
    ds.graph(C).parse(data=TTL)
    assert len(ds.graph(C)) == 3 and len(ds.graph(None)) == 0
    trig = "<http://example.org/g> { <http://example.org/a> <http://example.org/p> <http://example.org/b> }"
    with pytest.raises(ValueError, match="named graphs"):
        OxGraph().parse(data=trig, format="trig")
    ds2 = OxDataset().parse(data=trig, format="trig")
    assert ds2.graph_names() == [N(EX + "g")]


def test_parse_captures_declared_prefixes_into_the_graphs_dict():
    g = OxGraph()
    g.parse(data="@prefix a: <http://a/> . a:x a:y a:z .")
    g.parse(data="@prefix b: <http://b/> . b:x b:y b:z .")
    assert g.prefixes == {"a": "http://a/", "b": "http://b/"}


# ---- serialize / prefixes ------------------------------------------------------------------------------------------
def test_serialize_returns_str_and_writes_destinations(tmp_path, g):
    s = g.serialize(format="nt")
    assert isinstance(s, str) and s.count("\n") == 4
    p = tmp_path / "o.nt"
    assert g.serialize(p, format="nt") is None and p.read_text() == s
    buf = io.BytesIO()
    g.serialize(buf, format="nt")
    assert buf.getvalue().decode() == s
    txt = io.StringIO()
    g.serialize(txt, format="nt")
    assert txt.getvalue() == s


def test_serialize_prefixes_graph_dict_and_per_call_override(g):
    assert "@prefix" not in g.serialize()
    g.bind("ex", EX)
    assert "@prefix ex:" in g.serialize() and "ex:a" in g.serialize()
    out = g.serialize(prefixes={"e2": EX})
    assert "e2:a" in out or "ex:a" in out
    assert "@prefix other:" in g.serialize(prefixes={"other": "http://other/"})


def test_serialize_only_used(g):
    g.bind("ex", EX)
    g.bind("unused", "http://unused.example/")
    assert "unused" in g.serialize()
    only = g.serialize(only_used=True)
    assert "unused" not in only and "@prefix ex:" in only
    assert g.used_prefixes() == [("ex", EX)]


def test_serialize_base_and_base_free(g):
    assert "@base" in g.serialize(base=EX)


def test_serialize_dataset_to_a_triple_format_flattens_named_graphs():
    ds = OxDataset()
    ds.add((A, P, B))
    assert "example.org" in ds.serialize(format="turtle")  # only the default graph has content
    ds.graph(C).add((A, P, B))  # the same triple in a second graph is written once
    ds.graph(C).add((B, P, A))
    for kw in ({}, {"pretty": True}):
        flat = OxGraph().parse(data=ds.serialize(format="turtle", **kw), format="turtle")
        assert len(flat) == 2, kw
    assert len(OxGraph().parse(data=ds.serialize(format="nt"), format="nt")) == 2
    assert "GRAPH" in ds.serialize(format="trig") or "{" in ds.serialize(format="trig")  # a quad format keeps the graphs


def test_serialize_rdf11_without_interop_says_so(g):
    try:
        import starlayer.graph.interop  # noqa: F401
    except ImportError:
        with pytest.raises(NotImplementedError):
            g.serialize(rdf_version="1.1")


def test_bind_unbind():
    g = OxGraph()
    g.bind("a", "http://a/")
    g.bind("a", "http://other/", override=False)
    assert g.prefixes == {"a": "http://a/"}
    g.bind("a", "http://other/")
    assert g.prefixes["a"] == "http://other/"
    assert g.unbind("a") and not g.unbind("a")


def test_default_prefixes_are_copied_at_build_time():
    try:
        set_default_prefixes({"ex": EX})
        g1 = OxGraph()
        assert g1.prefixes == {"ex": EX} and g1.prefixes is not config.DEFAULT_PREFIXES
        set_default_prefixes({"zz": "http://z/"})
        assert g1.prefixes == {"ex": EX}  # isolated from later changes
        assert OxDataset().prefixes == {"zz": "http://z/"}
        g1.prefixes["mine"] = "http://m/"
        assert "mine" not in config.DEFAULT_PREFIXES
    finally:
        set_default_prefixes({})
    assert OxGraph().prefixes == {}


def test_dataset_views_share_the_datasets_prefix_dict():
    ds = OxDataset()
    assert ds.graph(A).prefixes is ds.prefixes


# ---- query / update ------------------------------------------------------------------------------------------------
def test_select_rows_vars_bindings(g):
    g.bind("ex", EX)
    r = g.query("SELECT ?o ?s WHERE { ?s ex:p ?o } ORDER BY ?o")
    assert r.type == "SELECT" and [v.value for v in r.vars] == ["o", "s"]
    rows = list(r)
    assert len(r) == 3 and rows[0]["s"] in (A, B) and rows[0].s == rows[0][1] and rows[0].get("nope", 1) == 1
    assert all(set(b) == {"o", "s"} for b in r.bindings)
    assert r.raw is not None and bool(r)
    with pytest.raises(KeyError):
        rows[0]["zzz"]


def test_select_unbound_variable_is_none_and_absent_in_bindings(g):
    r = g.query("SELECT ?s ?z WHERE { ?s ?p ?o OPTIONAL { ?s <http://nope/> ?z } } LIMIT 1")
    row = next(iter(r))
    assert row["z"] is None and "z" not in r.bindings[0]


def test_ask(g):
    assert g.query("ASK { ?s ?p ?o }").askAnswer is True and g.query("ASK { <http://x/> ?p ?o }").askAnswer is False
    assert not g.query("ASK { <http://x/> ?p ?o }") and g.query("ASK {?s ?p ?o}").type == "ASK"


def test_construct_and_describe(g):
    r = g.query("CONSTRUCT { ?s <http://example.org/z> ?o } WHERE { ?s <http://example.org/q> ?o }")
    assert r.type == "CONSTRUCT" and list(r) == [(A, N(EX + "z"), C)]
    assert isinstance(r.graph, OxGraph) and len(r.graph) == 1
    d = g.query("DESCRIBE <http://example.org/a>")
    assert d.type == "DESCRIBE" and len(d) >= 1 and bool(d)


def test_init_ns_overrides_graph_prefixes_and_init_bindings(g):
    g.bind("ex", "http://wrong/")
    r = g.query("SELECT ?o WHERE { ex:a ex:q ?o }", initNs={"ex": EX})
    assert [row["o"] for row in r] == [C]
    r = g.query("SELECT ?o WHERE { ?s <http://example.org/p> ?o }", initBindings={"s": B})
    assert [row["o"] for row in r] == [C]
    r = g.query("SELECT ?o WHERE { ?s <http://example.org/p> ?o }", initBindings={ox.Variable("s"): B})
    assert [row["o"] for row in r] == [C]


def test_init_bindings_of_unprojected_variable_uses_values_fallback(g):
    r = g.query("SELECT ?o WHERE { ?s <http://example.org/p> ?o }", initBindings={"s": A})
    assert len(r) == 2
    r = g.query("SELECT (COUNT(*) AS ?n) WHERE { ?s <http://example.org/p> ?o }", initBindings={"s": A})
    assert next(iter(r))["n"].value == "2"


def test_base_in_query(g):
    assert g.query("ASK { <a> <p> <b> }", base=EX).askAnswer is True


def test_query_graph_view_sees_its_graph_as_default_dataset_sees_the_union():
    ds = OxDataset()
    ds.add((A, P, B))
    ds.graph(C).add((B, P, D))
    q = "SELECT * WHERE { ?s ?p ?o }"
    assert len(ds.query(q)) == 2
    assert len(OxDataset(ds.store, default_union=False).query(q)) == 1
    assert len(ds.graph(C).query(q)) == 1 and len(ds.graph(None).query(q)) == 1
    assert len(ds.query("SELECT * WHERE { GRAPH ?g { ?s ?p ?o } }")) == 1


def test_query_rejects_unbuilt_features(g):
    with pytest.raises(NotImplementedError):
        g.query("ASK {}", entailment="rdfs")
    with pytest.raises(NotImplementedError):
        g.query(object())


def test_sparql12_directly(g):
    g.add((N(EX + "r"), N(RDF + "reifies"), ox.Triple(A, P, B)))
    r = g.query("VERSION '1.2' SELECT ?t WHERE { <http://example.org/r> <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> ?t . FILTER isTRIPLE(?t) }")
    assert next(iter(r))["t"] == ox.Triple(A, P, B)


def test_update_operations():
    ds = OxDataset()
    ds.update("INSERT DATA { <http://example.org/a> <http://example.org/p> 1 }")
    assert len(ds) == 1
    ds.update("INSERT DATA { GRAPH <http://example.org/g> { <http://example.org/a> <http://example.org/p> 2 } }")
    assert len(ds.graph("http://example.org/g")) == 1
    ds.update("COPY DEFAULT TO <http://example.org/h>")
    assert len(ds.graph("http://example.org/h")) == 1
    ds.update("DELETE WHERE { ?s ?p 1 }")
    ds.update("CLEAR GRAPH <http://example.org/h>")
    ds.update("DROP GRAPH <http://example.org/g>")
    assert ds.graph_names() in ([], [N(EX + "h")])
    ds.bind("ex", EX)
    ds.update("INSERT DATA { ex:a ex:p ex:b }")
    assert (A, P, B) in ds
    ds.update("INSERT DATA { zz:a zz:p zz:b }", initNs={"zz": "http://zz/"})
    assert (N("http://zz/a"), N("http://zz/p"), N("http://zz/b")) in ds


def test_update_from_a_graph_view_acts_on_the_store():
    ds = OxDataset()
    v = ds.graph(C)
    v.update("INSERT DATA { GRAPH <http://example.org/c> { <http://example.org/a> <http://example.org/p> 1 } }")
    assert len(v) == 1


# ---- set operators --------------------------------------------------------------------------------------------------
def test_set_operators_on_graphs():
    x, y = OxGraph(), OxGraph()
    x.extend([(A, P, B), (A, P, C)])
    y.extend([(A, P, C), (A, P, D)])
    assert set(x + y) == {(A, P, B), (A, P, C), (A, P, D)}
    assert set(x - y) == {(A, P, B)}
    assert set(x & y) == {(A, P, C)}
    assert set(x ^ y) == {(A, P, B), (A, P, D)}
    assert len(x) == 2 and len(y) == 2  # inputs untouched
    x.bind("ex", EX)
    assert (x + y).prefixes == {"ex": EX}
    x += y
    assert len(x) == 3
    with pytest.raises(TypeError):
        x + 1
    with pytest.raises(TypeError):
        x + OxDataset()


def test_set_operators_on_graph_views_of_one_store():
    ds = OxDataset()
    ds.graph(A).add((B, P, C))
    ds.graph(D).add((B, P, C))
    ds.graph(D).add((B, P, D))
    assert set(ds.graph(D) - ds.graph(A)) == {(B, P, D)}


def test_set_operators_on_datasets():
    x, y = OxDataset(), OxDataset()
    x.add((A, P, B))
    x.add((A, P, B, C))
    y.add((A, P, B))
    assert len(list((x - y).quads())) == 1
    assert len(list((x & y).quads())) == 1
    assert len(list((x + y).quads())) == 2
    assert len(list((x ^ y).quads())) == 1


# ---- reifiers ---------------------------------------------------------------------------------------------------------
def test_reification_helpers():
    g = OxGraph()
    t1, t2 = ox.Triple(A, P, B), ox.Triple(A, P, C)
    r1, r2 = N(EX + "r1"), ox.BlankNode()
    assert g.add_reification(r1, t1) is g
    g.add_reification(r2, (A, P, C))
    g.add_reification(r2, t1)
    g.add((r1, Q, L("note")))
    g.add((r1, N(EX + "src"), D))
    assert set(g.reifiers()) == {r1, r2}
    assert set(g.reifiers(t1)) == {r1, r2} and set(g.reifiers(t2)) == {r2}
    assert set(g.reifiers(predicate=Q)) == {r1}
    assert set(g.reifiers(t1, Q, L("note"))) == {r1}
    assert list(g.reifiers(ox.Triple(D, P, D))) == []
    assert set(g.reifications()) == {t1, t2} and len(list(g.reifications())) == 2  # distinct
    assert set(g.reifications(o=C)) == {t2} and set(g.reifications(p=P)) == {t1, t2} and list(g.reifications(s=B)) == []
    assert set(g.reifier_annotations(t1)) == {(r1, Q, L("note")), (r1, N(EX + "src"), D)}
    assert list(g.reifier_annotations(t2)) == []
    assert set(g.reified_triples(r2)) == {t1, t2} and list(g.reified_triples(D)) == []
    # the module-level functions take a bare store too
    assert set(reification.reifiers(g.store)) == {r1, r2}
    with pytest.raises(TypeError):
        g.add_reification(r1, A)


def test_reification_from_turtle_annotation_syntax():
    g = OxGraph().parse(data="@prefix : <http://example.org/> . :a :p :b {| :q 'n' |} . :a :p :c ~ :r2 .")
    ts = set(g.reifications())
    assert ts == {ox.Triple(A, P, B), ox.Triple(A, P, C)}
    assert {a[2] for t in ts for a in g.reifier_annotations(t)} == {L("n")}


# ---- persistence of the wrapper on a path ------------------------------------------------------------------------------
def test_dataset_on_disk(tmp_path):
    path = tmp_path / "db"
    ds = OxDataset(path=path)
    ds.parse(data=TTL)
    ds.graph(C).add((A, P, D))
    del ds
    again = OxDataset(path=path)
    assert len(again) == 4 and len(again.graph(C)) == 1


def test_result_one_shot_note(g):
    r = g.query("SELECT * WHERE { ?s ?p ?o }")
    assert isinstance(r.raw, ox.QuerySolutions)
    r2 = g.query("SELECT * WHERE { ?s ?p ?o }")
    assert len(list(r2)) == len(list(r2)) == 4  # materialized once, iterable repeatedly


def test_dataset_serializes_to_trig_by_default_and_a_graph_to_turtle():
    ds = OxDataset()
    ds.graph(C).add((A, P, B))
    assert "GRAPH" in ds.serialize() or "{" in ds.serialize()
    g = OxGraph()
    g.add((A, P, B))
    assert "{" not in g.serialize()
