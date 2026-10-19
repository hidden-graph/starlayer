"""Shared helpers for the Manchester conformance suite."""

from __future__ import annotations

import json
from pathlib import Path

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF
from starlayer.graph.compare import isomorphic
from starlayer.graph.parsers.manchester_parser import parse_manchester

HERE = Path(__file__).parent
GOLDEN_DIR = HERE / "goldens" / "owlapi-5.1.20"

# The OWL 2 RDF mapping's list-valued constructs whose member order is semantically irrelevant.
# OWL API iterates a HashSet when it writes them, so its list order does not match written order
# (docs/graph/manchester_syntax_gap_analysis.md, last row). Compared as sets, not sequences.
UNORDERED_LIST_PREDICATES = (
    OWL.intersectionOf,
    OWL.unionOf,
    OWL.oneOf,
    OWL.members,
    OWL.distinctMembers,
    OWL.disjointUnionOf,
    OWL.withRestrictions,
    OWL.hasKey,
)
# Order *is* significant here: owl:propertyChainAxiom is left as a real rdf:List.


def to_graph(triples) -> Graph:
    g = Graph()
    for t in triples:
        g.add(t)
    return g


def parse_to_graph(text: str, base: str | None = None) -> Graph:
    return to_graph(parse_manchester(text, base=base))


def flatten_unordered_lists(graph: Graph) -> Graph:
    """Copy of ``graph`` with each unordered rdf:List replaced by one triple per member, so isomorphism
    ignores the (arbitrary) list order of unions, intersections, enumerations and member sets."""
    out = Graph()
    list_cells: set = set()
    for pred in UNORDERED_LIST_PREDICATES:
        for s, _, head in graph.triples((None, pred, None)):
            if head == RDF.nil:
                continue
            members = []
            cell = head
            # A malformed list (missing rdf:rest, or a cycle) must not hang the comparison: stop, and
            # let the resulting graph difference report it.
            while cell is not None and cell != RDF.nil and cell not in list_cells:
                list_cells.add(cell)
                first = graph.value(cell, RDF.first)
                if first is not None:
                    members.append(first)
                cell = graph.value(cell, RDF.rest)
            for m in members:
                out.add((s, pred, m))
    for s, p, o in graph:
        if s in list_cells:
            continue
        if p in UNORDERED_LIST_PREDICATES and o != RDF.nil:
            continue
        out.add((s, p, o))
    return out


HARNESS_ONTOLOGY = URIRef("http://example.org/o")


def normalise_oracle_noise(graph: Graph, *, other: Graph | None = None) -> Graph:
    """Remove differences that come from how the OWL API writes RDF, not from parsing:

    - ``owl:distinctMembers`` (OWL 1 name) is the same axiom as ``owl:members`` on ``owl:AllDifferent``.
    - Language tags are case-insensitive (BCP 47); the oracle lower-cases them.
    - The harness always creates an ontology named by its request IRI, so an ``owl:Ontology`` triple for
      it appears even when the document had no ``Ontology:`` IRI. Dropped unless ``other`` has it too.
    """
    out = Graph()
    for s, p, o in graph:
        if p == OWL.distinctMembers:
            p = OWL.members
        if isinstance(o, Literal) and o.language:
            o = Literal(str(o), lang=o.language.lower())
        out.add((s, p, o))
    if other is not None and (HARNESS_ONTOLOGY, RDF.type, OWL.Ontology) not in other:
        out.remove((HARNESS_ONTOLOGY, RDF.type, OWL.Ontology))
    return out


def same_owl(ours: Graph, oracle: Graph) -> bool:
    """OWL-level equality against the oracle: isomorphic, unordered lists compared as sets, oracle
    writing noise normalised away (see ``normalise_oracle_noise``)."""
    return isomorphic(
        flatten_unordered_lists(normalise_oracle_noise(ours)),
        flatten_unordered_lists(normalise_oracle_noise(oracle, other=ours)),
    )


def load_golden(case_id: str) -> dict | None:
    path = GOLDEN_DIR / f"{case_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def owlapi_graph_from_golden(golden: dict) -> Graph:
    """The oracle's Turtle as a graph.

    The harness sets the Turtle writer's default prefix to the ontology IRI (``http://example.org/o``),
    which has no trailing ``#`` although the corpus declares ``Prefix: : <http://example.org/o#>``; the
    writer's own ``###  http://example.org/o#p`` comments show it meant ``#``-terminated names. Without
    this repair every name would differ from ours by a missing ``#`` for a reason unrelated to parsing.
    """
    ttl = golden["turtle"].replace(
        "@prefix : <http://example.org/o> .", "@prefix : <http://example.org/o#> .", 1
    )
    g = Graph()
    g.parse(data=ttl, format="turtle")
    return g


__all__ = [
    "BNode", "URIRef", "GOLDEN_DIR", "flatten_unordered_lists", "load_golden",
    "owlapi_graph_from_golden", "parse_to_graph", "same_owl", "to_graph",
]
