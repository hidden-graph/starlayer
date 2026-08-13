"""Extract a self-contained subgraph reachable from a given RDF node.

A W3C suite test file packs the data graph, shapes graph, manifest metadata,
and the expected result all into one document sharing one graph. Pulling out
"just the expected sh:ValidationReport" (rooted at the entry's mf:result
blank node) needs a closure walk, since it isn't a separately-parseable
document of its own.
"""

from __future__ import annotations

from rdflib import BNode, Graph
from rdflib.term import Node


def node_closure(graph: Graph, root: Node) -> Graph:
    """Return a new Graph of every triple reachable from root via blank-node objects."""
    out = Graph()
    seen: set[Node] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        for predicate, obj in graph.predicate_objects(node):
            out.add((node, predicate, obj))
            if isinstance(obj, BNode) and obj not in seen:
                stack.append(obj)
    return out
