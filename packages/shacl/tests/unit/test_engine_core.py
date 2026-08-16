from rdflib import Literal, Namespace
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl.engine import (
    STSH,
    ComponentRequest,
    build_report,
    evaluate_component,
    target_nodes,
)

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")


def test_target_nodes_returns_triple_term_target() -> None:
    data = StarLayerGraph()
    shapes = StarLayerGraph()
    shape = EX.Shape
    target = (EX.s, EX.p, EX.o)

    shapes.add((shape, SH.targetNode, target))

    result = target_nodes(data_graph=data, shacl_graph=shapes, shape_node=shape)

    assert result == (target,)


def test_target_nodes_supports_target_class_subjects_of_objects_of() -> None:
    data = StarLayerGraph()
    shapes = StarLayerGraph()
    shape = EX.Shape

    data.add((EX.alice, SH.type, EX.Person))
    data.add((EX.alice, EX.knows, EX.bob))
    data.add((EX.carol, EX.mentions, EX.alice))

    shapes.add((shape, SH.targetClass, EX.Person))
    shapes.add((shape, SH.targetSubjectsOf, EX.knows))
    shapes.add((shape, SH.targetObjectsOf, EX.mentions))

    result = target_nodes(data_graph=data, shacl_graph=shapes, shape_node=shape)

    assert EX.alice in result
    assert len(result) == 1


def test_evaluate_component_triple_term_node_kind() -> None:
    request = ComponentRequest(
        component={"name": STSH.TripleTermNodeKind},
        focus_node=EX.focus,
        value_nodes=((EX.s, EX.p, EX.o), EX.not_tt),
    )

    result = evaluate_component(request)

    assert result.conforms is False
    assert result.violations == (EX.not_tt,)


def test_evaluate_component_structural_has_value() -> None:
    request = ComponentRequest(
        component={"name": "hasValue", "value": (EX.a, EX.p, (EX.b, EX.p, EX.c))},
        focus_node=EX.focus,
        value_nodes=((EX.a, EX.p, (EX.b, EX.p, EX.c)),),
    )

    result = evaluate_component(request)

    assert result.conforms is True


def test_evaluate_component_in_equals_disjoint() -> None:
    in_request = ComponentRequest(
        component={"name": "in", "allowed": ((EX.a, EX.p, EX.b),)},
        focus_node=EX.focus,
        value_nodes=((EX.a, EX.p, EX.b), EX.other),
    )
    in_result = evaluate_component(in_request)
    assert in_result.conforms is False
    assert in_result.violations == (EX.other,)

    equals_request = ComponentRequest(
        component={"name": "equals", "other_values": ((EX.a, EX.p, EX.b),)},
        focus_node=EX.focus,
        value_nodes=((EX.a, EX.p, EX.b),),
    )
    equals_result = evaluate_component(equals_request)
    assert equals_result.conforms is True

    disjoint_request = ComponentRequest(
        component={"name": "disjoint", "other_values": ((EX.a, EX.p, EX.b),)},
        focus_node=EX.focus,
        value_nodes=((EX.a, EX.p, EX.b),),
    )
    disjoint_result = evaluate_component(disjoint_request)
    assert disjoint_result.conforms is False


def test_evaluate_component_literal_only_non_literal_violations() -> None:
    request = ComponentRequest(
        component={"name": "pattern"},
        focus_node=EX.focus,
        value_nodes=(EX.not_literal, Literal("ok")),
    )

    result = evaluate_component(request)

    assert result.conforms is False
    assert result.violations == (EX.not_literal,)


def test_build_report_emits_decoded_values() -> None:
    report_graph = StarLayerGraph()
    events = (
        {
            "focus_node": EX.alice,
            "result_path": EX.says,
            "value": (EX.bob, EX.knows, EX.carol),
            "source_constraint_component": SH.NodeKindConstraintComponent,
            "message": "value must be a triple term",
        },
    )

    out = build_report(events=events, graph_context=report_graph)

    assert any(o == (EX.bob, EX.knows, EX.carol) for _, _, o in out.triples((None, SH.value, None)))
    assert any(o == Literal(False) for _, _, o in out.triples((None, SH.conforms, None)))
