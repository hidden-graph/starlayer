"""Blank node labels are scoped to one document (RDF 1.2 Concepts; N-Quads, Turtle and TriG): ``_:b`` in two documents is two
blank nodes (GitHub issue #99). A parser entry point opens a scope with ``@per_document``; ``labelled_bnode`` inside it gives
one fresh node per label. Outside a scope it is ``BNode(label)``, so a caller that builds a term from a label on its own is
unchanged. A scope already open (TriG hands each graph block to the Turtle parser) is reused, so a label is one node
throughout its document."""

from __future__ import annotations

import functools
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from rdflib import BNode

__all__ = ["labelled_bnode", "per_document"]

_SCOPE: ContextVar[dict[str, BNode] | None] = ContextVar("starlayer_bnode_scope", default=None)


def labelled_bnode(label: str) -> BNode:
    scope = _SCOPE.get()
    if scope is None:
        return BNode(label)
    node = scope.get(label)
    if node is None:
        node = scope[label] = BNode()
    return node


def per_document(function: Callable[..., Any]) -> Callable[..., Any]:
    """Run ``function`` (a parser entry point that returns, not yields, its result) inside a blank-node scope."""

    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if _SCOPE.get() is not None:
            return function(*args, **kwargs)
        token = _SCOPE.set({})
        try:
            return function(*args, **kwargs)
        finally:
            _SCOPE.reset(token)

    return wrapper
