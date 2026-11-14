"""``len()`` of a graph and ``serialize()`` of a graph on the default graph use what the store does itself (its own length; its quads given to the
writer as they are) instead of making a Python object per statement. The answers must not change, and the cases the shortcut cannot
serve (a store with named graphs, a view of a named graph) must still be right."""

from __future__ import annotations

import threading

import pyoxigraph as ox
import pytest
from starlayer.graph import StarLayerDataset, StarLayerGraph

EX = "http://example.org/"
NT = ox.RdfFormat.N_TRIPLES


def n(name: str) -> ox.NamedNode:
    return ox.NamedNode(EX + name)


def graph(count: int = 50) -> StarLayerGraph:
    g = StarLayerGraph()
    g.extend((n(f"s{i}"), n("p"), ox.Literal(str(i))) for i in range(count))
    return g


def old_nt(g: StarLayerGraph) -> bytes:
    """What the writer produced before: a ``Triple`` made of each quad."""
    return ox.serialize([ox.Triple(q.subject, q.predicate, q.object) for q in g.quads()], None, NT)


# ---- len


def test_len_counts_the_triples():
    g = graph(50)
    assert len(g) == 50
    g.remove((n("s0"), None, None))
    assert len(g) == 49
    assert len(StarLayerGraph()) == 0


def test_len_follows_a_write_straight_to_the_store():
    g = graph(5)
    g.store.add(ox.Quad(n("x"), n("p"), n("y"), ox.DefaultGraph()))
    assert len(g) == 6


def test_len_counts_only_this_graph_when_the_store_has_others():
    ds = StarLayerDataset()
    ds.add((n("a"), n("p"), n("b"), n("g1")))
    ds.add((n("c"), n("p"), n("d"), n("g1")))
    ds.add((n("e"), n("p"), n("f")))  # the default graph
    default = StarLayerGraph(ds.store)
    named = StarLayerGraph(ds.store, identifier=n("g1"))
    assert len(default) == 1
    assert len(named) == 2
    assert len(ds.store) == 3  # what a plain store length would have said


def test_len_with_an_empty_named_graph_declared():
    g = graph(3)
    g.store.add_graph(n("empty"))
    assert len(g) == 3


def test_len_of_a_graph_view_of_the_default_graph_of_a_shared_store():
    g = graph(4)
    other = StarLayerGraph(g.store, identifier=n("other"))
    other.add((n("o"), n("p"), n("q")))
    assert len(g) == 4 and len(other) == 1


# ---- serialize


@pytest.mark.parametrize("fmt", ["nt", "turtle", "xml"])
def test_the_default_graph_serializes_as_before(fmt):
    g = graph(30)
    out = g.serialize(format=fmt)
    if fmt == "nt":
        assert out.encode() == old_nt(g)
    back = StarLayerGraph()
    back.parse(data=out, format=fmt)
    assert set(back.triples()) == set(g.triples())


def test_a_store_with_named_graphs_writes_only_the_default_graph():
    ds = StarLayerDataset()
    ds.add((n("a"), n("p"), n("b")))
    ds.add((n("c"), n("p"), n("d"), n("g1")))
    default = StarLayerGraph(ds.store)
    out = default.serialize(format="nt")  # a triple format refuses a quad with a graph name: only the default graph's quads may go in
    assert out.strip() == f"<{EX}a> <{EX}p> <{EX}b> ."


def test_a_view_of_a_named_graph_still_serializes():
    ds = StarLayerDataset()
    ds.add((n("c"), n("p"), n("d"), n("g1")))
    ds.add((n("e"), n("p"), n("f")))
    named = StarLayerGraph(ds.store, identifier=n("g1"))
    assert named.serialize(format="nt").strip() == f"<{EX}c> <{EX}p> <{EX}d> ."
    assert "g1" in named.serialize(format="nq")  # a quad format keeps the graph name


def test_triple_terms_and_directions_get_the_version_line_and_round_trip():
    g = StarLayerGraph()
    tt = ox.Triple(n("a"), n("p"), n("b"))
    g.add((n("r"), ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies"), tt))
    g.add((n("s"), n("label"), ox.Literal("hello", language="en", direction=ox.BaseDirection.LTR)))
    out = g.serialize(format="turtle")
    assert out.startswith("@version") or out.lstrip().startswith("VERSION")
    back = StarLayerGraph()
    back.parse(data=out, format="turtle")
    assert set(back.triples()) == set(g.triples())
    assert "<<(" not in g.serialize(format="nt", rdf_version="1.1")  # the RDF 1.1 export still has no triple term


def test_short_blank_node_labels_and_the_rdf11_export_still_work():
    g = StarLayerGraph()
    g.parse(data=f"<{EX}a> <{EX}p> [ <{EX}q> [ <{EX}r> 1 ] ] .", format="turtle")
    out = g.serialize(format="nt", bnode_labels="short")
    assert "_:b0" in out and "_:b1" in out
    again = g.serialize(format="nt", bnode_labels="short")
    assert out == again
    assert len(g.serialize(format="nt", rdf_version="1.1").strip().splitlines()) == 3


def test_serializing_from_another_thread_is_fine():
    """The writer reads the store's quad iterator within the call; it must not outlive it (a pyoxigraph iterator is bound to its thread)."""
    g = graph(200)
    results: list = []
    errors: list = []

    def work():
        try:
            for _ in range(10):
                results.append(len(g.serialize(format="nt").splitlines()))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and results == [200] * 40
