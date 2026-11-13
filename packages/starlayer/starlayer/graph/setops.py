"""Set operations on graphs and datasets: ``union``, ``intersection``, ``difference``, ``symmetric_difference``.

Oxigraph's ``Store`` and ``Dataset`` have no set operators, so StarLayer provides them as functions, and wires them to the operators
``+``, ``-``, ``&`` and ``^`` of the Oxigraph-backed ``StarLayerGraph`` and ``StarLayerDataset``.

The operands are ``pyoxigraph.Store`` / ``pyoxigraph.Dataset`` objects, or two ``StarLayerGraph`` / two ``StarLayerDataset`` objects (combined as
their stores, giving a ``StarLayerGraph`` / ``StarLayerDataset`` back, so the functions and the operators agree). An rdflib graph is a
``TypeError``: convert it with ``StarLayerGraph.from_rdflib`` first.

Semantics:

* A graph is a set of triples and a dataset a set of quads. Terms are compared exactly as the library compares them: triple terms by
  structure, literals by lexical form and datatype (a pyoxigraph *store* has already rewritten some lexical forms on insert; see issue
  #190).
* **Blank nodes are compared by label**, not by isomorphism. Two graphs that differ only in blank-node labels have an empty
  intersection and a full difference. Use ``starlayer.graph.compare`` or RDFC canonicalisation
  first when isomorphism is meant.
* Quads are compared with their graph name. The default graph is one graph like any other (``DefaultGraph``).
* Inputs are never modified. The result is a new object of the first operand's type, or ``into`` when given. ``into`` receives the
  result by *addition* and nothing is removed from it, so ``union(a, b, into=a)`` adds ``b`` to ``a`` in place, while
  ``difference(a, b, into=a)`` leaves ``a`` unchanged (it adds triples already there); to shrink a graph, build the difference
  and replace it.

Cost: ``difference`` and ``intersection`` stream the first operand and test membership in the second (no set is materialised);
``union`` copies one side then adds the other; ``symmetric_difference`` makes two passes.
"""

from __future__ import annotations

import functools
from collections.abc import Iterable, Iterator
from typing import Any

import pyoxigraph as ox

__all__ = ["difference", "intersection", "symmetric_difference", "union"]


def _check(x: Any) -> None:
    if not isinstance(x, (ox.Store, ox.Dataset)):
        raise TypeError(
            f"set operations take a pyoxigraph Store/Dataset or two StarLayerGraph / StarLayerDataset operands, not {type(x).__name__}"
            + (" (an OxigraphGraph view: pass its .store)" if type(x).__name__ == "OxigraphGraph" else "")
            + (" (an rdflib graph: convert it with StarLayerGraph.from_rdflib)" if type(x).__module__.startswith("rdflib") else "")
        )


# --------------------------------------------------------------------------------------------------------------------
# The adapter: iterate keys, test membership, add a key, make an empty result


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


def _prepare(a: Any, b: Any, into: Any) -> tuple[Any, Any, Any, Any]:
    for operand in (a, b, into):
        if operand is not None:
            _check(operand)
    target = into if into is not None else _Ox.empty_like(a)
    return _Ox(a), _Ox(b), target, _Ox


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
    return target


@_wrapped
def intersection(a: Any, b: Any, *, into: Any = None) -> Any:
    """What ``a`` and ``b`` both contain."""
    ia, ib, target, adapter = _prepare(a, b, into)
    adapter.add(target, [k for k in ia.keys() if ib.has(k)])
    return target


@_wrapped
def difference(a: Any, b: Any, *, into: Any = None) -> Any:
    """What ``a`` contains and ``b`` does not."""
    ia, ib, target, adapter = _prepare(a, b, into)
    adapter.add(target, [k for k in ia.keys() if not ib.has(k)])
    return target


@_wrapped
def symmetric_difference(a: Any, b: Any, *, into: Any = None) -> Any:
    """What is in exactly one of ``a`` and ``b``."""
    ia, ib, target, adapter = _prepare(a, b, into)
    only_a = [k for k in ia.keys() if not ib.has(k)]
    only_b = [k for k in ib.keys() if not ia.has(k)]
    adapter.add(target, only_a)
    adapter.add(target, only_b)
    return target
