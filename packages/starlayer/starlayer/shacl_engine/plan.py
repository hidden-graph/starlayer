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


class ShapeError(ValueError):
    """The shapes graph is malformed (the W3C suite's ``sht:Failure`` cases)."""


@dataclass(frozen=True)
class Path:
    """A SHACL property path. ``kind`` is one of: pred, inverse, seq, alt, zero_or_more, one_or_more, zero_or_one.
    ``pred`` carries ``iri``; the others carry ``args`` (one sub-path, or several for seq/alt). ``node`` is the path's
    term in the shapes graph (reported as ``sh:resultPath``)."""

    kind: str
    iri: Term = None
    args: tuple[Path, ...] = ()
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
    values: tuple[Term, ...] = ()  # sh:values node expressions (extra value nodes of a property shape)
    default_values: tuple[Term, ...] = ()  # sh:defaultValue node expressions (used only if there are no other value nodes)
    # (parameter predicate, value) -> {'deactivated': bool, 'severity': Term|None}, read from RDF 1.2 reifiers of the
    # shape's own triples (`sh:datatype xsd:boolean {| sh:deactivated true |}`); sh:property uses the same key shape.
    annotations: dict[tuple[Term, Term], dict[str, Any]] = field(default_factory=dict)
    deactivated_exprs: tuple[Term, ...] = ()  # sh:deactivated values that are node expressions, evaluated per focus node


@dataclass
class Plan:
    shapes_graph: Any
    _cache: dict[Term, Shape] = field(default_factory=dict)
    _components: list | None = None
    sparql_cache: dict = field(default_factory=dict)  # prefix declarations and checked queries, keyed by their inputs

    def components(self) -> list:
        """Built-in components plus the SPARQL-based constraint components declared in the shapes graph (built once)."""
        if self._components is None:
            from starlayer.shacl_engine.components.registry import static_specs
            from starlayer.shacl_engine.components.sparql_components import (
                declared_components,
            )

            self._components = static_specs() + declared_components(self)
        return self._components

    def shape(self, node: Term) -> Shape:
        if node not in self._cache:
            from starlayer.shacl_engine.builder import build_shape

            extra = {p for spec in self.components() for p in spec.predicates}
            self._cache[node] = build_shape(self.shapes_graph, node, extra)
        return self._cache[node]

    def all_shape_nodes(self) -> list[Term]:
        from starlayer.shacl_engine.builder import declared_shape_nodes

        return declared_shape_nodes(self.shapes_graph)


def is_shape_type(graph: Any, node: Term) -> bool:
    return any(t in (SH.NodeShape, SH.PropertyShape, SH.Shape) for t in graph.objects(node, RDF.type))
