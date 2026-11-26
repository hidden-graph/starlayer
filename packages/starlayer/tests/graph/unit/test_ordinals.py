"""Ordered children as ordinals (``starlayer.graph.ordinals``): reading, the edit helpers, ties and bad ordinals, and dense renumbering
before an RDFC-1.0 hash."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.errors import FormatError
from starlayer.graph import StarLayerGraph, ordinals
from starlayer.graph.rdfc import rdfc10_hash

EX = "http://example.org/"
P = ox.NamedNode(EX + "p")
PARENT = ox.NamedNode(EX + "parent")
T = ox.NamedNode(EX + "T")


def _node(g) -> ox.BlankNode:
    n = ox.BlankNode()
    g.add((n, ordinals.RDF_TYPE, T))
    return n


def _int(n) -> ox.Literal:
    return ordinals._integer(n)


def _three():
    g = StarLayerGraph(prefixes={})
    nodes = [_node(g) for _ in range(3)]
    ordinals.write_ordered(g, PARENT, P, nodes)
    return g, nodes


def test_write_and_read_in_order_with_literals_and_named_nodes_wrapped():
    g = StarLayerGraph(prefixes={})
    a, b = _node(g), _node(g)
    members = [b, ox.Literal("x"), ox.NamedNode(EX + "n"), a]
    ordinals.write_ordered(g, PARENT, P, members)
    assert ordinals.ordered_items(g, PARENT, P) == members
    children = ordinals.ordered_children(g, PARENT, P)
    assert children[0] == (b, b) and children[1][0] != children[1][1]  # a blank node is its own child, a literal sits in an Item
    assert next(g.objects(children[1][0], ordinals.ORD)) == _int(1)


def test_no_children_is_an_empty_list():
    assert ordinals.ordered_items(StarLayerGraph(prefixes={}), PARENT, P) == []


def test_order_is_ascending_ordinal_whatever_the_insertion_order():
    g = StarLayerGraph(prefixes={})
    nodes = [_node(g) for _ in range(3)]
    for n, number in zip(nodes, (7, 2, 40), strict=True):
        g.add((PARENT, P, n))
        g.add((n, ordinals.ORD, _int(number)))
    assert ordinals.ordered_items(g, PARENT, P) == [nodes[1], nodes[0], nodes[2]]


def test_a_tie_raises_a_format_error_and_is_not_broken_by_label():
    g = StarLayerGraph(prefixes={})
    for _ in range(2):
        n = _node(g)
        g.add((PARENT, P, n))
        g.add((n, ordinals.ORD, _int(1)))
    with pytest.raises(FormatError) as raised:
        ordinals.ordered_items(g, PARENT, P)
    assert raised.value.kind == "rdf" and "same tree:ord 1" in str(raised.value) and raised.value.context


def test_a_missing_ordinal_raises():
    g = StarLayerGraph(prefixes={})
    n = _node(g)
    g.add((PARENT, P, n))
    with pytest.raises(FormatError, match="0 tree:ord"):
        ordinals.ordered_items(g, PARENT, P)


@pytest.mark.parametrize("bad", [ox.Literal("x"), ox.Literal("1.5", datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#decimal")), _int(-1)])
def test_a_non_integer_or_negative_ordinal_raises(bad):
    g = StarLayerGraph(prefixes={})
    n = _node(g)
    g.add((PARENT, P, n))
    g.add((n, ordinals.ORD, bad))
    with pytest.raises(FormatError):
        ordinals.ordered_items(g, PARENT, P)


def test_a_named_node_that_is_not_in_an_item_and_an_item_without_a_value_raise():
    g = StarLayerGraph(prefixes={})
    g.add((PARENT, P, ox.NamedNode(EX + "n")))
    with pytest.raises(FormatError, match="Item"):
        ordinals.ordered_items(g, PARENT, P)
    h = StarLayerGraph(prefixes={})
    item = ox.BlankNode()
    h.add((PARENT, P, item))
    h.add((item, ordinals.RDF_TYPE, ordinals.ITEM))
    h.add((item, ordinals.ORD, _int(0)))
    with pytest.raises(FormatError, match="tree:value"):
        ordinals.ordered_items(h, PARENT, P)


def test_append_insert_remove_replace():
    g, (a, b, c) = _three()
    d, e = _node(g), _node(g)
    ordinals.append(g, PARENT, P, d)
    assert ordinals.ordered_items(g, PARENT, P) == [a, b, c, d]
    ordinals.insert_at(g, PARENT, P, 1, e)
    assert ordinals.ordered_items(g, PARENT, P) == [a, e, b, c, d]
    assert ordinals.remove_at(g, PARENT, P, 2) == b
    assert ordinals.ordered_items(g, PARENT, P) == [a, e, c, d]
    assert not list(g.objects(b, ordinals.ORD)) and not list(g.subjects(P, b))  # a removed child leaves the sequence
    ordinals.replace_at(g, PARENT, P, 0, b)
    assert ordinals.ordered_items(g, PARENT, P) == [b, e, c, d]
    ordinals.insert_at(g, PARENT, P, 99, a)  # past the end appends
    ordinals.insert_at(g, PARENT, P, 0, ox.Literal("first"))
    assert ordinals.ordered_items(g, PARENT, P) == [ox.Literal("first"), b, e, c, d, a]


def test_edits_on_an_empty_sequence_and_items():
    g = StarLayerGraph(prefixes={})
    ordinals.append(g, PARENT, P, ox.Literal("x"))
    ordinals.insert_at(g, PARENT, P, 0, ox.NamedNode(EX + "n"))
    assert ordinals.ordered_items(g, PARENT, P) == [ox.NamedNode(EX + "n"), ox.Literal("x")]
    assert ordinals.remove_at(g, PARENT, P, 0) == ox.NamedNode(EX + "n")
    assert ordinals.ordered_items(g, PARENT, P) == [ox.Literal("x")]
    assert not list(g.subjects(ordinals.RDF_TYPE, ordinals.ITEM)) == []  # the other Item stays; the removed one's triples are gone
    assert len(list(g.subjects(ordinals.RDF_TYPE, ordinals.ITEM))) == 1


def test_a_blank_node_that_already_has_a_parent_is_wrapped_so_it_stays_unambiguous():
    g, (a, _b, _c) = _three()
    other = ox.NamedNode(EX + "other")
    child = ordinals.append(g, other, P, a)
    assert child != a and ordinals.ordered_items(g, other, P) == [a]


def test_renumber_dense_closes_gaps_and_keeps_order():
    g, (a, b, c) = _three()
    ordinals.remove_at(g, PARENT, P, 1)
    assert sorted(int(x.value) for x in g.objects(None, ordinals.ORD)) == [0, 2]
    ordinals.renumber_dense(g)
    assert ordinals.ordered_items(g, PARENT, P) == [a, c]
    assert sorted(int(x.value) for x in g.objects(None, ordinals.ORD)) == [0, 1]
    ordinals.renumber_dense(g, PARENT, P)  # one sequence alone


def test_renumber_dense_refuses_a_node_with_two_parents_and_a_tie():
    g, (a, _b, _c) = _three()
    g.add((ox.NamedNode(EX + "other"), P, a))
    with pytest.raises(FormatError, match="ambiguous"):
        ordinals.renumber_dense(g)


def test_a_tree_and_its_renumbered_copy_hash_equal_and_a_gap_changes_the_hash():
    """Removing a middle child leaves a gap, so the hash differs from the tree written fresh; renumbering restores equality."""
    def build(kind):
        g = StarLayerGraph(prefixes={})
        parent = ox.NamedNode(EX + "parent")
        members = [ox.Literal(str(i)) for i in range(3)] if kind != "short" else [ox.Literal("0"), ox.Literal("2")]
        ordinals.write_ordered(g, parent, P, members)
        if kind == "gap":
            ordinals.remove_at(g, parent, P, 1)
        return g

    gapped, fresh = build("gap"), build("short")
    assert rdfc10_hash(gapped) != rdfc10_hash(fresh)
    ordinals.renumber_dense(gapped)
    assert rdfc10_hash(gapped) == rdfc10_hash(fresh)
