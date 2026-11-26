"""A union default graph that is a set.

Oxigraph builds a default graph from several graphs (``use_default_graph_as_union``, ``default_graph=[...]``, several ``FROM``)
without removing duplicates: a triple stored in two graphs is matched twice, so ``COUNT(*)``, ``SUM``, ``GROUP BY`` and a
``SELECT`` without ``DISTINCT`` over the union count it twice (``docs/working/oxigraph-upstream-issues.md`` section 5). The SPARQL
merge of graphs is a set, and so is an ``StarLayerDataset`` with ``default_union=True``.

Decision (measurements in that note): a dataset holding a triple in more than one graph runs its queries against a
deduplicated copy of the store (``Overlap.store``): the same named graphs and a default graph that is the set of the triples of
every graph. A dataset without such a triple runs on the store itself. The copy is cached and dropped when a write made through
this package happens to its store (``touch``; ``as_store()``, which hands out the raw store, calls it too; a write to another store
does not drop it). A write made on the raw store
through a reference kept from before is not seen: call ``touch()`` after it (checking ``len(store)`` on every query would be O(n),
about 70 ms on the code-KG data). SPARQL Update reads a copy of the union kept in a scratch graph (see
``run.update``). A query with its own ``FROM`` clauses is not changed: it names the graphs to merge itself.
"""

from __future__ import annotations

import threading
import weakref
from typing import Any

import pyoxigraph as ox

#: counts the writes made through the wrapper (any store); a copy built before the latest one is stale
_current = 0
_lock = threading.RLock()  # guards the counter: an unlocked read-increment-write from two threads can move it backwards


class StoreVersion:
    """The writes made through the wrapper to one store (a ``pyoxigraph.Store`` takes no attribute and no weak reference, so the count
    is kept here, one object for every wrapper of the store). It holds the store, so the store's ``id`` is not reused while it lives."""

    __slots__ = ("__weakref__", "entailed", "imports", "n", "rewritten", "store")

    def __init__(self, store: ox.Store) -> None:
        self.store = store
        self.n = 0
        #: the literals loaded through the wrapper that the store keeps in another form than written (``graph/lexical.py``)
        self.rewritten = 0
        #: the entailed copies of this store (``graph/entailment/cache.py``), shared by SPARQL and SHACL; made on first use. They live
        #: and die with this object, so a wrapper holds it (``_Base._version``) as long as it is to find them again.
        self.entailed: Any = None
        #: the resolved ``owl:imports`` of the graphs of this store (``graph/imports.py``); made on first use
        self.imports: Any = None

    def stamp(self) -> tuple[int, int]:
        """A value that differs after any write to this store, and after a write that did not say which store it was."""
        return (self.n, _epoch)


_versions: weakref.WeakValueDictionary[int, StoreVersion] = weakref.WeakValueDictionary()
_epoch = 0  # counts the writes that did not name their store: they are taken to have changed every store


def version_of(store: ox.Store) -> StoreVersion:
    """The write count of ``store``, shared by every wrapper of it. Hold the result as long as a stamp taken from it is to be compared:
    the count is dropped when nothing refers to it."""
    with _lock:
        version = _versions.get(id(store))
        if version is None or version.store is not store:
            version = StoreVersion(store)
            _versions[id(store)] = version
        return version


def touch(store: ox.Store | None = None) -> None:
    """Record a write made through the wrapper: copies built before it are stale. ``store`` is the store written to; a write on a raw
    store reference (which the wrapper cannot see) is recorded without one, and counts as a write to every store."""
    global _current, _epoch
    with _lock:
        _current += 1
        if store is None:
            _epoch += 1
        else:
            version_of(store).n += 1


def current() -> int:
    """The number of the latest write made through the wrapper (any store); a stamp taken before a write differs from it after."""
    return _current


def populated_graphs(store: ox.Store) -> int:
    """How many graphs (the default graph and blank-node graphs included) hold a triple, counted up to 2."""
    count = 0
    for g in (ox.DefaultGraph(), *store.named_graphs()):
        if next(store.quads_for_pattern(None, None, None, g), None) is not None:
            count += 1
            if count > 1:
                break
    return count


def has_overlap(store: ox.Store) -> bool:
    """True when some triple is stored in more than one graph (so that the union as Oxigraph evaluates it is not a set)."""
    if populated_graphs(store) < 2:
        return False
    count = "SELECT (COUNT(*) AS ?n) WHERE { %s }"
    n = next(iter(store.query(count % "?s ?p ?o", use_default_graph_as_union=True)))[0].value
    d = next(iter(store.query(count % "SELECT DISTINCT ?s ?p ?o WHERE { ?s ?p ?o }", use_default_graph_as_union=True)))[0].value
    return n != d


def merged_copy(store: ox.Store) -> ox.Store:
    """A new in-memory store with the quads of ``store`` and, as its default graph, the set of the triples of all its graphs."""
    out = ox.Store()
    out.extend(store)
    out.update("INSERT { ?s ?p ?o } WHERE { GRAPH ?g { ?s ?p ?o } }")
    for name in store.named_graphs():  # empty named graphs have no quad to carry them
        out.add_graph(name)
    return out


def fill_scratch(store: ox.Store, scratch: ox.NamedNode) -> None:
    """Fill graph ``scratch`` of ``store`` with the set of the triples of all its other graphs, the default graph included (done
    by the engine, which does not store a triple it inserts twice)."""
    store.update(f"INSERT {{ GRAPH <{scratch.value}> {{ ?s ?p ?o }} }} WHERE {{ {{ ?s ?p ?o }} UNION {{ GRAPH ?g {{ ?s ?p ?o }} }} }}")


class Overlap:
    """What one dataset has learned about its store: whether a triple is in more than one graph and, if so, the merged copy.
    One per ``StarLayerDataset`` (a ``pyoxigraph.Store`` takes no attribute and no weak reference, so the cache cannot sit on it)."""

    def __init__(self) -> None:
        """Start unscanned, so the first overlapping() or store() call scans."""
        self._stamp: tuple[int, int] | None = None
        self._watch: StoreVersion | None = None  # held, so the count the stamp came from is the one a later write adds to
        self._overlapping = False
        self._copy: ox.Store | None = None
        self._lock = threading.RLock()  # one scan and one copy at a time; a thread never records a stamp older than its data

    def overlapping(self, store: ox.Store) -> bool:
        """Whether a triple is in more than one graph of ``store``, rescanning after any write made through the wrapper to this store."""
        with self._lock:
            if self._watch is None or self._watch.store is not store:
                self._watch = version_of(store)
                self._stamp = None
            stamp = self._watch.stamp()  # taken before the scan: a write that lands during it leaves the stamp behind, so the next call rescans
            if self._stamp != stamp:
                self._overlapping = has_overlap(store)
                self._copy = None
                self._stamp = stamp
            return self._overlapping

    def store(self, store: ox.Store) -> ox.Store:
        """The store to run a union-default-graph query on: ``store`` itself, or its merged copy when a triple is in two graphs."""
        with self._lock:
            if not self.overlapping(store):
                return store
            if self._copy is None:
                self._copy = merged_copy(store)
            return self._copy
