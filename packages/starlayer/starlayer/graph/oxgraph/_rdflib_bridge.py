"""BRIDGE to rdflib. The only place in the Oxigraph wrapper that converts to and from rdflib terms.

Some capabilities still run on rdflib-based code that has no Oxigraph equivalent: ``owlrl`` (RDFS / OWL-RL closure), the OWL-DL
bridges (HermiT via owlready2, rustdl) and ``derive_shape``. They take a copy of the graph as rdflib terms, run, and the delta is
converted back to pyoxigraph terms. When one of them gets a native port, delete its use of this module; when the last one goes,
delete the module.

Everything here imports rdflib lazily, so ``import starlayer.graph.oxgraph`` stays free of it.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

import pyoxigraph as ox

from starlayer._optional import RDFLIB_EXTRA_HINT, have_rdflib, require_rdflib  # noqa: F401  (re-exported)


def to_rdflib_term(term: Any) -> Any:
    """pyoxigraph term -> rdflib / StarLayer term (a triple term becomes a ``TripleTerm``)."""
    from starlayer.shacl_engine.terms import from_engine

    return from_engine(term)


def to_rdflib_triples(triples: Iterable[tuple[Any, Any, Any]]) -> list[tuple[Any, Any, Any]]:
    from starlayer.shacl_engine.terms import from_engine

    return [(from_engine(s), from_engine(p), from_engine(o)) for s, p, o in triples]


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


# ---- decomposing triple terms for rdflib (the reasoners and the OWL-DL exporters cannot hold one) ----

# A dedicated, internal-only namespace for the synthetic reification edges -
# never emitted by any parser/serializer in this codebase, so it can never
# collide with a source graph's own use of classic RDF reification
# (rdf:subject/predicate/object) on unrelated blank nodes.
_TT_PREFIX = "urn:starlayer:canon-tt#"


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

    from starlayer.graph.model.dirlangstring import DirLangString, encode_dirlangstring
    from starlayer.graph.model.triple import TripleTerm

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


def decompose(graph: Any) -> Any:
    """Return a plain ``rdflib.Graph`` with every triple term replaced by a
    synthetic reification fragment (a fresh blank node per triple-term occurrence, three edges in an internal namespace, recursing
    for a nested one). Injective, and the result holds no triple term, which is what the rdflib reasoners need."""
    from rdflib import Graph

    if is_oxigraph_input(graph):
        graph = to_rdflib_triples(iter(graph))
    out = Graph()
    for s, p, o, _g in _decompose_quads((s, p, o, None) for s, p, o in graph):
        out.add((s, p, o))
    return out



def is_oxigraph_input(value: Any) -> bool:
    """True for an ``StarLayerGraph`` / ``StarLayerDataset`` or a bare ``pyoxigraph.Store``."""
    from starlayer.graph.oxgraph.core import StarLayerDataset, StarLayerGraph

    return isinstance(value, (StarLayerGraph, StarLayerDataset, ox.Store))


def to_rdflib_graph(value: Any) -> Any:
    """A snapshot of an ``StarLayerGraph`` / ``StarLayerDataset`` / bare ``Store`` as a plain ``rdflib.Graph`` (the library entry points that
    still run on rdflib code call this at the boundary). A dataset or store gives the union of its graphs; a graph view keeps its
    identifier and its prefixes. A triple term, which rdflib cannot hold, becomes the synthetic reification fragment
    ``rdflib_graph(decompose=True)`` writes. The result is a copy: writes to it do not reach ``value``."""
    from rdflib import URIRef

    from starlayer.graph.oxgraph.core import StarLayerDataset, StarLayerGraph

    if isinstance(value, ox.Store):
        value = StarLayerDataset(store=value)
    ident = value.identifier if isinstance(value, StarLayerGraph) else None
    g = rdflib_graph(iter(value))
    if isinstance(ident, ox.NamedNode):
        g = _with_identifier(g, URIRef(ident.value))
    for prefix, ns in dict(value.prefixes).items():
        g.bind(prefix, ns)
    return g


def to_rdflib_rdf11(value: Any, *, bnode_prefix: str | None = None, direction_policy: str = "datatype") -> Any:
    """A snapshot of an ``StarLayerGraph`` as a plain ``rdflib.Graph`` (identifier and prefixes kept), of an ``StarLayerDataset`` / bare ``Store``
    as an ``rdflib.Dataset`` (named graphs, also empty ones; ``default_union`` kept). RDF 1.2 is presented as RDF 1.1
    (``interop.to_rdf11``): a triple term becomes a blank node described by the ``rdf:PropositionForm`` basic encoding, a
    base-direction literal the datatype-IRI form. ``from_rdflib`` restores the directional literals, not the triple terms
    (a plain ``turtle`` parse does not adopt the basic encoding either; ``interop.from_basic`` does)."""
    from rdflib import BNode, Dataset, Graph, URIRef

    from starlayer.graph import interop
    from starlayer.graph.oxgraph.core import StarLayerDataset, StarLayerGraph

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
        for q in quads:
            n = name(q.graph_name)
            target = out.default_graph if n is None else out.graph(n)
            target.add((to_rdflib_term(q.subject), to_rdflib_term(q.predicate), to_rdflib_term(q.object)))
    for prefix, ns in dict(value.prefixes).items():
        out.bind(prefix, ns)
    return out


def _with_identifier(graph: Any, identifier: Any) -> Any:
    from rdflib import Graph

    out = Graph(identifier=identifier)
    for t in graph:
        out.add(t)
    return out


def as_rdflib_graph(graph: Any) -> Any:
    """``graph`` itself, or a snapshot ``rdflib.Graph`` if it is an Oxigraph graph: for ``rdflib_graph += x`` where ``x`` may be
    either kind (the ontology and shapes loaders return whatever class ``StarLayerGraph`` is)."""
    return to_rdflib_graph(graph) if is_oxigraph_input(graph) else graph


def merge_into(dst: Any, src: Any) -> None:
    """``dst += src`` for graphs of either kind (``StarLayerGraph`` ``+=`` takes only an ``StarLayerGraph``; rdflib's takes only rdflib). Triples
    only: no prefixes are copied, as with rdflib's ``+=``."""
    if is_oxigraph_input(dst):
        dst.extend(list(iter(src)))  # StarLayerGraph.add / extend convert rdflib terms
    elif is_oxigraph_input(src):
        for t in to_rdflib_triples(iter(src)):
            dst.add(t)
    else:
        dst += src


def is_oxigraph_dataset(value: Any) -> bool:
    """True for an ``StarLayerDataset`` or a bare ``pyoxigraph.Store`` (something with named graphs)."""
    from starlayer.graph.oxgraph.core import StarLayerDataset

    return isinstance(value, (StarLayerDataset, ox.Store))


def rdflib_quads(value: Any) -> list[tuple[Any, Any, Any, Any]]:
    """Every quad of an ``StarLayerDataset`` / ``Store`` as rdflib terms ``(s, p, o, g)``, ``g`` ``None`` for the default graph. An
    ``StarLayerGraph`` gives its triples with ``g`` ``None``."""
    from starlayer.graph.oxgraph.core import as_store

    if is_oxigraph_dataset(value):
        out = []
        for q in as_store(value).quads_for_pattern(None, None, None, None):
            g = None if isinstance(q.graph_name, ox.DefaultGraph) else to_rdflib_term(q.graph_name)
            out.append((to_rdflib_term(q.subject), to_rdflib_term(q.predicate), to_rdflib_term(q.object), g))
        return out
    return [(s, p, o, None) for s, p, o in to_rdflib_triples(iter(value))]


def ox_graph_from(graph: Any) -> Any:
    """An ``StarLayerGraph`` holding the triples of an rdflib / StarLayer graph (prefixes kept)."""
    from starlayer.graph.oxgraph.core import StarLayerGraph

    if isinstance(graph, StarLayerGraph):
        return graph
    out = StarLayerGraph()
    for prefix, ns in graph.namespaces():
        out.bind(prefix, str(ns))
    copy_into(out, graph)
    return out


def _used_namespace_prefixes(graph: Any, bound: dict[str, str]) -> dict[str, str]:
    """The ``graph``'s (an rdflib graph's) prefixes whose namespace some IRI of its triples (subject, predicate, object or
    literal datatype) lives in, and that are not already in ``bound`` by name or by namespace."""
    candidates = {}
    taken = set(bound.values())
    for prefix, ns in graph.namespaces():
        ns = str(ns)
        if prefix and prefix not in bound and ns not in taken:
            candidates.setdefault(ns, str(prefix))
    if not candidates:
        return {}
    used: dict[str, str] = {}
    seen: set[str] = set()

    def visit(term: Any) -> None:
        value = getattr(term, "datatype", None) if hasattr(term, "language") else term
        text = str(value) if value is not None and type(value).__name__ in ("URIRef", "NamedNode") else None
        if text is None or text in seen:
            return
        seen.add(text)
        cut = max(text.rfind("#"), text.rfind("/")) + 1
        ns = text[:cut]
        if ns in candidates:
            used[candidates[ns]] = ns

    for s, p, o in graph:
        visit(s)
        visit(p)
        visit(o)
    return used


def ox_result(graph: Any, *sources: Any) -> Any:
    """An ``StarLayerGraph`` holding the triples of ``graph`` (rdflib terms -> pyoxigraph terms): the result of a library function that
    ran on rdflib code for an Oxigraph input. Its prefixes are those of the Oxigraph graphs in ``sources`` (the inputs) plus the
    prefixes of ``graph`` that its IRIs actually use, never the 29 defaults an old-style ``StarLayerGraph`` binds. An ``StarLayerGraph``
    passes through unchanged."""
    from starlayer.graph.oxgraph.core import StarLayerGraph

    if isinstance(graph, StarLayerGraph):
        return graph
    prefixes: dict[str, str] = {}
    for src in sources:
        if is_oxigraph_input(src):
            for prefix, ns in dict(getattr(src, "prefixes", {})).items():
                prefixes.setdefault(prefix, ns)
    prefixes.update(_used_namespace_prefixes(graph, prefixes))
    out = StarLayerGraph(prefixes=prefixes)
    ident = getattr(graph, "identifier", None)
    from rdflib import URIRef

    if isinstance(ident, URIRef):
        out = StarLayerGraph(prefixes=prefixes, identifier=from_rdflib_term(ident))
    copy_into(out, graph)
    return out


def convert_result(value: Any, *sources: Any) -> Any:
    """``value`` (a graph, a result dataclass such as ``ValidationResult`` / ``RulesResult``, or a tuple / list / dict of those)
    with every old-style graph in it replaced by an ``StarLayerGraph`` (see ``ox_result``). Anything else is returned unchanged."""
    import dataclasses

    if isinstance(value, ox_types()):
        return value
    if hasattr(value, "namespaces") and hasattr(value, "triples") and hasattr(value, "add"):
        return ox_result(value, *sources)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        changes = {}
        for f in dataclasses.fields(value):
            if f.name == "data_graph":  # the caller's own object (inplace=True), never a copy
                continue
            old = getattr(value, f.name)
            new = convert_result(old, *sources)
            if new is not old:
                changes[f.name] = new
        return dataclasses.replace(value, **changes) if changes else value
    if isinstance(value, dict):
        return {k: convert_result(v, *sources) for k, v in value.items()}
    if isinstance(value, tuple) and not hasattr(value, "_fields"):
        return tuple(convert_result(v, *sources) for v in value)
    return value


def ox_types() -> tuple[type, ...]:
    from starlayer.graph.oxgraph.core import StarLayerDataset, StarLayerGraph

    return (StarLayerGraph, StarLayerDataset)


def ox_in_ox_out(*graph_params: str, owner_sources: str | None = None) -> Any:
    """Decorator: when any of the named graph parameters (or, for a method, any value of ``self.<owner_sources>``) is an
    Oxigraph graph / dataset / store, the graphs in the result are returned as ``StarLayerGraph`` (see ``convert_result``). With old-style
    or rdflib inputs the result is untouched."""
    import functools
    import inspect

    def decorate(fn: Any) -> Any:
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = fn(*args, **kwargs)
            bound = sig.bind_partial(*args, **kwargs).arguments
            given = [bound.get(n) for n in graph_params]
            if owner_sources and "self" in bound:
                given += list(getattr(bound["self"], owner_sources).values())
            flat: list[Any] = []
            for g in given:
                flat.extend(g if isinstance(g, (list, tuple)) else [g])
            sources = [g for g in flat if g is not None and is_oxigraph_input(g)]
            return convert_result(result, *sources) if sources else result

        return wrapper

    return decorate


def copy_into(target: Any, triples: Iterable[tuple[Any, Any, Any]]) -> None:
    """Add rdflib-term triples to an ``StarLayerGraph`` (its ``add`` converts lazily); one call, one transaction."""
    target.extend(list(triples))


def read_boundary(graph: Any, *terms: Any) -> tuple[Any, ...]:
    """For a library function that READS a graph with rdflib code: ``(graph, *terms)`` ready for it. An Oxigraph graph becomes a
    snapshot ``rdflib.Graph`` and any pyoxigraph term in ``terms`` its rdflib equivalent; anything else passes unchanged."""
    if not is_oxigraph_input(graph):
        return (graph, *terms)
    return (to_rdflib_graph(graph), *(from_engine_if_ox(t) for t in terms))


def from_engine_if_ox(term: Any) -> Any:
    """A pyoxigraph term as its rdflib equivalent; any other value unchanged."""
    if isinstance(term, (ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple)):
        return to_rdflib_term(term)
    return term


def to_engine_if_rdflib(term: Any) -> Any:
    """An rdflib term as its pyoxigraph equivalent; ``None`` and anything else unchanged."""
    from rdflib.term import Node

    return from_rdflib_term(term) if isinstance(term, Node) else term


def write_boundary(graph: Any, build: Any, *terms: Any) -> tuple[Any, ...]:
    """For a library function that WRITES a graph with rdflib code. ``build(rdflib_graph_or_None, *rdflib_terms)`` must return
    ``(graph, *result_terms)``. With an ``StarLayerGraph`` target, ``build`` gets a fresh rdflib graph; its triples are then added to
    the ``StarLayerGraph`` (one transaction) and the result terms returned as pyoxigraph terms. Any other target is passed through."""
    if graph is None or not is_oxigraph_input(graph):
        return build(graph, *terms)
    temp, *results = build(None, *(from_engine_if_ox(t) for t in terms))
    copy_into(graph, temp)
    return (graph, *(to_engine_if_rdflib(r) for r in results))


def default_boundary(build: Any, *terms: Any) -> tuple[Any, ...]:
    """For a library function that WRITES a graph with rdflib code when the caller gave none: ``build(None, *rdflib_terms)`` runs
    on a scratch rdflib graph and the result is returned as a fresh ``StarLayerGraph`` (see ``ox_result``) with the result terms as
    pyoxigraph terms."""
    temp, *results = build(None, *(from_engine_if_ox(t) for t in terms))
    return (ox_result(temp), *(to_engine_if_rdflib(r) for r in results))


def _decode_dirlang(term: Any) -> Any:
    from starlayer.graph.model.dirlangstring import decode_dirlang_datatype

    dt = getattr(term, "datatype", None)
    decoded = decode_dirlang_datatype(dt) if dt is not None else None
    if decoded is None:
        return None
    lang, direction = decoded
    return ox.Literal(str(term), language=lang, direction=ox.BaseDirection.RTL if direction == "rtl" else ox.BaseDirection.LTR)


def from_rdflib_term(term: Any) -> Any:
    """rdflib / StarLayer term -> pyoxigraph term (a decomposed directional-language encoding is restored)."""
    from rdflib import Literal as RLiteral

    from starlayer.shacl_engine.terms import to_engine

    if isinstance(term, RLiteral):
        restored = _decode_dirlang(term)
        if restored is not None:
            return restored
    return to_engine(term)


def legal_rdf_triples(triples: Iterable[tuple[Any, Any, Any]]) -> Iterator[tuple[Any, Any, Any]]:
    """The rdflib triples of ``triples`` that RDF allows, as pyoxigraph triples. OWL RL and RDFS also derive generalized triples
    such as ``"text" rdf:type rdfs:Literal`` (literal subject, or a non-IRI predicate), which no RDF store holds."""
    from rdflib import Literal as RLiteral
    from rdflib import URIRef

    for s, p, o in triples:
        if isinstance(s, RLiteral) or not isinstance(p, URIRef):
            continue
        yield from_rdflib_term(s), from_rdflib_term(p), from_rdflib_term(o)


# ---- rdflib / StarLayer terms <-> engine terms (moved from ``shacl_engine.terms``, which delegates here) -------------------------

_CACHE_MAX = 200_000
_TO_ENGINE: dict = {}
_FROM_ENGINE: dict = {}


def _T() -> Any:
    from starlayer.shacl_engine import terms

    return terms


def _rdflib_text(term: Any) -> str:
    """``str()`` of an rdflib / StarLayer term (IRI text, lexical form, blank node id): the one place the boundary reads one."""
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
    """rdflib / StarLayer term (or a 3-tuple, a triple term) -> pyoxigraph term. ``shacl_engine.terms.to_engine`` calls this for
    anything that is not already a pyoxigraph term. A term pyoxigraph rejects raises ``TermError`` (a ``ValueError``), or under
    ``term_policy("lenient")`` becomes an opaque stand-in that ``engine_to_foreign`` maps back (see ``TermError``)."""
    from rdflib import BNode, URIRef, Variable
    from rdflib import Literal as RLiteral

    from starlayer.graph.model.dirlangstring import DirLangString
    from starlayer.graph.model.triple import TripleTerm

    T = _T()
    cls = type(term)
    if cls is URIRef or cls is BNode:
        out = _TO_ENGINE.get(term)
        if out is None:
            out = T._iri_or_stand_in(_rdflib_text(term), term) if cls is URIRef else T._bnode_or_stand_in(_rdflib_text(term), term)
            if out.value.startswith((T._INVALID_IRI_PREFIX, T._INVALID_BNODE_PREFIX)) and T._POLICY.get() == "lenient":
                return out  # a stand-in is not cached: the strict policy must still reject the original
            if len(_TO_ENGINE) >= _CACHE_MAX:
                _TO_ENGINE.clear()
            _TO_ENGINE[term] = out
        return out
    if isinstance(term, URIRef):
        return T._iri_or_stand_in(_rdflib_text(term), term)
    if isinstance(term, BNode):
        return T._bnode_or_stand_in(_rdflib_text(term), term)
    if isinstance(term, DirLangString):
        if T.has_lone_surrogate(term.value):
            return T._surrogate_literal_stand_in(term.value, term, lang=term.language)
        return T._lang_literal_or_stand_in(term.value, term.language, term, T._DIRECTIONS[term.direction])
    if isinstance(term, RLiteral):
        lexical = _rdflib_text(term)
        if term.language:
            if T.has_lone_surrogate(lexical):
                return T._surrogate_literal_stand_in(lexical, term, lang=term.language)
            return T._lang_literal_or_stand_in(lexical, term.language, term)
        datatype = T._iri_or_stand_in(_rdflib_text(term.datatype), term.datatype) if term.datatype is not None else None
        if T.has_lone_surrogate(lexical):
            return T._surrogate_literal_stand_in(lexical, term, datatype=datatype)
        return ox.Literal(lexical, datatype=datatype) if datatype is not None else ox.Literal(lexical)
    if isinstance(term, Variable):  # SPARQL-algebra graphs (salg) store query variables as terms: no oxrdf equivalent
        return ox.NamedNode(T._VARIABLE_PREFIX + _rdflib_text(term))
    if isinstance(term, TripleTerm):
        return ox.Triple(T.to_engine(term.subject), T.to_engine(term.predicate), T.to_engine(term.object))
    if isinstance(term, tuple) and len(term) == 3:
        return ox.Triple(*(T.to_engine(t) for t in term))
    raise TypeError(f"cannot convert {term!r} ({type(term).__name__}) to an engine term")


def engine_to_foreign(term: Any) -> Any:
    """pyoxigraph term -> rdflib / StarLayer term (``URIRef``, ``BNode``, ``Literal(..., normalize=False)``, ``DirLangString``,
    ``TripleTerm``)."""
    if isinstance(term, ox.Triple):
        from starlayer.graph.model.triple import TripleTerm

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

    T = _T()
    if isinstance(term, ox.NamedNode):
        if term.value.startswith(T._VARIABLE_PREFIX):
            from rdflib import Variable

            return Variable(term.value[len(T._VARIABLE_PREFIX) :])
        if term.value.startswith(T._INVALID_IRI_PREFIX):
            return URIRef(unquote(term.value[len(T._INVALID_IRI_PREFIX) :], errors="surrogatepass"))
        return URIRef(term.value)
    if isinstance(term, ox.BlankNode):
        if term.value.startswith(T._INVALID_BNODE_PREFIX):
            return BNode(bytes.fromhex(term.value[len(T._INVALID_BNODE_PREFIX) :]).decode("utf-8", "surrogatepass"))
        return BNode(term.value)
    if term.language:
        if term.direction is not None:
            from starlayer.graph.model.dirlangstring import DirLangString

            return DirLangString(term.value, term.language, str(term.direction))
        return RLiteral(term.value, lang=term.language)
    dt = term.datatype.value
    if dt.startswith(T._INVALID_LITERAL_PREFIX):
        payload, _, spec = dt[len(T._INVALID_LITERAL_PREFIX) :].partition("-")
        lexical = bytes.fromhex(payload).decode("utf-8", "surrogatepass")
        if spec.startswith("l"):
            return RLiteral(lexical, lang=unquote(spec[1:], errors="surrogatepass"))
        if spec.startswith("d"):
            return RLiteral(lexical, datatype=URIRef(unquote(spec[1:], errors="surrogatepass")), normalize=False)
        return RLiteral(lexical)
    if dt.startswith(T._INVALID_LANG_PREFIX):
        return RLiteral(term.value, lang=unquote(dt[len(T._INVALID_LANG_PREFIX) :], errors="surrogatepass"))
    if dt.startswith(T._INVALID_IRI_PREFIX):
        return RLiteral(term.value, datatype=URIRef(unquote(dt[len(T._INVALID_IRI_PREFIX) :], errors="surrogatepass")), normalize=False)
    return RLiteral(term.value) if dt == T._XSD + "string" else RLiteral(term.value, datatype=URIRef(dt), normalize=False)


def _ill_formed(term: Any) -> Any:
    """The ``TermError`` ``to_engine`` raises for ``term`` under the strict policy, or None if it converts."""
    T = _T()
    with T.term_policy("error"):
        try:
            T.to_engine(term)
        except T.TermError as exc:
            return exc
    return None


_SCANNED: Any = None  # graph -> (len, errors): a graph is scanned once per size (a WeakKeyDictionary, made on first use)
_MAX_ERRORS = 100


def scan_graph(graph: Any, where: str = "graph") -> tuple[Any, ...]:
    """Every ill-formed term of an rdflib / StarLayer graph (first ``_MAX_ERRORS``), each located by ``where``, position and the
    first triple it occurs in. Distinct terms are checked once. A graph already scanned at the same size is not scanned again."""
    import contextlib
    import weakref

    global _SCANNED
    if _SCANNED is None:
        _SCANNED = weakref.WeakKeyDictionary()
    try:
        size = len(graph)
        cached = _SCANNED.get(graph)
        if cached is not None and cached[0] == size:
            return tuple(e.located(where, e.position, e.triple) for e in cached[1])
    except TypeError:
        size = None
    seen: set = set()
    errors: list = []
    for triple in graph.triples((None, None, None)):
        for position, term in zip(("subject", "predicate", "object"), triple, strict=True):
            if term in seen:
                continue
            seen.add(term)
            err = _ill_formed(term)
            if err is None:
                continue
            if err.kind == "iri" and err.term != term and getattr(term, "datatype", None) == err.term:
                position = "datatype of the object"  # noqa: PLW2901
            errors.append(err.located(where, position, triple))
            if len(errors) >= _MAX_ERRORS:
                break
        if len(errors) >= _MAX_ERRORS:
            break
    if size is not None:
        with contextlib.suppress(TypeError):
            _SCANNED[graph] = (size, tuple(errors))
    return tuple(errors)


def check_graphs(*labelled: tuple[Any, str]) -> tuple[Any, ...]:
    """The single up-front check of a run: scan each ``(graph, label)`` that is an rdflib / StarLayer graph (Oxigraph-backed
    graphs and ``None`` hold only well-formed terms) and, under the strict policy, raise one aggregate ``TermError`` naming every
    offender with its graph label. Under ``term_policy("lenient")`` return the offenders instead."""
    T = _T()
    errors: list = []
    done: set[int] = set()
    for graph, where in labelled:
        if graph is None or getattr(graph, "engine_terms", False) or isinstance(graph, ox.Store) or id(graph) in done:
            continue
        done.add(id(graph))
        errors.extend(scan_graph(graph, where))
    if errors and T._POLICY.get() != "lenient":
        raise T.TermError(errors[0].term, errors[0].kind, errors[0].reason, errors=tuple(errors))
    return tuple(errors)


def to_oxgraph(value: Any, where: str = "graph", *, restore_directions: bool = False) -> Any:
    """An Oxigraph-backed graph for any graph a caller may pass: an ``StarLayerGraph`` / ``StarLayerDataset`` as it is, a bare ``pyoxigraph.Store``
    as an ``StarLayerDataset``, and a plain rdflib graph or an old-style ``StarLayerGraph`` (``from_rdflib``: a supported public input)
    as an ``StarLayerGraph`` copy with its prefixes and, when it has an IRI identifier, that identifier. ``None`` stays ``None``.

    A term that is not an RDF term (a relative IRI ...) raises ``TermError`` naming every offender (``where`` labels the graph),
    or, under ``term_policy("lenient")``, is stored as the opaque stand-in (``Outcome.invalid_terms`` lists it; the stand-in, not
    the original, is what an Oxigraph result holds). Oxigraph normalises some literals on insert (``"04"^^xsd:integer`` becomes
    ``"4"``): ``preserves_lexical_forms`` is False on the result, as for any ``StarLayerGraph``. ``restore_directions=True`` turns a
    directional literal decomposed to its datatype-IRI form (``interop.encode_directions``) back into a real one."""
    if value is None:
        return None
    from starlayer.graph.oxgraph.core import StarLayerDataset, StarLayerGraph

    if isinstance(value, (StarLayerGraph, StarLayerDataset)):
        return value
    if isinstance(value, ox.Store):
        return StarLayerDataset(store=value)
    if not hasattr(value, "triples") or not hasattr(value, "namespaces"):
        raise TypeError(
            f"{where} must be an StarLayerGraph, StarLayerDataset, pyoxigraph Store, StarLayerGraph or rdflib Graph; got {type(value).__name__}"
        )
    T = _T()
    check_graphs((value, where))
    from rdflib import URIRef

    ident = getattr(value, "identifier", None)
    out = StarLayerGraph(identifier=T.to_engine(ident)) if type(ident) is URIRef else StarLayerGraph()
    for prefix, ns in value.namespaces():
        out.bind(prefix, str(ns))
    to_engine = from_rdflib_term if restore_directions else T.to_engine
    out.extend([(to_engine(s), to_engine(p), to_engine(o)) for s, p, o in value.triples((None, None, None))])
    return out


def to_oxdataset(value: Any, where: str = "dataset") -> Any:
    """A new ``StarLayerDataset`` from an rdflib ``Dataset`` / ``ConjunctiveGraph`` / StarLayer dataset (every graph, empty named graphs
    too, ``default_union`` kept) or from a plain graph (its triples go to the default graph, whatever its identifier). Terms are
    converted and checked as in ``to_oxgraph``, and a decomposed directional literal is restored. Prefixes are copied."""
    from starlayer.graph.oxgraph.core import StarLayerDataset

    if isinstance(value, (StarLayerDataset, ox.Store)) or not hasattr(value, "namespaces"):
        raise TypeError(f"{where} must be an rdflib Dataset, ConjunctiveGraph, Graph or StarLayerDataset; got {type(value).__name__}")
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
    check_graphs(*((g, f"{where} graph {g.identifier}") for g in graphs))
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
            ox.Quad(from_rdflib_term(s), from_rdflib_term(p), from_rdflib_term(o), name) for s, p, o in g.triples((None, None, None))
        )
    return out


class LegacyTermView:
    """A view over an engine-term graph that speaks rdflib terms (for code that still speaks rdflib terms)."""

    def __init__(self, view: Any) -> None:
        self.view = view

    @staticmethod
    def _in(t: Any) -> Any:
        return _T().to_engine(t)

    def triples(self, pattern: tuple[Any, Any, Any]) -> Iterator[tuple[Any, Any, Any]]:
        s, p, o = pattern
        for t in self.view.triples((self._in(s), self._in(p), self._in(o))):
            yield tuple(engine_to_foreign(x) for x in t)

    def objects(self, subject: Any = None, predicate: Any = None) -> Iterator[Any]:
        for o in self.view.objects(self._in(subject), self._in(predicate)):
            yield engine_to_foreign(o)

    def subjects(self, predicate: Any = None, object: Any = None) -> Iterator[Any]:  # noqa: A002
        for s in self.view.subjects(self._in(predicate), self._in(object)):
            yield engine_to_foreign(s)

    def predicate_objects(self, subject: Any = None) -> Iterator[tuple[Any, Any]]:
        for p, o in self.view.predicate_objects(self._in(subject)):
            yield engine_to_foreign(p), engine_to_foreign(o)

    def __contains__(self, triple: tuple[Any, Any, Any]) -> bool:
        return tuple(self._in(t) for t in triple) in self.view

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
        T = _T()
        rdf_nil, rdf_first, rdf_rest = (engine_to_foreign(x) for x in (T.RDF.nil, T.RDF.first, T.RDF.rest))
        seen: set = set()
        while head is not None and head != rdf_nil and head not in seen:
            seen.add(head)
            first = next(self.objects(head, rdf_first), None)
            if first is None:
                return
            yield first
            head = next(self.objects(head, rdf_rest), None)

    def query(self, text: str, init_bindings: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        """``OxigraphGraph.query`` with rdflib terms in and out (SELECT rows, ASK bool, CONSTRUCT triples)."""
        out = self.view.query(text, {k: self._in(v) for k, v in (init_bindings or {}).items()} or None, **kwargs)
        if isinstance(out, list):
            return [
                {k: engine_to_foreign(v) for k, v in row.items()}
                if isinstance(row, dict)
                else tuple(engine_to_foreign(x) for x in row)
                for row in out
            ]
        return out

    def __getattr__(self, name: str) -> Any:
        if name in ("namespaces", "namespace_manager", "identifier", "store"):
            return getattr(self.view, name)
        raise AttributeError(name)
