import pytest
from rdflib import Namespace

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayergraph_graph import StarLayerGraph

EX = Namespace("http://example.org/")

pyshacl = pytest.importorskip("pyshacl")

# SHACL 1.2 User Interfaces (https://www.w3.org/TR/shacl12-ui/, shui: =
# http://www.w3.org/ns/shacl-ui#) defines a widget/editor/viewer vocabulary
# for form generation - confirmed (via the spec's own scope statement) to be
# entirely orthogonal to SHACL validation: no new constraint types, no new
# validation semantics, nothing a validation/rules engine needs to
# implement. What IS in scope for starShacl: confirming shui: annotations
# on a shapes graph (shui:editor/shui:viewer/shui:propertyRole, referencing
# built-in widget instances like shui:DatePickerEditor) don't interfere with
# validate()/apply_rules()/the meta-shacl preflight - they should pass
# through as inert, unrecognized triples, the same way sh:order/sh:group
# already do.
#
# The widget-*selection* algorithm itself (shui:WidgetScore/
# shui:WidgetAcceptMatcher) is a genuinely separate, optional feature - not
# built here; see docs/shacl12-gap-matrix.md's "Not Covered / Deferred"
# section.


def _shapes_with_shui_annotations() -> str:
    return """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
        ex:PersonShape a sh:NodeShape ;
          sh:targetClass ex:Person ;
          sh:property [
            sh:path ex:birthDate ;
            sh:minCount 1 ;
            sh:datatype <http://www.w3.org/2001/XMLSchema#date> ;
            sh:name "Birth Date" ;
            sh:order 1 ;
            shui:editor shui:DatePickerEditor ;
            shui:viewer shui:LabelViewer ;
            shui:propertyRole shui:LabelRole ;
          ] .
    """


def test_shui_annotations_do_not_interfere_with_validation() -> None:
    data = StarLayerGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Person ; ex:birthDate "1990-01-01"^^<http://www.w3.org/2001/XMLSchema#date> .
        ex:bob a ex:Person .
    """, format="turtle")

    shapes = StarLayerGraph()
    shapes.parse(data=_shapes_with_shui_annotations(), format="turtle")

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is False
    assert "ex:bob" in result.report_text
    assert "ex:alice" not in result.report_text.split("Focus Node:")[-1]


def test_shui_annotations_do_not_break_meta_shacl_preflight() -> None:
    data = StarLayerGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Person ; ex:birthDate "1990-01-01"^^<http://www.w3.org/2001/XMLSchema#date> .
    """, format="turtle")

    shapes = StarLayerGraph()
    shapes.parse(data=_shapes_with_shui_annotations(), format="turtle")

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=True)
    assert result.conforms is True


def test_shui_annotations_do_not_interfere_with_rule_application() -> None:
    data = StarLayerGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice ex:parent ex:carol .
    """, format="turtle")

    shapes = StarLayerGraph()
    shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
        ex:R a sh:NodeShape ;
          sh:targetSubjectsOf ex:parent ;
          sh:property [ sh:path ex:parent ; shui:editor shui:InstancesSelectEditor ] ;
          sh:rule [
            a sh:TripleRule ;
            sh:subject sh:this ; sh:predicate ex:hasParent ; sh:object [ sh:path ex:parent ] ;
          ] .
    """, format="turtle")

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes)
    assert result.conforms is True
    derived = list(result.data_graph.triples((EX.alice, EX.hasParent, None)))
    assert derived == [(EX.alice, EX.hasParent, EX.carol)]


def test_shui_annotations_do_not_interfere_with_rdf12_triple_term_data() -> None:
    data = StarLayerGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice ex:claims <<( ex:bob ex:age 42 )>> .
    """, format="turtle12")

    shapes = StarLayerGraph()
    shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
        ex:S a sh:NodeShape ; sh:targetSubjectsOf ex:claims ;
          sh:property [ sh:path ex:claims ; sh:minCount 1 ; shui:viewer shui:DetailsViewer ] .
    """, format="turtle")

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=True)
    assert result.conforms is True
