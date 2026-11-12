"""Recording the stored triples an evaluation reads, for ``extract_subgraph`` (a fragment must hold what ``sh:values`` /
``sh:defaultValue`` read to compute their values, so that evaluating the fragment recomputes them).

``RecordingGraph`` stands in for the data graph: it forwards every read and notes the triples it returned. A SPARQL query runs
inside Oxigraph, where reads cannot be observed, so for ``sh:select`` the notes are the query's relevant triples
(``starlayer.sparql.relevant``).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

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
            self._reads |= self._query_reads(text, dict(init_bindings or {}), custom_functions)
        return result

    def _query_reads(self, text: str, bindings: dict, custom_functions: Any) -> set[_Triple]:
        """The triples the query depends on (``starlayer.sparql.relevant``). The support queries run on the engine's own
        Oxigraph view of the graph, with the same pre-bound variables and custom functions as the query."""
        from starlayer.sparql.relevant import relevant_triples

        base = self._g.materialised() if hasattr(self._g, "materialised") else self._g
        view = base.engine_view() if hasattr(base, "engine_view") else None

        def run(construct: str) -> Any:
            return view.query(construct, bindings, custom_functions=custom_functions)

        try:
            return relevant_triples(self._g, text, bindings, run if view is not None else None)[0]
        except ValueError:  # an update or DESCRIBE: nothing to record
            return set()
