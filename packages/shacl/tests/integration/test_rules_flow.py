import pytest
from rdflib import Namespace
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl import StarShaclValidator

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

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rules_infer_target_class.ttl"), format="turtle")

    validator = StarShaclValidator()
    result = validator.apply_rules(data_graph=data, shacl_graph=shapes)

    assert result.data_graph is data
    assert (EX.alice, EX.inferred, EX.yes) in data


def test_apply_rules_preserves_existing_triple_terms() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))
    data.add((EX.alice, EX.type, EX.Person))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rules_infer_target_node.ttl"), format="turtle")

    validator = StarShaclValidator()
    _ = validator.apply_rules(data_graph=data, shacl_graph=shapes)

    assert (EX.alice, EX.flag, EX.processed) in data
    assert (EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)) in data
