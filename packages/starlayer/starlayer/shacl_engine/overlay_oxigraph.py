"""``OxigraphOverlay``: the inferred-triples overlay of ``rules.InferredView`` kept in an in-memory ``pyoxigraph.Store``.

Experimental, opt-in (``rules.use_oxigraph_overlay(True)`` or ``STARLAYER_SHACL_OVERLAY=oxigraph``); see
docs/working/shacl-engine-overlay-oxigraph.md for the measurements and the recommendation.

Fidelity guard. A pyoxigraph store rewrites some literals on insert (``"04"^^xsd:integer`` -> ``"4"``, ``"1"^^xsd:boolean``
-> ``"true"``, ``"4.0"^^xsd:decimal`` -> ``"4"``, derived integer types such as ``xsd:unsignedByte`` -> ``xsd:integer``,
language tags lower-cased, ``xsd:string`` -> simple literal), and a lookup with an un-normalised literal matches the
normalised stored one. Derived triples can carry source literals (a copying rule, ``rdfs:subPropertyOf``), so a literal
that the store would not return exactly as given is never inserted: that triple stays in a small Python-side index
(``InferredView`` storage) and is returned exactly as inferred. Whether a literal is safe is decided once per
(lexical form, datatype, language) by a round trip through a scratch store, and cached. A pattern that names an unsafe
literal is answered from the Python side only, never from the store. A triple whose terms pyoxigraph cannot hold at all
(literal subject, ...) also stays Python-side.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pyoxigraph as ox

from starlayer.shacl_engine.rules import InferredView, Triple

_SCRATCH = ox.Store()
_SAFE: dict[tuple, bool] = {}
_S, _P = ox.NamedNode("http://example.org/scratch#s"), ox.NamedNode("http://example.org/scratch#p")


def literal_survives_store(term: ox.Literal) -> bool:
    """True if ``term`` (a literal) comes back from a pyoxigraph store exactly as given. Cached per
    (lexical form, datatype, language, direction)."""
    key = (term.value, term.datatype.value, term.language, None if term.direction is None else str(term.direction))
    ok = _SAFE.get(key)
    if ok is None:
        ok = _SAFE[key] = _round_trip_ok(term)
    return ok


def _round_trip_ok(term: ox.Literal) -> bool:
    try:
        _SCRATCH.clear()
        _SCRATCH.add(ox.Quad(_S, _P, term, ox.DefaultGraph()))
        back = next(iter(_SCRATCH)).object
        _SCRATCH.clear()
    except (TypeError, ValueError, RuntimeError):
        return False
    # exact comparison of the parts: Literal equality alone could hide a rewritten language-tag case
    return (back.value, back.datatype, back.language, back.direction) == (
        term.value,
        term.datatype,
        term.language,
        term.direction,
    )


def term_is_safe(term: Any) -> bool:
    """Can the store hold ``term`` and return it exactly? Triple terms are safe when their parts are."""
    if isinstance(term, ox.Literal):
        return literal_survives_store(term)
    if isinstance(term, ox.Triple):
        return term_is_safe(term.subject) and term_is_safe(term.predicate) and term_is_safe(term.object)
    return True


class OxigraphOverlay(InferredView):
    """Same interface as ``InferredView``. Safe inferred triples live in a pyoxigraph store, the rest in the inherited
    Python storage (``self._inferred`` / ``self._index``, the "side" set)."""

    def __init__(self, base: Any) -> None:
        super().__init__(base)
        self._store = ox.Store()
        self._stored = 0  # number of triples in the store

    # -- helpers
    def _in_store(self, s: Any, p: Any, o: Any) -> bool:
        return next(iter(self._store.quads_for_pattern(s, p, o, ox.DefaultGraph())), None) is not None

    def _store_quads(self, s: Any, p: Any, o: Any) -> Iterator[Any]:
        # Oxigraph raises on a literal / triple-term subject or a non-IRI predicate; RDF graphs simply have no match there.
        if isinstance(s, (ox.Literal, ox.Triple)) or (p is not None and not isinstance(p, ox.NamedNode)):
            return iter(())
        if (o is not None and not term_is_safe(o)) or (s is not None and not term_is_safe(s)):
            return iter(())  # an unsafe term is never in the store (and a lookup by it would match its normalised twin)
        return self._store.quads_for_pattern(s, p, o, ox.DefaultGraph())

    # -- writes
    def add(self, triple: Triple) -> bool:
        s, p, o = triple
        if triple in self.base or triple in self._inferred:
            return False
        if term_is_safe(o) and term_is_safe(s):
            try:
                if self._in_store(s, p, o):
                    return False
                self._store.add(ox.Quad(s, p, o, ox.DefaultGraph()))
                self._stored += 1
            except (TypeError, ValueError):
                return super().add(triple)  # a term pyoxigraph cannot hold: keep it on the Python side
            if self._mat is not None:
                self._mat.add(triple)
            return True
        return super().add(triple)

    def remove(self, triple: Triple) -> None:
        if triple in self._inferred:
            super().remove(triple)
            return
        s, p, o = triple
        if not (term_is_safe(o) and term_is_safe(s)):
            return
        try:
            if self._in_store(s, p, o):
                self._store.remove(ox.Quad(s, p, o, ox.DefaultGraph()))
                self._stored -= 1
                self._mat = None
        except (TypeError, ValueError):
            return

    @property
    def inferred(self) -> frozenset[Triple]:
        out = set(self._inferred)
        for q in self._store:
            out.add((q.subject, q.predicate, q.object))
        return frozenset(out)

    def __len__(self) -> int:
        return len(self._inferred) + self._stored

    # -- GraphView
    def triples(self, pattern: tuple[Any, Any, Any]) -> Iterator[Triple]:
        s, p, o = pattern
        yield from self.base.triples((s, p, o))
        for q in self._store_quads(s, p, o):
            yield q.subject, q.predicate, q.object
        yield from self._inferred_matching(s, p, o)

    def objects(self, subject: Any = None, predicate: Any = None) -> Iterator[Any]:
        seen: set = set()
        for o in self.base.objects(subject, predicate):
            if o not in seen:
                seen.add(o)
                yield o
        for q in self._store_quads(subject, predicate, None):
            o = q.object
            if o not in seen:
                seen.add(o)
                yield o
        for _s, _p, o in self._inferred_matching(subject, predicate, None):
            if o not in seen:
                seen.add(o)
                yield o

    def subjects(self, predicate: Any = None, object: Any = None) -> Iterator[Any]:  # noqa: A002
        seen: set = set()
        for s in self.base.subjects(predicate, object):
            if s not in seen:
                seen.add(s)
                yield s
        for q in self._store_quads(None, predicate, object):
            s = q.subject
            if s not in seen:
                seen.add(s)
                yield s
        for s, _p, _o in self._inferred_matching(None, predicate, object):
            if s not in seen:
                seen.add(s)
                yield s

    def predicate_objects(self, subject: Any = None) -> Iterator[tuple[Any, Any]]:
        for _s, p, o in self.triples((subject, None, None)):
            yield p, o

    def __contains__(self, triple: Triple) -> bool:
        if triple in self._inferred or triple in self.base:
            return True
        s, p, o = triple
        return next(iter(self._store_quads(s, p, o)), None) is not None

    # -- SPARQL: the materialised union is an StarLayerGraph (the store normalises its literals, as for any query on a store)
    def materialised(self) -> Any:
        if self._mat is None:
            from starlayer.shacl_engine.graphs import new_graph

            mat = new_graph()
            mat.extend(list(self.base.triples((None, None, None))))
            mat.extend(list(self.inferred))
            self._mat = mat
        return self._mat


__all__ = ["OxigraphOverlay", "literal_survives_store", "term_is_safe"]
