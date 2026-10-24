"""``used_prefixes()`` - the prefixes of a graph that matter (GitHub issue #29).

Every ``rdflib`` graph is bound to about 29 default prefixes (brick, csvw, dcat, geo, ...) that a file never mentions; the
Turtle 1.2 writer already writes only the ones an IRI of the graph is in. This is that rule as a function: a prefix is *in use*
when some IRI of the graph - a subject, predicate or object, a literal's datatype, or any part of a triple term - is in its
namespace. ``rdf:type`` as a predicate does not count (Turtle writes it as ``a``). The two StarLayer-internal prefixes (``sl:``, ``tt:``) are never returned.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from rdflib import RDF, Literal, URIRef

from starlayer.graph.model.triple import TripleTerm

__all__ = ["used_prefixes"]


_SL_NS = "https://github.com/hidden-graph/starlayergraph/ns#"


def _internal_namespaces() -> frozenset[str]:
    from starlayer.graph.model.encoding import TT_NS

    return frozenset({_SL_NS, str(TT_NS)})


def _collect(node: Any, used: set[str]) -> None:
    if isinstance(node, TripleTerm):
        for part in (node.subject, node.predicate, node.object):
            _collect(part, used)
    elif isinstance(node, URIRef):
        used.add(str(node))
    elif isinstance(node, Literal) and node.datatype:
        used.add(str(node.datatype))


def select_prefixes(namespaces: Iterable[tuple[str, Any]], used_uris: Iterable[str]) -> list[tuple[str, URIRef]]:
    """The ``(prefix, namespace)`` pairs, sorted by prefix, whose namespace some IRI in ``used_uris`` starts with.

    Shared by ``used_prefixes()`` and the Turtle 1.2 writers (which collect ``used_uris`` while formatting, so a term they fold
    away, such as a reifier written as ``~``, does not count)."""
    internal = _internal_namespaces()
    uris = set(used_uris)
    selected = []
    for prefix, namespace in sorted(namespaces, key=lambda pair: pair[0]):
        ns = str(namespace)
        if ns in internal:
            continue
        if any(u.startswith(ns) for u in uris):
            selected.append((prefix, URIRef(ns)))
    return selected


def used_prefixes(graph: Any) -> list[tuple[str, URIRef]]:
    """The prefixes of ``graph`` that are in use, as ``(prefix, namespace)`` pairs sorted by prefix.

    Use it for a graph that arrives with rdflib's default prefixes bound, to offer or write only the ones that matter. A prefix the
    file declared but never used is not returned (the writers drop it as well). Triple terms are searched too."""
    used: set[str] = set()
    for s, p, o in graph.triples((None, None, None)):
        _collect(s, used)
        if p != RDF.type:  # written as "a", so it needs no prefix (as in the Turtle writers)
            _collect(p, used)
        _collect(o, used)
    return select_prefixes(graph.namespaces(), used)
