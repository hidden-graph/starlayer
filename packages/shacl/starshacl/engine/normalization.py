from __future__ import annotations

from typing import Any

from rdflib import Dataset, Graph


def normalize_to_starlayer_graph(value: Any, *, name: str, force_default_union: bool = False) -> Any:
    """Normalize input graph to StarLayerGraph.

    A plain rdflib.Graph is always converted. Existing StarLayerGraph instances
    are returned as-is.

    ``force_default_union``: when ``value`` is an ``rdflib.Dataset`` (or
    ``StarLayerDataset``, a subclass), setting this mutates ``value.default_union
    = True`` before conversion - matching pySHACL's own native behavior when
    given a raw ``Dataset`` directly as ``ont_graph`` (``pyshacl/validator.py``:
    ``if isinstance(self.ont_graph, rdflib.Dataset): self.ont_graph.default_union
    = True``), so ontology triples across all named graphs are visible for
    inference regardless of how the caller constructed the dataset. Not used
    for ``data_graph``/``shacl_graph`` - pySHACL doesn't auto-union those
    either, only ``ont_graph``.
    """
    try:
        from starlayergraph.graph.starlayer_graph import StarLayerGraph
    except ImportError as exc:
        raise TypeError(
            f"{name} must be a StarLayerGraph, but starlayergraph is unavailable."
        ) from exc

    if isinstance(value, StarLayerGraph):
        return value

    if isinstance(value, Graph):
        if force_default_union and isinstance(value, Dataset):
            value.default_union = True
        return StarLayerGraph.from_rdflib(value)

    raise TypeError(
        f"{name} must be a StarLayerGraph or rdflib.Graph. Got {type(value).__name__}."
    )


def normalize_graph_inputs(
    data_graph: Any,
    shacl_graph: Any | None = None,
    ont_graph: Any | None = None,
) -> tuple[Any, Any | None, Any | None]:
    data = normalize_to_starlayer_graph(data_graph, name="data_graph")
    shapes = normalize_to_starlayer_graph(shacl_graph, name="shacl_graph") if shacl_graph is not None else None
    ont = (
        normalize_to_starlayer_graph(ont_graph, name="ont_graph", force_default_union=True)
        if ont_graph is not None
        else None
    )
    return data, shapes, ont
