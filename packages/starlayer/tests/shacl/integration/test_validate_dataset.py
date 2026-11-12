"""A dataset is validated as the union of its graphs, whatever its own ``default_union`` says (as pySHACL does); ``validate_each``
validates the graphs of a dataset one by one."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph.oxgraph import StarLayerDataset, StarLayerGraph
from starlayer.shacl import validate, validate_each

PREFIXES = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
GOOD, BAD = ox.NamedNode("http://g/good"), ox.NamedNode("http://g/bad")

SHAPES = PREFIXES + "ex:S a sh:NodeShape ; sh:targetClass ex:P ; sh:property [ sh:path ex:v ; sh:minCount 1 ] ."


def _shapes() -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=SHAPES, format="turtle12")
    return g


def _dataset(default_union: bool) -> StarLayerDataset:
    dataset = StarLayerDataset(default_union=default_union)
    dataset.graph(GOOD).parse(data=PREFIXES + "ex:a a ex:P ; ex:v 1 .", format="turtle12")
    dataset.graph(BAD).parse(data=PREFIXES + "ex:b a ex:P .", format="turtle12")
    return dataset


@pytest.mark.parametrize("default_union", [True, False])
def test_a_dataset_is_validated_as_the_union_of_its_graphs(default_union: bool) -> None:
    assert not validate(_dataset(default_union), _shapes(), meta_shacl=False).conforms


@pytest.mark.parametrize("default_union", [True, False])
def test_a_violation_that_needs_triples_of_two_graphs_is_found_only_in_the_union(default_union: bool) -> None:
    dataset = StarLayerDataset(default_union=default_union)
    dataset.graph(GOOD).parse(data=PREFIXES + "ex:a a ex:P .", format="turtle12")  # the type
    dataset.graph(BAD).parse(data=PREFIXES + "ex:a ex:v 1 .", format="turtle12")  # the value
    assert validate(dataset, _shapes(), meta_shacl=False).conforms  # together the node conforms
    per_graph = validate_each(dataset, _shapes(), meta_shacl=False)
    assert {name: r.conforms for name, r in per_graph.items()} == {GOOD: False, BAD: True}  # alone, one of them does not


def test_validate_each_validates_the_graphs_of_a_dataset_alone() -> None:
    results = validate_each(_dataset(False), _shapes(), meta_shacl=False)
    assert {name: r.conforms for name, r in results.items()} == {BAD: False, GOOD: True}
    assert list(results) == [BAD, GOOD]  # in a fixed order (by name)


def test_validate_each_includes_the_default_graph_only_when_it_holds_triples() -> None:
    dataset = _dataset(True)
    assert None not in validate_each(dataset, _shapes(), meta_shacl=False)
    dataset.default_graph.parse(data=PREFIXES + "ex:c a ex:P ; ex:v 2 .", format="turtle12")
    results = validate_each(dataset, _shapes(), meta_shacl=False)
    assert list(results)[0] is None and results[None].conforms


def test_validate_each_keeps_the_keys_of_a_mapping_and_the_positions_of_a_sequence() -> None:
    graph = StarLayerGraph()
    graph.parse(data=PREFIXES + "ex:a a ex:P ; ex:v 1 .", format="turtle12")
    assert list(validate_each({"one": graph}, _shapes(), meta_shacl=False)) == ["one"]
    assert list(validate_each([graph, graph], _shapes(), meta_shacl=False)) == [0, 1]
