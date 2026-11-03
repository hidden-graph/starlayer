"""``path_values()`` and ``is_inverse()`` - SHACL property paths as a public function (GitHub issue #30).

A path as SHACL Core 2.3.1 defines it: a predicate, ``sh:inversePath``, ``sh:alternativePath``, a sequence (an RDF list of
paths), ``sh:zeroOrMorePath``, ``sh:oneOrMorePath`` and ``sh:zeroOrOnePath``. The path is *written* in one graph (the shapes
graph) and *followed* through another (the data graph); pass the same graph twice, or omit ``shapes_graph``, when they are one.
Terms are pyoxigraph terms (an rdflib term is accepted and converted).
"""

from __future__ import annotations

from typing import Any

from starlayer.shacl_engine.terms import SH, BlankNode, engine_view, to_engine

__all__ = ["path_values", "is_inverse"]


def path_values(data_graph: Any, focus: Any, path: Any, shapes_graph: Any | None = None) -> frozenset[Any]:
    """The value nodes at the end of ``path``, followed from ``focus`` through ``data_graph``, as pyoxigraph terms.

    ``path`` is a predicate IRI or the root of a path expression written in ``shapes_graph`` (default: ``data_graph``).
    Repetition paths stop on a cycle. Raises ``ShapeError`` for a path expression that is malformed."""
    from starlayer.shacl_engine.paths import eval_path, parse_path

    data = engine_view(data_graph, "data graph")
    shapes = engine_view(data if shapes_graph is None else shapes_graph, "shapes graph")
    return frozenset(eval_path(data, parse_path(shapes, to_engine(path)), to_engine(focus)))


def is_inverse(shapes_graph: Any, path: Any) -> bool:
    """Whether ``path`` is an inverse path (``[ sh:inversePath <p> ]``) at its top level. A sequence or alternative that contains
    one is not."""
    path = to_engine(path)
    return isinstance(path, BlankNode) and (path, SH.inversePath, None) in engine_view(shapes_graph, "shapes graph")
