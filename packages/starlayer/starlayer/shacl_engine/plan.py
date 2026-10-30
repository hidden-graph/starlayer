"""The plan: shapes read once from a shapes graph into plain data, built lazily per shape node.

``Shape`` and ``Path`` are plain frozen data (dataclasses of terms and tuples) so a plan can be serialized for a Rust
executor later. ``Plan.shape(node)`` builds a shape on first use, so shapes referenced from ``sh:node``, ``sh:not``,
``sh:and`` etc. need no pre-pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rdflib import RDF, URIRef
from rdflib.namespace import Namespace

SH = Namespace("http://www.w3.org/ns/shacl#")
Term = Any


class ShapeError(Exception):
    """The shapes graph is malformed (the W3C suite's ``sht:Failure`` cases)."""


@dataclass(frozen=True)
class Path:
    """A SHACL property path. ``kind`` is one of: pred, inverse, seq, alt, zero_or_more, one_or_more, zero_or_one.
    ``pred`` carries ``iri``; the others carry ``args`` (one sub-path, or several for seq/alt). ``node`` is the path's
    term in the shapes graph (reported as ``sh:resultPath``)."""

    kind: str
    iri: Term = None
    args: tuple["Path", ...] = ()
    node: Term = None


@dataclass(frozen=True)
class Shape:
    node: Term
    is_property: bool
    path: Path | None
    targets: tuple[tuple[URIRef, Term], ...]  # (target predicate, target value)
    params: dict[URIRef, tuple[Term, ...]]  # every sh: parameter predicate present -> its values, in graph order
    property_shapes: tuple[Term, ...]
    severity: Term
    deactivated: bool
    messages: tuple[Term, ...]


@dataclass
class Plan:
    shapes_graph: Any
    _cache: dict[Term, Shape] = field(default_factory=dict)

    def shape(self, node: Term) -> Shape:
        if node not in self._cache:
            from starlayer.shacl_engine.builder import build_shape

            self._cache[node] = build_shape(self.shapes_graph, node)
        return self._cache[node]

    def all_shape_nodes(self) -> list[Term]:
        from starlayer.shacl_engine.builder import declared_shape_nodes

        return declared_shape_nodes(self.shapes_graph)


def is_shape_type(graph: Any, node: Term) -> bool:
    return any(t in (SH.NodeShape, SH.PropertyShape, SH.Shape) for t in graph.objects(node, RDF.type))
