from rdflib import Literal, Namespace
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.graph.oxgraph.core import OxGraph
from starlayer.shacl.normalization import (
    normalize_to_starlayer_graph,
)

EX = Namespace("http://example.org/")










def test_normalize_converts_a_starlayer_graph_to_an_oxgraph_copy() -> None:
    graph = StarLayerGraph()
    graph.add((EX.s, EX.p, Literal("x")))

    out = normalize_to_starlayer_graph(graph, name="data_graph")

    assert isinstance(out, OxGraph)
    assert (EX.s, EX.p, Literal("x")) in out
    graph.add((EX.s, EX.p, Literal("y")))
    assert len(out) == 1  # a copy, not a view




