import pytest
from rdflib import Namespace
from rdflib.collection import Collection

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayer_graph import StarLayerGraph

from ._shape_loader import load_shape


EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")


pyshacl = pytest.importorskip("pyshacl")


def test_rdf12_fixture_target_resolution_for_triple_term_target_node() -> None:
    data = StarLayerGraph()

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rdf12_target_node_shape.ttl"), format="turtle12")
    shapes.add((EX.TripleTargetShape, SH.targetNode, (EX.s, EX.p, EX.o)))

    validator = StarShaclValidator()
    nodes = validator.target_nodes(data_graph=data, shacl_graph=shapes, shape_node=EX.TripleTargetShape)

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

    validator = StarShaclValidator()
    nodes = validator.target_nodes(data_graph=data, shacl_graph=shapes, shape_node=EX.S)

    assert nodes == ((EX.bob, EX.knows, EX.carol),)


def test_rdf12_fixture_triple_term_node_kind_component_evaluation() -> None:
    data = StarLayerGraph()
    data.add((EX.focus, EX.says, (EX.s, EX.p, EX.o)))
    data.add((EX.focus, EX.says, EX.not_tt))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rdf12_triple_term_node_kind.ttl"), format="turtle12")

    property_shape = next(shapes.objects(EX.TripleTermNodeKindShape, SH.property))
    component_name = str(next(shapes.objects(property_shape, SH.nodeKind)))
    values = tuple(o for _, _, o in data.triples((EX.focus, EX.says, None)))

    validator = StarShaclValidator()
    result = validator.evaluate_component(
        component={"name": component_name},
        focus_node=EX.focus,
        value_nodes=values,
    )

    assert result.conforms is False
    assert EX.not_tt in result.violations


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

            ex:focus ex:says << ex:a ex:p ex:b >>, ex:not_tt .
            ex:focus ex:other ex:not_tt .
        """,
        format="turtle12",
    )

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape(shape_file), format="turtle12")

    property_shape = next(shapes.objects(shape_iri, SH.property))
    path = next(shapes.objects(property_shape, SH.path))
    values = tuple(o for _, _, o in data.triples((EX.focus, path, None)))

    component: dict[str, object]
    has_value = next(shapes.objects(property_shape, SH.hasValue), None)
    in_list = next(shapes.objects(property_shape, SH["in"]), None)
    equals_path = next(shapes.objects(property_shape, SH.equals), None)
    disjoint_path = next(shapes.objects(property_shape, SH.disjoint), None)

    if has_value is not None:
        component = {"name": "hasValue", "value": has_value}
    elif in_list is not None:
        component = {"name": "in", "allowed": tuple(Collection(shapes, in_list))}
    elif equals_path is not None:
        component = {
            "name": "equals",
            "other_values": tuple(o for _, _, o in data.triples((EX.focus, equals_path, None))),
        }
    elif disjoint_path is not None:
        component = {
            "name": "disjoint",
            "other_values": tuple(o for _, _, o in data.triples((EX.focus, disjoint_path, None))),
        }
    else:
        raise AssertionError("fixture must declare one structural component constraint")

    validator = StarShaclValidator()
    result = validator.evaluate_component(
        component=component,
        focus_node=EX.focus,
        value_nodes=values,
    )

    assert result.conforms is expected_conforms
    if not expected_conforms:
        assert len(result.violations) >= 1


# The tests above exercise starShacl's own native structural-component
# evaluator directly (evaluate_component) for the four families it natively
# supports (sh:hasValue/sh:in/sh:equals/sh:disjoint). sh:minCount/sh:maxCount
# and sh:not/sh:and/sh:or aren't part of that native evaluator's component
# set - they run through the generic pySHACL-encoded fallback path instead
# (validator.validate(), not evaluate_component()). These confirm that
# fallback path also correctly handles triple-term values for additional
# constraint families beyond the four already covered, per the gap matrix's
# "broader lifecycle orchestration" note - not a claim that these have been
# promoted into the native fast-path evaluator.


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

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
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

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
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

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    # The one value present DOES match the forbidden triple-term value, so
    # sh:not must flag it.
    assert result.conforms is False
    assert any(
        o == SH.NotConstraintComponent
        for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
    )
