"""RDF 1.2 reifier helpers over ``rdf:reifies``, as thin functions on a wrapper (``OxGraph`` / ``OxDataset``) or a bare
``pyoxigraph.Store`` (treated as a union dataset). Same contract as the methods of the old ``StarLayerGraph``
(``graph/graph/starlayer_graph.py``: ``add_reification``, ``reifiers``, ``reifications``, ``reifier_annotations``,
``reified_triples``), with pyoxigraph terms: a triple term is a ``pyoxigraph.Triple``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pyoxigraph as ox

from starlayer.graph.oxgraph import terms
from starlayer.graph.oxgraph.terms import RDF_REIFIES


def _view(g: Any) -> Any:
    if isinstance(g, ox.Store):
        from starlayer.graph.oxgraph.core import OxDataset

        return OxDataset(g)
    return g


def _tt(x: Any) -> ox.Triple:
    t = terms.term(x)
    if not isinstance(t, ox.Triple):
        raise TypeError("a triple term (pyoxigraph.Triple or an (s, p, o) tuple) is needed")
    return t


def add_reification(graph: Any, reifier: Any, triple_term: Any) -> Any:
    """Add ``reifier rdf:reifies triple_term``; returns ``graph`` so calls chain."""
    _view(graph).add((terms.term(reifier), RDF_REIFIES, _tt(triple_term)))
    return graph


def reifiers(graph: Any, TT: Any = None, predicate: Any = None, object: Any = None) -> Iterator[Any]:  # noqa: N803, A002
    """Distinct reifier nodes; the filters combine: reify ``TT`` AND have ``(reifier, predicate, object)`` in the graph."""
    g = _view(graph)
    seen: set = set()
    for r, _p, _o in g.triples((None, RDF_REIFIES, _tt(TT) if TT is not None else None)):
        if r in seen:
            continue
        seen.add(r)
        if (predicate is None and object is None) or next(g.triples((r, predicate, object)), None) is not None:
            yield r


def reifications(graph: Any, s: Any = None, p: Any = None, o: Any = None) -> Iterator[ox.Triple]:
    """Distinct triple terms that have at least one reifier and match the pattern."""
    g = _view(graph)
    s, p, o = terms.term(s), terms.term(p), terms.term(o)
    seen: set = set()
    for _r, _p, tt in g.triples((None, RDF_REIFIES, None)):
        if not isinstance(tt, ox.Triple) or tt in seen:
            continue
        if (s is not None and tt.subject != s) or (p is not None and tt.predicate != p) or (o is not None and tt.object != o):
            continue
        seen.add(tt)
        yield tt


def reifier_annotations(graph: Any, TT: Any) -> Iterator[tuple[Any, Any, Any]]:  # noqa: N803
    """``(reifier, predicate, value)`` for every reifier of ``TT``, without the ``rdf:reifies`` triple itself."""
    g = _view(graph)
    for r in list(reifiers(g, TT)):
        for _s, pred, val in g.triples((r, None, None)):
            if pred != RDF_REIFIES:
                yield r, pred, val


def reified_triples(graph: Any, reifier: Any) -> Iterator[ox.Triple]:
    """The triple terms reified by ``reifier``."""
    for _s, _p, o in _view(graph).triples((terms.term(reifier), RDF_REIFIES, None)):
        if isinstance(o, ox.Triple):
            yield o
