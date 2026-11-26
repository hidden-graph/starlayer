"""Short, stable blank node labels for output: ``serialize(..., bnode_labels="short")``.

A blank node's label in the store is a long random id, which makes a flat Turtle or N-Triples document hard to read. ``short_bnode_labels``
renames the blank nodes of the statements to be written, for that output only (the graph keeps its ids): ``_:b0``, ``_:b1``, ... The
numbers come from RDFC-1.0 canonicalisation, so the same graph is always labelled the same way and the statements are written in sorted
order. When canonicalisation is not possible (a blank node inside a triple term, which Oxigraph does not label stably, or a structure
that is too symmetric to canonicalise quickly) the numbers follow the order the statements are written in.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

import pyoxigraph as ox

from starlayer.errors import ExecutionError, only_kind
from starlayer.graph import rdfc_native

_CANONICAL = re.compile(r"c14n(\d+)")


def _has_blank(term: Any) -> bool:
    if isinstance(term, ox.BlankNode):
        return True
    return isinstance(term, ox.Triple) and any(_has_blank(t) for t in (term.subject, term.predicate, term.object))


def _rename(term: Any, label: Any) -> Any:
    if isinstance(term, ox.BlankNode):
        return ox.BlankNode(label(term.value))
    if isinstance(term, ox.Triple):
        return ox.Triple(_rename(term.subject, label), _rename(term.predicate, label), _rename(term.object, label))
    return term


def _rename_item(item: Any, label: Any) -> Any:
    if isinstance(item, ox.Quad):
        return ox.Quad(_rename(item.subject, label), _rename(item.predicate, label), _rename(item.object, label), _rename(item.graph_name, label))
    return ox.Triple(_rename(item.subject, label), _rename(item.predicate, label), _rename(item.object, label))


def _statement(item: Any) -> Any:
    """A ``Triple`` or ``Quad`` for an item that may be a 3- or 4-tuple of terms."""
    if isinstance(item, (ox.Triple, ox.Quad)):
        return item
    return ox.Triple(*item) if len(item) == 3 else ox.Quad(*item)


def short_bnode_labels(items: Iterable[Any], prefix: str = "b") -> list[Any]:
    """The statements (``pyoxigraph.Triple`` or ``Quad``) with their blank nodes renamed ``<prefix>0``, ``<prefix>1``, ...; statements without
    a blank node come back as they are."""
    items = [_statement(i) for i in items]
    if not any(_has_blank(t) for i in items for t in ((i.subject, i.predicate, i.object, i.graph_name) if isinstance(i, ox.Quad) else (i.subject, i.predicate, i.object))):
        return items
    as_quads = [i if isinstance(i, ox.Quad) else ox.Quad(i.subject, i.predicate, i.object, ox.DefaultGraph()) for i in items]
    triples_only = not any(isinstance(i, ox.Quad) for i in items)
    if not rdfc_native._bnode_in_triple_term(as_quads):
        try:
            canonical = rdfc_native._canonicalize(as_quads, "sha256")
        except ExecutionError as error:
            only_kind(error, "limit")
            canonical = None
        if canonical is not None:
            renamed = [_rename_item(q, lambda value: prefix + _CANONICAL.fullmatch(value).group(1)) for q in canonical]
            renamed.sort(key=lambda q: ox.serialize([q], format=ox.RdfFormat.N_QUADS).decode())
            return [ox.Triple(q.subject, q.predicate, q.object) for q in renamed] if triples_only else renamed
    seen: dict[str, str] = {}

    def label(value: str) -> str:
        if value not in seen:
            seen[value] = f"{prefix}{len(seen)}"
        return seen[value]

    return [_rename_item(i, label) for i in items]
