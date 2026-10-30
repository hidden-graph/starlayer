"""Shapes graph -> ``Shape`` / ``Path`` data. Paths and targets are owned by ``paths.py`` and ``targets.py``."""

from __future__ import annotations

from typing import Any

from rdflib import RDF, URIRef

from starlayer.shacl_engine.components.registry import all_param_predicates
from starlayer.shacl_engine.plan import SH, Path, Shape, ShapeError, Term
from starlayer.shacl_engine.targets import declared_shape_nodes, shape_targets  # noqa: F401  (re-exported)


def build_path(graph: Any, node: Term) -> Path:
    from starlayer.shacl_engine.paths import parse_path

    return parse_path(graph, node)


def build_shape(graph: Any, node: Term) -> Shape:
    path_values = list(graph.objects(node, SH.path))
    if len(path_values) > 1:
        raise ShapeError(f"{node}: more than one sh:path")
    path = build_path(graph, path_values[0]) if path_values else None
    params: dict[URIRef, tuple[Term, ...]] = {}
    for pred in all_param_predicates():
        values = tuple(graph.objects(node, pred))
        if values:
            params[pred] = values
    severities = list(graph.objects(node, SH.severity))
    deact = [v for v in graph.objects(node, SH.deactivated)]
    is_prop = path is not None or (node, RDF.type, SH.PropertyShape) in graph
    return Shape(
        node=node,
        is_property=is_prop,
        path=path,
        targets=tuple(shape_targets(graph, node)),
        params=params,
        property_shapes=tuple(graph.objects(node, SH.property)),
        severity=severities[0] if severities else SH.Violation,
        deactivated=any(str(v) in ("true", "1") for v in deact),
        messages=tuple(graph.objects(node, SH.message)),
    )
