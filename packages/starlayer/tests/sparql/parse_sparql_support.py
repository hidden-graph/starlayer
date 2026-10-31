"""Helpers shared by the parse_sparql tests: corpus collection and the tree comparison."""

from __future__ import annotations

from rdflib import BNode, Graph
from rdflib.collection import Collection
from rdflib.compare import isomorphic
from rdflib.namespace import RDF
from starlayer.graph.model.dirlangstring import DirLangString, encode_dirlangstring
from starlayer.graph.query.version_directive import strip_version_directive
from starlayer.sparql.sqe import sqe_parse_to_tree
from starlayer.sparql.sqe.vocab import TRIPLE_PATTERN

from tests.sparql.w3c_sparql12.harness import load_index


def w3c_entries(*types: str):
    return [e for e in load_index() if e.test_type in types]


def entry_key(entry) -> str:
    return entry.category + "/" + entry.test_iri.rsplit("#", 1)[-1]


def _sig(node, g: Graph) -> str:
    """A label-free signature of a term or sub-tree (blank nodes without properties are all '_')."""
    if not isinstance(node, BNode):
        return node.n3()
    props = sorted((str(p), _sig(o, g)) for p, o in g.predicate_objects(node))
    return "_" if not props else "{" + ",".join(f"{p}={o}" for p, o in props) + "}"


def canonical_graph(g: Graph) -> Graph:
    """Copy of ``g`` with each run of adjacent triple patterns in any list sorted by signature.

    The current path orders patterns with rdflib's selectivity heuristic (``reorderTriples``), which also
    breaks ties on random blank-node ids; the new parser keeps the order written. Only that order differs.
    """
    out = Graph()
    for t in g:
        out.add(tuple(encode_dirlangstring(x) if isinstance(x, DirLangString) else x for x in t))
    heads = [s for s in set(g.subjects(RDF.first, None)) if not list(g.subjects(RDF.rest, s))]
    for head in heads:
        items = list(Collection(g, head))
        if not any((i, RDF.type, TRIPLE_PATTERN) in g for i in items):
            continue
        new, run = [], []
        for item in items + [None]:
            if item is not None and (item, RDF.type, TRIPLE_PATTERN) in g:
                run.append(item)
                continue
            new += sorted(run, key=lambda n: _sig(n, g))
            run = []
            if item is not None:
                new.append(item)
        if new != items:
            node = head
            while node != RDF.nil:  # unlink the old chain, then lay the new one on the same head
                nxt = out.value(node, RDF.rest)
                out.remove((node, None, None))
                node = nxt
            Collection(out, head, new)
    return out


def same_tree(new: tuple, old: tuple) -> bool:
    return isomorphic(canonical_graph(new[0]), canonical_graph(old[0]))


def current_tree(text: str):
    text, _ = strip_version_directive(text)
    return sqe_parse_to_tree(text)
