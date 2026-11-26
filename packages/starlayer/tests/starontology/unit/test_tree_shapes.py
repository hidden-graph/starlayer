"""The shared ordered-children shapes (``tree_shapes.ttl``): checked through a small toy vocabulary that uses them the way ``srl:`` does
(``sh:class`` plus ``sh:node tree:OrdShape`` for typed children, ``tree:ItemShape`` for wrapped ones), and through the appendix B1 case at
the structure level: one named filter shared by two queries' ``where`` lists."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer import starontology
from starlayer.graph import StarLayerGraph
from starlayer.graph import ordinals as o
from starlayer.shacl import validate

EX = "http://example.org/"
TOY = """
@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix tree: <https://github.com/hidden-graph/starlayer/ns/tree#> .
ex:QueryShape a sh:NodeShape ; sh:targetClass ex:Query ;
  sh:property [ sh:path ex:where ; sh:class ex:Filter ; sh:node tree:OrdShape ] ;
  sh:property [ sh:path ex:uses ; sh:node tree:ItemShape ; sh:property [ sh:path tree:value ; sh:nodeKind sh:IRI ] ] .
"""


def _shapes() -> StarLayerGraph:
    shapes = starontology.get_ontology_graph("tree_shacl")
    shapes.parse(data=TOY, format="turtle")
    return shapes


def _n(name: str) -> ox.NamedNode:
    return ox.NamedNode(EX + name)


def _typed(g, cls="Filter") -> ox.BlankNode:
    node = ox.BlankNode()
    g.add((node, o.RDF_TYPE, _n(cls)))
    return node


def _query(g) -> ox.BlankNode:
    q = _typed(g, "Query")
    return q


def _report(g):
    return validate(g, _shapes())


def _messages(report) -> str:
    return report.report_text


def test_a_well_formed_sequence_conforms_with_gaps_allowed():
    g = StarLayerGraph(prefixes={})
    q = _query(g)
    for number in (0, 5, 9):
        f = _typed(g)
        g.add((q, _n("where"), f))
        g.add((f, o.ORD, o._integer(number)))
    assert _report(g).conforms


def test_two_children_with_the_same_ordinal_are_rejected():
    g = StarLayerGraph(prefixes={})
    q = _query(g)
    for number in (0, 1, 1):
        f = _typed(g)
        g.add((q, _n("where"), f))
        g.add((f, o.ORD, o._integer(number)))
    report = _report(g)
    assert not report.conforms and "same tree:ord" in _messages(report)


@pytest.mark.parametrize("bad", ['"x"', '"1.5"^^<http://www.w3.org/2001/XMLSchema#decimal>', "-1", '"1"^^<http://www.w3.org/2001/XMLSchema#string>'])
def test_a_non_integer_or_negative_ordinal_is_rejected(bad):
    g = StarLayerGraph(prefixes={})
    q = _query(g)
    f = _typed(g)
    g.add((q, _n("where"), f))
    g.parse(data=f"<{EX}s> <{EX}p> {bad} .", format="turtle")
    value = next(g.objects(_n("s"), _n("p")))
    g.add((f, o.ORD, value))
    assert not _report(g).conforms


def test_a_missing_ordinal_and_two_ordinals_are_rejected():
    g = StarLayerGraph(prefixes={})
    q = _query(g)
    f = _typed(g)
    g.add((q, _n("where"), f))
    assert not _report(g).conforms  # none
    g.add((f, o.ORD, o._integer(0)))
    assert _report(g).conforms
    g.add((f, o.ORD, o._integer(1)))
    assert not _report(g).conforms  # two


def test_an_item_needs_one_value_and_one_ordinal():
    g = StarLayerGraph(prefixes={})
    q = _query(g)
    o.write_ordered(g, q, _n("uses"), [_n("a")])
    assert _report(g).conforms
    item = next(g.objects(q, _n("uses")))
    g.remove((item, o.VALUE, None))
    assert not _report(g).conforms


def test_a_blank_child_under_two_parents_is_rejected():
    """The ordinal is on the child, so a blank child held by two parents has no single position."""
    g = StarLayerGraph(prefixes={})
    shared = _typed(g)
    g.add((shared, o.ORD, o._integer(0)))
    for _ in range(2):
        q = _query(g)
        g.add((q, _n("where"), shared))
    report = _report(g)
    assert not report.conforms and "more than one parent" in _messages(report)


def test_a_blank_child_held_through_two_properties_of_one_parent_is_rejected():
    g = StarLayerGraph(prefixes={})
    q = _query(g)
    f = _typed(g)
    g.add((f, o.ORD, o._integer(0)))
    g.add((q, _n("where"), f))
    g.add((q, _n("other"), f))
    assert not _report(g).conforms


def test_a_named_node_carrying_an_ordinal_itself_is_rejected():
    g = StarLayerGraph(prefixes={})
    q = _query(g)
    g.add((_n("f1"), o.RDF_TYPE, _n("Filter")))
    g.add((q, _n("where"), _n("f1")))
    g.add((_n("f1"), o.ORD, o._integer(0)))
    report = _report(g)
    assert not report.conforms and "cannot carry tree:ord itself" in _messages(report)


def test_hypothesis_a_named_node_in_items_can_be_shared_by_two_parents():
    """Appendix B1 at the structure level: two ordered parents hold the same named node, each in its own Item at its own position."""
    g = StarLayerGraph(prefixes={})
    q1, q2 = _query(g), _query(g)
    shared = _n("sharedFilter")
    o.write_ordered(g, q1, _n("uses"), [_n("other"), shared])
    o.write_ordered(g, q2, _n("uses"), [shared, _n("third")])
    assert _report(g).conforms
    assert o.ordered_items(g, q1, _n("uses")) == [_n("other"), shared]
    assert o.ordered_items(g, q2, _n("uses")) == [shared, _n("third")]  # unambiguous: the shared node has a different position under each
    assert o.append(g, q2, _n("uses"), shared)  # even twice under one parent
    assert o.ordered_items(g, q2, _n("uses")) == [shared, _n("third"), shared]
    assert _report(g).conforms


def test_the_same_blank_node_under_two_parents_is_rejected_where_the_named_one_is_accepted():
    """The contrast of the two: the blank node carries its ordinal itself, the named node does not."""
    g = StarLayerGraph(prefixes={})
    q1, q2 = _query(g), _query(g)
    blank = _typed(g)
    g.add((q1, _n("where"), blank))
    g.add((q2, _n("where"), blank))
    g.add((blank, o.ORD, o._integer(0)))
    assert not _report(g).conforms


def test_a_loop_cannot_be_written_in_an_ordered_sequence():
    """A sequence has no cells to link back: the longest read is the number of children, and a node that is its own child still reads once."""
    g = StarLayerGraph(prefixes={})
    q = _query(g)
    g.add((q, _n("where"), q))
    g.add((q, o.ORD, o._integer(0)))
    assert o.ordered_items(g, q, _n("where")) == [q]  # finite: one child
    assert not _report(g).conforms  # the child is not an ex:Filter
