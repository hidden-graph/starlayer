"""Helpers shared by the parse_sparql tests: corpus collection and the tree comparison."""

from __future__ import annotations

from rdflib import BNode, Graph, URIRef
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


_RUN = URIRef("urn:test:run")
_MEMBER = URIRef("urn:test:member")


def canonical_graph(g: Graph) -> Graph:
    """Copy of ``g`` in which each run of adjacent triple patterns in a list becomes one unordered set.

    The current path orders the patterns of a block with rdflib's selectivity heuristic (``reorderTriples``),
    breaking ties on random blank-node ids; the new parser keeps the order written. Only that order differs,
    so each run is replaced by a node with one ``urn:test:member`` edge per pattern (graph isomorphism then
    treats the run as a set but still follows the blank nodes the patterns share).
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
            if run:
                node = BNode()
                out.add((node, RDF.type, _RUN))
                for member in run:
                    out.add((node, _MEMBER, member))
                new.append(node)
                run = []
            if item is not None:
                new.append(item)
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


# ---------------------------------------------------------------------------
# The vendored W3C SPARQL 1.1 suite (tests/sparql/w3c_sparql11/data)
# ---------------------------------------------------------------------------

import csv  # noqa: E402
import os  # noqa: E402
from dataclasses import dataclass  # noqa: E402

DATA_DIR_11 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "w3c_sparql11", "data")


@dataclass
class Entry11:
    category: str
    test_type: str
    name: str
    query_file: str
    update_file: str
    data_file: str
    result_file: str
    test_iri: str

    @property
    def file(self) -> str:
        return self.query_file or self.update_file

    def read(self, filename: str | None = None) -> str:
        with open(os.path.join(DATA_DIR_11, self.category, filename or self.file), encoding="utf-8") as f:
            return f.read()

    @property
    def key(self) -> str:
        return "11/" + self.category + "/" + self.test_iri.rsplit("#", 1)[-1]


def w3c11_entries(*types: str, ext: str | None = None) -> list[Entry11]:
    """The 1.1 index entries of the given types whose request file has the extension ``ext`` (``.rq``/``.ru``)."""
    index = os.path.join(DATA_DIR_11, "index.tsv")
    if not os.path.exists(index):
        return []
    with open(index, encoding="utf-8", newline="") as f:
        rows = [Entry11(**r) for r in csv.DictReader(f, delimiter="\t")]
    return [e for e in rows if e.test_type in types and (ext is None or e.file.endswith(ext))]
