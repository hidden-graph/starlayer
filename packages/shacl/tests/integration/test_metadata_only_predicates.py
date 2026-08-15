import pytest
from rdflib import Namespace

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayer_graph import StarLayerGraph

EX = Namespace("http://example.org/")

pyshacl = pytest.importorskip("pyshacl")

# docs/shacl12-gap-matrix.md marks sh:agentInstruction/sh:intent/sh:unit/
# sh:order as "n/a - metadata-only, no validation effect" - but that status
# was never backed by a regression test confirming they're actually inert
# (as opposed to accidentally rejected by the meta-shacl preflight, or
# tripping some unrelated crash). Found via a test-coverage audit; mirrors
# test_shacl_ui_compatibility.py's confirmed-inert pattern for shui:
# annotations.


def _shapes_with_metadata_only_annotations() -> str:
    return """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:PersonShape a sh:NodeShape ;
          sh:targetClass ex:Person ;
          sh:property [
            sh:path ex:heightCm ;
            sh:minCount 1 ;
            sh:datatype <http://www.w3.org/2001/XMLSchema#integer> ;
            sh:name "Height" ;
            sh:order 1 ;
            sh:unit <http://qudt.org/vocab/unit/CentiM> ;
            sh:agentInstruction "Ask the user for their height in centimeters." ;
            sh:intent "Used to size default clothing recommendations." ;
          ] .
    """


def test_metadata_only_predicates_do_not_interfere_with_validation() -> None:
    data = StarLayerGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Person ; ex:heightCm 170 .
        ex:bob a ex:Person .
    """, format="turtle")

    shapes = StarLayerGraph()
    shapes.parse(data=_shapes_with_metadata_only_annotations(), format="turtle")

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is False
    assert "ex:bob" in result.report_text
    assert "ex:alice" not in result.report_text.split("Focus Node:")[-1]


def test_metadata_only_predicates_do_not_break_meta_shacl_preflight() -> None:
    data = StarLayerGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Person ; ex:heightCm 170 .
    """, format="turtle")

    shapes = StarLayerGraph()
    shapes.parse(data=_shapes_with_metadata_only_annotations(), format="turtle")

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=True)
    assert result.conforms is True


def test_conforms_to_shapes_graph_does_not_interfere_with_validation() -> None:
    """sh:conformsToShapesGraph (SHACL 1.2 Core section 6.6.1, added to the
    published spec 2026-08-03 - see docs/shacl12-gap-matrix.md) is a
    data-graph-level self-descriptive assertion (domain sh:DataGraph, range
    sh:ShapesGraph) - unlike the shape-level annotations above, this one
    lives in the *data* graph, not the shapes graph, so it's a distinct
    inert-metadata case worth its own regression test rather than assuming
    the shape-annotation coverage above extends to it.
    """
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:MyDataGraph a sh:DataGraph ;
              sh:conformsToShapesGraph ex:MyShapesGraph .
            ex:alice a ex:Person ; ex:heightCm 170 .
            ex:bob a ex:Person .
        """,
        format="turtle",
    )

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:PersonShape a sh:NodeShape ;
              sh:targetClass ex:Person ;
              sh:property [ sh:path ex:heightCm ; sh:minCount 1 ; sh:datatype xsd:integer ] .
        """,
        format="turtle",
    )

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=True)
    assert result.conforms is False
    assert "ex:bob" in result.report_text
    assert "ex:alice" not in result.report_text.split("Focus Node:")[-1]


def test_metadata_only_predicates_do_not_interfere_with_rule_application() -> None:
    data = StarLayerGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice ex:parent ex:carol .
    """, format="turtle")

    shapes = StarLayerGraph()
    shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:R a sh:NodeShape ;
          sh:targetSubjectsOf ex:parent ;
          sh:property [
            sh:path ex:parent ;
            sh:unit <http://qudt.org/vocab/unit/CentiM> ;
            sh:agentInstruction "Not relevant to this rule." ;
            sh:intent "Regression coverage only." ;
          ] ;
          sh:rule [
            a sh:TripleRule ;
            sh:subject sh:this ; sh:predicate ex:hasParent ; sh:object [ sh:path ex:parent ] ;
          ] .
    """, format="turtle")

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes)
    assert result.conforms is True
    derived = list(result.data_graph.triples((EX.alice, EX.hasParent, None)))
    assert derived == [(EX.alice, EX.hasParent, EX.carol)]
