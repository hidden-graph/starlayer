"""A ``StarLayerDataset`` with one named graph per given graph, for the tests of ``validate_each`` (which takes only a dataset)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pyoxigraph as ox
from starlayer.graph import StarLayerDataset


def name_of(i: int) -> ox.NamedNode:
    """The graph name ``dataset_of`` gives the ``i``-th graph of a sequence."""
    return ox.NamedNode(f"urn:test:graph:{i}")


def dataset_of(graphs: Iterable[Any] | Mapping[Any, Any]) -> StarLayerDataset:
    """A dataset holding each graph under a name: the mapping's keys, or ``name_of(position)``."""
    items = graphs.items() if isinstance(graphs, Mapping) else ((name_of(i), g) for i, g in enumerate(graphs))
    dataset = StarLayerDataset()
    for name, graph in items:
        dataset.graph(name).extend(graph)
    return dataset
