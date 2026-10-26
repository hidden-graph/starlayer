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


def _is_dataset(graph: Any) -> bool:
    return hasattr(graph, "contexts") and hasattr(graph, "default_context")


def _collect_from_graph(graph: Any, used: set[str]) -> None:
    for s, p, o in graph.triples((None, None, None)):
        _collect(s, used)
        if p != RDF.type:  # written as "a", so it needs no prefix (as in the Turtle writers)
            _collect(p, used)
        _collect(o, used)


def used_prefixes(graph: Any) -> list[tuple[str, URIRef]]:
    """The prefixes of a graph or dataset that are in use, as ``(prefix, namespace)`` pairs sorted by prefix.

    Use it for a graph that arrives with rdflib's default prefixes bound, to offer or write only the ones that matter. A prefix the
    file declared but never used is not returned (the writers drop it as well). This is what the Turtle 1.2 writer writes as
    ``@prefix`` lines (it is the writer's own answer, so the two cannot disagree: ``rdf:reifies`` folded into ``{| |}`` or ``~``,
    ``rdf:first`` / ``rdf:rest`` folded into ``( )`` and a bare ``1`` do not make ``rdf`` or ``xsd`` count; a prefix that is not a
    valid ``PN_PREFIX`` is shown as the ``pfxN`` the writer renames it to). For a dataset the triples of every graph count, and so do
    the names of the named graphs, so the answer is the prefixes the whole dataset needs."""
    from starlayer.graph.serializers.turtle12 import render_turtle12

    chosen: dict[str, URIRef] = {}
    if _is_dataset(graph):
        # StarLayerDataset.contexts() yields StarLayerGraphs (triple terms restored); a plain rdflib Dataset uses graphs()
        contexts = graph.contexts() if hasattr(graph, "_sg_cache") or not hasattr(graph, "graphs") else graph.graphs()
        names: set[str] = set()
        for context in contexts:
            for prefix, namespace in render_turtle12(context)[0]:
                chosen[prefix] = URIRef(namespace)
            if isinstance(context.identifier, URIRef):
                names.add(str(context.identifier))
        for prefix, namespace in select_prefixes(graph.namespaces(), names):
            chosen.setdefault(prefix, namespace)
    else:
        for prefix, namespace in render_turtle12(graph)[0]:
            chosen[prefix] = URIRef(namespace)
    return sorted(chosen.items())


def prefixes_to_keep(graph: Any, keep: Iterable[str] = ()) -> list[tuple[str, URIRef]]:
    """The bindings a reduced copy of ``graph`` should have: the ones in use, plus any of ``keep`` (prefix names) that ``graph``
    has bound, whether used or not. Sorted by prefix."""
    chosen = dict(used_prefixes(graph))
    # one name given as a bare string is one name, not a set of characters; None means none
    wanted = {keep} if isinstance(keep, str) else set(keep or ())
    for prefix, namespace in graph.namespaces():
        if prefix in wanted:
            chosen.setdefault(prefix, URIRef(str(namespace)))
    return sorted(chosen.items())


def unbind_prefix(graph: Any, prefix: str) -> bool:
    """Take the binding of ``prefix`` away from ``graph``'s store; True if there was one.

    rdflib's ``Graph`` and ``NamespaceManager`` have no such call (``bind`` only adds or replaces). The binding is removed from
    the store's own tables for the stores that keep a prefix map this library can reach: rdflib's in-memory store and
    ``oxrdflib``'s ``OxigraphStore``. Any other store (a SQL store, a remote endpoint) raises ``NotImplementedError`` rather
    than pretending: copy the graph with ``reduce_prefixes()`` there. Graphs of one dataset share their store, so the prefix is
    gone from all of them (GitHub issue #44).
    """
    manager = graph.namespace_manager
    store = manager.store
    namespace = store.namespace(prefix)
    if namespace is None:
        return False
    if hasattr(store, "_Memory__namespace"):  # rdflib.plugins.stores.memory.Memory
        store._Memory__namespace.pop(prefix, None)
        if store._Memory__prefix.get(namespace) == prefix:
            del store._Memory__prefix[namespace]
    elif hasattr(store, "_delete_from_prefix"):  # oxrdflib.OxigraphStore: removes the binding in both directions
        store._delete_from_prefix(prefix)
    else:
        raise NotImplementedError(
            f"a {type(store).__name__} keeps its namespace bindings where unbind() cannot reach them; "
            "build a copy without the prefix with reduce_prefixes(keep=...) instead"
        )
    manager.reset()  # the manager caches prefix lookups
    return True
