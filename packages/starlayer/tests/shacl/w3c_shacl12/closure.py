"""Extract a self-contained subgraph reachable from a given RDF node.

A W3C suite test file packs the data graph, shapes graph, manifest metadata,
and the expected result all into one document sharing one graph. Pulling out
"just the expected sh:ValidationReport" (rooted at the entry's mf:result
blank node) needs a closure walk, since it isn't a separately-parseable
document of its own.
"""

from __future__ import annotations

import pyoxigraph as ox
from tests.lexical_graph import LexicalGraph


def node_closure(graph, root) -> LexicalGraph:
    """Return a new graph of every triple reachable from root via blank-node objects (a triple term holds its own parts)."""
    out = LexicalGraph()
    seen: set = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        for predicate, obj in graph.predicate_objects(node):
            out.add((node, predicate, obj))
            if isinstance(obj, ox.BlankNode) and obj not in seen:
                stack.append(obj)
    return out
