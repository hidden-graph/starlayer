from rdflib import Graph, Literal, Namespace
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl.engine import normalize_graph_inputs, normalize_to_starlayer_graph

EX = Namespace("http://example.org/")


def test_normalize_returns_same_starlayer_graph() -> None:
    graph = StarLayerGraph()

    out = normalize_to_starlayer_graph(graph, name="data_graph")

    assert out is graph


def test_normalize_converts_rdflib_graph() -> None:
    graph = Graph()
    graph.add((EX.s, EX.p, Literal("x")))

    out = normalize_to_starlayer_graph(graph, name="data_graph")

    assert isinstance(out, StarLayerGraph)
    assert (EX.s, EX.p, Literal("x")) in out


def test_normalize_graph_inputs_handles_optional_graphs() -> None:
    data = Graph()
    shapes = Graph()
    data.add((EX.s, EX.p, Literal("d")))
    shapes.add((EX.shape, EX.path, EX.p))

    out_data, out_shapes, out_ont = normalize_graph_inputs(data, shapes, None)

    assert isinstance(out_data, StarLayerGraph)
    assert isinstance(out_shapes, StarLayerGraph)
    assert out_ont is None
