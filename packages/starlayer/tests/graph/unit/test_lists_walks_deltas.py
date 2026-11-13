"""RDF list writing, ``set``, transitive walks, extra namespace behaviour and ``GraphDelta``."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph import (
    RDF,
    RDFS,
    SKOS,
    GraphDelta,
    Namespace,
    StarLayerDataset,
    StarLayerGraph,
    diff,
    literal,
)

EX = Namespace("http://e/")


def test_add_list_writes_cells_and_items_reads_them_back():
    g = StarLayerGraph()
    head = g.add_list([EX.a, literal(2), (EX.s, EX.p, EX.o)])
    assert isinstance(head, ox.BlankNode) and len(g) == 6
    assert list(g.items(head)) == [EX.a, literal(2), ox.Triple(EX.s, EX.p, EX.o)]


def test_the_empty_list_is_nil_and_writes_nothing():
    g = StarLayerGraph()
    assert g.add_list([]) == RDF.nil and len(g) == 0


def test_a_named_head():
    g = StarLayerGraph()
    assert g.add_list([EX.a, EX.b], head=EX.cell) == EX.cell
    assert list(g.items(EX.cell)) == [EX.a, EX.b]


def test_remove_list_removes_the_cells_and_nothing_else():
    g = StarLayerGraph()
    head = g.add_list([EX.a, EX.b])
    g.add((EX.x, EX.p, head))
    g.add((EX.a, EX.label, literal("kept")))
    g.remove_list(head)
    assert sorted(map(str, g.triples())) == sorted(map(str, [(EX.x, EX.p, head), (EX.a, EX.label, literal("kept"))]))


def test_a_list_with_a_cycle_or_a_broken_cell_is_a_value_error():
    g = StarLayerGraph()
    g.add_list([EX.a, EX.b], head=EX.c1)
    (rest,) = list(g.objects(EX.c1, RDF.rest))
    g.remove((rest, RDF.rest, None))
    g.add((rest, RDF.rest, EX.c1))
    with pytest.raises(ValueError, match="cycle"):
        g.remove_list(EX.c1)
    with pytest.raises(ValueError, match="not a list cell"):
        g.remove_list(EX.nothing)


def test_set_list_replaces_what_was_there():
    g = StarLayerGraph()
    g.set_list(EX.x, EX.p, [EX.a, EX.b])
    before = len(g)
    head = g.set_list(EX.x, EX.p, [EX.c])
    assert list(g.items(next(g.objects(EX.x, EX.p)))) == [EX.c] and head == next(g.objects(EX.x, EX.p))
    assert len(g) == 3 < before
    assert g.set_list(EX.x, EX.p, []) == RDF.nil and len(g) == 1


def test_set_keeps_one_value():
    g = StarLayerGraph()
    g.set((EX.a, EX.name, literal("one")))
    g.set((EX.a, EX.name, literal("two")))
    g.set((EX.a, EX.other, literal("x")))
    assert list(g.objects(EX.a, EX.name)) == [literal("two")] and len(g) == 2


def test_transitive_walks_include_the_start_and_end_on_a_cycle():
    g = StarLayerGraph()
    for a, b in [(EX.a, EX.b), (EX.b, EX.c), (EX.c, EX.a), (EX.c, EX.d)]:
        g.add((a, RDFS.subClassOf, b))
    down = list(g.transitive_objects(EX.a, RDFS.subClassOf))
    assert down[0] == EX.a and set(down) == {EX.a, EX.b, EX.c, EX.d} and len(down) == 4
    up = list(g.transitive_subjects(RDFS.subClassOf, EX.d))
    assert up[0] == EX.d and set(up) == {EX.a, EX.b, EX.c, EX.d}
    assert list(g.transitive_objects(EX.lonely, RDFS.subClassOf)) == [EX.lonely]


def test_a_dataset_has_the_same_methods():
    d = StarLayerDataset()
    d.set((EX.a, EX.p, literal(1)))
    d.set((EX.a, EX.p, literal(2)))
    assert [t[2] for t in d.triples((EX.a, EX.p, None))] == [literal(2)]


def test_namespace_membership_and_equality():
    assert EX.a in EX and "http://e/a" in EX and "http://other/a" not in EX and "http://e/" not in EX and 5 not in EX
    assert EX == Namespace("http://e/") and hash(EX) == hash(Namespace("http://e/")) and EX != Namespace("http://f/")
    assert EX.term("part-1") == EX["part-1"] and repr(EX) == "Namespace('http://e/')" and str(EX) == "http://e/"
    assert SKOS.Concept == ox.NamedNode("http://www.w3.org/2004/02/skos/core#Concept")


def test_a_delta_turns_one_graph_into_another_and_back():
    old, new = StarLayerGraph(), StarLayerGraph()
    old.extend([(EX.a, EX.p, EX.b), (EX.a, EX.q, EX.b)])
    new.extend([(EX.a, EX.p, EX.c), (EX.a, EX.q, EX.b)])
    delta = diff(old, new)
    assert delta.added == {(EX.a, EX.p, EX.c)} and delta.removed == {(EX.a, EX.p, EX.b)} and delta and len(delta) == 2
    assert delta.applied_to(old) == frozenset(new.triples()) and len(old) == 2  # applied_to leaves the graph alone
    assert set(delta.apply(old).triples()) == set(new.triples())
    assert set(delta.inverse().apply(old).triples()) == {(EX.a, EX.p, EX.b), (EX.a, EX.q, EX.b)}


def test_deltas_compose_to_their_net_effect():
    a = GraphDelta(added=[(EX.s, EX.p, EX.x)], removed=[(EX.s, EX.p, EX.y)])
    b = GraphDelta(added=[(EX.s, EX.p, EX.y)], removed=[(EX.s, EX.p, EX.x)])
    assert not a.then(b) and not GraphDelta()
    c = GraphDelta(added=[(EX.s, EX.p, EX.z)])
    assert a.then(c).added == {(EX.s, EX.p, EX.x), (EX.s, EX.p, EX.z)} and a.then(c).removed == {(EX.s, EX.p, EX.y)}


def test_a_triple_in_both_sets_is_no_change():
    d = GraphDelta(added=[(EX.s, EX.p, EX.o)], removed=[(EX.s, EX.p, EX.o)])
    assert not d and d.added == frozenset()
