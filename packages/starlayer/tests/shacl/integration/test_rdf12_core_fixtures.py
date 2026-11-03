import pytest
from rdflib import Namespace
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl import StarShaclSchema

from ._shape_loader import load_shape

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")


def test_rdf12_fixture_target_resolution_for_triple_term_target_node() -> None:
    data = StarLayerGraph()

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rdf12_target_node_shape.ttl"), format="turtle12")
    shapes.add((EX.TripleTargetShape, SH.targetNode, (EX.s, EX.p, EX.o)))

    validator = StarShaclSchema(shacl_graph=shapes)
    nodes = validator.target_nodes(data_graph=data, shape_node=EX.TripleTargetShape)

    assert nodes == ((EX.s, EX.p, EX.o),)


def test_rdf12_target_objects_of_resolves_triple_term_value_as_target() -> None:
    # sh:targetObjectsOf ex:says: a triple term is a perfectly valid object
    # position value, so it must resolve as a genuine target/focus node here
    # too - not just the already-tested explicit sh:targetNode case.
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetObjectsOf ex:says .
        """,
        format="turtle",
    )

    validator = StarShaclSchema(shacl_graph=shapes)
    nodes = validator.target_nodes(data_graph=data, shape_node=EX.S)

    assert nodes == ((EX.bob, EX.knows, EX.carol),)


def test_rdf12_fixture_triple_term_node_kind_component_evaluation() -> None:
    data = StarLayerGraph()
    data.add((EX.focus, EX.says, (EX.s, EX.p, EX.o)))
    data.add((EX.focus, EX.says, EX.not_tt))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rdf12_triple_term_node_kind.ttl"), format="turtle12")

    result = StarShaclSchema(shacl_graph=shapes).validate(data_graph=data, meta_shacl=False)

    assert result.conforms is False
    values = {o for _, _, o in result.report_graph.triples((None, SH.value, None))}
    assert values == {EX.not_tt}


@pytest.mark.parametrize(
    "shape_file,shape_iri,expected_conforms",
    [
        (
            "rdf12_has_value_shape.ttl",
            EX.HasValueShape,
            True,
        ),
        (
            "rdf12_in_shape.ttl",
            EX.InShape12,
            False,
        ),
        (
            "rdf12_equals_shape.ttl",
            EX.EqualsShape12,
            False,
        ),
        (
            "rdf12_disjoint_shape.ttl",
            EX.DisjointShape12,
            False,
        ),
    ],
)
def test_rdf12_fixture_structural_component_behaviors(
    shape_file: str,
    shape_iri: object,
    expected_conforms: bool,
) -> None:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .

            ex:focus ex:says <<( ex:a ex:p ex:b )>>, ex:not_tt .
            ex:focus ex:other ex:not_tt .
        """,
        format="turtle12",
    )

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape(shape_file), format="turtle12")

    result = StarShaclSchema(shacl_graph=shapes).validate(data_graph=data, meta_shacl=False)

    assert result.conforms is expected_conforms
    if not expected_conforms:
        assert len(list(result.report_graph.triples((None, SH.focusNode, EX.focus)))) >= 1


# sh:minCount/sh:maxCount and sh:not with triple-term values.


def test_rdf12_min_max_count_with_triple_term_values() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))
    data.add((EX.alice, EX.says, (EX.bob, EX.likes, EX.dave)))

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:property [ sh:path ex:says ; sh:minCount 2 ; sh:maxCount 2 ] .
        """,
        format="turtle",
    )

    validator = StarShaclSchema(shacl_graph=shapes)
    result = validator.validate(data_graph=data, meta_shacl=False)
    assert result.conforms is True


def test_rdf12_max_count_violates_with_too_many_triple_term_values() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))
    data.add((EX.alice, EX.says, (EX.bob, EX.likes, EX.dave)))

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:property [ sh:path ex:says ; sh:maxCount 1 ] .
        """,
        format="turtle",
    )

    validator = StarShaclSchema(shacl_graph=shapes)
    result = validator.validate(data_graph=data, meta_shacl=False)
    assert result.conforms is False
    assert any(
        o == SH.MaxCountConstraintComponent
        for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
    )


def test_rdf12_not_wrapping_has_value_with_triple_term_value() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:property [
                sh:path ex:says ;
                sh:not [ sh:hasValue <<( ex:bob ex:knows ex:carol )>> ] ;
              ] .
        """,
        format="turtle12",
    )

    validator = StarShaclSchema(shacl_graph=shapes)
    result = validator.validate(data_graph=data, meta_shacl=False)
    # The one value present DOES match the forbidden triple-term value, so
    # sh:not must flag it.
    assert result.conforms is False
    assert any(
        o == SH.NotConstraintComponent
        for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
    )
