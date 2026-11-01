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
    """An ``OxGraph`` holding the triples of ``graph`` (rdflib terms -> pyoxigraph terms): the result of a library function that
    ran on rdflib code for an Oxigraph input. Its prefixes are those of the Oxigraph graphs in ``sources`` (the inputs) plus the
    prefixes of ``graph`` that its IRIs actually use, never the 29 defaults an old-style ``StarLayerGraph`` binds. An ``OxGraph``
    passes through unchanged."""
    from starlayer.graph.oxgraph.core import OxGraph

    if isinstance(graph, OxGraph):
        return graph
    prefixes: dict[str, str] = {}
    for src in sources:
        if is_oxigraph_input(src):
            for prefix, ns in dict(getattr(src, "prefixes", {})).items():
                prefixes.setdefault(prefix, ns)
    prefixes.update(_used_namespace_prefixes(graph, prefixes))
    out = OxGraph(prefixes=prefixes)
    ident = getattr(graph, "identifier", None)
    from rdflib import URIRef

    if isinstance(ident, URIRef):
        out = OxGraph(prefixes=prefixes, identifier=from_rdflib_term(ident))
    copy_into(out, graph)
    return out


def convert_result(value: Any, *sources: Any) -> Any:
    """``value`` (a graph, a result dataclass such as ``ValidationResult`` / ``RulesResult``, or a tuple / list / dict of those)
    with every old-style graph in it replaced by an ``OxGraph`` (see ``ox_result``). Anything else is returned unchanged."""
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
    from starlayer.graph.oxgraph.core import OxDataset, OxGraph

    return (OxGraph, OxDataset)


def ox_in_ox_out(*graph_params: str, owner_sources: str | None = None) -> Any:
    """Decorator: when any of the named graph parameters (or, for a method, any value of ``self.<owner_sources>``) is an
    Oxigraph graph / dataset / store, the graphs in the result are returned as ``OxGraph`` (see ``convert_result``). With old-style
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
