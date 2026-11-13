"""A small in-memory graph of pyoxigraph terms that keeps every literal exactly as written.

``StarLayerGraph`` stores through Oxigraph, which normalizes lexical forms ("4.0"^^xsd:decimal stays, "04"^^xsd:integer becomes "4");
the W3C expected reports and manifests must be read as written, so the test harness holds them here. It implements the engine's
``GraphView`` surface plus the few helpers the tests use (``value``, ``items``, ``add``).
"""

from __future__ import annotations

from collections.abc import Iterator

import pyoxigraph as ox
from starlayer.graph import RDF


class LexicalGraph:
    """Triples in a set; ``None`` in a pattern is a wildcard."""

    engine_terms = True
    preserves_lexical_forms = True

    def __init__(self) -> None:
        self._triples: set[tuple] = set()
        self.prefixes: dict[str, str] = {}

    def add(self, triple: tuple) -> LexicalGraph:
        """Add a (subject, predicate, object) triple."""
        self._triples.add(tuple(triple))
        return self

    def bind(self, prefix: str, namespace: object) -> None:
        """Remember a prefix (kept only so a copy can carry it)."""
        self.prefixes[prefix] = str(namespace)

    def namespaces(self) -> Iterator[tuple[str, str]]:
        """The bound (prefix, namespace) pairs."""
        return iter(self.prefixes.items())

    def triples(self, pattern: tuple = (None, None, None)) -> Iterator[tuple]:
        """The triples matching ``pattern``."""
        s, p, o = pattern
        for triple in list(self._triples):
            if (s is None or triple[0] == s) and (p is None or triple[1] == p) and (o is None or triple[2] == o):
                yield triple

    def objects(self, subject=None, predicate=None) -> Iterator:
        """The objects of the matching triples."""
        return (o for _s, _p, o in self.triples((subject, predicate, None)))

    def subjects(self, predicate=None, object=None) -> Iterator:  # noqa: A002
        """The subjects of the matching triples."""
        return (s for s, _p, _o in self.triples((None, predicate, object)))

    def predicate_objects(self, subject=None) -> Iterator[tuple]:
        """The (predicate, object) pairs of the matching triples."""
        return ((p, o) for _s, p, o in self.triples((subject, None, None)))

    def subject_objects(self, predicate=None) -> Iterator[tuple]:
        """The (subject, object) pairs of the matching triples."""
        return ((s, o) for s, _p, o in self.triples((None, predicate, None)))

    def value(self, subject=None, predicate=None, object=None, default=None):  # noqa: A002
        """The first matching term in the position left empty, or ``default``."""
        for s, p, o in self.triples((subject, predicate, object)):
            return o if object is None else (p if predicate is None else s)
        return default

    def items(self, head) -> Iterator:
        """The members of the RDF collection starting at ``head``."""
        while head is not None and head != RDF.nil:
            yield self.value(head, RDF.first)
            head = self.value(head, RDF.rest)

    def serialize(self, format: str = "turtle") -> str:  # noqa: A002 - for failure messages
        """The triples as text (``turtle`` or ``nt``), for a readable assertion message."""
        fmt = ox.RdfFormat.N_TRIPLES if format in ("nt", "ntriples") else ox.RdfFormat.TURTLE
        quads = [ox.Quad(s, p, o, ox.DefaultGraph()) for s, p, o in sorted(self._triples, key=str)]
        return ox.serialize(quads, format=fmt).decode("utf-8")

    def __contains__(self, triple: tuple) -> bool:
        return next(self.triples(triple), None) is not None

    def __iter__(self) -> Iterator[tuple]:
        return iter(list(self._triples))

    def __len__(self) -> int:
        return len(self._triples)

    def __add__(self, other: LexicalGraph) -> LexicalGraph:
        out = LexicalGraph()
        out._triples = self._triples | set(other)
        return out


__all__ = ["LexicalGraph", "ox"]
