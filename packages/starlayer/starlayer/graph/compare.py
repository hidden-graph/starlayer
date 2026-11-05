"""Graph comparison: ``isomorphic``.

Two graphs or datasets are isomorphic when they are equal up to blank-node relabelling. Both sides are canonicalised
with Oxigraph's native RDFC-1.0 (``starlayer.graph.rdfc_native``), so graph names count and triple terms are compared
by structure, a blank node inside a triple term included. An rdflib ``Graph`` or ``Dataset`` is first copied into an
Oxigraph-backed graph (``to_oxgraph`` / ``to_oxdataset`` of the rdflib bridge, which needs rdflib; a caller holding one
has it installed). Oxigraph reads a simple literal and its ``xsd:string`` form as one term and lower-cases language tags,
so those differences never make two graphs unequal.
"""

from __future__ import annotations

from typing import Any

__all__ = ["isomorphic"]


def as_quads(graph: Any) -> list:
    """The quads of an Oxigraph-backed graph / dataset / ``pyoxigraph.Store`` as pyoxigraph quads (a graph's triples go into the
    default graph); an rdflib graph or dataset is converted first."""
    import pyoxigraph as ox

    from starlayer.graph.oxgraph._rdflib_bridge import (
        is_oxigraph_input,
        to_oxdataset,
        to_oxgraph,
    )

    if not is_oxigraph_input(graph):
        graph = to_oxdataset(graph, "graph") if hasattr(graph, "graphs") or hasattr(graph, "contexts") else to_oxgraph(graph, "graph")
    if isinstance(graph, ox.Store):
        return list(graph)
    from starlayer.graph.oxgraph.core import StarLayerDataset

    if isinstance(graph, StarLayerDataset):
        return list(graph.quads())
    return [ox.Quad(s, p, o, ox.DefaultGraph()) for s, p, o in graph]


def isomorphic(graph1: Any, graph2: Any) -> bool:
    """True if the two graphs or datasets (``StarLayerGraph``, ``StarLayerDataset``, ``pyoxigraph.Store``, or rdflib ``Graph`` /
    ``Dataset``) are equal up to blank-node relabelling: equal canonical N-Quads (RDFC-1.0). Datasets are compared as datasets,
    graph names included; a dataset against a plain graph compares the dataset's quads with the graph's triples in the default
    graph.

    Raises:
        starlayer.graph.rdfc_native.CanonicalizationComplexityError: a highly symmetric blank-node structure that the
            canonicaliser could not finish (see ``rdfc_native``).
    """
    from starlayer.graph import rdfc_native

    return rdfc_native.isomorphic(as_quads(graph1), as_quads(graph2))
