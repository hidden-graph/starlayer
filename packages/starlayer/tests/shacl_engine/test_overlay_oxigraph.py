"""``OxigraphOverlay`` (opt-in): same answers as ``InferredView``, and source literals survive unchanged (fidelity guard)."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph.graph.entailment_regimes import ENTAILMENT
from starlayer.graph.oxgraph import OxGraph
from starlayer.shacl_engine import rules
from starlayer.shacl_engine.entailment import entailed_view
from starlayer.shacl_engine.overlay_oxigraph import (
    OxigraphOverlay,
    literal_survives_store,
    term_is_safe,
)
from starlayer.shacl_engine.rules import InferredView, apply_rules
from starlayer.shacl_engine.terms import (
    RDF,
    XSD,
    engine_view,
    to_engine_triple,
)

Literal, URIRef = ox.Literal, ox.NamedNode

EX = "http://example.com/ns#"
PRE = """
@prefix ex: <http://example.com/ns#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex: a sh:ShapesGraph ; sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.com/ns#" ] .
"""
def lit(lexical: str, datatype: URIRef) -> Literal:
    """An engine literal keeps exactly the lexical form it is built with ("04"^^xsd:integer stays "04")."""
    return Literal(lexical, datatype=datatype)


# Literals the store would rewrite (lexical form, datatype, or language case) next to ones it keeps.
REWRITTEN = [
    lit("04", XSD.integer),
    lit("1", XSD.boolean),
    lit("5", XSD.unsignedByte),
    lit("4.0", XSD.decimal),
]
SOURCE = REWRITTEN[:4]
# In the engine term model, "x"^^xsd:string is the simple literal and a language tag is lower-cased at construction, so
# those two no longer differ between the engine and the store: they are safe.
KEPT = [
    Literal("x", datatype=XSD.string),
    Literal("hi", language="en-US"),
Literal("4", datatype=XSD.integer), Literal("true", datatype=XSD.boolean), Literal("plain"), Literal("hi", language="en")]


def ex(name: str) -> URIRef:
    return URIRef(EX + name)


def graph(ttl: str) -> OxGraph:
    g = OxGraph()
    g.parse(data=PRE + ttl, format="turtle")
    return g


@pytest.fixture(params=["python", "oxigraph"])
def overlay_kind(request):
    previous = rules._OXIGRAPH_OVERLAY
    rules.use_oxigraph_overlay(request.param == "oxigraph")
    yield request.param
    rules.use_oxigraph_overlay(previous)


def exact(term: Literal) -> tuple:
    return (term.value, term.datatype, term.language, term.direction, type(term))


def test_guard_classifies_literals() -> None:
    assert not any(literal_survives_store(t) for t in REWRITTEN)
    assert all(literal_survives_store(t) for t in KEPT)
    assert term_is_safe(ex("a")) and not term_is_safe(REWRITTEN[0])


def test_unsafe_literals_stay_python_side_and_come_back_exact() -> None:
    view = OxigraphOverlay(engine_view(OxGraph()))
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
    view = OxigraphOverlay(engine_view(OxGraph()))
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
    view = entailed_view(data, ENTAILMENT.RDFS)
    assert isinstance(view, OxigraphOverlay if overlay_kind == "oxigraph" else InferredView)
    got = {exact(o) for o in view.objects(ex("s"), ex("q"))}
    want = {exact(o) for o in engine_view(data).objects(ex("s"), ex("p"))}
    assert got == want and len(got) == 4
    # the data graph is an OxGraph, so "04"^^xsd:integer and "1"^^xsd:boolean are already "4" and "true" when the overlay reads them
    assert ("4", XSD.integer, None, None, Literal) in got and ("true", XSD.boolean, None, None, Literal) in got
    assert ("5", XSD.integer, None, None, Literal) in got


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
        assert got == {exact(o) for o in engine_view(data).objects(ex("s"), ex("p"))}
        # the data graph is an OxGraph: "04"^^xsd:integer is stored (and copied) as "4", "5"^^xsd:unsignedByte as "5"^^xsd:integer
        assert ("4", XSD.integer, None, None, Literal) in got and ("5", XSD.integer, None, None, Literal) in got
    assert {(s, p, exact(o)) for s, p, o in map(to_engine_triple, res.inferred) if isinstance(o, Literal)} == {
        (ex("s"), ex(p), exact(o)) for p in ("copy", "copy2") for o in engine_view(data).objects(ex("s"), ex("p"))
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
        plain = entailed_view(data, ENTAILMENT.RDFS)
        rules.use_oxigraph_overlay(True)
        oxi = entailed_view(data, ENTAILMENT.RDFS)
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


def test_add_after_materialise_keeps_the_materialised_union_in_step() -> None:
    view = OxigraphOverlay(engine_view(OxGraph()))
    view.materialised()
    view.add((ex("s"), ex("p"), Literal("5", datatype=XSD.integer)))  # store side
    view.add((ex("s"), ex("p"), lit("04", XSD.integer)))  # python side
    assert len(view.materialised()) == 2  # (the materialised graph is an OxGraph: "04" is held as "4", still distinct from "5")
