"""Graph comparison utilities — thin re-exports from rdflib.compare."""

from rdflib.compare import graph_diff, isomorphic

__all__ = ["isomorphic", "graph_diff"]
