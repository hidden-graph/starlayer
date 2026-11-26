"""The ``manch:`` tree writes its ordered children as ordinals (``tree:ord``, ``graph/ordinals.py``), not as ``rdf:List``: what that
changes for the decoder, ``manchester_validate``, editing through the helpers, and hashing."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.errors import FormatError
from starlayer.graph import StarLayerGraph, ordinals
from starlayer.graph.compare import isomorphic
from starlayer.graph.manchester._ox_terms import RDF, BNode, URIRef
from starlayer.graph.manchester.parser import parse_manchester
from starlayer.graph.rdfc import rdfc10_hash
from starlayer.starontology.manchester import (
    MANCH,
    manchester_parse_to_tree,
    manchester_tree_to_owl,
    manchester_tree_to_text,
    manchester_validate,
)

EX = "http://example.org/vehicles#"
HEADER = f"Prefix: : <{EX}>\n"
GUIDE = HEADER + """
Class: Vehicle
Class: Car
    SubClassOf: Vehicle

ObjectProperty: hasWheelCount
"""

TEXT = HEADER + """Prefix: xsd: <http://www.w3.org/2001/XMLSchema#>
Ontology: <http://example.org/o>
Import: <http://example.org/a>
Import: <http://example.org/b>
Class: A
    SubClassOf: B and C, p some {i, j}
    DisjointUnionOf: B, C
ObjectProperty: p
    SubPropertyChain: p o p
DataProperty: d
    Range: xsd:integer[>= 1, < 9]
Individual: i
    Facts: p j
EquivalentClasses: A, B
"""


def _graph(text: str = TEXT) -> StarLayerGraph:
    g = StarLayerGraph()
    g.extend(list(manchester_parse_to_tree(text)))
    return g


def _types(g: StarLayerGraph, cls: URIRef):
    return sorted(g.subjects(RDF.type, cls), key=str)


def test_no_rdf_list_is_written():
    g = _graph()
    assert not any(p in (RDF.first, RDF.rest) for _s, p, _o in g)
    assert manchester_validate(g).conforms


def test_the_baseline_conforms_and_renders():
    g = _graph(GUIDE)
    assert manchester_validate(g).conforms
    assert manchester_tree_to_text(g).count("Class:") == 2


# --- the decoder refuses a tree whose order is not defined ----------------------------------------------------------

def _first_child(g, parent_type, prop):
    parent = _types(g, parent_type)[0]
    return parent, [o for o in g.objects(parent, prop)]


def test_a_tie_is_a_format_error_and_a_shape_violation():
    g = _graph(GUIDE)
    doc = _types(g, MANCH.Document)[0]
    frames = list(g.objects(doc, MANCH.frames))
    number = next(g.objects(frames[0], ordinals.ORD))
    g.remove((frames[1], ordinals.ORD, None))
    g.add((frames[1], ordinals.ORD, number))
    with pytest.raises(FormatError) as raised:
        manchester_tree_to_text(g)
    assert raised.value.kind == "rdf"
    assert not manchester_validate(g).conforms


def test_a_missing_ordinal_is_a_format_error_and_a_shape_violation():
    g = _graph(GUIDE)
    frame = next(g.objects(_types(g, MANCH.Document)[0], MANCH.frames))
    g.remove((frame, ordinals.ORD, None))
    with pytest.raises(FormatError) as raised:
        manchester_tree_to_text(g)
    assert raised.value.kind == "rdf"
    assert not manchester_validate(g).conforms


def test_a_non_integer_ordinal_is_a_format_error_and_a_shape_violation():
    g = _graph(GUIDE)
    frame = next(g.objects(_types(g, MANCH.Document)[0], MANCH.frames))
    g.remove((frame, ordinals.ORD, None))
    g.add((frame, ordinals.ORD, ox.Literal("zero")))
    with pytest.raises(FormatError) as raised:
        manchester_tree_to_text(g)
    assert raised.value.kind == "rdf"
    assert not manchester_validate(g).conforms


def test_a_blank_child_under_two_parents_is_rejected():
    g = _graph(GUIDE)
    car = next(f for f in g.subjects(RDF.type, MANCH.ClassFrame) if next(g.objects(f, MANCH.clauses), None) is not None)
    clause = next(g.objects(car, MANCH.clauses))
    other = next(f for f in g.subjects(RDF.type, MANCH.ObjectPropertyFrame))
    g.add((other, MANCH.clauses, clause))
    assert not manchester_validate(g).conforms


def test_a_named_node_shared_through_a_tree_item_is_accepted():
    """The same IRI is a member of two sequences (two axioms), each time in its own tree:Item at its own position."""
    g = _graph(HEADER + "EquivalentClasses: :A, :B\nDisjointClasses: :B, :A\n")
    items = list(g.subjects(ordinals.VALUE, URIRef(EX + "A")))
    assert len(items) == 2 and all((i, RDF.type, ordinals.ITEM) in g for i in items)
    assert manchester_validate(g).conforms
    assert manchester_tree_to_text(g).count(f"<{EX}A>") == 2


# --- editing through the helpers -------------------------------------------------------------------------------------

def _car_clause(g):
    return next(g.subjects(RDF.type, MANCH.ClassSubClassOfClause))


def _some(g, prop="hasWheelCount", filler="http://www.w3.org/2001/XMLSchema#integer"):
    node = BNode()
    g.add((node, RDF.type, MANCH.Some))
    g.add((node, MANCH.onProperty, URIRef(EX + prop)))
    g.add((node, MANCH.filler, URIRef(filler)))
    item = BNode()
    g.add((item, RDF.type, MANCH.ClauseItem))
    g.add((item, MANCH.value, node))
    return item


def _roundtrips(g) -> str:
    text = manchester_tree_to_text(g)
    again = manchester_tree_to_text(manchester_parse_to_tree(text))
    assert text == again
    assert isomorphic(manchester_tree_to_owl(g), manchester_tree_to_owl(manchester_parse_to_tree(text)))
    return text


def test_append_to_the_subclassof_clause_is_the_guide_edit():
    """Guide 06.05.3: ``hasWheelCount some xsd:integer`` becomes the second superclass of ``Car``."""
    g = manchester_parse_to_tree(GUIDE, tree_graph=StarLayerGraph())
    ordinals.append(g, _car_clause(g), MANCH.items, _some(g))
    text = _roundtrips(g)
    assert f"SubClassOf: <{EX}Vehicle>, <{EX}hasWheelCount> some <http://www.w3.org/2001/XMLSchema#integer>" in text
    assert manchester_validate(g).conforms
    assert len(manchester_tree_to_owl(g)) > len(parse_manchester(GUIDE))


def test_insert_remove_and_replace_render_and_reparse():
    g = manchester_parse_to_tree(GUIDE, tree_graph=StarLayerGraph())
    clause = _car_clause(g)
    ordinals.insert_at(g, clause, MANCH.items, 0, _some(g, "first"))
    text = manchester_tree_to_text(g)
    assert text.index("first") < text.index("Vehicle>", text.index("Car"))
    assert _roundtrips(g)

    ordinals.replace_at(g, clause, MANCH.items, 0, _some(g, "second"))
    text = manchester_tree_to_text(g)
    assert "second" in text and "first" not in text
    assert manchester_validate(g).conforms

    ordinals.remove_at(g, clause, MANCH.items, 0)
    assert manchester_tree_to_text(g).count("some") == 0
    assert manchester_validate(g).conforms
    _roundtrips(g)


# --- a large document hashes -------------------------------------------------------------------------------------------

def _frames(n: int) -> str:
    lines = ["Prefix: : <http://example.org/big#>", "Prefix: xsd: <http://www.w3.org/2001/XMLSchema#>", "Ontology: <http://example.org/big>", ""]
    for i in range(n):
        lines += [f"ObjectProperty: p{i}", f"DataProperty: d{i}"]
    for i in range(n):
        lines += [
            f"Class: C{i}",
            f"    SubClassOf: C{(i + 1) % n} and p{i} some C{(i + 2) % n}, p{i} min 2 C{(i + 3) % n}, d{i} some xsd:integer[>= 1, < 9]",
            f"    EquivalentTo: C{(i + 4) % n} or (p{i} only C{(i + 5) % n} and not C{(i + 6) % n})",
            f"    DisjointWith: C{(i + 7) % n}",
        ]
    lines.append("EquivalentClasses: C0, C1, C2")
    return "\n".join(lines) + "\n"


def test_a_60_frame_document_validates_hashes_and_a_renumbered_copy_hashes_equal():
    g = manchester_parse_to_tree(_frames(60))
    assert manchester_validate(g).conforms
    digest = rdfc10_hash(ordinals.renumber_dense(g))
    assert digest == rdfc10_hash(ordinals.renumber_dense(manchester_parse_to_tree(_frames(60))))  # two parses, other blank node labels
    assert manchester_tree_to_text(g) == manchester_tree_to_text(manchester_parse_to_tree(_frames(60)))


def test_sixty_identical_axioms_hash():
    """With ``rdf:List`` cells RDFC-1.0 refused 60 identical ``EquivalentClasses:`` axioms (531 blank nodes it could not tell apart)."""
    g = manchester_parse_to_tree(HEADER + "EquivalentClasses: :A, :B and :C, :D some :E\n" * 60)
    assert len(rdfc10_hash(ordinals.renumber_dense(g))) == 64


def test_removing_a_frame_leaves_a_gap_that_renumber_dense_closes():
    g = manchester_parse_to_tree(_frames(5))
    doc = _types(g, MANCH.Document)[0]

    def numbers():
        return sorted(int(next(g.objects(f, ordinals.ORD)).value) for f in g.objects(doc, MANCH.frames))

    ordinals.remove_at(g, doc, MANCH.frames, 0)
    assert numbers()[0] == 1  # the gap is data: it is in the tree and so in its hash
    before = rdfc10_hash(g)
    ordinals.renumber_dense(g, doc, MANCH.frames)
    assert numbers() == list(range(len(numbers())))
    assert rdfc10_hash(g) != before
