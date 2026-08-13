"""Per-constraint sh:severity/sh:deactivated via RDF-1.2 inline reification
annotation (SHACL 1.2 Core) - distinct from, and finer-grained than, a
shape's own sh:severity/sh:deactivated (already handled generically by
pySHACL for every constraint). Found via the W3C SHACL 1.2 test suite's
severity-003/deactivated-003 fixtures.
"""

import pytest
from rdflib import Namespace

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayergraph_graph import StarLayerGraph

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")


def test_datatype_annotation_severity_overrides_shape_default() -> None:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:datatype xsd:integer {| sh:severity sh:Warning |} .
        """,
        format="turtle12",
    )
    data = StarLayerGraph()
    data.add((EX.alice, EX.dummy, EX.alice))  # focus node itself is the target; no extra data needed

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    severities = {o for _, _, o in result.report_graph.triples((None, SH.resultSeverity, None))}
    assert severities == {SH.Warning}


def test_datatype_annotation_deactivated_skips_that_constraint() -> None:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:datatype xsd:boolean {| sh:deactivated true |} .
        """,
        format="turtle12",
    )
    data = StarLayerGraph()
    data.add((EX.alice, EX.dummy, EX.alice))

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_property_reference_annotation_deactivated_skips_only_that_reference() -> None:
    """Deactivates one specific sh:property *reference*, not the referenced
    shape's own constraints generically - a shape referenced via a second,
    non-annotated sh:property elsewhere would still be checked there.
    """
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:property ex:RequiresProperty {| sh:deactivated true |} .
            ex:RequiresProperty a sh:PropertyShape ;
              sh:path ex:requiredProp ;
              sh:minCount 1 .
        """,
        format="turtle12",
    )
    data = StarLayerGraph()
    data.add((EX.alice, EX.dummy, EX.alice))  # no ex:requiredProp at all

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_property_reference_without_annotation_still_conforms_normally() -> None:
    # Confirms the annotation-filtering doesn't accidentally suppress a
    # genuinely non-deactivated sh:property reference.
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:property ex:RequiresProperty .
            ex:RequiresProperty a sh:PropertyShape ;
              sh:path ex:requiredProp ;
              sh:minCount 1 .
        """,
        format="turtle12",
    )
    data = StarLayerGraph()
    data.add((EX.alice, EX.dummy, EX.alice))

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert SH.MinCountConstraintComponent in {
        o for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
    }
