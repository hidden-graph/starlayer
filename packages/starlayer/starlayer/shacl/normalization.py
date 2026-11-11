from __future__ import annotations

from typing import Any


def normalize_to_starlayer_graph(value: Any, *, name: str, force_default_union: bool = False) -> Any:
    """Normalize an input graph to an Oxigraph-backed graph (``StarLayerGraph`` / ``StarLayerDataset``).

    An ``StarLayerGraph`` or ``StarLayerDataset`` is returned as it is; a bare ``pyoxigraph.Store`` becomes an ``StarLayerDataset`` over it. A plain
    ``rdflib.Graph`` or an old-style ``StarLayerGraph`` is converted to an ``StarLayerGraph`` copy (``from_rdflib``: a supported input;
    literals Oxigraph normalises on insert, such as ``"04"^^xsd:integer``, come out normalised).

    Args:
        value: The graph to normalize.
        name: The parameter name to use in a TypeError message, so callers get an error naming their own argument.
        force_default_union: Whether a dataset's named graphs must all be visible (the ontology graph: its axioms count wherever
            they sit). An ``StarLayerDataset`` without ``default_union`` is viewed through one that has it (the caller's object is not
            changed); a rdflib dataset has ``default_union`` set on it, as before.

    Raises:
        TypeError: If ``value`` is not a graph the library accepts.
    """
    from starlayer.graph.oxgraph.core import StarLayerDataset, StarLayerGraph

    if value is None:
        raise TypeError(f"{name} must be a graph (StarLayerGraph, StarLayerDataset or rdflib.Graph). Got None.")
    if isinstance(value, StarLayerDataset):
        if force_default_union and not value.default_union:
            return StarLayerDataset(store=value.store, prefixes=value.prefixes)
        return value
    if isinstance(value, StarLayerGraph):
        return value
    if force_default_union and hasattr(value, "default_union") and hasattr(value, "graphs"):  # an rdflib Dataset
        value.default_union = True
    from starlayer.shacl_engine.terms import engine_view

    try:
        return engine_view(value, name)
    except TypeError as exc:
        if not hasattr(value, "triples"):
            raise TypeError(
                f"{name} must be an StarLayerGraph, StarLayerDataset, StarLayerGraph or rdflib.Graph. Got {type(value).__name__}."
            ) from exc
        raise


def normalize_graph_inputs(
    data_graph: Any,
    shacl_graph: Any | None = None,
    ont_graph: Any | None = None,
) -> tuple[Any, Any | None, Any | None]:
    """Normalizes a data/shapes/ontology graph, in any shape a caller may
    pass, to an Oxigraph-backed graph (or ``None``) via ``normalize_to_starlayer_graph()``.
    """
    data = normalize_to_starlayer_graph(data_graph, name="data_graph")
    shapes = normalize_to_starlayer_graph(shacl_graph, name="shacl_graph") if shacl_graph is not None else None
    ont = (
        normalize_to_starlayer_graph(ont_graph, name="ont_graph", force_default_union=True)
        if ont_graph is not None
        else None
    )
    return data, shapes, ont
