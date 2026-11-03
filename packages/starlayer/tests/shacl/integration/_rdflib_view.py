"""Read an engine result (an OxGraph of pyoxigraph terms) through rdflib terms, for tests that assert with rdflib vocabulary."""

from __future__ import annotations

from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl_engine.terms import from_engine


def rd(graph):
    """A StarLayerGraph copy of ``graph`` in rdflib terms (blank node ids kept); a graph already in rdflib terms is returned as is."""
    if not getattr(graph, "engine_terms", False):
        return graph
    out = StarLayerGraph()
    for s, p, o in graph.triples((None, None, None)):
        out.add((from_engine(s), from_engine(p), from_engine(o)))
    return out


def rdn(terms):
    """The pyoxigraph terms of an engine result (e.g. target_nodes) as rdflib terms, same container type."""
    converted = [from_engine(t) for t in terms]
    return set(converted) if isinstance(terms, (set, frozenset)) else converted
