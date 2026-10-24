"""``path_values()`` and ``is_inverse()`` - SHACL property paths as a public function (GitHub issue #30).

A path as SHACL Core 2.3.1 defines it: a predicate, ``sh:inversePath``, ``sh:alternativePath``, a sequence (an RDF list of
paths), ``sh:zeroOrMorePath``, ``sh:oneOrMorePath`` and ``sh:zeroOrOnePath``. The path is *written* in one graph (the shapes
graph) and *followed* through another (the data graph); pass the same graph twice, or omit ``shapes_graph``, when they are one.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from rdflib import BNode
from rdflib.namespace import SH

__all__ = ["path_values", "is_inverse"]


def path_values(data_graph: Any, focus: Any, path: Any, shapes_graph: Any | None = None) -> frozenset[Any]:
    """The value nodes at the end of ``path``, followed from ``focus`` through ``data_graph``.

    ``path`` is a predicate IRI or the root of a path expression written in ``shapes_graph`` (default: ``data_graph``).
    Repetition paths stop on a cycle. Raises ``NotImplementedError`` for a blank node that is not one of the path forms."""
    from starlayer.shacl.subgraph_extraction import _walk_path

    shapes = SimpleNamespace(graph=data_graph if shapes_graph is None else shapes_graph)
    values, _traversed = _walk_path(data_graph, focus, path, shapes)
    return values


def is_inverse(shapes_graph: Any, path: Any) -> bool:
    """Whether ``path`` is an inverse path (``[ sh:inversePath <p> ]``) at its top level. A sequence or alternative that contains
    one is not."""
    return isinstance(path, BNode) and (path, SH.inversePath, None) in shapes_graph
