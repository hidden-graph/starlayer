"""``OxigraphGraph``: a ``GraphView`` straight over a ``pyoxigraph.Store`` (no rdflib graph in between).

Terms handed to and from the engine stay ``rdflib`` nodes plus ``starlayer.graph.model`` ``TripleTerm`` /
``DirLangString``; conversion happens only here, in ``to_ox`` / ``from_ox``.

Known, parked limitations (oxigraph/oxigraph#526): Oxigraph normalizes literals on storage ("04"^^xsd:integer becomes
"4", "1"^^xsd:boolean becomes "true", some ill-formed literals are rewritten or dropped), so ``preserves_lexical_forms``
is False. Oxigraph also reports ``"x"`` and ``"x"^^xsd:string`` as the same term; ``from_ox`` returns the simple
rdflib ``Literal("x")``, so an explicit rdflib ``Literal("x", datatype=XSD.string)`` does not round-trip.

Graph selection: ``graph_name=UNION`` (the default) reads the union of all graphs, de-duplicating triples that occur in
several graphs; ``graph_name=DEFAULT`` reads the default graph; an IRI/blank node reads that named graph.

``query``: SPARQL runs natively through ``Store.query``. Pre-bound variables use pyoxigraph's ``substitutions``
(RDF-dev SEP-0007). Limitation of the library: a substituted variable must appear in a SELECT projection (use
``SELECT *`` or project it); ASK and CONSTRUCT have no such restriction.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyoxigraph as ox
from rdflib import BNode, Literal, URIRef
from rdflib.namespace import XSD

from starlayer.graph.model.dirlangstring import DirLangString
from starlayer.graph.model.triple import TripleTerm

UNION = object()
DEFAULT = object()

_XSD_STRING = str(XSD.string)
_DIRECTIONS = {"ltr": ox.BaseDirection.LTR, "rtl": ox.BaseDirection.RTL}


# Term conversion caches. The same IRIs and blank nodes are converted millions of times in a run; both term kinds are
# immutable and compare by (type, lexical value), so sharing one converted object is behaviour-identical. Literals are
# not cached on the to_ox side (rdflib Literal equality/hash is value-based across datatypes, so it is not a safe key).
# Bounded: a cache that grows past _CACHE_MAX entries is cleared (a plain, cheap eviction; the working set refills).
_CACHE_MAX = 200_000
_TO_OX: dict = {}
_FROM_OX: dict = {}


def to_ox(term: Any) -> Any:
    """Engine term -> pyoxigraph term. ``None`` stays ``None`` (a wildcard)."""
    if term is None:
        return None
    cls = type(term)
    if cls is URIRef or cls is BNode:
        out = _TO_OX.get(term)
        if out is None:
            if len(_TO_OX) >= _CACHE_MAX:
                _TO_OX.clear()
            out = _TO_OX[term] = ox.NamedNode(str(term)) if cls is URIRef else ox.BlankNode(str(term))
        return out
    if isinstance(term, URIRef):
        return ox.NamedNode(str(term))
    if isinstance(term, BNode):
        return ox.BlankNode(str(term))
    if isinstance(term, DirLangString):
        return ox.Literal(term.value, language=term.language, direction=_DIRECTIONS[term.direction])
    if isinstance(term, Literal):
        if term.language:
            return ox.Literal(str(term), language=term.language)
        if term.datatype is not None:
            return ox.Literal(str(term), datatype=ox.NamedNode(str(term.datatype)))
        return ox.Literal(str(term))
    if isinstance(term, TripleTerm):
        return ox.Triple(to_ox(term.subject), to_ox(term.predicate), to_ox(term.object))
    if isinstance(term, tuple) and len(term) == 3:
        return to_ox(TripleTerm(*term))
    raise TypeError(f"cannot convert {term!r} ({type(term).__name__}) to an Oxigraph term")


def from_ox(term: Any) -> Any:
    """pyoxigraph term -> engine term (IRIs, blank nodes and literals are cached; triple terms are rebuilt)."""
    if term is None:
        return None
    if isinstance(term, ox.Triple):
        return TripleTerm(from_ox(term.subject), from_ox(term.predicate), from_ox(term.object))
    out = _FROM_OX.get(term)
    if out is None:
        out = _from_ox(term)
        if len(_FROM_OX) >= _CACHE_MAX:
            _FROM_OX.clear()
        _FROM_OX[term] = out
    return out


def _from_ox(term: Any) -> Any:
    if isinstance(term, ox.NamedNode):
        return URIRef(term.value)
    if isinstance(term, ox.BlankNode):
        return BNode(term.value)
    if isinstance(term, ox.Literal):
        if term.language:
            if term.direction is not None:
                return DirLangString(term.value, term.language, str(term.direction))
            return Literal(term.value, lang=term.language)
        dt = term.datatype.value
        return Literal(term.value) if dt == _XSD_STRING else Literal(term.value, datatype=URIRef(dt))
    if isinstance(term, ox.Triple):
        return TripleTerm(from_ox(term.subject), from_ox(term.predicate), from_ox(term.object))
    raise TypeError(f"unknown pyoxigraph term {term!r}")


class OxigraphGraph:
    preserves_lexical_forms = False
    native_sparql = True

    def __init__(self, store: ox.Store | None = None, graph_name: Any = UNION) -> None:
        self.store = store if store is not None else ox.Store()
        self.graph_name = graph_name
        if graph_name is UNION:
            self._graph = None
        elif graph_name is DEFAULT:
            self._graph = ox.DefaultGraph()
        else:
            self._graph = to_ox(graph_name)

    # ---- constructors -------------------------------------------------------------------------------------------
    @classmethod
    def from_file(cls, path: str | Path, *, graph_name: Any = UNION, base_iri: str | None = None) -> OxigraphGraph:
        """Load a Turtle / TriG / N-Triples / N-Quads file (by extension). A triple-only format goes to the default
        graph, or to ``graph_name`` when that is a named graph."""
        path = Path(path)
        fmt = ox.RdfFormat.from_extension(path.suffix.lstrip(".")) or ox.RdfFormat.TURTLE
        target = graph_name if graph_name not in (UNION, DEFAULT) else None
        store = ox.Store()
        store.load(path=str(path), format=fmt, base_iri=base_iri, to_graph=to_ox(target))
        return cls(store, graph_name)

    @classmethod
    def from_text(
        cls, text: str, *, format: str = "turtle", graph_name: Any = UNION, base_iri: str | None = None
    ) -> OxigraphGraph:
        fmt = {"turtle": ox.RdfFormat.TURTLE, "trig": ox.RdfFormat.TRIG, "nt": ox.RdfFormat.N_TRIPLES}[format]
        target = graph_name if graph_name not in (UNION, DEFAULT) else None
        store = ox.Store()
        store.load(text.encode(), format=fmt, base_iri=base_iri, to_graph=to_ox(target))
        return cls(store, graph_name)

    @classmethod
    def from_graph(cls, graph: Any, *, graph_name: Any = UNION) -> OxigraphGraph:
        """Copy the triples of an rdflib / StarLayerGraph (anything with ``.triples((None, None, None))``) in."""
        store = ox.Store()
        target = ox.DefaultGraph() if graph_name in (UNION, DEFAULT) else to_ox(graph_name)
        store.bulk_extend(
            ox.Quad(to_ox(s), to_ox(p), to_ox(o), target) for s, p, o in graph.triples((None, None, None))
        )
        return cls(store, graph_name)

    def add(self, triple: tuple[Any, Any, Any]) -> None:
        g = ox.DefaultGraph() if self._graph is None else self._graph
        self.store.add(ox.Quad(*(to_ox(t) for t in triple), g))

    # ---- GraphView ----------------------------------------------------------------------------------------------
    def _quads(self, s: Any, p: Any, o: Any) -> Iterator[ox.Quad]:
        # Oxigraph raises on a literal / triple term subject or a non-IRI predicate; RDF graphs simply have no match.
        if isinstance(s, (Literal, DirLangString, TripleTerm)) or (p is not None and not isinstance(p, URIRef)):
            return iter(())
        return self.store.quads_for_pattern(to_ox(s), to_ox(p), to_ox(o), self._graph)

    def triples(self, pattern: tuple[Any, Any, Any]) -> Iterator[tuple[Any, Any, Any]]:
        s, p, o = pattern
        seen: set | None = set() if self._graph is None else None
        for q in self._quads(s, p, o):
            key = (q.subject, q.predicate, q.object)
            if seen is not None:
                if key in seen:
                    continue
                seen.add(key)
            yield from_ox(q.subject), from_ox(q.predicate), from_ox(q.object)

    def objects(self, subject: Any = None, predicate: Any = None) -> Iterator[Any]:
        # Only the object is converted; with subject and predicate fixed the union de-duplicates on the object alone.
        if subject is None or predicate is None:
            for _s, _p, o in self.triples((subject, predicate, None)):
                yield o
            return
        seen: set | None = set() if self._graph is None else None
        for q in self._quads(subject, predicate, None):
            o = q.object
            if seen is not None:
                if o in seen:
                    continue
                seen.add(o)
            yield from_ox(o)

    def subjects(self, predicate: Any = None, object: Any = None) -> Iterator[Any]:
        if predicate is None or object is None:
            for s, _p, _o in self.triples((None, predicate, object)):
                yield s
            return
        seen: set | None = set() if self._graph is None else None
        for q in self._quads(None, predicate, object):
            s = q.subject
            if seen is not None:
                if s in seen:
                    continue
                seen.add(s)
            yield from_ox(s)

    def predicate_objects(self, subject: Any = None) -> Iterator[tuple[Any, Any]]:
        for _s, p, o in self.triples((subject, None, None)):
            yield p, o

    def __contains__(self, triple: tuple[Any, Any, Any]) -> bool:
        s, p, o = triple
        return next(iter(self._quads(s, p, o)), None) is not None

    def __len__(self) -> int:
        return sum(1 for _ in self.triples((None, None, None)))

    # ---- SPARQL -------------------------------------------------------------------------------------------------
    def sparql_query(self, text: str, init_bindings: dict[str, Any] | None = None) -> Any:
        """The ``SparqlCapable`` hook (see ``interface.py``): SELECT/ASK with pre-bound variables, run natively.
        Oxigraph requires a substituted variable to be projected; when it is not, the query is run through
        StarLayer's query layer on a StarLayerGraph copy instead (slower, same answer)."""
        from starlayer.shacl_engine.interface import Solutions

        subs = {ox.Variable(str(k).lstrip("?$")): to_ox(v) for k, v in (init_bindings or {}).items()} or None
        kwargs: dict[str, Any] = {"substitutions": subs}
        if self._graph is None:
            kwargs["use_default_graph_as_union"] = True
        else:
            kwargs["default_graph"] = self._graph
        try:
            result = self.store.query(text, **kwargs)
        except RuntimeError:
            from starlayer.shacl_engine.sparql_support import starlayer_sparql_query

            return starlayer_sparql_query(self.to_starlayer_graph(), text, init_bindings)
        if isinstance(result, ox.QueryBoolean):
            return Solutions(boolean=bool(result))
        names = tuple(v.value for v in result.variables)
        rows = tuple({n: from_ox(sol[n]) for n in names if sol[n] is not None} for sol in result)
        return Solutions(variables=names, rows=rows)

    def to_starlayer_graph(self) -> Any:
        """A StarLayerGraph copy of this view (cached until the store changes size)."""
        cached = getattr(self, "_sl_copy", None)
        if cached is not None and cached[0] == len(self):
            return cached[1]
        from starlayer.graph.graph.starlayer_graph import StarLayerGraph

        g = StarLayerGraph()
        for s, p, o in self.triples((None, None, None)):
            g.add((s, p, o))
        self._sl_copy = (len(self), g)
        return g

    def query(self, text: str, init_bindings: dict[str, Any] | None = None, *, base_iri: str | None = None) -> Any:
        """Run SPARQL natively. SELECT -> ``list[dict[str, term]]`` (unbound variables absent); ASK -> ``bool``;
        CONSTRUCT/DESCRIBE -> ``list[(s, p, o)]``. ``init_bindings`` maps variable names (with or without ``?``/``$``)
        to engine terms and uses pyoxigraph ``substitutions``."""
        subs = {ox.Variable(str(k).lstrip("?$")): to_ox(v) for k, v in (init_bindings or {}).items()} or None
        kwargs: dict[str, Any] = {"base_iri": base_iri, "substitutions": subs}
        if self._graph is None:
            kwargs["use_default_graph_as_union"] = True
        else:
            kwargs["default_graph"] = self._graph
        result = self.store.query(text, **kwargs)
        if isinstance(result, ox.QueryBoolean):
            return bool(result)
        if isinstance(result, ox.QuerySolutions):
            names = [v.value for v in result.variables]
            return [
                {n: from_ox(sol[n]) for n in names if sol[n] is not None}
                for sol in result
            ]
        return [(from_ox(t.subject), from_ox(t.predicate), from_ox(t.object)) for t in result]
