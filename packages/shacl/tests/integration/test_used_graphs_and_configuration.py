import pytest
from rdflib import Literal, Namespace, URIRef
from rdflib.namespace import RDF
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl import StarShaclValidator

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")

# SHACL 1.2 Core sections 6.7.1.5-6.7.1.8 (added to the published spec
# 2026-08-03, found via a spec-drift audit - see docs/shacl12-gap-matrix.md)
# add sh:usedDataGraph/sh:usedShapesGraph/sh:usedConfiguration/
# sh:ProcessorConfiguration to the validation report vocabulary: all
# optional (MAY) provenance metadata a processor can choose to populate.
# sh:usedDataGraph/sh:usedShapesGraph need the caller to supply IRI identity
# for graphs that are normally anonymous in-memory rdflib.Graphs - no
# default/invented IRI. sh:usedConfiguration/sh:ProcessorConfiguration is
# opt-in (include_used_configuration=True) since the spec leaves its
# properties fully undefined - an empty blank node by default on every
# report would be pure noise.


def _valid_data() -> StarLayerGraph:
    data = StarLayerGraph()
    data.add((EX.alice, EX.age, Literal(30)))
    return data


def _shapes() -> StarLayerGraph:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:S a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [ sh:path ex:age ; sh:datatype xsd:integer ] .
        """,
        format="turtle",
    )
    return shapes


def test_used_data_graph_and_shapes_graph_absent_by_default() -> None:
    validator = StarShaclValidator()
    result = validator.validate(data_graph=_valid_data(), shacl_graph=_shapes(), meta_shacl=False)

    assert list(result.report_graph.triples((None, SH.usedDataGraph, None))) == []
    assert list(result.report_graph.triples((None, SH.usedShapesGraph, None))) == []


def test_used_data_graph_and_shapes_graph_added_when_iris_supplied() -> None:
    validator = StarShaclValidator()
    result = validator.validate(
        data_graph=_valid_data(),
        shacl_graph=_shapes(),
        meta_shacl=False,
        data_graph_iri="http://example.org/graphs/data1",
        shapes_graph_iri="http://example.org/graphs/shapes1",
    )

    report_node = next(result.report_graph.subjects(RDF.type, SH.ValidationReport))
    assert (report_node, SH.usedDataGraph, URIRef("http://example.org/graphs/data1")) in result.report_graph
    assert (report_node, SH.usedShapesGraph, URIRef("http://example.org/graphs/shapes1")) in result.report_graph


def test_used_data_graph_accepts_a_real_uriref_and_versioned_literal() -> None:
    # The spec explicitly allows "the version IRI of a data/shapes graph"
    # as a value too - a Literal in the general case, not always a URIRef.
    validator = StarShaclValidator()
    result = validator.validate(
        data_graph=_valid_data(),
        shacl_graph=_shapes(),
        meta_shacl=False,
        data_graph_iri=URIRef("http://example.org/graphs/data1"),
        shapes_graph_iri=Literal("http://example.org/graphs/shapes1#v2"),
    )

    report_node = next(result.report_graph.subjects(RDF.type, SH.ValidationReport))
    assert (report_node, SH.usedDataGraph, URIRef("http://example.org/graphs/data1")) in result.report_graph
    assert (
        report_node,
        SH.usedShapesGraph,
        Literal("http://example.org/graphs/shapes1#v2"),
    ) in result.report_graph


def test_used_configuration_absent_by_default() -> None:
    validator = StarShaclValidator()
    result = validator.validate(data_graph=_valid_data(), shacl_graph=_shapes(), meta_shacl=False)

    assert list(result.report_graph.triples((None, SH.usedConfiguration, None))) == []
    assert list(result.report_graph.triples((None, RDF.type, SH.ProcessorConfiguration))) == []


def test_used_configuration_added_when_opted_in() -> None:
    validator = StarShaclValidator()
    result = validator.validate(
        data_graph=_valid_data(),
        shacl_graph=_shapes(),
        meta_shacl=False,
        include_used_configuration=True,
    )

    report_node = next(result.report_graph.subjects(RDF.type, SH.ValidationReport))
    config_nodes = list(result.report_graph.objects(report_node, SH.usedConfiguration))
    assert len(config_nodes) == 1
    assert (config_nodes[0], RDF.type, SH.ProcessorConfiguration) in result.report_graph


def test_used_data_graph_and_shapes_graph_work_through_apply_rules() -> None:
    # apply_rules() forwards arbitrary kwargs through to validate() via
    # resolve_profile_options/**options - confirm that path actually
    # reaches the new named parameters, not just validate() called directly.
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:R a sh:NodeShape ;
              sh:targetSubjectsOf ex:parent ;
              sh:rule [
                a sh:TripleRule ;
                sh:subject sh:this ; sh:predicate ex:hasParent ; sh:object [ sh:path ex:parent ] ;
              ] .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.add((EX.alice, EX.parent, EX.carol))

    validator = StarShaclValidator()
    result = validator.apply_rules(
        data_graph=data,
        shacl_graph=shapes,
        data_graph_iri="http://example.org/graphs/data1",
    )

    report_node = next(result.report_graph.subjects(RDF.type, SH.ValidationReport))
    assert (report_node, SH.usedDataGraph, URIRef("http://example.org/graphs/data1")) in result.report_graph
