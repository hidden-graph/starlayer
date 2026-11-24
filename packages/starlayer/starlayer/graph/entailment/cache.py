"""The entailed copy of a store, kept once per store and shared by SPARQL query-time entailment and SHACL validation.

Both ask :func:`entailed_store_view` for a copy of the store with the triples a regime entails added; whichever asks first builds
it, the other finds it. The cache is a dict on the store's ``StoreVersion`` (``execution/union.py``: one object for every wrapper
of a store, held by each wrapper), so a second wrapper of the same store, or a new wrapper made for one call, uses the same entries.

Invalidation is by the write count of the store (``StoreVersion.stamp()``), nothing else: a write made through this package moves
it; a write on a raw ``pyoxigraph.Store`` reference does not, and needs ``union.touch()`` (``as_store()`` does it first).

An entry is keyed by what the wrapper reads (a graph, or a dataset and whether its default graph is the union), the set of regimes,
the engine (``OWL-Direct`` only; the timeout is not part of the key), and the ontology graph the closure also read (``ont_graph``:
SHACL only). A larger regime set is never used for a smaller one. At most ``MAX_ENTRIES`` entries are kept per store, the least
recently used one is dropped first.

The copy is a ``StarLayerGraph`` / ``StarLayerDataset`` of its own store, so it is read-only for the callers: nothing may write to it.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Iterable
from typing import Any

import pyoxigraph as ox

from starlayer.graph.execution import union

#: entailed copies kept per store
MAX_ENTRIES = 4
RECOMPUTE = ("onChange", "never", "always")


class _Entry:
    """One kept copy, with the write count of its store (and of its ontology graph) at the time it was made."""

    __slots__ = ("copy", "ont_hold", "ont_stamp", "stamp")

    def __init__(self, copy: Any, stamp: Any, ont_stamp: Any, ont_hold: Any) -> None:
        self.copy = copy
        self.stamp = stamp
        self.ont_stamp = ont_stamp
        self.ont_hold = ont_hold  # the ontology's StoreVersion: held so that its ``id`` in the key is not reused


class EntailmentCache:
    """The entries of one store (``StoreVersion.entailed``)."""

    __slots__ = ("entries", "lock")

    def __init__(self) -> None:
        self.entries: OrderedDict[tuple, _Entry] = OrderedDict()
        self.lock = threading.RLock()

    def clear(self) -> None:
        with self.lock:
            self.entries.clear()


def cache_of(store: Any) -> EntailmentCache:
    """The cache of ``store`` (made on first use)."""
    version = union.version_of(store)
    with union._lock:
        if version.entailed is None:
            version.entailed = EntailmentCache()
        return version.entailed


def clear(graph: Any) -> None:
    """Drop every entailed copy kept for the store of ``graph``."""
    version = union.version_of(graph.store)
    if version.entailed is not None:
        version.entailed.clear()


def _view_key(graph: Any) -> tuple:
    """What a wrapper reads of its store: its graph, or the whole store with the default graph alone or as the union."""
    from starlayer.graph.core import StarLayerDataset

    if isinstance(graph, StarLayerDataset):
        return ("dataset", graph.default_union)
    return ("graph", graph.identifier)


def content_fingerprint(triples: Iterable[Any]) -> tuple[int, int]:
    """How many triples there are and a hash of their set (the sum of their hashes, wrapped to 64 bits)."""
    count = total = 0
    for t in triples:
        count += 1
        total += hash(t)
    return count, total & 0xFFFFFFFFFFFFFFFF


def _ont_identity(ont_graph: Any) -> tuple[tuple, Any, Any, Any]:
    """``(key part, stamp, version held, triples)`` of the ontology graph: a graph by its store (its write count is checked like the
    data's), an iterable of triples by a fingerprint of its content (which is then part of the key)."""
    if ont_graph is None:
        return (), None, None, None
    if hasattr(ont_graph, "store"):
        version = union.version_of(ont_graph.store)
        return ("ont", id(version), _view_key(ont_graph)), version.stamp(), version, None
    triples = list(ont_graph)
    return ("ont-triples", content_fingerprint(triples)), None, None, triples


def _ont_triples(ont_graph: Any, held: Any) -> list:
    return held if held is not None else list(ont_graph.triples((None, None, None)))


def entailed_store_view(
    graph: Any,
    regimes: Iterable[Any],
    *,
    engine: str = "hermit",
    timeout: Any = None,
    ont_graph: Any = None,
    recompute: str = "onChange",
) -> Any:
    """``graph`` and what ``regimes`` entail, as a copy of its store: a ``StarLayerGraph`` (or a dataset, of the same ``default_union``)
    over a new in-memory store that holds every graph of the store plus the entailed triples, in the graph this wrapper reads. Neither
    ``graph`` nor ``ont_graph`` is changed, and the caller must not change the copy either: it is the one every later call gets.

    ``regimes`` are regime IRIs (strings or ``NamedNode``), several are one combined run. ``ont_graph`` (a graph, or an iterable of
    triples) is visible to the reasoner only: the copy holds the data and the entailed triples, not the ontology's. ``recompute``
    says when the copy is made again, as for ``query()``: ``"onChange"`` after a write to the store (or to the ontology graph's), ``"never"``
    only when none is kept, ``"always"`` every time, keeping none. ``engine`` and ``timeout`` are for ``OWL-Direct`` (the timeout
    defaults to ``infer.DEFAULT_TIMEOUT``)."""
    from starlayer.graph.entailment import infer as ent

    if recompute not in RECOMPUTE:
        raise ValueError(f"recompute must be one of ['always', 'never', 'onChange'], got {recompute!r}")
    names = frozenset(ent._regime_iri(r) for r in regimes)
    direct = ent.OWL_DIRECT_REGIME in names
    key = (_view_key(graph), names, engine if direct else None)
    ont_key, ont_stamp, ont_version, ont_held = _ont_identity(ont_graph)
    key += ont_key
    timeout = ent.DEFAULT_TIMEOUT if timeout is None else timeout
    cache = cache_of(graph.store)
    version = union.version_of(graph.store)
    with cache.lock:
        hit = cache.entries.get(key)
        stamp = version.stamp()  # taken before the reasoner runs: a write that lands during it leaves the copy stale
        if hit is not None and recompute != "always" and (recompute == "never" or (hit.stamp == stamp and hit.ont_stamp == ont_stamp)):
            cache.entries.move_to_end(key)
            _share_prefixes(hit.copy, graph)
            return hit.copy
        copy = build_entailed_copy(
            graph, names, engine=engine, timeout=timeout, ont=None if ont_graph is None else _ont_triples(ont_graph, ont_held)
        )
        if recompute == "always":
            cache.entries.pop(key, None)  # "always" keeps nothing: what was kept is dropped and this copy lives for the one call
        else:
            cache.entries[key] = _Entry(copy, stamp, ont_stamp, ont_version)
            cache.entries.move_to_end(key)
            while len(cache.entries) > MAX_ENTRIES:
                cache.entries.popitem(last=False)
        return copy


def _share_prefixes(copy: Any, graph: Any) -> None:
    """The prefixes bound to ``graph`` since the copy was made count too (a copy is shared by wrappers of one store: the last caller's win)."""
    copy.prefixes.clear()
    copy.prefixes.update(graph.prefixes)


def build_entailed_copy(graph: Any, regimes: frozenset[str], *, engine: str, timeout: Any, ont: list | None = None) -> Any:
    """A copy of the whole store (every graph, empty named ones too) with what ``regimes`` entail added to the graph ``graph`` reads.
    On a dataset each non-empty named graph also gets what the regimes entail from that graph alone (one reasoner run per graph), so
    ``GRAPH <g> { }`` patterns see it. ``ont`` (triples) is read by every run and not copied. ``graph``'s store is not changed."""
    from starlayer.graph import core
    from starlayer.graph.entailment import infer as ent

    def entailed(of: Any) -> set[tuple[Any, Any, Any]]:
        if ont:
            combined = core.StarLayerGraph()
            combined.extend(list(of.triples()))
            combined.extend(ont)
            of = combined
        return ent._delta_for(of, regimes, engine, timeout)

    delta = entailed(graph)
    store = ox.Store()
    store.extend(graph.store)
    for name in graph.store.named_graphs():
        store.add_graph(name)
    if isinstance(graph, core.StarLayerDataset):
        copy: Any = core.StarLayerDataset(store=store, default_union=graph.default_union, prefixes=dict(graph.prefixes))
        for name in graph.store.named_graphs():
            view = core._sharing(core.StarLayerGraph(graph.store, identifier=name), graph.prefixes)
            if len(view):
                store.extend(copy._quad(t, name) for t in entailed(view))
    else:
        copy = core.StarLayerGraph(store=store, identifier=graph.identifier, prefixes=dict(graph.prefixes))
    g = copy._add_graph()
    store.extend(copy._quad(t, g) for t in delta)  # not copy.extend(): that counts as a write
    return copy


__all__ = ["MAX_ENTRIES", "EntailmentCache", "build_entailed_copy", "cache_of", "clear", "content_fingerprint", "entailed_store_view"]
