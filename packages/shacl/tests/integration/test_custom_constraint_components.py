import pytest
from rdflib import Namespace
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl import StarShaclValidator

EX = Namespace("http://example.org/")

pyshacl = pytest.importorskip("pyshacl")

# User-defined, reusable SPARQL-based sh:ConstraintComponent (SHACL Core /
# SHACL 1.2 SPARQL Extensions - https://www.w3.org/TR/shacl12-sparql/):
# a shapes graph can declare its own `a sh:ConstraintComponent` with
# sh:parameter/sh:validator (or sh:nodeValidator/sh:propertyValidator), and
# pySHACL's own CustomConstraintComponent/SPARQLConstraintComponent
# machinery (pyshacl/constraints/sparql/sparql_based_constraint_components.py)
# already implements this - but nothing in starShacl had ever exercised it,
# so it was unconfirmed whether it worked at all, and unconfirmed whether it
# interacted correctly with RDF-1.2 triple-term data through the
# TripleTermAdapter encode/decode layer. Both are confirmed working here.
#
# Constructing the SELECT-based case surfaced a real pySHACL bug: a
# malformed custom-validator SPARQL SELECT query that raises
# pyshacl.errors.ValidationFailure crashed starShacl's own report decoding
# with an unrelated-looking TypeError, because pySHACL's validate() returns
# the ValidationFailure object itself as report_graph rather than raising it
# or producing a real Graph - see docs/pyshacl-upstream-issues.md's
# 2026-07-19 entry. Fixed with a defensive re-raise in
# starshacl/validator.py::validate(). test_malformed_custom_validator_raises_cleanly
# below locks in that fix.


def test_ask_based_custom_component_flags_violations() -> None:
    data = StarLayerGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice ex:score 80 .
        ex:bob ex:score 20 .
    """, format="turtle")

    shapes = StarLayerGraph()
    shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:MinScoreConstraintComponent a sh:ConstraintComponent ;
          sh:parameter [ sh:path ex:minScore ] ;
          sh:validator [
            a sh:SPARQLAskValidator ;
            sh:ask "ASK { FILTER (?value >= ?minScore) }" ;
          ] .
        ex:ScoreShape a sh:NodeShape ;
          sh:targetSubjectsOf ex:score ;
          sh:property [ sh:path ex:score ; ex:minScore 50 ] .
    """, format="turtle")

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is False
    assert "MinScoreConstraintComponent" in result.report_text
    assert "Focus Node: ex:bob" in result.report_text
    assert "Focus Node: ex:alice" not in result.report_text


def test_select_based_custom_component_flags_violations() -> None:
    data = StarLayerGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice ex:score 80 .
        ex:bob ex:score 20 .
    """, format="turtle")

    shapes = StarLayerGraph()
    shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:MinScoreConstraintComponent a sh:ConstraintComponent ;
          sh:parameter [ sh:path ex:minScore ] ;
          sh:propertyValidator [
            a sh:SPARQLSelectValidator ;
            sh:select "SELECT $this ?value WHERE { FILTER (?value < ?minScore) }" ;
          ] .
        ex:ScoreShape a sh:NodeShape ;
          sh:targetSubjectsOf ex:score ;
          sh:property [ sh:path ex:score ; ex:minScore 50 ] .
    """, format="turtle")

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is False
    assert "Value Node: Literal(\"20\"" in result.report_text


def test_ask_based_custom_component_over_rdf12_triple_term_value() -> None:
    data = StarLayerGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice ex:claims <<( ex:bob ex:age 42 )>> .
        ex:carol ex:claims ex:not_a_triple .
    """, format="turtle12")

    shapes = StarLayerGraph()
    shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:MustBeTripleTermComponent a sh:ConstraintComponent ;
          sh:parameter [ sh:path ex:mustBeTripleTerm ] ;
          sh:validator [
            a sh:SPARQLAskValidator ;
            sh:ask "ASK { FILTER (isTRIPLE(?value)) }" ;
          ] .
        ex:ClaimShape a sh:NodeShape ;
          sh:targetSubjectsOf ex:claims ;
          sh:property [ sh:path ex:claims ; ex:mustBeTripleTerm true ] .
    """, format="turtle")

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is False
    # ex:carol's plain-IRI value fails isTRIPLE(); ex:alice's real triple
    # term passes - confirms the custom validator's SPARQL 1.2 syntax gets
    # the same query rewriting sh:sparql/sh:construct already get.
    assert "Focus Node: ex:carol" in result.report_text
    assert "Focus Node: ex:alice" not in result.report_text


def test_malformed_custom_validator_raises_cleanly_not_a_confusing_typeerror() -> None:
    data = StarLayerGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice ex:score 80 .
    """, format="turtle")

    shapes = StarLayerGraph()
    shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:MinScoreConstraintComponent a sh:ConstraintComponent ;
          sh:parameter [ sh:path ex:minScore ] ;
          sh:propertyValidator [
            a sh:SPARQLSelectValidator ;
            sh:select "SELECT $this ?value WHERE { BIND($this AS ?this) FILTER (?value < ?minScore) }" ;
          ] .
        ex:ScoreShape a sh:NodeShape ; sh:targetSubjectsOf ex:score ;
          sh:property [ sh:path ex:score ; ex:minScore 50 ] .
    """, format="turtle")

    with pytest.raises(pyshacl.errors.ValidationFailure, match="pre-bound"):
        StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
