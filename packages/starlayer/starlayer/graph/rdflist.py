"""RDF lists and graph walks, as thin functions on a graph (bound as methods of ``StarLayerGraph`` / ``StarLayerDataset``).
A list is a chain of list nodes: blank nodes that each have one ``rdf:first`` (the member) and one ``rdf:rest`` (the next list node, or
``rdf:nil``); its head is the first list node, and ``rdf:nil`` alone is the empty list.
``add_list`` writes the list nodes of a list (``rdf:first`` / ``rdf:rest`` on fresh blank nodes), ``remove_list`` takes them away,
``set_list`` replaces a property's list, and ``transitive_objects`` / ``transitive_subjects`` follow a predicate to a fixpoint.
Reading a list is ``graph.items(head)``. Terms are pyoxigraph terms.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

import pyoxigraph as ox

from starlayer.errors import FormatError

from starlayer.graph import terms
from starlayer.graph.terms import RDF_FIRST, RDF_NIL, RDF_REST


def add_list(graph: Any, items: Iterable[Any], head: Any = None) -> Any:
    """Write ``items`` as an RDF list and return its head: ``rdf:nil`` for no items, else the first list node (``head``, a node the caller
    names, or a fresh blank node). An item that is a 3-tuple is a triple term. Nothing points at the head yet: add that triple
    yourself, or use ``set_list``."""
    members = [terms.term(i) for i in items]
    if not members:
        return RDF_NIL
    cells = [terms.term(head) if head is not None and n == 0 else ox.BlankNode() for n in range(len(members))]
    triples = []
    for n, (cell, member) in enumerate(zip(cells, members, strict=True)):
        triples.append((cell, RDF_FIRST, member))
        triples.append((cell, RDF_REST, cells[n + 1] if n + 1 < len(cells) else RDF_NIL))
    graph.extend(triples)
    return cells[0]


def list_cells(graph: Any, head: Any) -> list[Any]:
    """The list nodes of the list that starts at ``head``, in order (empty for ``rdf:nil``). Raises a ``FormatError`` (kind ``"rdf"``) for a cycle or a list node
    without exactly one ``rdf:rest``."""
    cells: list[Any] = []
    seen: set[Any] = set()
    node = terms.term(head)
    while node != RDF_NIL:
        if node in seen:
            raise FormatError("the list has a cycle", kind="rdf", context=f"rdf:List at {head}")
        seen.add(node)
        rest = list(graph.objects(node, RDF_REST))
        if len(rest) != 1:
            raise FormatError(f"{node} is not a list cell: it has {len(rest)} rdf:rest", kind="rdf", context=f"rdf:List at {head}")
        cells.append(node)
        node = rest[0]
    return cells


def remove_list(graph: Any, head: Any) -> Any:
    """Remove the list nodes of the list that starts at ``head`` (their ``rdf:first`` and ``rdf:rest`` triples). Members are not touched and
    the triple that points at the head stays; ``graph`` is returned."""
    for cell in list_cells(graph, head):
        graph.remove((cell, RDF_FIRST, None))
        graph.remove((cell, RDF_REST, None))
    return graph


def set_list(graph: Any, subject: Any, predicate: Any, items: Iterable[Any]) -> Any:
    """Make ``items`` the one list that ``subject`` has for ``predicate``: remove what was there (a list's list nodes too, when the value is
    one) and write the new list. Returns its head."""
    subject, predicate = terms.term(subject), terms.term(predicate)
    for old in list(graph.objects(subject, predicate)):
        if isinstance(old, ox.BlankNode) or old == RDF_NIL:
            try:
                remove_list(graph, old)
            except FormatError:  # the value is a blank node but not a list: only the link goes
                pass
    graph.remove((subject, predicate, None))
    head = add_list(graph, items)
    graph.add((subject, predicate, head))
    return head


def transitive_objects(graph: Any, subject: Any, predicate: Any, remember: set[Any] | None = None) -> Iterator[Any]:
    """``subject`` and every node reached from it by repeating ``predicate`` (``subject predicate ?o``, then from each ``?o``), each once,
    ``subject`` first; a cycle ends. (``rdflib.Graph.transitive_objects``.)"""
    seen = set() if remember is None else remember
    stack = [terms.term(subject)]
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        yield node
        stack.extend(o for o in graph.objects(node, predicate) if o not in seen)


def transitive_subjects(graph: Any, predicate: Any, object: Any, remember: set[Any] | None = None) -> Iterator[Any]:  # noqa: A002
    """``object`` and every node that reaches it by repeating ``predicate`` (``?s predicate object``, then ``?s2 predicate ?s``), each once,
    ``object`` first; a cycle ends. (``rdflib.Graph.transitive_subjects``.)"""
    seen = set() if remember is None else remember
    stack = [terms.term(object)]
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        yield node
        stack.extend(s for s in graph.subjects(predicate, node) if s not in seen)
