from starlayer.shacl.types import MutableStarLayerGraphProtocol, StarLayerGraphProtocol


def test_plain_container_does_not_match_protocol() -> None:
    graph = object()

    assert not isinstance(graph, StarLayerGraphProtocol)
    assert not isinstance(graph, MutableStarLayerGraphProtocol)
