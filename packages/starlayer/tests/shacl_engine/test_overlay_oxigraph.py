"""``OxigraphOverlay`` (opt-in): same answers as ``InferredView``, and source literals survive unchanged (fidelity guard)."""

from __future__ import annotations

import pytest
from rdflib import RDF, Literal, URIRef
from rdflib.namespace import XSD
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl_engine import rules
from starlayer.shacl_engine.entailment import entailed_view
from starlayer.shacl_engine.overlay_oxigraph import (
    OxigraphOverlay,
    literal_survives_store,
    term_is_safe,
)
from starlayer.shacl_engine.rules import InferredView, apply_rules

EX = "http://example.com/ns#"
PRE = """
@prefix ex: <http://example.com/ns#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex: a sh:ShapesGraph ; sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.com/ns#" ] .
"""
def lit(lexical: str, datatype: URIRef) -> Literal:
    """A literal that keeps its lexical form (rdflib would otherwise normalise "04"^^xsd:integer to "4")."""
    return Literal(lexical, datatype=datatype, normalize=False)


# Literals the store would rewrite (lexical form, datatype, or language case) next to ones it keeps.
REWRITTEN = [
    lit("04", XSD.integer),
    lit("1", XSD.boolean),
    lit("5", XSD.unsignedByte),
    lit("4.0", XSD.decimal),
    Literal("x", datatype=XSD.string),
    Literal("hi", lang="en-US"),
]
SOURCE = REWRITTEN[:4]
KEPT = [Literal("4", datatype=XSD.integer), Literal("true", datatype=XSD.boolean), Literal("plain"), Literal("hi", lang="en")]


def ex(name: str) -> URIRef:
    return URIRef(EX + name)


def graph(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PRE + ttl, format="turtle")
    return g


@pytest.fixture(params=["python", "oxigraph"])
def overlay_kind(request):
    previous = rules._OXIGRAPH_OVERLAY
    rules.use_oxigraph_overlay(request.param == "oxigraph")
    yield request.param
    rules.use_oxigraph_overlay(previous)


def exact(term: Literal) -> tuple:
    return (str(term), term.datatype, term.language, type(term))


def test_guard_classifies_literals() -> None:
    assert not any(literal_survives_store(t) for t in REWRITTEN)
    assert all(literal_survives_store(t) for t in KEPT)
    assert term_is_safe(ex("a")) and not term_is_safe(REWRITTEN[0])


def test_unsafe_literals_stay_python_side_and_come_back_exact() -> None:
    view = OxigraphOverlay(StarLayerGraph())
    for i, term in enumerate([*REWRITTEN, *KEPT]):
        assert view.add((ex("s"), ex(f"p{i}"), term)) is True
        assert view.add((ex("s"), ex(f"p{i}"), term)) is False
    assert len(view._inferred) == len(REWRITTEN) and view._stored == len(KEPT)
    for i, term in enumerate([*REWRITTEN, *KEPT]):
        (got,) = list(view.objects(ex("s"), ex(f"p{i}")))
        assert exact(got) == exact(term)
        assert (ex("s"), ex(f"p{i}"), term) in view
    # a lookup by an un-normalised literal must not hit the normalised twin that the store holds
    view.add((ex("t"), ex("n"), Literal("4", datatype=XSD.integer)))
    assert (ex("t"), ex("n"), lit("04", XSD.integer)) not in view
    assert list(view.subjects(ex("n"), lit("04", XSD.integer))) == []
    assert list(view.subjects(ex("n"), Literal("4", datatype=XSD.integer))) == [ex("t")]


def test_remove_both_sides() -> None:
    view = OxigraphOverlay(StarLayerGraph())
    a, b = (ex("s"), ex("p"), lit("04", XSD.integer)), (ex("s"), ex("p"), Literal("4", datatype=XSD.integer))
    view.add(a)
    view.add(b)
    view.remove(a)
    view.remove(b)
    assert not list(view.triples((None, None, None))) and len(view) == 0


def test_subproperty_entailment_keeps_source_literals(overlay_kind) -> None:
    data = graph(
        """
        ex:p rdfs:subPropertyOf ex:q .
        """
    )
    for o in SOURCE:
        data.add((ex("s"), ex("p"), o))
    view = entailed_view(data, "rdfs")
    assert isinstance(view, OxigraphOverlay if overlay_kind == "oxigraph" else InferredView)
    got = {exact(o) for o in view.objects(ex("s"), ex("q"))}
    want = {exact(o) for o in data.objects(ex("s"), ex("p"))}
    assert got == want and len(got) == 4
    assert ("04", XSD.integer, None, Literal) in got and ("1", XSD.boolean, None, Literal) in got
    assert ("5", XSD.unsignedByte, None, Literal) in got


def test_copying_rule_keeps_source_literals(overlay_kind) -> None:
    data = graph(
        """
        ex:R a sh:SPARQLRule ; sh:prefixes ex: ;
          sh:construct "CONSTRUCT { ?s ex:copy ?o } WHERE { ?s ex:p ?o }" .
        ex:T a sh:NodeShape ; sh:targetNode ex:s ; sh:rule ex:C .
        ex:C a sh:SPARQLRule ; sh:prefixes ex: ;
          sh:construct "CONSTRUCT { $this ex:copy2 ?o } WHERE { $this ex:p ?o }" .
        """
    )
    for o in SOURCE[:3]:
        data.add((ex("s"), ex("p"), o))
    res = apply_rules(data)
    for pred in ("copy", "copy2"):
        got = {exact(o) for o in res.view.objects(ex("s"), ex(pred))}
        assert got == {exact(o) for o in data.objects(ex("s"), ex("p"))}
        assert ("04", XSD.integer, None, Literal) in got and ("5", XSD.unsignedByte, None, Literal) in got
    assert {(s, p, exact(o)) for s, p, o in res.inferred if isinstance(o, Literal)} == {
        (ex("s"), ex(p), exact(o)) for p in ("copy", "copy2") for o in data.objects(ex("s"), ex("p"))
    }


def test_same_answers_as_inferred_view() -> None:
    data = graph(
        """
        ex:A rdfs:subClassOf ex:B . ex:B rdfs:subClassOf ex:C . ex:p rdfs:subPropertyOf ex:q . ex:q rdfs:range ex:R .
        ex:a a ex:A ; ex:p ex:b, "x" . ex:b a ex:B .
        """
    )
    data.add((ex("a"), ex("p"), lit("04", XSD.integer)))
    previous = rules._OXIGRAPH_OVERLAY
    try:
        rules.use_oxigraph_overlay(False)
        plain = entailed_view(data, "rdfs")
        rules.use_oxigraph_overlay(True)
        oxi = entailed_view(data, "rdfs")
    finally:
        rules.use_oxigraph_overlay(previous)
    assert set(plain.triples((None, None, None))) == set(oxi.triples((None, None, None)))
    assert plain.inferred == oxi.inferred
    for pattern in [(ex("a"), RDF.type, None), (None, RDF.type, ex("C")), (ex("a"), None, None), (None, ex("q"), None)]:
        assert set(plain.triples(pattern)) == set(oxi.triples(pattern))
    assert set(plain.subjects(RDF.type, ex("C"))) == set(oxi.subjects(RDF.type, ex("C")))
    assert set(plain.objects(ex("a"), ex("q"))) == set(oxi.objects(ex("a"), ex("q")))
    assert set(plain.predicate_objects(ex("a"))) == set(oxi.predicate_objects(ex("a")))
    assert oxi.construct("CONSTRUCT { ?s <http://x/y> ?o } WHERE { ?s <http://example.com/ns#q> ?o }", None)
