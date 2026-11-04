from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl.types import MutableStarLayerGraphProtocol, StarLayerGraphProtocol


def test_starlayer_graph_matches_protocol() -> None:
    graph = StarLayerGraph()

    assert isinstance(graph, StarLayerGraphProtocol)
    assert isinstance(graph, MutableStarLayerGraphProtocol)


