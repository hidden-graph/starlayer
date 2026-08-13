from starlayergraph.graph.starlayergraph_graph import StarLayerGraph

from starshacl.types import (
    MutableStarLayerGraphProtocol,
    StarLayerGraphProtocol,
    is_mutable_starlayergraph_graph_like,
    is_starlayergraph_graph_like,
)


def test_starlayergraph_graph_matches_protocol() -> None:
    graph = StarLayerGraph()

    assert isinstance(graph, StarLayerGraphProtocol)
    assert isinstance(graph, MutableStarLayerGraphProtocol)
    assert is_starlayergraph_graph_like(graph) is True
    assert is_mutable_starlayergraph_graph_like(graph) is True


def test_plain_container_does_not_match_protocol() -> None:
    graph = object()

    assert is_starlayergraph_graph_like(graph) is False
    assert is_mutable_starlayergraph_graph_like(graph) is False
