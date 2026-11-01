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


def to_rdflib_term(term: Any) -> Any:
    """pyoxigraph term -> rdflib / StarLayer term (a triple term becomes a ``TripleTerm``)."""
    from starlayer.shacl_engine.terms import from_engine

    return from_engine(term)


def to_rdflib_triples(triples: Iterable[tuple[Any, Any, Any]]) -> list[tuple[Any, Any, Any]]:
    from starlayer.shacl_engine.terms import from_engine

    return [(from_engine(s), from_engine(p), from_engine(o)) for s, p, o in triples]


def rdflib_graph(triples: Iterable[tuple[Any, Any, Any]], *, decompose: bool = True) -> Any:
    """A plain ``rdflib.Graph`` with the triples. ``decompose=True`` replaces every triple term with a synthetic reification
    fragment (what the reasoners need; they cannot hold a triple term), as ``starlayer.graph.compare._decompose`` does."""
    from rdflib import Graph

    rows = to_rdflib_triples(triples)
    out = Graph()
    if decompose:
        from starlayer.graph.compare import _decompose_quads

        for s, p, o, _g in _decompose_quads((s, p, o, None) for s, p, o in rows):
            out.add((s, p, o))
    else:
        for t in rows:
            out.add(t)
    return out


def starlayer_graph(triples: Iterable[tuple[Any, Any, Any]], prefixes: dict[str, str] | None = None) -> Any:
    """An old-style ``StarLayerGraph`` (keeps triple terms) holding the triples; used where the code to run needs RDF 1.2."""
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph

    g = StarLayerGraph()
    for prefix, ns in (prefixes or {}).items():
        g.bind(prefix, ns)
    for t in to_rdflib_triples(triples):
        g.add(t)
    return g


def is_oxigraph_input(value: Any) -> bool:
    """True for an ``OxGraph`` / ``OxDataset`` or a bare ``pyoxigraph.Store``."""
    from starlayer.graph.oxgraph.core import OxDataset, OxGraph

    return isinstance(value, (OxGraph, OxDataset, ox.Store))


def to_starlayer_graph(value: Any) -> Any:
    """A snapshot of an ``OxGraph`` / ``OxDataset`` / bare ``Store`` as an old-style ``StarLayerGraph`` (the library entry points
    that still run on rdflib code call this at the boundary). A dataset or store gives the union of its graphs; a graph view
    keeps its identifier and its prefixes. The result is a copy: writes to it do not reach ``value``."""
    from rdflib import URIRef

    from starlayer.graph.graph.starlayer_graph import StarLayerGraph
    from starlayer.graph.oxgraph.core import OxDataset, OxGraph

    if isinstance(value, ox.Store):
        value = OxDataset(store=value)
    ident = value.identifier if isinstance(value, OxGraph) else None
    g = StarLayerGraph(identifier=URIRef(ident.value)) if isinstance(ident, ox.NamedNode) else StarLayerGraph()
    for prefix, ns in dict(value.prefixes).items():
        g.bind(prefix, ns)
    for t in to_rdflib_triples(iter(value)):
        g.add(t)
    return g


def as_rdflib_graph(graph: Any) -> Any:
    """``graph`` itself, or a snapshot ``StarLayerGraph`` if it is an Oxigraph graph: for ``rdflib_graph += x`` where ``x`` may be
    either kind (the ontology and shapes loaders return whatever class ``StarLayerGraph`` is)."""
    return to_starlayer_graph(graph) if is_oxigraph_input(graph) else graph


def merge_into(dst: Any, src: Any) -> None:
    """``dst += src`` for graphs of either kind (``OxGraph`` ``+=`` takes only an ``OxGraph``; rdflib's takes only rdflib). Triples
    only: no prefixes are copied, as with rdflib's ``+=``."""
    if is_oxigraph_input(dst):
        dst.extend(list(iter(src)))  # OxGraph.add / extend convert rdflib terms
    elif is_oxigraph_input(src):
        for t in to_rdflib_triples(iter(src)):
            dst.add(t)
    else:
        dst += src


def is_oxigraph_dataset(value: Any) -> bool:
    """True for an ``OxDataset`` or a bare ``pyoxigraph.Store`` (something with named graphs)."""
    from starlayer.graph.oxgraph.core import OxDataset

    return isinstance(value, (OxDataset, ox.Store))


def rdflib_quads(value: Any) -> list[tuple[Any, Any, Any, Any]]:
    """Every quad of an ``OxDataset`` / ``Store`` as rdflib terms ``(s, p, o, g)``, ``g`` ``None`` for the default graph. An
    ``OxGraph`` gives its triples with ``g`` ``None``."""
    from starlayer.graph.oxgraph.core import as_store

    if is_oxigraph_dataset(value):
        out = []
        for q in as_store(value).quads_for_pattern(None, None, None, None):
            g = None if isinstance(q.graph_name, ox.DefaultGraph) else to_rdflib_term(q.graph_name)
            out.append((to_rdflib_term(q.subject), to_rdflib_term(q.predicate), to_rdflib_term(q.object), g))
        return out
    return [(s, p, o, None) for s, p, o in to_rdflib_triples(iter(value))]


def ox_graph_from(graph: Any) -> Any:
    """An ``OxGraph`` holding the triples of an rdflib / StarLayer graph (prefixes kept)."""
    from starlayer.graph.oxgraph.core import OxGraph

    if isinstance(graph, OxGraph):
        return graph
    out = OxGraph()
    for prefix, ns in graph.namespaces():
        out.bind(prefix, str(ns))
    copy_into(out, graph)
    return out


def copy_into(target: Any, triples: Iterable[tuple[Any, Any, Any]]) -> None:
    """Add rdflib-term triples to an ``OxGraph`` (its ``add`` converts lazily); one call, one transaction."""
    target.extend(list(triples))


def read_boundary(graph: Any, *terms: Any) -> tuple[Any, ...]:
    """For a library function that READS a graph with rdflib code: ``(graph, *terms)`` ready for it. An Oxigraph graph becomes a
    snapshot ``StarLayerGraph`` and any pyoxigraph term in ``terms`` its rdflib equivalent; anything else passes unchanged."""
    if not is_oxigraph_input(graph):
        return (graph, *terms)
    return (to_starlayer_graph(graph), *(from_engine_if_ox(t) for t in terms))


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
    ``(graph, *result_terms)``. With an ``OxGraph`` target, ``build`` gets a fresh rdflib graph; its triples are then added to
    the ``OxGraph`` (one transaction) and the result terms returned as pyoxigraph terms. Any other target is passed through."""
    if graph is None or not is_oxigraph_input(graph):
        return build(graph, *terms)
    temp, *results = build(None, *(from_engine_if_ox(t) for t in terms))
    copy_into(graph, temp)
    return (graph, *(to_engine_if_rdflib(r) for r in results))


def _decode_dirlang(term: Any) -> Any:
    from starlayer.graph.model.encoding import decode_dirlang_datatype

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
