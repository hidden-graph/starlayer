"""``target_shapes``: the shapes that target a node, the reverse of ``target_nodes``."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl import StarShaclProcessor, target_nodes, target_shapes
from starlayer.shacl.engine.terms import NS

EX = NS("http://example.org/")
PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"

SHAPES = """
ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person .
ex:NamedShape a sh:NodeShape ; sh:targetSubjectsOf ex:name .
ex:KnownShape a sh:NodeShape ; sh:targetObjectsOf ex:knows .
ex:BobShape a sh:NodeShape ; sh:targetNode ex:bob .
ex:AdultShape a sh:NodeShape ; sh:class ex:Person ; sh:property [ sh:path ex:age ; sh:minInclusive 18 ] .
ex:AdultTargetShape a sh:NodeShape ; sh:targetWhere ex:AdultShape .
ex:Animal a sh:ShapeClass .
ex:OffShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:deactivated true .
ex:Hidden a sh:NodeShape ; sh:targetNode ex:nobody .
"""
DATA = """
ex:Student rdfs:subClassOf ex:Person .
ex:alice a ex:Person ; ex:name "Alice" ; ex:age 30 .
ex:bob a ex:Student ; ex:age 12 ; ex:knows ex:carol .
ex:carol ex:name "Carol" .
ex:rex a ex:Animal .
ex:plain ex:other 1 .
"""
NODES = ["alice", "bob", "carol", "rex", "plain"]


def _graph(turtle: str) -> StarLayerGraph:
    return StarLayerGraph().parse(data=PFX + turtle, format="turtle")


@pytest.fixture(scope="module")
def graphs():
    return _graph(SHAPES), _graph(DATA)


def test_the_shapes_of_a_node_are_the_shapes_that_target_it(graphs):
    shapes, data = graphs
    assert set(target_shapes(data_graph=data, shacl_graph=shapes, node=EX.alice)) == {EX.PersonShape, EX.NamedShape, EX.AdultTargetShape}
    assert set(target_shapes(data_graph=data, shacl_graph=shapes, node=EX.bob)) == {EX.PersonShape, EX.BobShape}  # a subclass instance, and a named target
    assert set(target_shapes(data_graph=data, shacl_graph=shapes, node=EX.carol)) == {EX.NamedShape, EX.KnownShape}


def test_a_shape_that_is_also_a_class_targets_its_instances(graphs):
    shapes, data = graphs
    assert EX.Animal in target_shapes(data_graph=data, shacl_graph=shapes, node=EX.rex)


def test_a_node_no_shape_targets_has_no_shapes_and_a_deactivated_shape_is_left_out(graphs):
    shapes, data = graphs
    assert target_shapes(data_graph=data, shacl_graph=shapes, node=EX.plain) == ()
    assert EX.OffShape not in target_shapes(data_graph=data, shacl_graph=shapes, node=EX.alice)


@pytest.mark.parametrize("name", NODES)
def test_it_is_the_reverse_of_target_nodes(graphs, name):
    shapes, data = graphs
    node = getattr(EX, name)
    expected = {
        shape
        for shape in (EX.PersonShape, EX.NamedShape, EX.KnownShape, EX.BobShape, EX.AdultTargetShape, EX.Animal, EX.OffShape, EX.Hidden)
        if node in target_nodes(data_graph=data, shacl_graph=shapes, shape_node=shape)
    } - {EX.OffShape}  # a deactivated shape targets nodes, but validate() skips it
    assert set(target_shapes(data_graph=data, shacl_graph=shapes, node=node)) == expected


def test_the_method_uses_the_bound_graphs_and_settings(graphs):
    shapes, data = graphs
    processor = StarShaclProcessor(shacl_graph=shapes, data_graph=data)
    assert processor.target_shapes(node=EX.alice) == target_shapes(data_graph=data, shacl_graph=shapes, node=EX.alice)
    other = _graph("ex:dave a ex:Person .")
    assert EX.PersonShape in processor.target_shapes(node=EX.dave, data_graph=other)


def test_the_method_needs_a_data_graph():
    with pytest.raises(ValueError, match="data_graph"):
        StarShaclProcessor(shacl_graph=_graph(SHAPES)).target_shapes(node=EX.alice)
