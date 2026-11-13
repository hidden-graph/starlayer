"""``TreeIndex``: the read side of a graph (``value``, ``objects``, ``predicate_objects``, ``in``, ``items``) over a list of
triples held in memory.

``sqe_tree_to_text`` reads a tree through those graph methods. The query rewrites (``rewrite.py``, ``entailment.py``) render a
tree they have just built from a parsed query; going through a ``StarLayerGraph`` would cost a store write per triple and an
Oxigraph store rewrites some literal lexical forms, which a query that is about to be run must not suffer. A ``TreeIndex``
answers the same calls from a dict and changes nothing.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator
from typing import Any

from starlayer.sparql._oxterms import RDF


class TreeIndex:
    """In-memory triple index answering the graph read calls that ``sqe_tree_to_text`` makes."""

    def __init__(self, triples: Iterable[tuple[Any, Any, Any]]) -> None:
        """Index ``triples`` by subject, consuming the iterable once."""
        self._by_subject: dict[Any, list[tuple[Any, Any]]] = defaultdict(list)
        for s, p, o in triples:
            self._by_subject[s].append((p, o))

    def predicate_objects(self, subject: Any = None) -> Iterator[tuple[Any, Any]]:
        """Yield the ``(predicate, object)`` pairs of ``subject`` in insertion order."""
        return iter(self._by_subject.get(subject, ()))

    def objects(self, subject: Any = None, predicate: Any = None) -> Iterator[Any]:
        """Yield the objects of ``subject``, only those under ``predicate`` unless it is ``None``."""
        return (o for p, o in self._by_subject.get(subject, ()) if predicate is None or p == predicate)

    def value(self, subject: Any = None, predicate: Any = None, object: Any = None, default: Any = None) -> Any:  # noqa: A002
        """Return the first object of ``subject`` under ``predicate``, or ``default`` if there is none.

        Subject and predicate are both required; ``ValueError`` otherwise.

        Args:
            object: Accepted for the graph interface and ignored.
        """
        if subject is None or predicate is None:
            raise ValueError("TreeIndex.value needs a subject and a predicate")
        return next(self.objects(subject, predicate), default)

    def __contains__(self, triple: tuple[Any, Any, Any]) -> bool:
        """Whether a triple matches; a ``None`` predicate or object is a wildcard, a ``None`` subject matches nothing."""
        s, p, o = triple
        return any((p is None or q == p) and (o is None or o == x) for q, x in self._by_subject.get(s, ()))

    def items(self, head: Any) -> Iterator[Any]:
        """Yield the members of the RDF list starting at ``head``, in order."""
        while head != RDF.nil:
            yield self.value(head, RDF.first)
            head = self.value(head, RDF.rest)


def as_engine_graph(graph: Any, root: Any = None) -> tuple[Any, Any]:
    """``(graph, root)`` with pyoxigraph terms: a ``StarLayerGraph`` or ``TreeIndex`` passes as it is; an rdflib graph (and an rdflib
    root) is copied by the rdflib bridge, relative IRIs becoming the stand-ins ``_oxterms`` takes apart again. Needs rdflib only
    when handed an rdflib graph."""
    if graph is None or getattr(graph, "engine_terms", False) or isinstance(graph, TreeIndex):
        return graph, root
    from starlayer.shacl_engine.terms import engine_view, term_policy, to_engine

    with term_policy("lenient"):
        return engine_view(graph), to_engine(root)


def fill_foreign(target: Any, tree: Any) -> None:
    """Copy the triples of the ``StarLayerGraph`` ``tree`` into ``target``, an rdflib graph (terms converted by the bridge)."""
    from starlayer.shacl_engine.terms import from_engine

    for s, p, o in tree.triples((None, None, None)):
        target.add((from_engine(s), from_engine(p), from_engine(o)))
