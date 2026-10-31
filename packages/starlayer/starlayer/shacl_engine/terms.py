"""The engine's term model: pyoxigraph ``NamedNode`` / ``BlankNode`` / ``Literal`` / ``Triple`` (one-to-one with Rust
``oxrdf``), plus the adapters at the boundary with rdflib / StarLayer terms.

Inside the engine every term is a pyoxigraph term. Literals keep exactly the lexical form and datatype they were built
with; value-space logic lives in ``xsd_values``. A language-tagged literal with a base direction is an ``ox.Literal`` with
``direction`` set; a triple term is an ``ox.Triple``. Outside the engine (callers' graphs, the report graph, query-layer
results) terms are rdflib ``URIRef`` / ``BNode`` / ``Literal`` and ``starlayer.graph.model`` ``TripleTerm`` /
``DirLangString``; ``to_engine`` / ``from_engine`` convert, preserving lexical forms (``str(literal)`` as the parser
stored it on the way in, ``Literal(..., normalize=False)`` on the way out).

Known conversion limits: pyoxigraph validates on construction, so an rdflib ``URIRef`` that is not an absolute IRI, a
language tag that is not BCP47, or a blank node id that is not a valid Oxigraph id raises ``ValueError`` in
``to_engine``. rdflib's graph accepts them.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pyoxigraph as ox

NamedNode, BlankNode, Literal, Triple = ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple

_DIRECTIONS = {"ltr": ox.BaseDirection.LTR, "rtl": ox.BaseDirection.RTL}
_XSD = "http://www.w3.org/2001/XMLSchema#"


class NS:
    """A namespace of pyoxigraph ``NamedNode`` constants: ``SH.minCount``, ``SH["class"]``. Terms are created once."""

    __slots__ = ("_base", "_cache")

    def __init__(self, base: str) -> None:
        object.__setattr__(self, "_base", base)
        object.__setattr__(self, "_cache", {})

    def __getitem__(self, name: str) -> ox.NamedNode:
        node = self._cache.get(name)
        if node is None:
            node = self._cache[name] = ox.NamedNode(self._base + name)
        return node

    def __getattr__(self, name: str) -> ox.NamedNode:
        if name.startswith("__"):
            raise AttributeError(name)
        return self[name]

    def __str__(self) -> str:
        return self._base


RDF = NS("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
RDFS = NS("http://www.w3.org/2000/01/rdf-schema#")
XSD = NS(_XSD)
OWL = NS("http://www.w3.org/2002/07/owl#")
SH = NS("http://www.w3.org/ns/shacl#")
DCTERMS = NS("http://purl.org/dc/terms/")

# ---- kind tests and text ----------------------------------------------------------------------------------------------

is_iri = lambda t: isinstance(t, ox.NamedNode)  # noqa: E731
is_bnode = lambda t: isinstance(t, ox.BlankNode)  # noqa: E731
is_literal = lambda t: isinstance(t, ox.Literal)  # noqa: E731
is_triple = lambda t: isinstance(t, ox.Triple)  # noqa: E731


def text(term: Any) -> str:
    """Human text of a term, as ``str(rdflib term)`` gave it: IRI text, literal lexical form, blank node id."""
    if isinstance(term, (ox.NamedNode, ox.BlankNode, ox.Literal)):
        return term.value
    if isinstance(term, ox.Triple):
        return f"<<( {text(term.subject)} {text(term.predicate)} {text(term.object)} )>>"
    return str(term)


def local_name(iri: ox.NamedNode) -> str:
    v = iri.value
    return v.rsplit("#", 1)[-1] if "#" in v else v.rsplit("/", 1)[-1]


def datatype_iri(lit: ox.Literal) -> ox.NamedNode:
    """The RDF datatype of a literal (``rdf:langString`` / ``rdf:dirLangString`` for tagged strings): ``Literal.datatype``."""
    return lit.datatype


# ---- constructors -----------------------------------------------------------------------------------------------------


def literal(lexical: str, datatype: ox.NamedNode | None = None, lang: str | None = None) -> ox.Literal:
    if lang:
        return ox.Literal(lexical, language=lang)
    return ox.Literal(lexical, datatype=datatype) if datatype is not None else ox.Literal(lexical)


def boolean(value: bool) -> ox.Literal:
    return ox.Literal("true" if value else "false", datatype=XSD.boolean)


def integer(value: int) -> ox.Literal:
    return ox.Literal(str(value), datatype=XSD.integer)


TRUE = boolean(True)
FALSE = boolean(False)

# ---- rdflib / StarLayer <-> engine -------------------------------------------------------------------------------------

_CACHE_MAX = 200_000
_TO_ENGINE: dict = {}
_FROM_ENGINE: dict = {}
_VARIABLE_PREFIX = "urn:starlayer:variable:"  # an rdflib ``Variable`` crosses the boundary as this IRI


def to_engine(term: Any) -> Any:
    """rdflib / StarLayer term -> pyoxigraph term. ``None`` stays ``None``; a 3-tuple becomes a triple term; a term that
    already is a pyoxigraph term is returned as it is."""
    if term is None:
        return None
    from rdflib import BNode, URIRef, Variable
    from rdflib import Literal as RLiteral

    from starlayer.graph.model.dirlangstring import DirLangString
    from starlayer.graph.model.triple import TripleTerm

    cls = type(term)
    if cls is URIRef or cls is BNode:
        out = _TO_ENGINE.get(term)
        if out is None:
            if len(_TO_ENGINE) >= _CACHE_MAX:
                _TO_ENGINE.clear()
            out = _TO_ENGINE[term] = ox.NamedNode(str(term)) if cls is URIRef else ox.BlankNode(str(term))
        return out
    if isinstance(term, (ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple)):
        return term
    if isinstance(term, URIRef):
        return ox.NamedNode(str(term))
    if isinstance(term, BNode):
        return ox.BlankNode(str(term))
    if isinstance(term, DirLangString):
        return ox.Literal(term.value, language=term.language, direction=_DIRECTIONS[term.direction])
    if isinstance(term, RLiteral):
        if term.language:
            return ox.Literal(str(term), language=term.language)
        if term.datatype is not None:
            return ox.Literal(str(term), datatype=ox.NamedNode(str(term.datatype)))
        return ox.Literal(str(term))
    if isinstance(term, Variable):  # SPARQL-algebra graphs (salg) store query variables as terms: no oxrdf equivalent
        return ox.NamedNode(_VARIABLE_PREFIX + str(term))
    if isinstance(term, TripleTerm):
        return ox.Triple(to_engine(term.subject), to_engine(term.predicate), to_engine(term.object))
    if isinstance(term, tuple) and len(term) == 3:
        return ox.Triple(*(to_engine(t) for t in term))
    raise TypeError(f"cannot convert {term!r} ({type(term).__name__}) to an engine term")


def from_engine(term: Any) -> Any:
    """pyoxigraph term -> rdflib / StarLayer term (``URIRef``, ``BNode``, ``Literal(..., normalize=False)``,
    ``DirLangString``, ``TripleTerm``). Anything that is not a pyoxigraph term is returned unchanged."""
    if isinstance(term, ox.Triple):
        from starlayer.graph.model.triple import TripleTerm

        return TripleTerm(from_engine(term.subject), from_engine(term.predicate), from_engine(term.object))
    if not isinstance(term, (ox.NamedNode, ox.BlankNode, ox.Literal)):
        return term
    out = _FROM_ENGINE.get(term)
    if out is None:
        out = _from_engine(term)
        if len(_FROM_ENGINE) >= _CACHE_MAX:
            _FROM_ENGINE.clear()
        _FROM_ENGINE[term] = out
    return out


def _from_engine(term: Any) -> Any:
    from rdflib import BNode, URIRef
    from rdflib import Literal as RLiteral

    if isinstance(term, ox.NamedNode):
        if term.value.startswith(_VARIABLE_PREFIX):
            from rdflib import Variable

            return Variable(term.value[len(_VARIABLE_PREFIX) :])
        return URIRef(term.value)
    if isinstance(term, ox.BlankNode):
        return BNode(term.value)
    if term.language:
        if term.direction is not None:
            from starlayer.graph.model.dirlangstring import DirLangString

            return DirLangString(term.value, term.language, str(term.direction))
        return RLiteral(term.value, lang=term.language)
    dt = term.datatype.value
    return RLiteral(term.value) if dt == _XSD + "string" else RLiteral(term.value, datatype=URIRef(dt), normalize=False)


def from_engine_triple(t: tuple[Any, Any, Any]) -> tuple[Any, Any, Any]:
    return from_engine(t[0]), from_engine(t[1]), from_engine(t[2])


def to_engine_triple(t: tuple[Any, Any, Any]) -> tuple[Any, Any, Any]:
    return to_engine(t[0]), to_engine(t[1]), to_engine(t[2])


# ---- graph views -------------------------------------------------------------------------------------------------------


class RdflibTermView:
    """A ``GraphView`` that yields engine (pyoxigraph) terms from an rdflib ``Graph`` / ``StarLayerGraph``: patterns are
    converted to rdflib terms on the way in, results to engine terms on the way out. ``graph`` is the wrapped graph;
    ``namespaces`` / ``namespace_manager`` pass through so report prefixes still work."""

    engine_terms = True
    preserves_lexical_forms = True

    def __init__(self, graph: Any) -> None:
        self.graph = graph

    def _in(self, t: Any) -> Any:
        return None if t is None else from_engine(t)

    def triples(self, pattern: tuple[Any, Any, Any]) -> Iterator[tuple[Any, Any, Any]]:
        s, p, o = pattern
        try:
            it = self.graph.triples((self._in(s), self._in(p), self._in(o)))
            for ts, tp, to in it:
                yield to_engine(ts), to_engine(tp), to_engine(to)
        except (TypeError, ValueError):
            return

    def objects(self, subject: Any = None, predicate: Any = None) -> Iterator[Any]:
        for _s, _p, o in self.triples((subject, predicate, None)):
            yield o

    def subjects(self, predicate: Any = None, object: Any = None) -> Iterator[Any]:  # noqa: A002
        for s, _p, _o in self.triples((None, predicate, object)):
            yield s

    def predicate_objects(self, subject: Any = None) -> Iterator[tuple[Any, Any]]:
        for _s, p, o in self.triples((subject, None, None)):
            yield p, o

    def __contains__(self, triple: tuple[Any, Any, Any]) -> bool:
        s, p, o = triple
        return next(iter(self.triples((s, p, o))), None) is not None

    def __len__(self) -> int:
        return len(self.graph)

    def __getattr__(self, name: str) -> Any:
        if name in ("namespaces", "namespace_manager", "identifier"):
            return getattr(self.graph, name)
        raise AttributeError(name)


def engine_view(graph: Any) -> Any:
    """The engine's term view of ``graph``: an Oxigraph-backed view or an already-engine view as it is; anything else
    (rdflib, StarLayerGraph) through ``RdflibTermView``."""
    if graph is None or getattr(graph, "engine_terms", False):
        return graph
    return RdflibTermView(graph)


class LegacyTermView:
    """The inverse adapter: a view over an engine-term graph that speaks rdflib terms (for code that still is rdflib)."""

    def __init__(self, view: Any) -> None:
        self.view = view

    def triples(self, pattern: tuple[Any, Any, Any]) -> Iterator[tuple[Any, Any, Any]]:
        s, p, o = pattern
        for t in self.view.triples((to_engine(s), to_engine(p), to_engine(o))):
            yield from_engine_triple(t)

    def objects(self, subject: Any = None, predicate: Any = None) -> Iterator[Any]:
        for o in self.view.objects(to_engine(subject), to_engine(predicate)):
            yield from_engine(o)

    def subjects(self, predicate: Any = None, object: Any = None) -> Iterator[Any]:  # noqa: A002
        for s in self.view.subjects(to_engine(predicate), to_engine(object)):
            yield from_engine(s)

    def predicate_objects(self, subject: Any = None) -> Iterator[tuple[Any, Any]]:
        for p, o in self.view.predicate_objects(to_engine(subject)):
            yield from_engine(p), from_engine(o)

    def __contains__(self, triple: tuple[Any, Any, Any]) -> bool:
        return tuple(to_engine(t) for t in triple) in self.view

    def __len__(self) -> int:
        return len(self.view)

    def predicates(self, subject: Any = None, object: Any = None) -> Iterator[Any]:  # noqa: A002
        seen: set = set()
        for _s, p, _o in self.triples((subject, None, object)):
            if p not in seen:
                seen.add(p)
                yield p

    def items(self, head: Any) -> Iterator[Any]:
        """Members of the rdf:list at ``head`` (as ``rdflib.Graph.items``)."""
        rdf_nil, rdf_first, rdf_rest = from_engine(RDF.nil), from_engine(RDF.first), from_engine(RDF.rest)
        seen: set = set()
        while head is not None and head != rdf_nil and head not in seen:
            seen.add(head)
            first = next(self.objects(head, rdf_first), None)
            if first is None:
                return
            yield first
            head = next(self.objects(head, rdf_rest), None)

    def __getattr__(self, name: str) -> Any:
        if name in ("namespaces", "namespace_manager", "identifier"):
            return getattr(self.view, name)
        raise AttributeError(name)
