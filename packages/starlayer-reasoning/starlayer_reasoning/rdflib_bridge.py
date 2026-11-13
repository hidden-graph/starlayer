"""The conversion between pyoxigraph terms and rdflib terms, for everything in this package that runs on rdflib.

``owlrl`` (OWL-RL and the combined regimes), the OWL-DL engines (HermiT through owlready2, rustdl) and ``StarLayerGraph.from_rdflib`` /
``to_rdflib`` work on rdflib graphs. A graph is copied to rdflib terms, the reasoner runs, and what it adds is converted back to pyoxigraph
terms. rdflib cannot hold a triple term, so the copy replaces each one with a synthetic reification fragment (``decompose``) and a
directional-language literal with the datatype-IRI form; both are undone on the way back.

rdflib is imported where it is used, so ``import starlayer_reasoning`` itself does not need it until a conversion runs.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

import pyoxigraph as ox
from starlayer.shacl.engine.terms import (
    INVALID_BNODE_PREFIX,
    INVALID_IRI_PREFIX,
    INVALID_LANG_PREFIX,
)

_XSD_STRING = "http://www.w3.org/2001/XMLSchema#string"
_DIRECTIONS = {"ltr": ox.BaseDirection.LTR, "rtl": ox.BaseDirection.RTL}

_CACHE_MAX = 200_000
_TO_ENGINE: dict = {}
_FROM_ENGINE: dict = {}

# A dedicated, internal-only namespace for the synthetic reification edges: nothing else writes it, so it can never collide with a
# source graph's own use of classic RDF reification (rdf:subject/predicate/object) on unrelated blank nodes.
_TT_PREFIX = "urn:starlayer:canon-tt#"


def to_rdflib_term(term: Any) -> Any:
    """A pyoxigraph term as an rdflib term (a triple term becomes a ``TripleTerm``)."""
    return engine_to_foreign(term)


def to_rdflib_triples(triples: Iterable[tuple[Any, Any, Any]]) -> list[tuple[Any, Any, Any]]:
    """pyoxigraph triples as rdflib-term triples."""
    return [(engine_to_foreign(s), engine_to_foreign(p), engine_to_foreign(o)) for s, p, o in triples]



def rdflib_graph(triples: Iterable[tuple[Any, Any, Any]], *, decompose: bool = True) -> Any:
    """A plain ``rdflib.Graph`` with the triples. ``decompose=True`` replaces every triple term with a synthetic reification
    fragment (what the reasoners need; they cannot hold a triple term), as ``decompose`` does."""
    from rdflib import Graph

    rows = to_rdflib_triples(triples)
    out = Graph()
    if decompose:
        for s, p, o, _g in _decompose_quads((s, p, o, None) for s, p, o in rows):
            out.add((s, p, o))
    else:
        for t in rows:
            out.add(t)
    return out

def _escape_predicate(p: Any) -> Any:
    """Keep the decomposition injective: a source predicate in the internal
    namespace is moved under ``..#escaped:`` so it can never be mistaken for
    one of the three synthetic edges (``subject``/``predicate``/``object``)
    that stand for a triple term."""
    from rdflib import URIRef

    if isinstance(p, URIRef) and str(p).startswith(_TT_PREFIX):
        return URIRef(_TT_PREFIX + "escaped:" + str(p)[len(_TT_PREFIX) :])
    return p

def _decompose_quads(quads: Any) -> list:
    """Quads with every triple term replaced by a synthetic reification
    fragment placed in the same graph as the quad that held the term, see
    the module docstring for why that suffices. Returns de-duplicated quads
    (a set, as a graph would be); the decomposition is injective."""
    from rdflib import BNode, Literal, URIRef
    from rdflib.namespace import XSD

    from starlayer_reasoning.model.dirlangstring import (
        DirLangString,
        encode_dirlangstring,
    )
    from starlayer_reasoning.model.triple import TripleTerm

    out: dict = {}

    def _term(node: Any, g: Any) -> Any:
        """A triple term becomes a fresh blank node (recursing for a nested
        triple term in object position); a DirLangString is re-encoded as
        the same flat Literal form used at this codebase's own read/write
        boundary; an explicit-xsd:string Literal is normalized down to the
        simple-literal form (datatype=None) it's semantically sugar for, per
        RDF 1.1 Concepts (see module docstring); a language tag is
        lower-cased (tags compare case-insensitively); anything else
        (already a plain rdflib term) passes through unchanged."""
        if isinstance(node, TripleTerm):
            tt_node = BNode()
            out[(tt_node, URIRef(_TT_PREFIX + "subject"), _term(node.subject, g), g)] = None
            out[(tt_node, URIRef(_TT_PREFIX + "predicate"), node.predicate, g)] = None
            out[(tt_node, URIRef(_TT_PREFIX + "object"), _term(node.object, g), g)] = None
            return tt_node
        if isinstance(node, DirLangString):
            return encode_dirlangstring(node)
        if isinstance(node, Literal):
            if node.datatype == XSD.string and node.language is None:
                return Literal(str(node))
            if node.language and node.language != node.language.lower():
                return Literal(str(node), lang=node.language.lower())
        return node

    for s, p, o, g in quads:
        out[(_term(s, g), _escape_predicate(p), _term(o, g), g)] = None
    return list(out)

def decomposition_nodes(graph: Any) -> set:
    """The synthetic blank nodes ``_decompose_quads`` made for triple terms in ``graph`` (a decomposed rdflib graph)."""
    from rdflib import URIRef

    return {s for s, _p, _o in graph.triples((None, URIRef(_TT_PREFIX + "subject"), None))}

def drop_decomposition(triples: Iterable[tuple[Any, Any, Any]], nodes: set) -> Iterator[tuple[Any, Any, Any]]:
    """``triples`` without those that mention the decomposition: a node of ``nodes`` or a term of the internal namespace. A
    reasoner's entailments about these placeholders are not entailments about the user's graph."""
    from rdflib import URIRef

    for t in triples:
        if any(x in nodes or (isinstance(x, URIRef) and str(x).startswith(_TT_PREFIX)) for x in t):
            continue
        yield t

def decompose(graph: Any) -> Any:
    """Return a plain ``rdflib.Graph`` (``graph`` is an rdflib graph or an Oxigraph-backed one) with every triple term replaced by a
    synthetic reification fragment (a fresh blank node per triple-term occurrence, three edges in an internal namespace, recursing
    for a nested one). Injective, and the result holds no triple term, which is what the rdflib reasoners need."""
    from rdflib import Graph
    from starlayer.graph.inputs import is_oxigraph_input

    if is_oxigraph_input(graph):
        graph = to_rdflib_triples(iter(graph))
    out = Graph()
    for s, p, o, _g in _decompose_quads((s, p, o, None) for s, p, o in graph):
        out.add((s, p, o))
    return out

def to_rdflib_rdf11(value: Any, *, bnode_prefix: str | None = None, direction_policy: str = "datatype") -> Any:
    """A snapshot of an ``StarLayerGraph`` as a plain ``rdflib.Graph`` (identifier and prefixes kept), of an ``StarLayerDataset`` / bare ``Store``
    as an ``rdflib.Dataset`` (named graphs, also empty ones; ``default_union`` kept). RDF 1.2 is presented as RDF 1.1
    (``interop.to_rdf11``): a triple term becomes a blank node described by the ``rdf:PropositionForm`` basic encoding, a
    base-direction literal the datatype-IRI form. ``from_rdflib`` restores the directional literals, not the triple terms
    (a plain ``turtle`` parse does not adopt the basic encoding either; ``interop.from_basic`` does)."""
    from rdflib import BNode, Dataset, Graph, URIRef
    from starlayer.graph import interop
    from starlayer.graph.core import StarLayerDataset, StarLayerGraph

    if isinstance(value, ox.Store):
        value = StarLayerDataset(store=value)
    quads = interop.to_rdf11(list(value.quads()), bnode_prefix=bnode_prefix, direction_policy=direction_policy)

    def name(g: Any) -> Any:
        return None if isinstance(g, ox.DefaultGraph) else URIRef(g.value) if isinstance(g, ox.NamedNode) else BNode(g.value)

    if isinstance(value, StarLayerGraph):
        ident = name(value.identifier)
        out: Any = Graph(identifier=ident) if ident is not None else Graph()
        for q in quads:
            out.add((to_rdflib_term(q.subject), to_rdflib_term(q.predicate), to_rdflib_term(q.object)))
    else:
        out = Dataset(default_union=value.default_union)
        for g in value.store.named_graphs():
            out.graph(name(g))
        # `Dataset.default_graph` is new in rdflib 7.3; `default_context` is the name before it (deprecated since).
        default = getattr(out, "default_graph", None)
        if default is None:
            default = out.default_context
        for q in quads:
            n = name(q.graph_name)
            target = default if n is None else out.graph(n)
            target.add((to_rdflib_term(q.subject), to_rdflib_term(q.predicate), to_rdflib_term(q.object)))
    for prefix, ns in dict(value.prefixes).items():
        out.bind(prefix, ns)
    return out

def _decode_dirlang(term: Any) -> Any:
    from starlayer_reasoning.model.dirlangstring import decode_dirlang_datatype

    dt = getattr(term, "datatype", None)
    decoded = decode_dirlang_datatype(dt) if dt is not None else None
    if decoded is None:
        return None
    lang, direction = decoded
    return ox.Literal(str(term), language=lang, direction=ox.BaseDirection.RTL if direction == "rtl" else ox.BaseDirection.LTR)

def from_rdflib_term(term: Any) -> Any:
    """rdflib / StarLayer term -> pyoxigraph term (a decomposed directional-language encoding is restored)."""
    from rdflib import Literal as RLiteral

    if isinstance(term, RLiteral):
        restored = _decode_dirlang(term)
        if restored is not None:
            return restored
    return foreign_to_engine(term)

def legal_rdf_triples(triples: Iterable[tuple[Any, Any, Any]]) -> Iterator[tuple[Any, Any, Any]]:
    """The rdflib triples of ``triples`` that RDF allows, as pyoxigraph triples. OWL RL and RDFS also derive generalized triples
    such as ``"text" rdf:type rdfs:Literal`` (literal subject, or a non-IRI predicate), which no RDF store holds."""
    from rdflib import Literal as RLiteral
    from rdflib import URIRef

    for s, p, o in triples:
        if isinstance(s, RLiteral) or not isinstance(p, URIRef):
            continue
        yield from_rdflib_term(s), from_rdflib_term(p), from_rdflib_term(o)

def _rdflib_text(term: Any) -> str:
    """``str()`` of an rdflib term (IRI text, lexical form, blank node id): the one place this module reads one."""
    return str(term)  # str-ok: an rdflib term, whose str() is its lexical value


def show(term: Any) -> str:
    """A short, never-raising rendering of an rdflib term for messages (``URIRef.n3()`` refuses an invalid IRI)."""
    from rdflib import BNode, URIRef
    from rdflib import Literal as RLiteral

    if isinstance(term, URIRef):
        return f"<{_rdflib_text(term)}>"
    if isinstance(term, BNode):
        return f"_:{_rdflib_text(term)}"
    if isinstance(term, RLiteral):
        suffix = f"@{term.language}" if term.language else (f"^^<{_rdflib_text(term.datatype)}>" if term.datatype else "")
        return f"{_rdflib_text(term)!r}{suffix}"
    if isinstance(term, tuple):
        return "(" + " ".join(show(t) for t in term) + ")"
    return repr(term)

def foreign_to_engine(term: Any) -> Any:
    """rdflib / StarLayer term (or a 3-tuple, a triple term) -> pyoxigraph term; a pyoxigraph term is returned as it is.
    ``shacl.engine.terms.to_engine`` calls this for the StarLayer value classes. A term pyoxigraph rejects (a relative IRI, a
    blank node id or language tag it does not accept) raises ``ValueError``."""
    if isinstance(term, (ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple)):
        return term
    from rdflib import BNode, URIRef
    from rdflib import Literal as RLiteral

    from starlayer_reasoning.model.dirlangstring import DirLangString
    from starlayer_reasoning.model.triple import TripleTerm

    cls = type(term)
    if cls is URIRef or cls is BNode:
        out = _TO_ENGINE.get(term)
        if out is None:
            out = ox.NamedNode(_rdflib_text(term)) if cls is URIRef else ox.BlankNode(_rdflib_text(term))
            if len(_TO_ENGINE) >= _CACHE_MAX:
                _TO_ENGINE.clear()
            _TO_ENGINE[term] = out
        return out
    if isinstance(term, URIRef):
        return ox.NamedNode(_rdflib_text(term))
    if isinstance(term, BNode):
        return ox.BlankNode(_rdflib_text(term))
    if isinstance(term, DirLangString):
        return ox.Literal(term.value, language=term.language, direction=_DIRECTIONS[term.direction])
    if isinstance(term, RLiteral):
        lexical = _rdflib_text(term)
        if term.language:
            return ox.Literal(lexical, language=term.language)
        if term.datatype is not None:
            return ox.Literal(lexical, datatype=ox.NamedNode(_rdflib_text(term.datatype)))
        return ox.Literal(lexical)
    if isinstance(term, TripleTerm):
        return ox.Triple(foreign_to_engine(term.subject), foreign_to_engine(term.predicate), foreign_to_engine(term.object))
    if isinstance(term, tuple) and len(term) == 3:
        return ox.Triple(*(foreign_to_engine(t) for t in term))
    raise TypeError(f"cannot convert {term!r} ({type(term).__name__}) to an engine term")

def engine_to_foreign(term: Any) -> Any:
    """pyoxigraph term -> rdflib / StarLayer term (``URIRef``, ``BNode``, ``Literal(..., normalize=False)``, ``DirLangString``,
    ``TripleTerm``)."""
    if isinstance(term, ox.Triple):
        from starlayer_reasoning.model.triple import TripleTerm

        return TripleTerm(engine_to_foreign(term.subject), engine_to_foreign(term.predicate), engine_to_foreign(term.object))
    out = _FROM_ENGINE.get(term)
    if out is None:
        out = _engine_to_foreign(term)
        if len(_FROM_ENGINE) >= _CACHE_MAX:
            _FROM_ENGINE.clear()
        _FROM_ENGINE[term] = out
    return out

def _engine_to_foreign(term: Any) -> Any:
    from urllib.parse import unquote

    from rdflib import BNode, URIRef
    from rdflib import Literal as RLiteral

    if isinstance(term, ox.NamedNode):
        if term.value.startswith(INVALID_IRI_PREFIX):
            return URIRef(unquote(term.value[len(INVALID_IRI_PREFIX) :], errors="surrogatepass"))
        return URIRef(term.value)
    if isinstance(term, ox.BlankNode):
        if term.value.startswith(INVALID_BNODE_PREFIX):
            return BNode(bytes.fromhex(term.value[len(INVALID_BNODE_PREFIX) :]).decode("utf-8", "surrogatepass"))
        return BNode(term.value)
    if term.language:
        if term.direction is not None:
            from starlayer_reasoning.model.dirlangstring import DirLangString

            return DirLangString(term.value, term.language, str(term.direction))
        return RLiteral(term.value, lang=term.language)
    dt = term.datatype.value
    if dt.startswith(INVALID_LANG_PREFIX):
        return RLiteral(term.value, lang=unquote(dt[len(INVALID_LANG_PREFIX) :], errors="surrogatepass"))
    if dt.startswith(INVALID_IRI_PREFIX):
        return RLiteral(term.value, datatype=URIRef(unquote(dt[len(INVALID_IRI_PREFIX) :], errors="surrogatepass")), normalize=False)
    return RLiteral(term.value) if dt == _XSD_STRING else RLiteral(term.value, datatype=URIRef(dt), normalize=False)

def is_rdf_triple(triple: tuple[Any, Any, Any]) -> bool:
    """False for a generalized triple (a literal subject, a predicate that is not an IRI): Oxigraph cannot hold it. owlrl's closure
    makes such triples."""
    from rdflib import Literal, URIRef

    return not isinstance(triple[0], Literal) and isinstance(triple[1], URIRef)

def graph_from_rdflib(value: Any, *, restore_directions: bool = False) -> Any:
    """A new ``StarLayerGraph`` from an rdflib ``Graph``, with its prefixes and, when it has an IRI identifier, that identifier.

    A term that is not an RDF term (a relative IRI ...) raises ``ValueError``; a generalized triple (a literal subject, a predicate
    that is not an IRI, as owlrl makes) is left out. Oxigraph normalises some literals on insert (``"04"^^xsd:integer`` becomes
    ``"4"``). ``restore_directions=True`` turns a directional literal written in its datatype-IRI form (``interop.encode_directions``)
    back into a real one."""
    from rdflib import URIRef
    from starlayer.graph.core import StarLayerGraph

    ident = getattr(value, "identifier", None)
    out = StarLayerGraph(identifier=foreign_to_engine(ident)) if type(ident) is URIRef else StarLayerGraph()
    for prefix, ns in value.namespaces():
        out.bind(prefix, str(ns))
    convert = from_rdflib_term if restore_directions else foreign_to_engine
    out.extend([(convert(s), convert(p), convert(o)) for s, p, o in value.triples((None, None, None)) if is_rdf_triple((s, p, o))])
    return out


def dataset_from_rdflib(value: Any) -> Any:
    """A new ``StarLayerDataset`` from an rdflib ``Dataset`` / ``ConjunctiveGraph`` / StarLayer dataset (every graph, empty named graphs
    too, ``default_union`` kept) or from a plain graph (its triples go to the default graph, whatever its identifier). Terms are
    converted and checked as in ``graph_from_rdflib``, and a decomposed directional literal is restored. Prefixes are copied."""
    from starlayer.graph.core import StarLayerDataset

    if isinstance(value, (StarLayerDataset, ox.Store)) or not hasattr(value, "namespaces"):
        raise TypeError(f"expected an rdflib Dataset, ConjunctiveGraph or Graph; got {type(value).__name__}")
    if hasattr(value, "graphs") or hasattr(value, "contexts"):
        import warnings

        graphs = list(value.graphs() if hasattr(value, "graphs") else value.contexts())
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            default = getattr(value, "default_graph", None)
            if default is None:
                default = getattr(value, "default_context", None)
        default_id = getattr(default, "identifier", None)
        union = bool(getattr(value, "default_union", True))
    else:
        graphs, default_id, union = [value], value.identifier, True
    out = StarLayerDataset(default_union=union)
    for prefix, ns in value.namespaces():
        out.bind(prefix, str(ns))
    for g in graphs:
        if g.identifier == default_id:
            name: Any = ox.DefaultGraph()
        else:
            name = from_rdflib_term(g.identifier)
            out.store.add_graph(name)
        out.store.extend(
            ox.Quad(from_rdflib_term(s), from_rdflib_term(p), from_rdflib_term(o), name)
            for s, p, o in g.triples((None, None, None))
            if is_rdf_triple((s, p, o))
        )
    return out
