import pytest
from rdflib import Namespace

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayergraph_graph import StarLayerGraph

from ._shape_loader import load_shape


EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")

# Mirrors the SHACL 1.2 Core spec's own examples for sh:subsetOf,
# sh:rootClass, and sh:uniqueValuesFor.


def _violation_components(result) -> list:
    return [o for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))]


def test_subset_of_conforms_when_value_is_among_comparison_path_values() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_subset_of.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Bob ex:child "Calvin", "Donald" ; ex:favoriteChild "Calvin" .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_subset_of_violates_when_value_is_not_among_comparison_path_values() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_subset_of.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Bob ex:child "Calvin", "Donald" ; ex:favoriteChild "Huey" .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert SH.SubsetOfConstraintComponent in _violation_components(result)


def test_subset_of_conforms_with_compound_sequence_path_comparison() -> None:
    # sh:subsetOf's own comparison argument can be any SHACL property path,
    # not just a simple IRI - here a sequence path ( ex:p1 ex:p2 ), matching
    # the W3C SHACL 1.2 test suite's subsetOf-002 fixture shape.
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:ParentShape a sh:NodeShape ;
              sh:targetNode ex:Alice ;
              sh:property ex:ParentShape-favoriteChild .
            ex:ParentShape-favoriteChild a sh:PropertyShape ;
              sh:path ex:favoriteChild ;
              sh:subsetOf ( ex:p1 ex:p2 ) .
        """,
        format="turtle",
    )

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Alice ex:favoriteChild ex:Grandkid ; ex:p1 ex:Middle .
            ex:Middle ex:p2 ex:Grandkid .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_subset_of_violates_with_compound_sequence_path_comparison() -> None:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:ParentShape a sh:NodeShape ;
              sh:targetNode ex:Alice ;
              sh:property ex:ParentShape-favoriteChild .
            ex:ParentShape-favoriteChild a sh:PropertyShape ;
              sh:path ex:favoriteChild ;
              sh:subsetOf ( ex:p1 ex:p2 ) .
        """,
        format="turtle",
    )

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Alice ex:favoriteChild ex:Stranger ; ex:p1 ex:Middle .
            ex:Middle ex:p2 ex:Grandkid .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert SH.SubsetOfConstraintComponent in _violation_components(result)


def test_root_class_conforms_for_self_and_transitive_subclass() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_root_class.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:Animal a rdfs:Class .
            ex:Mammal rdfs:subClassOf ex:Animal .
            ex:Dog rdfs:subClassOf ex:Mammal .
            ex:Zoo ex:holds ex:Dog, ex:Animal .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_root_class_violates_for_unrelated_class() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_root_class.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:Animal a rdfs:Class .
            ex:Mammal rdfs:subClassOf ex:Animal .
            ex:Dog rdfs:subClassOf ex:Mammal .
            ex:Plant rdfs:subClassOf ex:Organism .
            ex:Zoo ex:holds ex:Dog, ex:Animal, ex:Plant .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert SH.RootClassConstraintComponent in _violation_components(result)


def test_unique_values_for_flags_only_duplicates_among_target_nodes() -> None:
    # Matches the spec's own worked example exactly: Record2/Record3 both
    # violate (duplicate "Two"), Record1 does not (its "One" is only
    # duplicated by ex:UnrelatedNode, which isn't a target of this shape).
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_unique_values_for.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Record1 a ex:Record ; ex:id "One" .
            ex:UnrelatedNode ex:id "One" .
            ex:Record2 a ex:Record ; ex:id "Two" .
            ex:Record3 a ex:Record ; ex:id "Two" .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    violations = _violation_components(result)
    assert violations == [SH.UniqueValuesForConstraintComponent, SH.UniqueValuesForConstraintComponent]
    violating_focus_nodes = {o for _, _, o in result.report_graph.triples((None, SH.focusNode, None))}
    assert violating_focus_nodes == {EX.Record2, EX.Record3}
