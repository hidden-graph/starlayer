"""Can the shapes tell a broken ``manch:`` tree from a good one?

Passing every valid tree (test_mc_tree.py) only shows the shapes are not too strict. This file checks they
are not too lax: take valid trees, damage them in ways a hand- or LLM-authored tree could be damaged, and
require ``manchester_validate`` to reject them.

The first run of a full mutation scan (``tools/mutation_scan.py``: 430 mutants, one per distinct
(node class, property, operator) in the corpus) found 10 trees that PASSED validation yet crash the
decoder, and a list shape that accepted unterminated and cyclic lists. Both are fixed; these tests keep
them fixed. The cause of the first: validation runs with RDFS inference, several ``manch:`` properties
declare an ``rdfs:domain``, so a deleted ``rdf:type`` was inferred straight back and every shape was
satisfied - the decoder, reading asserted types, was not. ``manchester_validate`` now has a pre-flight
check on the asserted graph.
"""

from __future__ import annotations

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF
from starlayer.starontology.manchester import (
    MANCH,
    _concrete_classes,
    _preflight,
    manchester_parse_to_tree,
    manchester_tree_to_text,
    manchester_validate,
)

from .corpus import CASES

# A document that contains the list-bearing constructs: prefixes, imports, an enumeration, a datatype
# restriction with facets, a data enumeration, clauses and a Misc axiom.
RICH = """\
Prefix: : <http://example.org/o#>
Prefix: xsd: <http://www.w3.org/2001/XMLSchema#>
Ontology: <http://example.org/o>
Import: <http://example.org/imported>
Class: A
  SubClassOf: p some {i, j}
  SubClassOf: d some xsd:integer[>= 1, < 9]
  SubClassOf: d some {1, 2}
  SubClassOf: B and C
EquivalentClasses: A, B
"""


def _tree(text: str = RICH) -> Graph:
    g = Graph()
    for t in manchester_parse_to_tree(text):
        g.add(t)
    return g


def _head_of(g: Graph, predicate: URIRef):
    return next(o for _, p, o in g if p == predicate)


def _cells(g: Graph, head):
    cells = []
    while head != RDF.nil:
        cells.append(head)
        head = g.value(head, RDF.rest)
    return cells


def test_the_unmutated_tree_conforms():
    assert manchester_validate(_tree())[0]


# --- types: a node must be ASSERTED with a concrete class (pre-flight, no SHACL needed) -----------------

def _trees_of_the_corpus():
    for case in CASES:
        try:
            yield case.id, _tree(case.text)
        except Exception:  # noqa: BLE001 - a case the parser rejects has no tree
            continue


@pytest.mark.manchester_conformance
def test_dropping_the_type_of_any_node_class_is_caught():
    """For every concrete class that occurs anywhere in the corpus, delete the rdf:type of one such node:
    the pre-flight must flag it (and it did not, before: inference supplied the type back)."""
    concrete = _concrete_classes()
    seen: set = set()
    missed: list = []
    for case_id, g in _trees_of_the_corpus():
        for node, _, cls in list(g.triples((None, RDF.type, None))):
            if cls not in concrete or cls in seen:
                continue
            seen.add(cls)
            mutant = Graph()
            for t in g:
                mutant.add(t)
            mutant.remove((node, RDF.type, cls))
            # Only a node that still has a manch: property is a meaningful mutant.
            if not any(str(p).startswith(str(MANCH)) for _, p, _ in mutant.triples((node, None, None))):
                continue
            if not _preflight(mutant):
                missed.append((case_id, str(cls).rsplit("#", 1)[-1]))
    assert len(seen) > 40, "the corpus should exercise most concrete classes"
    assert not missed, f"type removal not caught for: {missed}"


def test_a_tree_with_no_document_is_rejected():
    g = _tree()
    (doc,) = list(g.subjects(RDF.type, MANCH.Document))
    g.remove((doc, RDF.type, MANCH.Document))
    assert not manchester_validate(g)[0]


def test_two_documents_are_rejected():
    g = _tree()
    g.add((BNode(), RDF.type, MANCH.Document))
    assert not manchester_validate(g)[0]


def test_an_unknown_manch_type_is_rejected():
    g = _tree()
    frame = next(g.subjects(RDF.type, MANCH.ClassFrame))
    g.add((frame, RDF.type, MANCH.NotAClass))
    ok, _, text = manchester_validate(g)
    assert not ok and "not a class" in text


def test_the_report_graph_carries_the_preflight_findings():
    from rdflib.namespace import Namespace

    sh = Namespace("http://www.w3.org/ns/shacl#")
    g = _tree()
    frame = next(g.subjects(RDF.type, MANCH.ClassFrame))
    g.remove((frame, RDF.type, MANCH.ClassFrame))
    ok, report, _ = manchester_validate(g)
    assert not ok
    assert any(True for _ in report.subjects(RDF.type, sh.ValidationResult))
    assert (None, sh.conforms, Literal(False)) in report


# --- lists: well-formed means terminated and acyclic, and the items have the right kind -----------------

LIST_PREDICATES = [MANCH.frames, MANCH.prefixes, MANCH.imports, MANCH.individuals, MANCH.facets,
                   MANCH.literals, MANCH.operands, MANCH.items, MANCH.clauses]


@pytest.mark.parametrize("predicate", LIST_PREDICATES, ids=lambda p: str(p).rsplit("#", 1)[-1])
def test_an_unterminated_list_is_rejected(predicate):
    g = _tree()
    last = _cells(g, _head_of(g, predicate))[-1]
    g.remove((last, RDF.rest, RDF.nil))
    assert not manchester_validate(g)[0]


@pytest.mark.parametrize("predicate", LIST_PREDICATES, ids=lambda p: str(p).rsplit("#", 1)[-1])
def test_a_cyclic_list_is_rejected(predicate):
    g = _tree()
    head = _head_of(g, predicate)
    last = _cells(g, head)[-1]
    g.remove((last, RDF.rest, RDF.nil))
    g.add((last, RDF.rest, head))
    assert not manchester_validate(g)[0]


@pytest.mark.parametrize(
    ("predicate", "bad_item"),
    [
        (MANCH.prefixes, Literal("not a PrefixDecl")),
        (MANCH.imports, Literal("not an IRI")),
        (MANCH.individuals, Literal("not an IRI")),
        (MANCH.literals, URIRef("urn:not-a-literal")),
        (MANCH.facets, Literal("not a FacetRestriction")),
    ],
    ids=["prefixes", "imports", "individuals", "literals", "facets"],
)
def test_a_list_item_of_the_wrong_kind_is_rejected(predicate, bad_item):
    g = _tree()
    first = _cells(g, _head_of(g, predicate))[0]
    g.remove((first, RDF.first, None))
    g.add((first, RDF.first, bad_item))
    assert not manchester_validate(g)[0]


# --- the property that matters: whatever validates must decode ------------------------------------------

def test_every_single_triple_removal_that_validates_still_decodes():
    """Remove each triple of the rich tree in turn. A mutant may legitimately validate (optional things
    removed: annotations, an unqualified cardinality's filler) but must then decode. Validating and then
    crashing the decoder is the hole this file exists to close."""
    base = _tree()
    holes = []
    for t in sorted(base, key=str):
        if not (t[1] == RDF.type or str(t[1]).startswith(str(MANCH)) or t[1] in (RDF.first, RDF.rest)):
            continue
        mutant = Graph()
        for u in base:
            mutant.add(u)
        mutant.remove(t)
        if not manchester_validate(mutant)[0]:
            continue
        try:
            manchester_tree_to_text(mutant)
        except Exception as error:  # noqa: BLE001
            holes.append((t, type(error).__name__))
    assert not holes, f"{len(holes)} mutants validate but cannot be decoded, e.g. {holes[:3]}"
