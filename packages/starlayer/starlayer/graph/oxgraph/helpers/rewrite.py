"""``skolemize`` / ``de_skolemize`` (Oxigraph has none), ``cbd`` (concise bounded description) and ``empty_like``.

Ported from rdflib's ``Graph.skolemize`` / ``de_skolemize`` / ``cbd`` as ``StarLayerGraph`` and ``StarLayerDataset`` use them.
The skolem IRI is rdflib's: ``https://rdflib.github.io/.well-known/genid/rdflib/<bnode id>``, so output and input interoperate
with the old class.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlparse

import pyoxigraph as ox

from starlayer.graph.oxgraph import terms

SKOLEM_AUTHORITY = "https://rdflib.github.io"
SKOLEM_GENID = "/.well-known/genid/"
RDFLIB_SKOLEM_GENID = "/.well-known/genid/rdflib/"

_RDF = terms.RDF
_SUBJECT, _PREDICATE, _OBJECT = (ox.NamedNode(_RDF + n) for n in ("subject", "predicate", "object"))


def _need_graph(target: Any, what: str) -> None:
    if not (hasattr(target, "extend") and hasattr(target, "store")):
        raise TypeError(f"{what}() target graph must be an StarLayerGraph or StarLayerDataset, not {type(target).__name__}.")


def empty_like(g: Any) -> Any:
    """A new, empty, in-memory graph of the same kind (``StarLayerGraph`` -> ``StarLayerGraph``, ``StarLayerDataset`` -> ``StarLayerDataset`` with the same
    ``default_union``) with a copy of the namespace bindings."""
    from starlayer.graph.oxgraph.core import StarLayerDataset, StarLayerGraph

    prefixes = dict(g.prefixes)
    if isinstance(g, StarLayerDataset):
        return StarLayerDataset(default_union=g.default_union, prefixes=prefixes)
    return StarLayerGraph(prefixes=prefixes)


def _new_graph_like(g: Any) -> Any:
    """The default target of ``cbd`` / ``skolemize``: a plain ``StarLayerGraph`` with the source's prefixes (also for a dataset)."""
    from starlayer.graph.oxgraph.core import StarLayerGraph

    return StarLayerGraph(prefixes=dict(g.prefixes))


# ---- skolemization ----------------------------------------------------------------------------------------------------


def skolem_iri(bnode: ox.BlankNode, authority: str | None = None, basepath: str | None = None) -> ox.NamedNode:
    return ox.NamedNode(urljoin(authority or SKOLEM_AUTHORITY, (basepath or RDFLIB_SKOLEM_GENID) + bnode.value))


def _is_rdflib_skolem(iri: str) -> bool:
    p = urlparse(iri)
    return not (p.params or p.query or p.fragment) and p.path.rfind(RDFLIB_SKOLEM_GENID) == 0


def _is_external_skolem(iri: str) -> bool:
    return urlparse(iri).path.rfind(SKOLEM_GENID) == 0


def _map_term(t: Any, fn: Callable[[Any], Any]) -> Any:
    """``fn`` applied to a term; a triple term is rebuilt with ``fn`` applied to its subject and object (nested ones too), so a
    blank node used inside and outside a triple term stays one node. The predicate is never mapped."""
    if isinstance(t, ox.Triple):
        return ox.Triple(_map_term(t.subject, fn), t.predicate, _map_term(t.object, fn))
    return fn(t)


def _rewrite(g: Any, target: Any, fn: Callable[[Any], Any]) -> Any:
    target.extend((_map_term(s, fn), p, _map_term(o, fn)) for s, p, o in g.triples())
    return target


def skolemize(g: Any, new_graph: Any = None, bnode: Any = None, authority: str | None = None, basepath: str | None = None) -> Any:
    """Blank nodes of subjects and objects (inside triple terms too) as skolem IRIs, into ``new_graph`` (default a new
    ``StarLayerGraph``). With ``bnode`` only that blank node is replaced."""
    if new_graph is None:
        new_graph = _new_graph_like(g)
    else:
        _need_graph(new_graph, "skolemize")

    def fn(t: Any) -> Any:
        if isinstance(t, ox.BlankNode) and (bnode is None or t == bnode):
            return skolem_iri(t, authority, basepath)
        return t

    return _rewrite(g, new_graph, fn)


def de_skolemize(g: Any, new_graph: Any = None, uriref: Any = None) -> Any:
    """Skolem IRIs back to blank nodes (rdflib's own skolem IRIs restore the original id; other ``/.well-known/genid/`` IRIs
    get a fresh blank node, one per IRI within the call). With ``uriref`` only that IRI is replaced."""
    if new_graph is None:
        new_graph = _new_graph_like(g)
    else:
        _need_graph(new_graph, "de_skolemize")
    fresh: dict[str, ox.BlankNode] = {}

    def fn(t: Any) -> Any:
        if not isinstance(t, ox.NamedNode) or (uriref is not None and t != uriref):
            return t
        if _is_rdflib_skolem(t.value):
            return ox.BlankNode(urlparse(t.value).path[len(RDFLIB_SKOLEM_GENID) :])
        if _is_external_skolem(t.value):
            return fresh.setdefault(t.value, ox.BlankNode())
        return t

    return _rewrite(g, new_graph, fn)


# ---- concise bounded description ----------------------------------------------------------------------------------------


def cbd(g: Any, resource: Any, *, target_graph: Any = None, include_reifications: bool = True) -> Any:
    """The Concise Bounded Description of ``resource`` (W3C member submission): its statements, recursively those of blank-node
    objects, and (``include_reifications``) the description of each ``rdf:Statement`` node reifying one of them. Returns
    ``target_graph`` (default a new ``StarLayerGraph``)."""
    if target_graph is None:
        target_graph = _new_graph_like(g)
    else:
        _need_graph(target_graph, "cbd")
    collected: set[tuple[Any, Any, Any]] = set()
    described: set[Any] = set()  # subjects whose statements are already in `collected` (rdflib's `(o, None, None) not in subgraph`)

    # An RDF list is a chain of blank nodes, so the walk is an explicit stack, not recursion.
    stack: list[Any] = [terms.term(resource)]
    while stack:
        uri = stack.pop()
        if uri in described:
            continue
        reif_index: dict[tuple, set] = {}
        if include_reifications:
            for stmt in g.subjects(_SUBJECT, uri):
                p, o = g.value(stmt, _PREDICATE), g.value(stmt, _OBJECT)
                if p is not None and o is not None:
                    reif_index.setdefault((uri, p, o), set()).add(stmt)
        described.add(uri)
        for s, p, o in g.triples((uri, None, None)):
            collected.add((s, p, o))
            if isinstance(o, ox.BlankNode) and o not in described:
                stack.append(o)
            for stmt in sorted(reif_index.get((s, p, o), ()), key=str):
                if stmt not in described:
                    stack.append(stmt)

    target_graph.extend(collected)
    return target_graph
