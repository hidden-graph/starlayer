"""Small helpers over Oxigraph-backed graphs, for the engine modules that build graphs (reports, extracts, closures).

Every graph the engine builds is an ``StarLayerGraph`` (pyoxigraph terms, its own in-memory store). ``StarLayerGraph`` is imported
lazily: ``starlayer.graph.oxgraph`` imports the engine's SPARQL view.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pyoxigraph as ox

from starlayer.shacl_engine.terms import RDF


def new_graph(like: Any = None, *, identifier: Any = None) -> Any:
    """A fresh empty ``StarLayerGraph``, with the prefixes ``like`` binds (when it binds any: ``namespaces()``)."""
    from starlayer.graph.oxgraph.core import StarLayerGraph

    out = StarLayerGraph(identifier=identifier)
    namespaces = getattr(like, "namespaces", None)
    if namespaces is not None:
        try:
            for prefix, ns in namespaces():
                out.bind(prefix, ns if isinstance(ns, str) else f"{ns}")  # str-ok: a namespace (rdflib ``URIRef`` or str)
        except Exception:  # noqa: BLE001  (a view without namespace support just keeps no prefixes)
            pass
    return out


def list_items(graph: Any, head: Any) -> list[Any]:
    """The members of the RDF list at ``head`` (cycle-safe, tolerant of a malformed tail)."""
    out: list[Any] = []
    seen: set = set()
    while head is not None and head != RDF.nil and head not in seen:
        seen.add(head)
        first = next(iter(graph.objects(head, RDF.first)), None)
        if first is None:
            break
        out.append(first)
        head = next(iter(graph.objects(head, RDF.rest)), None)
    return out


def add_list(graph: Any, items: Iterable[Any]) -> Any:
    """Add an RDF list of ``items`` to ``graph``; return its head (``rdf:nil`` for no items)."""
    members = list(items)
    if not members:
        return RDF.nil
    nodes = [ox.BlankNode() for _ in members]
    triples = []
    for i, (node, member) in enumerate(zip(nodes, members, strict=True)):
        triples.append((node, RDF.first, member))
        triples.append((node, RDF.rest, nodes[i + 1] if i + 1 < len(nodes) else RDF.nil))
    graph.extend(triples)
    return nodes[0]


def copy_cbd(src: Any, dst: Any, node: Any, seen: set) -> None:
    """The concise bounded description of ``node`` (its triples, recursing into blank-node objects) from ``src`` into ``dst``."""
    pending = [node]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        batch = []
        for p, o in src.predicate_objects(current):
            batch.append((current, p, o))
            if isinstance(o, ox.BlankNode):
                pending.append(o)
        dst.extend(batch)
