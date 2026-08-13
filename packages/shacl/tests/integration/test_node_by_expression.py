"""sh:nodeByExpression (SHACL 1.2 Core): like sh:node, but the referenced
shape is computed via a node expression rather than given directly. Found
missing entirely via the W3C SHACL 1.2 test suite's nodeByExpression-001
fixtures (at both node-shape and property-shape level) - pySHACL has no
notion of this predicate at all.
"""

import pytest
from rdflib import Namespace

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayergraph_graph import StarLayerGraph

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")


def test_node_by_expression_at_node_shape_violates_when_value_does_not_conform() -> None:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:TestClass a sh:NodeShape ;
              sh:targetClass ex:TestClass ;
              sh:nodeByExpression ex:TestNodeShape .
            ex:TestNodeShape a sh:NodeShape ;
              sh:class ex:OtherClass .
        """,
        format="turtle12",
    )
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Invalid a ex:TestClass .
            ex:Valid a ex:TestClass, ex:OtherClass .
        """,
        format="turtle12",
    )

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert {o for _, _, o in result.report_graph.triples((None, SH.focusNode, None))} == {EX.Invalid}
    assert {o for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))} == {
        SH.NodeByExpressionConstraintComponent
    }
    assert {o for _, _, o in result.report_graph.triples((None, SH.sourceConstraint, None))} == {EX.TestNodeShape}


def test_node_by_expression_at_property_shape_violates_when_value_does_not_conform() -> None:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:Issue a sh:NodeShape ;
              sh:targetClass ex:Issue ;
              sh:property ex:Issue-assignedTo .
            ex:Issue-assignedTo sh:path ex:assignedTo ;
              sh:nodeByExpression ex:AssignedToShape .
            ex:AssignedToShape a sh:NodeShape ;
              sh:property [ sh:path ex:email ; sh:minCount 1 ] .
        """,
        format="turtle12",
    )
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Issue1 a ex:Issue ; ex:assignedTo ex:PersonWithoutEmail .
            ex:Issue2 a ex:Issue ; ex:assignedTo ex:PersonWithEmail .
            ex:PersonWithEmail ex:email "person@example.org" .
        """,
        format="turtle12",
    )

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert {o for _, _, o in result.report_graph.triples((None, SH.focusNode, None))} == {EX.Issue1}
    assert {o for _, _, o in result.report_graph.triples((None, SH.value, None))} == {EX.PersonWithoutEmail}
    assert {o for _, _, o in result.report_graph.triples((None, SH.sourceConstraint, None))} == {EX.AssignedToShape}


def test_node_by_expression_conforms_when_value_conforms() -> None:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:TestClass a sh:NodeShape ;
              sh:targetClass ex:TestClass ;
              sh:nodeByExpression ex:TestNodeShape .
            ex:TestNodeShape a sh:NodeShape ;
              sh:class ex:OtherClass .
        """,
        format="turtle12",
    )
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Valid a ex:TestClass, ex:OtherClass .
        """,
        format="turtle12",
    )

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True
