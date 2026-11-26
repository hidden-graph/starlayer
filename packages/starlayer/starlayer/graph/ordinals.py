"""Ordered children as ordinals, the counterpart of ``rdflist`` for the syntax trees that do not use an ``rdf:List`` (vocabulary ``tree:``,
``starontology/tree/``).

A parent holds its children for one property as plain ``parent p child`` triples, and each child carries its position: ``child tree:ord 3``
(a non-negative ``xsd:integer``). The order is ascending ordinal. Gaps are allowed (a removal leaves one), two children of one parent and
property with the same ordinal are an error (``FormatError``), never broken by blank node label. A child that cannot carry an ordinal
itself, a literal, a named node (it may be held by several parents, each at its own position) or a nested sequence, sits in a wrapper
node ``[ a tree:Item ; tree:ord 3 ; tree:value x ]``; a blank node child carries ``tree:ord`` directly and so has one parent only (the
shapes in ``tree_shapes.ttl`` reject a second one).

Reading is ``ordered_items`` (the members in order) or ``ordered_children`` (each child node with its member). ``append``, ``insert_at``,
``remove_at`` and ``replace_at`` edit one sequence; ``renumber_dense`` makes every sequence 0, 1, 2, ... and is the step to run before
canonicalising or hashing a tree (the ordinals are part of the data, so a tree with a gap hashes differently from the same tree without
one). ``write_ordered`` is the writer for an encoder that fills a list of triples instead of a graph. Terms are pyoxigraph terms.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

import pyoxigraph as ox

from starlayer.errors import FormatError
from starlayer.graph import terms
from starlayer.graph.terms import RDF_TYPE

TREE = "https://github.com/hidden-graph/starlayer/ns/tree#"
ORD = ox.NamedNode(TREE + "ord")
ITEM = ox.NamedNode(TREE + "Item")
VALUE = ox.NamedNode(TREE + "value")
_XSD_INTEGER = ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer")


def _integer(n: int) -> ox.Literal:
    return ox.Literal(str(n), datatype=_XSD_INTEGER)


def _where(parent: Any, prop: Any) -> str:
    return f"{prop} on {parent}"


def _ordinal(graph: Any, node: Any, parent: Any, prop: Any) -> int:
    values = list(graph.objects(node, ORD))
    if len(values) != 1:
        raise FormatError(f"a child of {_where(parent, prop)} has {len(values)} tree:ord values, not one: {node}", kind="rdf", context=_where(parent, prop))
    value = values[0]
    if not (isinstance(value, ox.Literal) and value.datatype == _XSD_INTEGER):
        raise FormatError(f"tree:ord of a child of {_where(parent, prop)} is not an xsd:integer: {value}", kind="rdf", context=_where(parent, prop))
    number = int(value.value)
    if number < 0:
        raise FormatError(f"tree:ord of a child of {_where(parent, prop)} is negative: {number}", kind="rdf", context=_where(parent, prop))
    return number


def _member(graph: Any, node: Any, parent: Any, prop: Any) -> Any:
    """What a child stands for: the node itself, or the ``tree:value`` of its ``tree:Item`` wrapper."""
    if (node, RDF_TYPE, ITEM) in graph:
        values = list(graph.objects(node, VALUE))
        if len(values) != 1:
            raise FormatError(f"a tree:Item of {_where(parent, prop)} has {len(values)} tree:value, not one: {node}", kind="rdf", context=_where(parent, prop))
        return values[0]
    if not isinstance(node, ox.BlankNode):
        raise FormatError(f"{node} is a child of {_where(parent, prop)} without a tree:Item wrapper; only a blank node carries tree:ord itself", kind="rdf", context=_where(parent, prop))
    return node


def _ordered(graph: Any, parent: Any, prop: Any) -> list[tuple[int, Any, Any]]:
    parent, prop = terms.term(parent), terms.term(prop)
    found = []
    for child in graph.objects(parent, prop):
        member = _member(graph, child, parent, prop)
        found.append((_ordinal(graph, child, parent, prop), child, member))
    found.sort(key=lambda row: row[0])
    for before, after in zip(found, found[1:], strict=False):
        if before[0] == after[0]:
            raise FormatError(
                f"two children of {_where(parent, prop)} have the same tree:ord {before[0]}, so their order is not defined",
                kind="rdf", context=_where(parent, prop),
            )
    return found


def ordered_children(graph: Any, parent: Any, prop: Any) -> list[tuple[Any, Any]]:
    """``(child node, member)`` for each child ``parent`` holds for ``prop``, in ascending ordinal; for a ``tree:Item`` the member is its
    ``tree:value``, otherwise the child node itself. No children is an empty list. Raises ``FormatError`` (kind ``"rdf"``) for a child without
    exactly one non-negative ``xsd:integer`` ordinal, a named node or literal that is not in an Item, an Item without exactly one value, or
    two children with the same ordinal."""
    return [(child, member) for _number, child, member in _ordered(graph, parent, prop)]


def ordered_items(graph: Any, parent: Any, prop: Any) -> list[Any]:
    """The members of the sequence ``parent`` holds for ``prop``, in order; see ``ordered_children`` for what it raises."""
    return [member for _number, _child, member in _ordered(graph, parent, prop)]


def _writes(parent: Any, prop: Any, member: Any, number: int, shared: bool = False) -> list[tuple[Any, Any, Any]]:
    """The triples of one child at ``number``: the blank node itself carries the ordinal, anything else (or a blank node that already has a
    parent, ``shared``) goes into a fresh Item."""
    if isinstance(member, ox.BlankNode) and not shared:
        return [(parent, prop, member), (member, ORD, _integer(number))]
    item = ox.BlankNode()
    return [(parent, prop, item), (item, RDF_TYPE, ITEM), (item, ORD, _integer(number)), (item, VALUE, member)]


def write_ordered(sink: Any, parent: Any, prop: Any, members: Iterable[Any]) -> None:
    """Add the children ``members`` of ``parent`` for ``prop`` to ``sink`` (a graph or anything with ``add``), at ordinals 0, 1, 2, ...: a
    blank node carries its own ordinal, any other term goes into a ``tree:Item``. Nothing is written for no members."""
    for number, member in enumerate(members):
        for triple in _writes(parent, prop, member, number):
            sink.add(triple)


def _held(graph: Any, node: Any) -> bool:
    """Does something already point at ``node`` or give it an ordinal?"""
    return any(True for _ in graph.triples((None, None, node))) or any(True for _ in graph.objects(node, ORD))


def _put(graph: Any, parent: Any, prop: Any, member: Any, number: int) -> Any:
    member = terms.term(member)
    shared = isinstance(member, ox.BlankNode) and _held(graph, member)
    triples = _writes(parent, prop, member, number, shared)
    graph.extend(triples)
    return triples[0][2]


def _drop(graph: Any, child: Any, parent: Any, prop: Any) -> None:
    """Remove ``child`` from the sequence: the link and its ordinal, and the wrapper's own triples; the member stays."""
    graph.remove((parent, prop, child))
    graph.remove((child, ORD, None))
    if (child, RDF_TYPE, ITEM) in graph:
        graph.remove((child, RDF_TYPE, ITEM))
        graph.remove((child, VALUE, None))


def append(graph: Any, parent: Any, prop: Any, member: Any) -> Any:
    """Add ``member`` after the last child of ``parent`` for ``prop``; returns the child node (the member itself, or its Item)."""
    parent, prop = terms.term(parent), terms.term(prop)
    rows = _ordered(graph, parent, prop)
    return _put(graph, parent, prop, member, rows[-1][0] + 1 if rows else 0)


def insert_at(graph: Any, parent: Any, prop: Any, index: int, member: Any) -> Any:
    """Insert ``member`` so that it is at position ``index`` (0 is first; an index at or past the end appends). The children from that
    position on move up by one ordinal where they must, so the ordinals before it are unchanged. Returns the child node."""
    parent, prop = terms.term(parent), terms.term(prop)
    rows = _ordered(graph, parent, prop)
    if index < 0:
        raise ValueError("index must not be negative")
    if index >= len(rows):
        return append(graph, parent, prop, member)
    target = rows[index][0]
    for number, child, _unused in rows[index:]:
        graph.remove((child, ORD, None))
        graph.add((child, ORD, _integer(number + 1)))
    return _put(graph, parent, prop, member, target)


def remove_at(graph: Any, parent: Any, prop: Any, index: int) -> Any:
    """Remove the child at position ``index`` and return its member. The other ordinals are not changed (a gap is left;
    ``renumber_dense`` closes it)."""
    parent, prop = terms.term(parent), terms.term(prop)
    rows = _ordered(graph, parent, prop)
    _number, child, member = rows[index]
    _drop(graph, child, parent, prop)
    return member


def replace_at(graph: Any, parent: Any, prop: Any, index: int, member: Any) -> Any:
    """Put ``member`` at position ``index`` in place of the child that was there, at the same ordinal. Returns the new child node."""
    parent, prop = terms.term(parent), terms.term(prop)
    rows = _ordered(graph, parent, prop)
    number, child, _old = rows[index]
    _drop(graph, child, parent, prop)
    return _put(graph, parent, prop, member, number)


def renumber_dense(graph: Any, parent: Any = None, prop: Any = None) -> Any:
    """Make the ordinals 0, 1, 2, ... without gaps, keeping the order: for the sequence of ``parent`` and ``prop``, or, with neither, for every
    sequence in ``graph``. Run it before RDFC-1.0 canonicalisation or a hash, so a tree that lost a child hashes as the same tree written
    fresh. Raises ``FormatError`` where an order is not defined (a tie, a bad ordinal) or a node with an ordinal has more than one parent or
    property. Returns ``graph``."""
    if parent is not None:
        groups = {(terms.term(parent), terms.term(prop))}
    else:
        incoming: dict[Any, set[tuple[Any, Any]]] = defaultdict(set)
        for child in {s for s, _p, _o in graph.triples((None, ORD, None))}:
            for s, p, _o in graph.triples((None, None, child)):
                incoming[child].add((s, p))
            if len(incoming[child]) != 1:
                raise FormatError(
                    f"{child} carries tree:ord and has {len(incoming[child])} parents or properties, so its position is ambiguous",
                    kind="rdf",
                )
        groups = {pair for pairs in incoming.values() for pair in pairs}
    for group_parent, group_prop in groups:
        for new, (number, child, _unused) in enumerate(_ordered(graph, group_parent, group_prop)):
            if number != new:
                graph.remove((child, ORD, None))
                graph.add((child, ORD, _integer(new)))
    return graph
