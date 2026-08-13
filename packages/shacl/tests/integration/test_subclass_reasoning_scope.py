import pytest
from rdflib import Namespace

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayergraph_graph import StarLayerGraph


EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")

# SHACL 1.2 Core's "SHACL Type" definition (Issue 185, changelog: "Added
# parameter to look up rdfs:subClassOf triples in the union of the shapes
# graph and the data graph") notes implementations MAY be parameterized to
# also read rdfs:subClassOf from the shapes graph, not just the data graph.
# starshacl exposes this as an opt-in validate() keyword,
# rdfs_subclass_reasoning_includes_shapes_graph, consulted by the native
# sh:rootClass and list-valued sh:class passes (both use
# _is_subclass_of_or_self).


def _shapes_with_root_class_and_shapes_graph_subclass_assertion() -> StarLayerGraph:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

            # This rdfs:subClassOf assertion lives only in the SHAPES graph.
            ex:Lion rdfs:subClassOf ex:Animal .

            ex:S a sh:NodeShape ;
              sh:targetNode ex:Zoo ;
              sh:property [
                sh:path ex:holds ;
                sh:rootClass ex:Animal ;
              ] .
        """,
        format="turtle",
    )
    return shapes


def _data_zoo_holds_lion() -> StarLayerGraph:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Zoo ex:holds ex:Lion .
        """,
        format="turtle",
    )
    return data


def test_root_class_ignores_shapes_graph_subclass_assertion_by_default() -> None:
    validator = StarShaclValidator()
    result = validator.validate(
        data_graph=_data_zoo_holds_lion(),
        shacl_graph=_shapes_with_root_class_and_shapes_graph_subclass_assertion(),
        meta_shacl=False,
    )

    assert result.conforms is False


def test_root_class_honors_shapes_graph_subclass_assertion_when_opted_in() -> None:
    validator = StarShaclValidator()
    result = validator.validate(
        data_graph=_data_zoo_holds_lion(),
        shacl_graph=_shapes_with_root_class_and_shapes_graph_subclass_assertion(),
        meta_shacl=False,
        rdfs_subclass_reasoning_includes_shapes_graph=True,
    )

    assert result.conforms is True


def _shapes_with_list_valued_class_and_shapes_graph_subclass_assertion() -> StarLayerGraph:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

            # This rdfs:subClassOf assertion lives only in the SHAPES graph.
            ex:Tiger rdfs:subClassOf ex:Cat .

            ex:S a sh:NodeShape ;
              sh:targetClass ex:Person ;
              sh:property [
                sh:path ex:pet ;
                sh:class ( ex:Cat ex:Dog ) ;
              ] .
        """,
        format="turtle",
    )
    return shapes


def _data_alice_has_tiger() -> StarLayerGraph:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Tiggy a ex:Tiger .
            ex:Alice a ex:Person ; ex:pet ex:Tiggy .
        """,
        format="turtle",
    )
    return data


def test_list_valued_class_ignores_shapes_graph_subclass_assertion_by_default() -> None:
    validator = StarShaclValidator()
    result = validator.validate(
        data_graph=_data_alice_has_tiger(),
        shacl_graph=_shapes_with_list_valued_class_and_shapes_graph_subclass_assertion(),
        meta_shacl=False,
    )

    assert result.conforms is False


def test_list_valued_class_honors_shapes_graph_subclass_assertion_when_opted_in() -> None:
    validator = StarShaclValidator()
    result = validator.validate(
        data_graph=_data_alice_has_tiger(),
        shacl_graph=_shapes_with_list_valued_class_and_shapes_graph_subclass_assertion(),
        meta_shacl=False,
        rdfs_subclass_reasoning_includes_shapes_graph=True,
    )

    assert result.conforms is True
