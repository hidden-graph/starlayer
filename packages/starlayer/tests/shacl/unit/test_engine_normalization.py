import pyoxigraph as ox
import pytest
from starlayer.graph import StarLayerGraph as Graph
from starlayer.graph.core import StarLayerDataset, StarLayerGraph
from starlayer.shacl.normalization import (
    normalize_graph_inputs,
    normalize_to_starlayer_graph,
)
from tests.support.terms import Namespace, lit

EX = Namespace("http://example.org/")


def test_normalize_returns_the_same_oxgraph() -> None:
    graph = StarLayerGraph()

    out = normalize_to_starlayer_graph(graph, name="data_graph")

    assert out is graph


def test_normalize_returns_the_same_oxdataset() -> None:
    dataset = StarLayerDataset()

    assert normalize_to_starlayer_graph(dataset, name="data_graph") is dataset


def test_normalize_wraps_a_bare_store_in_an_oxdataset() -> None:
    store = ox.Store()
    store.add(ox.Quad(ox.NamedNode("http://example.org/s"), ox.NamedNode("http://example.org/p"), ox.Literal("x"), ox.DefaultGraph()))

    out = normalize_to_starlayer_graph(store, name="data_graph")

    assert isinstance(out, StarLayerDataset)
    assert (ox.NamedNode("http://example.org/s"), ox.NamedNode("http://example.org/p"), ox.Literal("x")) in out


def test_normalize_rejects_a_value_that_is_not_a_graph_and_names_the_argument() -> None:
    with pytest.raises(TypeError, match="my_graph"):
        normalize_to_starlayer_graph(((EX.s, EX.p, EX.o),), name="my_graph")


def test_normalize_graph_inputs_handles_optional_graphs() -> None:
    data = Graph()
    shapes = Graph()
    data.add((EX.s, EX.p, lit("d")))
    shapes.add((EX.shape, EX.path, EX.p))

    out_data, out_shapes, out_ont = normalize_graph_inputs(data, shapes, None)

    assert isinstance(out_data, StarLayerGraph)
    assert isinstance(out_shapes, StarLayerGraph)
    assert out_ont is None
