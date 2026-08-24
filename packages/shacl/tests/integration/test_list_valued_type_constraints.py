import pytest
from rdflib import Namespace
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl import StarShaclValidator

from ._shape_loader import load_shape

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")

# SHACL 1.2 generalizes sh:class/sh:datatype/sh:nodeKind to accept a SHACL
# list (union of choices), not just a single IRI. pySHACL 0.40 mishandles the
# list form the same way it mishandles path-valued property pairs: it treats
# the list blank node itself as if it were the single required value, which
# nothing ever matches, making every value spuriously fail. These tests
# confirm the native fix against the spec's own worked examples.


def _violation_components(result) -> list:
    return [o for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))]


def test_list_valued_class_conforms_for_any_listed_class() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_list_valued_class.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Tessie a ex:Cat .
            ex:Rusty a ex:Dog .
            ex:Alice a ex:Person ; ex:pet ex:Tessie, ex:Rusty .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_list_valued_class_violates_for_unlisted_class() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_list_valued_class.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Fluffy a ex:Unicorn .
            ex:Bob a ex:Person ; ex:pet ex:Fluffy .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert SH.ClassConstraintComponent in _violation_components(result)


def test_list_valued_datatype_conforms_for_string_and_lang_string() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_list_valued_datatype.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Estonia ex:label "Estonia", "Estland"@de .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_list_valued_datatype_violates_for_unlisted_datatype() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_list_valued_datatype.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Estonia ex:label "Estonia", 42 .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert SH.DatatypeConstraintComponent in _violation_components(result)


def test_list_valued_node_kind_conforms_for_iri_and_blank_node() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_list_valued_node_kind.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Bob ex:knows ex:Alice, _:john .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_list_valued_node_kind_violates_for_literal() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_list_valued_node_kind.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Bob ex:knows "Bob" .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert SH.NodeKindConstraintComponent in _violation_components(result)


# sh:TripleTerm as a list-valued sh:nodeKind member (rdf:reifies's own value
# type). Unlike the tests above, these run with meta_shacl left at its
# default (True) rather than meta_shacl=False - the constraint component
# itself already recognized sh:TripleTerm correctly, but starshacl's own
# meta-shapes well-formedness preflight (shacl12-validation-shapes.ttl's
# nodeKind-in replacement rule) rejected any shape using it before
# validation ever ran, since sh:TripleTerm wasn't in its allowed sh:in list.
# These tests would fail on that ReportableRuntimeError with the fix
# reverted, even though test_list_valued_node_kind_* above would still pass
# (they never exercise the meta-shacl path at all).

def test_triple_term_node_kind_conforms_for_real_triple_term() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_triple_term_node_kind.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
            ex:claim rdf:reifies <<( ex:bob ex:knows ex:carol )>> .
        """,
        format="turtle12",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes)

    assert result.conforms is True


def test_triple_term_node_kind_violates_for_non_triple_term() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_triple_term_node_kind.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
            ex:claim rdf:reifies ex:not_a_triple_term .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes)

    assert result.conforms is False
    assert SH.NodeKindConstraintComponent in _violation_components(result)


def test_simple_iri_valued_class_still_handled_by_pyshacl_directly() -> None:
    # Simple-IRI values (the pre-existing SHACL 1.0/1.1 form) must keep
    # working unchanged - only SHACL-list values are diverted natively.
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .
            ex:S a sh:NodeShape ;
              sh:targetNode ex:Bob ;
              sh:property [
                sh:path ex:address ;
                sh:class ex:PostalAddress ;
              ] .
        """,
        format="turtle",
    )

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Bob ex:address [ a ex:PostalAddress ] .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True
