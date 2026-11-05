"""Set operations on graphs and datasets: ``union``, ``intersection``, ``difference``, ``symmetric_difference``.

rdflib gives its graphs the operators ``+``, ``-``, ``&`` and ``^``. Oxigraph's ``Store`` and ``Dataset`` have none, so StarLayer
provides them as functions that behave the same way on both families, ready to be wired to operators on the Oxigraph-backed
``StarLayerGraph`` wrapper.

The Oxigraph-backed ``StarLayerGraph`` and ``StarLayerDataset`` are accepted as operands too (and as ``into``): they are combined as their
stores and give an ``StarLayerGraph`` / ``StarLayerDataset`` back, so the functions and the operators agree. Two families are supported; the operands of one call must belong to the same family (convert one side first, otherwise a
``TypeError`` says so):

* the rdflib family: ``rdflib.Graph``, ``rdflib.Dataset``/``ConjunctiveGraph`` and the StarLayer subclasses;
* the pyoxigraph family: ``pyoxigraph.Store`` and ``pyoxigraph.Dataset``.

Semantics, identical in both:

* A graph is a set of triples and a dataset a set of quads. Terms are compared exactly as the library compares them: triple terms by
  structure, literals by lexical form and datatype (a pyoxigraph *store* has already rewritten some lexical forms on insert; see issue
  #190).
* **Blank nodes are compared by label**, not by isomorphism. Two graphs that differ only in blank-node labels have an empty
  intersection and a full difference. This is what rdflib's operators do. Use ``starlayer.graph.compare`` or RDFC canonicalisation
  first when isomorphism is meant.
* Quads are compared with their graph name. The default graph is one graph like any other (``urn:x-rdflib:default`` in rdflib,
  ``DefaultGraph`` in pyoxigraph).
* Inputs are never modified. The result is a new object of the first operand's type, or ``into`` when given. ``into`` receives the
  result by *addition* and nothing is removed from it, so ``union(a, b, into=a)`` adds ``b`` to ``a`` in place, while
  ``difference(a, b, into=a)`` leaves ``a`` unchanged (it adds triples already there); to shrink a graph, build the difference
  and replace it.
* For rdflib graphs the result binds the prefixes of both operands (as rdflib's ``__add__`` does); Oxigraph stores hold no prefixes.

Cost: ``difference`` and ``intersection`` stream the first operand and test membership in the second (no set is materialised);
``union`` copies one side then adds the other; ``symmetric_difference`` makes two passes.
"""

from __future__ import annotations

import functools
import sys
from collections.abc import Iterable, Iterator
from typing import Any

import pyoxigraph as ox

__all__ = ["difference", "intersection", "symmetric_difference", "union"]


def _rdflib() -> Any:
    """The ``rdflib`` module if it is loaded, else ``None``. rdflib is an optional extra and is never imported here: an rdflib graph
    can only reach this module if its owner has already imported rdflib."""
    return sys.modules.get("rdflib")


def _family(x: Any) -> str:
    if isinstance(x, (ox.Store, ox.Dataset)):
        return "ox"
    rdflib = _rdflib()
    if rdflib is not None:
        if isinstance(x, rdflib.ConjunctiveGraph):  # includes rdflib.Dataset
            return "rdflib-dataset"
        if isinstance(x, rdflib.Graph):
            return "rdflib-graph"
    raise TypeError(
        f"set operations take an rdflib Graph/Dataset or a pyoxigraph Store/Dataset, not {type(x).__name__}"
        + (" (an OxigraphGraph view: pass its .store)" if type(x).__name__ == "OxigraphGraph" else "")
    )


def _same_family(a: Any, b: Any) -> str:
    fa, fb = _family(a), _family(b)
    if fa != fb:
        raise TypeError(
            f"cannot combine a {type(a).__name__} with a {type(b).__name__}: they belong to different families "
            f"({fa} and {fb}); convert one side first"
        )
    return fa


# --------------------------------------------------------------------------------------------------------------------
# One small adapter per family: iterate keys, test membership, add a key, make an empty result


class _RdflibGraph:
    def __init__(self, g: Any) -> None:
        self.g = g

    def keys(self) -> Iterator[Any]:
        return iter(self.g)  # (s, p, o) triples

    def has(self, key: Any) -> bool:
        return key in self.g

    @staticmethod
    def add(target: Any, keys: Iterable[Any]) -> None:
        for k in keys:
            target.add(k)

    @staticmethod
    def empty_like(a: Any) -> Any:
        make = getattr(a, "empty_like", None)
        return make() if make is not None else type(a)()


class _RdflibDataset:
    def __init__(self, d: Any) -> None:
        self.d = d
        # Read the graphs without creating any: Dataset.graph(identifier) registers a new context.
        self.by_id = {g.identifier: g for g in d.graphs()}

    def keys(self) -> Iterator[Any]:
        for gid, graph in list(self.by_id.items()):
            for s, p, o in graph:
                yield (s, p, o, gid)

    def has(self, key: Any) -> bool:
        graph = self.by_id.get(key[3])
        return graph is not None and key[:3] in graph

    @staticmethod
    def add(target: Any, keys: Iterable[Any]) -> None:
        for s, p, o, gid in keys:
            target.graph(gid).add((s, p, o))

    @staticmethod
    def empty_like(a: Any) -> Any:
        make = getattr(a, "empty_like", None)
        return make() if make is not None else type(a)()


class _Ox:
    def __init__(self, s: Any) -> None:
        self.s = s

    def keys(self) -> Iterator[Any]:
        return iter(self.s)  # ox.Quad (Store.__iter__ and Dataset.__iter__ both yield quads)

    def has(self, key: Any) -> bool:
        return key in self.s

    @staticmethod
    def add(target: Any, keys: Iterable[Any]) -> None:
        if isinstance(target, ox.Store):
            target.bulk_extend(keys)
        else:
            for k in keys:
                target.add(k)

    @staticmethod
    def empty_like(a: Any) -> Any:
        return ox.Dataset() if isinstance(a, ox.Dataset) else ox.Store()


_ADAPTERS = {"rdflib-graph": _RdflibGraph, "rdflib-dataset": _RdflibDataset, "ox": _Ox}


def _bind_prefixes(result: Any, *sources: Any) -> None:
    """Carry the operands' prefix bindings onto an rdflib result, as ``Graph.__add__`` does."""
    rdflib = _rdflib()
    if rdflib is None or not isinstance(result, rdflib.Graph):
        return
    for src in sources:
        for prefix, namespace in src.namespaces():
            result.bind(prefix, namespace, override=False)


def _prepare(a: Any, b: Any, into: Any) -> tuple[Any, Any, Any, Any]:
    family = _same_family(a, b)
    if into is not None and _family(into) != family:
        raise TypeError(f"`into` is a {type(into).__name__}, not in the same family as the operands")
    adapter = _ADAPTERS[family]
    target = into if into is not None else adapter.empty_like(a)
    return adapter(a), adapter(b), target, adapter


def _wrapped(fn: Any) -> Any:
    """Let ``fn`` take ``StarLayerGraph`` / ``StarLayerDataset`` operands: run it on their stores and wrap the result the way the operators do."""

    @functools.wraps(fn)
    def run(a: Any, b: Any, *, into: Any = None) -> Any:
        from starlayer.graph.oxgraph.core import StarLayerDataset, StarLayerGraph

        wrappers = (StarLayerGraph, StarLayerDataset)
        if not any(isinstance(x, wrappers) for x in (a, b, into)):
            return fn(a, b, into=into)
        if type(a) is not type(b) or not isinstance(a, wrappers):
            raise TypeError(f"cannot combine a {type(a).__name__} with a {type(b).__name__}: pass two StarLayerGraph or two StarLayerDataset operands")
        if into is not None and type(into) is not type(a):
            raise TypeError(f"`into` is a {type(into).__name__}, not a {type(a).__name__}")

        def as_ox(x: Any) -> Any:
            if isinstance(x, StarLayerDataset):
                return x.store
            store = ox.Store()
            store.extend(ox.Quad(*t, ox.DefaultGraph()) for t in x.triples())
            return store

        result = fn(as_ox(a), as_ox(b))
        if into is not None:
            into.extend(result if isinstance(into, StarLayerDataset) else (q.triple for q in result))
            return into
        if isinstance(a, StarLayerDataset):
            wrapped: Any = StarLayerDataset(store=result, default_union=a._union)
        else:
            wrapped = StarLayerGraph(store=result)
        wrapped.prefixes.update({**b.prefixes, **a.prefixes})
        return wrapped

    return run


@_wrapped
def union(a: Any, b: Any, *, into: Any = None) -> Any:
    """Everything in ``a`` or ``b``. ``union(a, b, into=a)`` adds ``b`` to ``a`` in place."""
    ia, ib, target, adapter = _prepare(a, b, into)
    if into is not a:
        adapter.add(target, ia.keys())
    if into is not b:
        adapter.add(target, ib.keys())
    _bind_prefixes(target, a, b)
    return target


@_wrapped
def intersection(a: Any, b: Any, *, into: Any = None) -> Any:
    """What ``a`` and ``b`` both contain."""
    ia, ib, target, adapter = _prepare(a, b, into)
    adapter.add(target, [k for k in ia.keys() if ib.has(k)])
    _bind_prefixes(target, a, b)
    return target


@_wrapped
def difference(a: Any, b: Any, *, into: Any = None) -> Any:
    """What ``a`` contains and ``b`` does not."""
    ia, ib, target, adapter = _prepare(a, b, into)
    adapter.add(target, [k for k in ia.keys() if not ib.has(k)])
    _bind_prefixes(target, a, b)
    return target


@_wrapped
def symmetric_difference(a: Any, b: Any, *, into: Any = None) -> Any:
    """What is in exactly one of ``a`` and ``b``."""
    ia, ib, target, adapter = _prepare(a, b, into)
    only_a = [k for k in ia.keys() if not ib.has(k)]
    only_b = [k for k in ib.keys() if not ia.has(k)]
    adapter.add(target, only_a)
    adapter.add(target, only_b)
    _bind_prefixes(target, a, b)
    return target
