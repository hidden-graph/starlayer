"""Regression tests from the SHACL-engine values bug hunt: the ill-formed-term policy on rdflib graphs."""

from __future__ import annotations

import pytest

rdflib = pytest.importorskip("rdflib")

from starlayer.shacl_engine import validate  # noqa: E402
from starlayer.shacl_engine.terms import TermError  # noqa: E402

SHAPES = (
    "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://ex.org/> . "
    "ex:S a sh:NodeShape ; sh:targetNode ex:s ; sh:property [ sh:path ex:p ; sh:minCount 1 ] ."
)
S, P = rdflib.URIRef("http://ex.org/s"), rdflib.URIRef("http://ex.org/p")


def test_scan_sees_a_same_size_edit_of_a_reused_rdflib_graph():
    shapes = rdflib.Graph().parse(data=SHAPES, format="turtle")
    data = rdflib.Graph()
    data.add((S, P, rdflib.URIRef("relative")))
    with pytest.raises(TermError):
        validate(data, shapes)
    data.remove((None, None, None))
    data.add((S, P, rdflib.URIRef("http://ex.org/o")))
    assert validate(data, shapes).conforms  # same size, the bad term is gone
    data.remove((None, None, None))
    data.add((S, P, rdflib.URIRef("relative2")))
    with pytest.raises(TermError):
        validate(data, shapes)  # same size again, a new bad term


def test_literal_subject_is_a_term_error_or_lenient_stand_in():
    shapes = rdflib.Graph().parse(data=SHAPES, format="turtle")
    data = rdflib.Graph()
    data.add((S, P, rdflib.Literal("hello")))
    data.add((rdflib.Literal("hello"), rdflib.RDF.type, rdflib.RDFS.Literal))  # a generalized triple, as owlrl makes
    with pytest.raises(TermError):
        validate(data, shapes)
    assert validate(data, shapes, invalid_terms="lenient").conforms


def test_non_iri_predicate_is_a_term_error():
    shapes = rdflib.Graph().parse(data=SHAPES, format="turtle")
    data = rdflib.Graph()
    data.add((S, rdflib.BNode("b"), rdflib.Literal("x")))
    with pytest.raises(TermError):
        validate(data, shapes)


def test_report_text_shows_the_original_language_tag_in_lenient_mode():
    shapes = rdflib.Graph().parse(
        format="turtle",
        data="@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.org/> . "
        "ex:S a sh:NodeShape ; sh:targetSubjectsOf ex:p ; "
        "sh:property [ sh:path ex:p ; sh:datatype <http://www.w3.org/2001/XMLSchema#integer> ] .",
    )
    data = rdflib.Graph()
    data.add((rdflib.URIRef("http://example.org/s"), rdflib.URIRef("http://example.org/p"), rdflib.Literal("v", lang="e")))
    out = validate(data, shapes, invalid_terms="lenient")
    assert "invalid-lang" not in out.report_text
    assert 'Literal("v", lang=e)' in out.report_text
