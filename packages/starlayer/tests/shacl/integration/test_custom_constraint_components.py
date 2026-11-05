import pytest
from rdflib import Namespace
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.shacl import ShapeError, StarShaclSchema

EX = Namespace("http://example.org/")

# User-defined, reusable SPARQL-based sh:ConstraintComponent (SHACL 1.2 SPARQL
# Extensions - https://www.w3.org/TR/shacl12-sparql/): a shapes graph can
# declare its own `a sh:ConstraintComponent` with sh:parameter/sh:validator
# (or sh:nodeValidator/sh:propertyValidator). ASK validators pre-bind $this and
# $value; SELECT validators pre-bind $this and the parameters only (Appendix A).
# A SELECT that assigns a pre-bound variable is an ill-formed shapes graph and
# raises ShapeError.


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

    result = StarShaclSchema(shacl_graph=shapes).validate(data_graph=data, meta_shacl=False)
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
            sh:select "SELECT $this ?value WHERE { $this $PATH ?value . FILTER (?value < $minScore) }" ;
          ] .
        ex:ScoreShape a sh:NodeShape ;
          sh:targetSubjectsOf ex:score ;
          sh:property [ sh:path ex:score ; ex:minScore 50 ] .
    """, format="turtle")

    result = StarShaclSchema(shacl_graph=shapes).validate(data_graph=data, meta_shacl=False)
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

    result = StarShaclSchema(shacl_graph=shapes).validate(data_graph=data, meta_shacl=False)
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

    with pytest.raises(ShapeError, match="pre-bound"):
        StarShaclSchema(shacl_graph=shapes).validate(data_graph=data, meta_shacl=False)
