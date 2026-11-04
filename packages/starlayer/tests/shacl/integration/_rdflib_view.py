"""Read an engine result (an OxGraph of pyoxigraph terms) through rdflib terms, for tests that assert with rdflib vocabulary."""

from __future__ import annotations

from rdflib import Graph
from starlayer.shacl_engine.terms import from_engine


class RdflibView(Graph):
    """A plain ``rdflib.Graph`` that also holds StarLayer ``TripleTerm`` objects (rdflib's own ``add`` rejects them).

    Only for reading results in tests; nothing here is the StarLayer graph class."""

    def add(self, triple):  # noqa: D102
        self.store.add(triple, self)
        return self


def rd(graph):
    """``graph`` copied into an ``RdflibView`` in rdflib terms (blank node ids kept); a graph already in rdflib terms is returned as is."""
    if not getattr(graph, "engine_terms", False):
        return graph
    out = RdflibView()
    for prefix, namespace in getattr(graph, "prefixes", {}).items():
        out.bind(prefix, str(namespace), override=True)
    for s, p, o in graph.triples((None, None, None)):
        out.add((from_engine(s), from_engine(p), from_engine(o)))
    return out


def rdn(terms):
    """The pyoxigraph terms of an engine result (e.g. target_nodes) as rdflib terms, same container type."""
    converted = [from_engine(t) for t in terms]
    return set(converted) if isinstance(terms, (set, frozenset)) else converted
