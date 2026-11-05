"""Expressions of the parser's ``Node`` trees (SRL filters and assignments): their text, their variables, their nodes.

The text is rendered by ``sqe/expr_text.py`` from the same ``spexpr:`` tree the ``sqe:`` / ``srl:`` encoder builds, so an
expression keeps the parentheses that make ``(?y + 1) * 2`` mean what it says and every SPARQL 1.2 built-in has a rendering.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pyoxigraph as ox

from .parse_sparql import Node

__all__ = ["expr_nodes", "expr_variables", "render_expression"]


def expr_nodes(expr: Any) -> Iterator[Any]:
    """Every ``Node`` and every term under ``expr`` (and ``expr`` itself), in document order."""
    yield expr
    if isinstance(expr, Node):
        for value in expr.f.values():
            yield from expr_nodes(value)
    elif isinstance(expr, (list, tuple)):
        for item in expr:
            yield from expr_nodes(item)


def expr_variables(expr: Any) -> set[ox.Variable]:
    """Every variable anywhere in ``expr``."""
    return {n for n in expr_nodes(expr) if isinstance(n, ox.Variable)}


def render_expression(expr: Any, prefixes: dict[str, str] | None = None) -> str:
    """The SPARQL text of an expression tree (or a bare term), using ``prefixes`` (prefix -> namespace) for IRIs where given."""
    from .parse_sparql import _Encoder, _Sink
    from .sqe._memtree import TreeIndex
    from .sqe.expr_text import expr_text

    sink = _Sink()
    node = _Encoder(sink).term(expr)
    return expr_text(node, TreeIndex(sink), prefixes or {})
