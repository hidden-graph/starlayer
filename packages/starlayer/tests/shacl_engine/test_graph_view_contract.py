"""One contract suite for the engine's ``GraphView`` protocol, run over every implementation.

Implementations: ``OxGraph`` and ``OxigraphGraph`` (both over an Oxigraph store; ``preserves_lexical_forms = False``:
Oxigraph normalizes literals on storage, oxigraph/oxigraph#526). Terms are pyoxigraph terms throughout.
"""

from __future__ import annotations

import pyoxigraph as ox
import pytest
import rdflib
from pyoxigraph import BlankNode as BNode
from pyoxigraph import Literal
from starlayer.graph.model.dirlangstring import DirLangString
from starlayer.graph.model.triple import TripleTerm as RdflibTripleTerm
from starlayer.graph.oxgraph import OxGraph
from starlayer.shacl_engine.interface import GraphView
from starlayer.shacl_engine.oxigraph_view import (
    DEFAULT,
    OxigraphGraph,
    from_ox,
    to_ox,
)
from starlayer.shacl_engine.terms import NS as Namespace
from starlayer.shacl_engine.terms import RDF, integer, text

EX = Namespace("http://example.com/ns#")
URIRef = ox.NamedNode
REIFIES = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")
B1, B2 = BNode("b1"), BNode("b2")
TripleTerm = ox.Triple
TT = TripleTerm(EX.a, EX.p, Literal("v"))
DLS = Literal("salaam", language="ar", direction=ox.BaseDirection.RTL)

TRIPLES = [
    (EX.a, EX.p, EX.b),
    (EX.a, EX.p, EX.c),
    (EX.a, EX.q, Literal("plain")),
    (EX.a, EX.q, Literal("hola", language="es")),
    (EX.a, EX.q, DLS),
    (EX.a, EX.n, integer(7)),
    (EX.b, EX.p, B1),
    (B1, EX.p, B2),
    (B2, EX.q, Literal("x", datatype=EX.custom)),
    (EX.r, REIFIES, TT),
    # list (ex:l1 ex:l2) hanging off ex:c
    (EX.c, EX.list, EX.l1),
    (EX.l1, RDF.first, EX.m1),
    (EX.l1, RDF.rest, EX.l2),
    (EX.l2, RDF.first, EX.m2),
    (EX.l2, RDF.rest, RDF.nil),
]


def _starlayer(triples):
    g = OxGraph()
    for t in triples:
        g.add(t)
    return g


def _oxgraph(triples):
    return _starlayer(triples)


def _oxigraph(triples):
    return OxigraphGraph.from_graph(_starlayer(triples))


@pytest.fixture(params=["OxGraph", "OxigraphGraph"])
def view(request):
    return (_oxgraph if request.param == "OxGraph" else _oxigraph)(TRIPLES)


def test_satisfies_protocol(view):
    assert isinstance(view, GraphView)


def test_triples_fully_bound_and_wildcards(view):
    assert set(view.triples((EX.a, EX.p, EX.b))) == {(EX.a, EX.p, EX.b)}
    assert set(view.triples((EX.a, EX.p, None))) == {(EX.a, EX.p, EX.b), (EX.a, EX.p, EX.c)}
    assert {s for s, _, _ in view.triples((None, EX.p, EX.b))} == {EX.a}
    assert len(list(view.triples((EX.a, None, None)))) == 6
    assert {o for _, _, o in view.triples((None, EX.p, None))} == {EX.b, EX.c, B1, B2}
    assert len(set(view.triples((None, None, None)))) == len(TRIPLES)
    assert list(view.triples((EX.nope, None, None))) == []


def test_objects(view):
    assert set(view.objects(EX.a, EX.p)) == {EX.b, EX.c}
    assert set(view.objects(EX.a, None)) >= {EX.b, EX.c, integer(7)}
    assert set(view.objects(None, RDF.first)) == {EX.m1, EX.m2}
    assert set(view.objects()) >= {EX.b, B1, TT}


def test_subjects(view):
    assert set(view.subjects(EX.p, EX.b)) == {EX.a}
    assert set(view.subjects(EX.p, None)) == {EX.a, EX.b, B1}
    assert set(view.subjects(None, EX.c)) == {EX.a}
    assert EX.r in set(view.subjects())


def test_predicate_objects(view):
    po = set(view.predicate_objects(EX.a))
    assert (EX.p, EX.b) in po and (EX.n, integer(7)) in po and len(po) == 6
    assert len(set(view.predicate_objects())) == len({(p, o) for _, p, o in TRIPLES})


def test_contains(view):
    assert (EX.a, EX.p, EX.b) in view
    assert (EX.a, EX.p, EX.nope) not in view
    assert (EX.a, EX.q, DLS) in view
    assert (EX.r, REIFIES, TT) in view


def test_blank_nodes_round_trip(view):
    assert set(view.objects(EX.b, EX.p)) == {B1}
    (o,) = view.objects(B1, EX.p)
    assert isinstance(o, BNode) and o == B2
    assert (B1, EX.p, B2) in view


def test_language_and_direction_literals(view):
    objs = set(view.objects(EX.a, EX.q))
    assert Literal("hola", language="es") in objs
    assert DLS in objs
    assert Literal("plain") in objs
    dls = next(o for o in objs if o.direction is not None)
    assert (dls.value, dls.language, dls.direction) == ("salaam", "ar", ox.BaseDirection.RTL)
    # a language literal is not equal to the same text with a direction
    assert set(view.subjects(EX.q, Literal("salaam", language="ar"))) == set()
    assert set(view.subjects(EX.q, DLS)) == {EX.a}


def test_datatyped_literals(view):
    assert set(view.objects(EX.a, EX.n)) == {integer(7)}
    assert set(view.objects(B2, EX.q)) == {Literal("x", datatype=EX.custom)}
    assert set(view.subjects(EX.n, integer(7))) == {EX.a}


def test_triple_terms(view):
    (tt,) = view.objects(EX.r, REIFIES)
    assert isinstance(tt, ox.Triple)
    assert (tt.subject, tt.predicate, tt.object) == (EX.a, EX.p, Literal("v"))
    assert set(view.subjects(REIFIES, TripleTerm(EX.a, EX.p, Literal("v")))) == {EX.r}
    assert set(view.subjects(REIFIES, TripleTerm(EX.a, EX.p, Literal("other")))) == set()


def test_rdf_list_traversal(view):
    members, node = [], next(iter(view.objects(EX.c, EX.list)))
    while node != RDF.nil:
        (first,) = view.objects(node, RDF.first)
        (node,) = view.objects(node, RDF.rest)
        members.append(first)
    assert members == [EX.m1, EX.m2]


def test_stable_under_repeated_iteration(view):
    assert sorted(map(text, view.objects(EX.a, EX.p))) == sorted(map(text, view.objects(EX.a, EX.p)))


# ---- Oxigraph only: graph selection, conversion, query ----------------------------------------------------------------

G1, G2 = URIRef("http://example.com/g1"), URIRef("http://example.com/g2")


@pytest.fixture
def dataset() -> OxigraphGraph:
    return (OxigraphGraph.from_text(
        """@prefix ex: <http://example.com/ns#> .
        ex:d ex:p ex:default .
        ex:both ex:p ex:x .
        <http://example.com/g1> { ex:s1 ex:p ex:o1 . ex:both ex:p ex:x . }
        <http://example.com/g2> { ex:s2 ex:p ex:o2 . ex:both ex:p ex:x . }""",
        format="trig",
    ))


def test_union_default_and_named_graphs(dataset):
    store = dataset.store
    union = OxigraphGraph(store)
    assert set(union.subjects(EX.p, None)) == {EX.d, EX.both, EX.s1, EX.s2}
    # the same triple in three graphs is reported once in the union
    assert len(list(union.triples((EX.both, EX.p, EX.x)))) == 1
    default = OxigraphGraph(store, DEFAULT)
    assert set(default.subjects(EX.p, None)) == {EX.d, EX.both}
    g1 = OxigraphGraph(store, G1)
    assert set(g1.subjects(EX.p, None)) == {EX.s1, EX.both}
    assert (EX.s2, EX.p, EX.o2) not in g1 and (EX.s2, EX.p, EX.o2) in OxigraphGraph(store, G2) and (EX.s2, EX.p, EX.o2) in union
    assert len(list(union.triples((None, None, None)))) == 4


def test_flags():
    assert OxigraphGraph.preserves_lexical_forms is False
    assert OxigraphGraph.native_sparql is True


# the boundary: ``to_ox`` / ``from_ox`` convert the rdflib / StarLayer terms a caller may still pass (rdflib input is supported)
RDFLIB_EX = rdflib.Namespace("http://example.com/ns#")


@pytest.mark.parametrize(
    "term",
    [
        RDFLIB_EX.a,
        rdflib.BNode("n1"),
        rdflib.Literal("s"),
        rdflib.Literal("s", lang="en"),
        rdflib.Literal("s", lang="en-GB"),
        DirLangString("s", "he", "rtl"),
        rdflib.Literal(5),
        rdflib.Literal(1.5),
        rdflib.Literal("x", datatype=RDFLIB_EX.custom),
        rdflib.Literal("2020-01-01", datatype=rdflib.XSD.date),
        RdflibTripleTerm(RDFLIB_EX.a, RDFLIB_EX.p, rdflib.Literal("v", lang="fr")),
        RdflibTripleTerm(rdflib.BNode("t"), RDFLIB_EX.p, RdflibTripleTerm(RDFLIB_EX.a, RDFLIB_EX.p, RDFLIB_EX.b)),
    ],
)
def test_conversion_round_trip(term):
    assert from_ox(to_ox(term)) == term
    assert type(from_ox(to_ox(term))) is type(term)


def test_conversion_wildcard_and_errors():
    assert to_ox(None) is None and from_ox(None) is None
    assert from_ox(to_ox((RDFLIB_EX.a, RDFLIB_EX.p, RDFLIB_EX.b))) == RdflibTripleTerm(RDFLIB_EX.a, RDFLIB_EX.p, RDFLIB_EX.b)
    with pytest.raises(TypeError):
        to_ox(42)


def test_from_file_trig_and_turtle(tmp_path):
    f = tmp_path / "d.ttl"
    f.write_text("@prefix ex: <http://example.com/ns#> . ex:a ex:p <<( ex:x ex:y 1 )>> .")
    g = OxigraphGraph.from_file(f)
    (tt,) = g.objects(EX.a, EX.p)
    assert tt == TripleTerm(EX.x, EX.y, Literal(1))
    t = tmp_path / "d.trig"
    t.write_text("@prefix ex: <http://example.com/ns#> . ex:g { ex:a ex:p ex:b }")
    assert (EX.a, EX.p, EX.b) in OxigraphGraph.from_file(t)


def test_query_select_ask_construct_and_bindings(dataset):
    sel = dataset.query("SELECT ?s ?o WHERE { ?s <http://example.com/ns#p> ?o }")
    assert {(r["s"], r["o"]) for r in sel} >= {(EX.d, EX.default), (EX.s1, EX.o1)}
    this = dataset.query("SELECT * WHERE { ?this <http://example.com/ns#p> ?o }", {"this": EX.s2})
    assert this == [{"this": EX.s2, "o": EX.o2}]
    assert dataset.query("ASK { ?this <http://example.com/ns#p> ?o }", {"?this": EX.s1}) is True
    assert dataset.query("ASK { ?this <http://example.com/ns#p> ?o }", {"this": EX.nope}) is False
    built = dataset.query("CONSTRUCT { ?s <http://example.com/ns#q> ?o } WHERE { ?s <http://example.com/ns#p> ?o }")
    assert (EX.s1, EX.q, EX.o1) in built
    # a named-graph view queries only that graph
    only = OxigraphGraph(dataset.store, G1).query("SELECT ?s WHERE { ?s <http://example.com/ns#p> ?o }")
    assert {r["s"] for r in only} == {EX.s1, EX.both}
    # triple terms and directional literals bind and come back
    tt = TripleTerm(EX.x, EX.y, DLS)
    got = dataset.query("SELECT ?t WHERE { VALUES ?x { 1 } }", {"t": tt})
    assert got == [{"t": tt}]
