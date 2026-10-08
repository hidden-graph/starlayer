import pytest
from rdflib import Namespace
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl import StarShaclSchema

from ._shape_loader import load_shape

EX = Namespace("http://example.org/")


pyshacl = pytest.importorskip("pyshacl")


def test_apply_rules_adds_inferred_triple() -> None:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice a ex:Person .
        """,
        format="turtle",
    )
    original_triples = set(data)

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rules_infer_target_class.ttl"), format="turtle")

    validator = StarShaclSchema(shacl_graph=shapes)
    result = validator.apply_rules(data_graph=data)

    # apply_rules() never mutates the caller's own data_graph - result.inferred_graph
    # is a separate object holding strictly the rule-produced triples (the
    # SHACL 1.2 Inference Rules spec's own "inference graph" term).
    assert result.inferred_graph is not data
    assert set(data) == original_triples
    assert (EX.alice, EX.inferred, EX.yes) in result.inferred_graph
    assert (EX.alice, EX.inferred, EX.yes) not in data


def test_apply_rules_preserves_existing_triple_terms() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))
    data.add((EX.alice, EX.type, EX.Person))
    original_triples = set(data)

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rules_infer_target_node.ttl"), format="turtle")

    validator = StarShaclSchema(shacl_graph=shapes)
    result = validator.apply_rules(data_graph=data)

    # The base triple-term triple is untouched in the caller's own graph,
    # and - being base data, not rule output - correctly absent from the
    # returned inference graph too.
    assert set(data) == original_triples
    assert (EX.alice, EX.flag, EX.processed) in result.inferred_graph
    assert (EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)) in data
    assert (EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)) not in result.inferred_graph
