"""Recording the stored triples an evaluation reads, for ``extract_subgraph`` (a fragment must hold what ``sh:values`` /
``sh:defaultValue`` read to compute their values, so that evaluating the fragment recomputes them).

``RecordingGraph`` stands in for the data graph: it forwards every read and notes the triples it returned. A SPARQL query runs
inside Oxigraph, where reads cannot be observed, so for ``sh:select`` the notes are the triples that match a triple pattern of
the query (constants and the pre-bound variables fixed, other variables free): a superset of what the query reads, never less.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

import pyoxigraph as ox

_Triple = tuple[Any, Any, Any]


class RecordingGraph:
    """A read-only view of an engine graph that records the triples read while ``recording()`` is active."""

    engine_terms = True

    def __init__(self, graph: Any) -> None:
        self._g = graph
        self._reads: set[_Triple] | None = None

    @contextmanager
    def recording(self) -> Iterator[set[_Triple]]:
        outer, self._reads = self._reads, set()
        try:
            yield self._reads
        finally:
            self._reads = outer

    def __getattr__(self, name: str) -> Any:
        return getattr(self._g, name)

    def _read(self, pattern: _Triple) -> Iterator[_Triple]:
        for t in self._g.triples(pattern):
            triple = (t[0], t[1], t[2])
            if self._reads is not None:
                self._reads.add(triple)
            yield triple

    def triples(self, pattern: _Triple = (None, None, None)) -> Iterator[_Triple]:
        return self._read(pattern)

    def __iter__(self) -> Iterator[_Triple]:
        return self._read((None, None, None))

    def __contains__(self, item: Any) -> bool:
        return item in self._g

    def __len__(self) -> int:
        return len(self._g)

    def _project(self, pattern: _Triple, slot: int, unique: bool) -> Iterator[Any]:
        seen: set = set()
        for t in self._read(pattern):
            if unique:
                if t[slot] in seen:
                    continue
                seen.add(t[slot])
            yield t[slot]

    def objects(self, subject: Any = None, predicate: Any = None, unique: bool = False) -> Iterator[Any]:
        return self._project((subject, predicate, None), 2, unique)

    def subjects(self, predicate: Any = None, object: Any = None, unique: bool = False) -> Iterator[Any]:  # noqa: A002
        return self._project((None, predicate, object), 0, unique)

    def predicates(self, subject: Any = None, object: Any = None, unique: bool = False) -> Iterator[Any]:  # noqa: A002
        return self._project((subject, None, object), 1, unique)

    def predicate_objects(self, subject: Any = None) -> Iterator[tuple[Any, Any]]:
        for _s, p, o in self._read((subject, None, None)):
            yield p, o

    def subject_objects(self, predicate: Any = None) -> Iterator[tuple[Any, Any]]:
        for s, _p, o in self._read((None, predicate, None)):
            yield s, o

    def subject_predicates(self, object: Any = None) -> Iterator[tuple[Any, Any]]:  # noqa: A002
        for s, p, _o in self._read((None, None, object)):
            yield s, p

    def value(self, subject: Any = None, predicate: Any = None, object: Any = None, default: Any = None, any: bool = True) -> Any:  # noqa: A002
        slot = 0 if subject is None else 1 if predicate is None else 2
        found = [t[slot] for t in self._read((subject, predicate, object))]
        if not found:
            return default
        if not any and len(found) > 1:
            raise ValueError("value() found more than one match")
        return found[0]

    def sparql_query(self, text: str, init_bindings: Mapping[str, Any] | None = None, custom_functions: Any = None) -> Any:
        result = self._g.sparql_query(text, init_bindings, custom_functions)
        if self._reads is not None:
            self._reads |= query_reads(self._g, text, init_bindings or {})
        return result


def query_reads(graph: Any, text: str, bindings: Mapping[str, Any]) -> set[_Triple]:
    """The triples of ``graph`` that match some triple pattern of the query ``text`` (``bindings`` fix the pre-bound variables)."""
    from starlayer.sparql.parse_sparql import Node, parse_sparql

    patterns: list[Node] = []

    def walk(item: Any) -> None:
        if isinstance(item, Node):
            if item.kind == "TriplePattern":
                patterns.append(item)
            for value in item.f.values():
                walk(value)
        elif isinstance(item, (list, tuple)):
            for value in item:
                walk(value)

    walk(parse_sparql(text))

    def fixed(term: Any) -> Any:
        if isinstance(term, (ox.NamedNode, ox.Literal, ox.BlankNode)):
            return term
        name = getattr(term, "value", None)
        if isinstance(term, ox.Variable) and name in bindings:
            return bindings[name]
        return None  # a free variable, a path, a triple term: any

    reads: set[_Triple] = set()
    for pattern in patterns:
        s, p, o = (fixed(pattern.f.get(k)) for k in ("s", "p", "o"))
        for t in graph.triples((s, p, o)):
            reads.add((t[0], t[1], t[2]))
    return reads
