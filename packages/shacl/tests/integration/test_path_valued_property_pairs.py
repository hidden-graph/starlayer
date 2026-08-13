import pytest
from rdflib import Namespace

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayer_graph import StarLayerGraph

from ._shape_loader import load_shape


EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")

# SHACL 1.2 generalizes sh:equals/sh:disjoint/sh:lessThan/sh:lessThanOrEquals
# to accept a full property path, not just a simple predicate IRI. pySHACL
# 0.40 doesn't evaluate a complex path here at all - it silently treats it as
# resolving to an empty node set, which makes sh:equals spuriously fail
# (nothing is "in" an empty set) and sh:disjoint/sh:lessThan/
# sh:lessThanOrEquals spuriously pass (nothing overlaps with, or compares
# unfavorably against, an empty set). These tests confirm the native fix,
# not just new behavior - each has a case that pySHACL alone gets wrong.


def _violation_components(result) -> list:
    return [o for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))]


def test_path_valued_equals_conforms_via_sequence_path() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_path_valued_equals.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice ex:hasFriend ex:bob ; ex:knowsIndirectly ex:carol .
            ex:bob ex:hasFriend ex:carol .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_path_valued_equals_violates_on_mismatch() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_path_valued_equals.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice ex:hasFriend ex:bob ; ex:knowsIndirectly ex:dave .
            ex:bob ex:hasFriend ex:carol .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert SH.EqualsConstraintComponent in _violation_components(result)


def test_path_valued_disjoint_violates_when_paths_overlap() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_path_valued_disjoint.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice ex:knows ex:carol ; ex:hasFriend ex:bob .
            ex:bob ex:hasFriend ex:carol .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert SH.DisjointConstraintComponent in _violation_components(result)


def test_path_valued_disjoint_conforms_when_no_overlap() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_path_valued_disjoint.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice ex:knows ex:dave ; ex:hasFriend ex:bob .
            ex:bob ex:hasFriend ex:carol .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_path_valued_less_than_or_equals_conforms() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_path_valued_less_than_or_equals.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:meeting1 ex:startTime 5 ; ex:relatedEvent ex:meeting2 .
            ex:meeting2 ex:endTime 10 .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_path_valued_less_than_or_equals_allows_equal_values() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_path_valued_less_than_or_equals.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:meeting1 ex:startTime 10 ; ex:relatedEvent ex:meeting2 .
            ex:meeting2 ex:endTime 10 .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_path_valued_less_than_or_equals_violates() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_path_valued_less_than_or_equals.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:meeting1 ex:startTime 15 ; ex:relatedEvent ex:meeting2 .
            ex:meeting2 ex:endTime 10 .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert SH.LessThanOrEqualsConstraintComponent in _violation_components(result)


def test_simple_iri_valued_equals_still_handled_by_pyshacl_directly() -> None:
    # Simple-IRI values (the pre-existing SHACL 1.0/1.1 form) must keep
    # working unchanged - only complex paths are diverted to the native pass.
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .
            ex:S a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path ex:nickname ;
                sh:equals ex:alias ;
              ] .
        """,
        format="turtle",
    )

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice ex:nickname "Ally" ; ex:alias "Ally" .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True
