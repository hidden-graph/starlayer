"""RDF 1.2 reifier helpers over ``rdf:reifies``, as thin functions on a wrapper (``StarLayerGraph`` / ``StarLayerDataset``) or a bare
``pyoxigraph.Store`` (treated as a union dataset). Same contract as the methods of the old ``StarLayerGraph``
(``graph/entailment/starlayer_graph.py``: ``add_reification``, ``reifiers``, ``reified_triples``, ``annotations``), with pyoxigraph terms:
a triple term is a ``pyoxigraph.Triple``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pyoxigraph as ox

from starlayer.graph import terms
from starlayer.graph.terms import RDF_REIFIES


def _view(g: Any) -> Any:
    if isinstance(g, ox.Store):
        from starlayer.graph.core import StarLayerDataset

        return StarLayerDataset(g)
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


def reifiers(graph: Any, tt: Any = None, predicate: Any = None, object: Any = None) -> Iterator[Any]:  # noqa: A002
    """Distinct reifier nodes: every reifier, or with ``tt`` those of that triple term. ``predicate`` and ``object`` narrow it to reifiers
    that also have ``(reifier, predicate, object)`` in the graph."""
    g = _view(graph)
    seen: set = set()
    for r, _p, _o in g.triples((None, RDF_REIFIES, _tt(tt) if tt is not None else None)):
        if r in seen:
            continue
        seen.add(r)
        if (predicate is None and object is None) or next(g.triples((r, predicate, object)), None) is not None:
            yield r


def reified_triples(graph: Any, reifier: Any = None) -> Iterator[ox.Triple]:
    """The triple terms reified by ``reifier``, or with no reifier every triple term that has at least one reifier (each once)."""
    g = _view(graph)
    if reifier is not None:
        for _s, _p, o in g.triples((terms.term(reifier), RDF_REIFIES, None)):
            if isinstance(o, ox.Triple):
                yield o
        return
    seen: set = set()
    for _r, _p, o in g.triples((None, RDF_REIFIES, None)):
        if isinstance(o, ox.Triple) and o not in seen:
            seen.add(o)
            yield o


def annotations(graph: Any, tt: Any = None) -> Iterator[tuple[Any, Any, Any]]:
    """``(reifier, predicate, value)`` for every reifier of ``tt`` (or of any triple term, with no ``tt``), without the ``rdf:reifies``
    triple itself: what an annotation block ``{| ... |}`` writes."""
    g = _view(graph)
    for r in list(reifiers(g, tt)):
        for _s, pred, val in g.triples((r, None, None)):
            if pred != RDF_REIFIES:
                yield r, pred, val


def remove_reification(graph: Any, reifier: Any, triple_term: Any = None) -> Any:
    """Remove ``reifier rdf:reifies triple_term`` (every ``rdf:reifies`` link of the reifier when ``triple_term`` is None);
    its annotation triples and its other links stay. Returns ``graph``."""
    _view(graph).remove((terms.term(reifier), RDF_REIFIES, _tt(triple_term) if triple_term is not None else None))
    return graph


def triple_terms(graph: Any, subject: Any = None, predicate: Any = None, object: Any = None) -> Iterator[ox.Triple]:  # noqa: A002
    """Distinct triple terms that occur as the object of a triple in ``graph`` (reified or not) and match the pattern."""
    g = _view(graph)
    s, p, o = terms.term(subject), terms.term(predicate), terms.term(object)
    seen: set = set()
    for _s, _p, tt in g.triples((None, None, None)):
        if not isinstance(tt, ox.Triple) or tt in seen:
            continue
        if (s is not None and tt.subject != s) or (p is not None and tt.predicate != p) or (o is not None and tt.object != o):
            continue
        seen.add(tt)
        yield tt
