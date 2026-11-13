"""The graph objects StarLayer's functions take, and the error for anything else.

A function that takes a graph takes a ``StarLayerGraph``, a ``StarLayerDataset`` or a ``pyoxigraph.Store``. An rdflib graph is a
``TypeError`` that names ``StarLayerGraph.from_rdflib``, the one explicit conversion (it lives in the ``starlayer-reasoning``
package, with the other code that needs rdflib).
"""

from __future__ import annotations

import sys
from typing import Any

import pyoxigraph as ox

__all__ = ["as_oxigraph", "is_oxigraph_dataset", "is_oxigraph_input"]


def is_oxigraph_input(value: Any) -> bool:
    """True for a ``StarLayerGraph`` / ``StarLayerDataset`` or a bare ``pyoxigraph.Store``."""
    from starlayer.graph.oxgraph.core import StarLayerDataset, StarLayerGraph

    return isinstance(value, (StarLayerGraph, StarLayerDataset, ox.Store))


def is_oxigraph_dataset(value: Any) -> bool:
    """True for a ``StarLayerDataset`` or a bare ``pyoxigraph.Store`` (something with named graphs)."""
    from starlayer.graph.oxgraph.core import StarLayerDataset

    return isinstance(value, (StarLayerDataset, ox.Store))


def as_oxigraph(value: Any, where: str = "graph") -> Any:
    """``value`` as a ``StarLayerGraph`` or ``StarLayerDataset``: those as they are, a ``pyoxigraph.Store`` as a dataset over it,
    ``None`` as ``None``. Anything else, an rdflib graph above all, is a ``TypeError`` (``where`` names the argument)."""
    if value is None:
        return None
    from starlayer.graph.oxgraph.core import StarLayerDataset, StarLayerGraph

    if isinstance(value, (StarLayerGraph, StarLayerDataset)):
        return value
    if isinstance(value, ox.Store):
        return StarLayerDataset(store=value)
    rdflib = sys.modules.get("rdflib")
    if rdflib is not None and isinstance(value, rdflib.Graph):
        raise TypeError(
            f"an rdflib graph ({type(value).__name__}) is not accepted as the {where}: convert it with StarLayerGraph.from_rdflib(graph) "
            "(StarLayerDataset.from_rdflib for a Dataset)"
        )
    raise TypeError(f"the {where} must be a StarLayerGraph, StarLayerDataset or pyoxigraph Store, not {type(value).__name__}")
