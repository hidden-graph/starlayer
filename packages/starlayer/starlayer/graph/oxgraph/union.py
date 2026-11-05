"""A union default graph that is a set.

Oxigraph builds a default graph from several graphs (``use_default_graph_as_union``, ``default_graph=[...]``, several ``FROM``)
without removing duplicates: a triple stored in two graphs is matched twice, so ``COUNT(*)``, ``SUM``, ``GROUP BY`` and a
``SELECT`` without ``DISTINCT`` over the union count it twice (``docs/working/oxigraph-upstream-issues.md`` section 5). The SPARQL
merge of graphs is a set, and so is an ``StarLayerDataset`` with ``default_union=True``.

Decision (measurements in that note): a dataset holding a triple in more than one graph runs its queries against a
deduplicated copy of the store (``Overlap.store``): the same named graphs and a default graph that is the set of the triples of
every graph. A dataset without such a triple runs on the store itself. The copy is cached and dropped when a write made through
this package happens (``touch``; ``as_store()``, which hands out the raw store, calls it too). A write made on the raw store
through a reference kept from before is not seen: call ``touch()`` after it (checking ``len(store)`` on every query would be O(n),
about 70 ms on the code-KG data). SPARQL Update reads a copy of the union kept in a scratch graph (see
``run.update``). A query with its own ``FROM`` clauses is not changed: it names the graphs to merge itself.
"""

from __future__ import annotations

import itertools

import pyoxigraph as ox

#: counts the writes made through the wrapper (any store); a copy built before the latest one is stale
_writes = itertools.count(1)
_current = 0


def touch() -> None:
    """Record a write made through the wrapper: copies built before it are stale."""
    global _current
    _current = next(_writes)


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
        self._stamp: int | None = None
        self._overlapping = False
        self._copy: ox.Store | None = None

    def overlapping(self, store: ox.Store) -> bool:
        if self._stamp != _current:
            self._overlapping = has_overlap(store)
            self._copy = None
            self._stamp = _current
        return self._overlapping

    def store(self, store: ox.Store) -> ox.Store:
        """The store to run a union-default-graph query on: ``store`` itself, or its merged copy when a triple is in two graphs."""
        if not self.overlapping(store):
            return store
        if self._copy is None:
            self._copy = merged_copy(store)
        return self._copy
