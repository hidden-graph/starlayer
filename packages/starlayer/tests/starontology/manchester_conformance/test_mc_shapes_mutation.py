"""Can the shapes tell a broken ``manch:`` tree from a good one?

Passing every valid tree (test_mc_tree.py) only shows the shapes are not too strict. This file checks they
are not too lax: take valid trees, damage them in ways a hand- or LLM-authored tree could be damaged, and
require ``manchester_validate`` to reject them.

The first run of a full mutation scan (``tools/mutation_scan.py``: 430 mutants, one per distinct
(node class, property, operator) in the corpus) found 10 trees that PASSED validation yet crash the
decoder, and a list shape that accepted unterminated and cyclic lists. Both were fixed; since the ordered children became
``tree:ord`` ordinals (no ``rdf:List``) the list tests are the ordinal ones below: a missing, tied or non-integer ordinal,
an item of the wrong kind, a blank child under two parents. These tests keep it fixed. The cause of the first: validation runs with RDFS inference, several ``manch:`` properties
declare an ``rdfs:domain``, so a deleted ``rdf:type`` was inferred straight back and every shape was
satisfied - the decoder, reading asserted types, was not. ``manchester_validate`` now has a pre-flight
check on the asserted graph.
"""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph as Graph
from starlayer.graph import ordinals
from starlayer.graph.manchester._ox_terms import RDF, BNode, URIRef, Vocab
from starlayer.graph.manchester._ox_terms import lexical as Literal
from starlayer.starontology.manchester import (
    MANCH,
    _concrete_classes,
    _preflight,
    manchester_parse_to_tree,
    manchester_tree_to_text,
    manchester_validate,
)

from .corpus import CASES

# A document that contains the ordered-children constructs: prefixes, imports, an enumeration, a datatype
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
    g.extend(list(manchester_parse_to_tree(text)))
    return g


def test_the_unmutated_tree_conforms():
    assert manchester_validate(_tree()).conforms


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
            mutant.extend(list(g))
            mutant.remove((node, RDF.type, cls))
            # Only a node that still has a manch: property is a meaningful mutant.
            if not any(p in MANCH for _, p, _ in mutant.triples((node, None, None))):
                continue
            if not _preflight(mutant):
                missed.append((case_id, cls.value.rsplit("#", 1)[-1]))
    assert len(seen) > 40, "the corpus should exercise most concrete classes"
    assert not missed, f"type removal not caught for: {missed}"


def test_a_tree_with_no_document_is_rejected():
    g = _tree()
    (doc,) = list(g.subjects(RDF.type, MANCH.OntologyDocument))
    g.remove((doc, RDF.type, MANCH.OntologyDocument))
    assert not manchester_validate(g).conforms


def test_two_documents_are_rejected():
    g = _tree()
    g.add((BNode(), RDF.type, MANCH.OntologyDocument))
    assert not manchester_validate(g).conforms


def test_an_unknown_manch_type_is_rejected():
    g = _tree()
    frame = next(g.subjects(RDF.type, MANCH.ClassFrame))
    g.add((frame, RDF.type, MANCH.NotAClass))
    outcome = manchester_validate(g)
    ok = outcome.conforms
    text = outcome.report_text
    assert not ok and "not a class" in text


def test_the_report_graph_carries_the_preflight_findings():
    sh = Vocab("http://www.w3.org/ns/shacl#")
    g = _tree()
    frame = next(g.subjects(RDF.type, MANCH.ClassFrame))
    g.remove((frame, RDF.type, MANCH.ClassFrame))
    outcome = manchester_validate(g)
    ok = outcome.conforms
    report = outcome.report_graph
    assert not ok
    assert any(True for _ in report.subjects(RDF.type, sh.ValidationResult))
    assert (None, sh.conforms, Literal(False)) in report


# --- ordered children: every child has exactly one ordinal, no two share one, the items have the right kind -----------

ORDERED = """\
Prefix: : <http://example.org/o#>
Prefix: xsd: <http://www.w3.org/2001/XMLSchema#>
Ontology: <http://example.org/o>
Import: <http://example.org/imported>
Import: <http://example.org/imported2>
Class: A
  SubClassOf: p some {i, j}
  SubClassOf: d some xsd:integer[>= 1, < 9]
  SubClassOf: d some {1, 2}
  SubClassOf: B and C, D
Class: E
EquivalentClasses: A, B
"""

ORDERED_PREDICATES = [MANCH.frames, MANCH.prefixes, MANCH.imports, MANCH.individuals, MANCH.facets,
                      MANCH.literals, MANCH.operands, MANCH.items, MANCH.clauses]


def _children(g: Graph, predicate: URIRef):
    """``(parent, [child nodes])`` of the first parent that holds at least two children for ``predicate``."""
    from collections import defaultdict

    by_parent = defaultdict(list)
    for s_, _, o in g.triples((None, predicate, None)):
        by_parent[s_].append(o)
    return next((parent, kids) for parent, kids in by_parent.items() if len(kids) >= 2)


def test_the_ordered_tree_conforms():
    assert manchester_validate(_tree(ORDERED)).conforms


@pytest.mark.parametrize("predicate", ORDERED_PREDICATES, ids=lambda p: p.value.rsplit("#", 1)[-1])
def test_a_child_without_an_ordinal_is_rejected(predicate):
    g = _tree(ORDERED)
    _parent, kids = _children(g, predicate)
    g.remove((kids[0], ordinals.ORD, None))
    assert not manchester_validate(g).conforms


@pytest.mark.parametrize("predicate", ORDERED_PREDICATES, ids=lambda p: p.value.rsplit("#", 1)[-1])
def test_two_children_with_the_same_ordinal_are_rejected(predicate):
    g = _tree(ORDERED)
    _parent, kids = _children(g, predicate)
    number = next(g.objects(kids[0], ordinals.ORD))
    g.remove((kids[1], ordinals.ORD, None))
    g.add((kids[1], ordinals.ORD, number))
    assert not manchester_validate(g).conforms


@pytest.mark.parametrize("predicate", ORDERED_PREDICATES, ids=lambda p: p.value.rsplit("#", 1)[-1])
def test_an_ordinal_that_is_not_an_integer_is_rejected(predicate):
    g = _tree(ORDERED)
    _parent, kids = _children(g, predicate)
    g.remove((kids[0], ordinals.ORD, None))
    g.add((kids[0], ordinals.ORD, Literal("first")))
    assert not manchester_validate(g).conforms


@pytest.mark.parametrize(
    ("predicate", "bad_item"),
    [
        (MANCH.imports, Literal("not an IRI")),
        (MANCH.individuals, Literal("not an IRI")),
        (MANCH.literals, URIRef("urn:not-a-literal")),
    ],
    ids=["imports", "individuals", "literals"],
)
def test_an_item_value_of_the_wrong_kind_is_rejected(predicate, bad_item):
    g = _tree(ORDERED)
    _parent, kids = _children(g, predicate)
    g.remove((kids[0], ordinals.VALUE, None))
    g.add((kids[0], ordinals.VALUE, bad_item))
    assert not manchester_validate(g).conforms


@pytest.mark.parametrize("predicate", [MANCH.prefixes, MANCH.facets, MANCH.frames, MANCH.clauses],
                         ids=lambda p: p.value.rsplit("#", 1)[-1])
def test_a_child_of_the_wrong_class_is_rejected(predicate):
    g = _tree(ORDERED)
    _parent, kids = _children(g, predicate)
    (old,) = [o for o in g.objects(kids[0], RDF.type) if o in MANCH]
    g.remove((kids[0], RDF.type, old))
    g.add((kids[0], RDF.type, MANCH.OntologyDocument if old != MANCH.OntologyDocument else MANCH.Frame))
    assert not manchester_validate(g).conforms


def test_a_blank_child_under_two_parents_is_rejected():
    """A clause carries its ordinal itself, so it can have one frame only; a second frame holding it makes its position ambiguous."""
    g = _tree(ORDERED)
    (clause_owner,) = {s_ for s_, _, _ in g.triples((None, MANCH.clauses, None))}
    clause = next(o for _, _, o in g.triples((clause_owner, MANCH.clauses, None)))
    other = next(f for f in g.subjects(RDF.type, MANCH.ClassFrame) if f != clause_owner)
    g.add((other, MANCH.clauses, clause))
    assert not manchester_validate(g).conforms


def test_a_node_with_a_value_but_no_item_type_is_caught_before_inference():
    """tree:value has the domain tree:Item, so RDFS inference would give the type back and hide the fault from every shape."""
    g = _tree(ORDERED)
    item = next(g.subjects(ordinals.VALUE, None))
    g.remove((item, RDF.type, ordinals.ITEM))
    assert any("tree:Item" in message for _node, message in _preflight(g))
    assert not manchester_validate(g).conforms


# --- the property that matters: whatever validates must decode ------------------------------------------

def test_every_single_triple_removal_that_validates_still_decodes():
    """Remove each triple of the rich tree in turn. A mutant may legitimately validate (optional things
    removed: annotations, an unqualified cardinality's filler) but must then decode. Validating and then
    crashing the decoder is the hole this file exists to close."""
    base = _tree()
    holes = []
    for t in sorted(base, key=str):
        if not (t[1] == RDF.type or t[1] in MANCH or t[1] in (ordinals.ORD, ordinals.VALUE)):
            continue
        mutant = Graph()
        mutant.extend(list(base))
        mutant.remove(t)
        if not manchester_validate(mutant).conforms:
            continue
        try:
            manchester_tree_to_text(mutant)
        except Exception as error:  # noqa: BLE001
            holes.append((t, type(error).__name__))
    assert not holes, f"{len(holes)} mutants validate but cannot be decoded, e.g. {holes[:3]}"
