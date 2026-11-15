"""Oxigraph's own store methods on the graph and the dataset: a writer keeps the write counter, and a graph acts on its own graph only."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph import NamedNode, StarLayerDataset, StarLayerGraph
from starlayer.graph.execution import union

TTL = b"<http://e/s> <http://e/p> <http://e/o> ."
G = NamedNode("http://e/g")
OTHER = NamedNode("http://e/other")
QUAD = (NamedNode("http://e/a"), NamedNode("http://e/b"), NamedNode("http://e/c"))


@pytest.fixture
def pair():
    d = StarLayerDataset()
    return d, d.graph(G)


def bumps(call):
    before = union.current()
    call()
    return union.current() > before


def test_load_goes_to_this_graph_and_bumps_the_counter(pair):
    d, g = pair
    assert bumps(lambda: g.load(TTL, ox.RdfFormat.TURTLE))
    assert len(g) == 1 and len(d.default_graph) == 0


def test_bulk_load_on_a_dataset_goes_to_the_default_graph_unless_told(pair):
    d, g = pair
    assert bumps(lambda: d.bulk_load(TTL, ox.RdfFormat.TURTLE))
    assert len(d.default_graph) == 1 and len(g) == 0
    d.load(TTL, ox.RdfFormat.TURTLE, to_graph=G)
    assert len(g) == 1


def test_a_graph_will_not_load_into_another_graph(pair):
    _, g = pair
    with pytest.raises(ValueError):
        g.load(TTL, ox.RdfFormat.TURTLE, to_graph=OTHER)


def test_bulk_extend_keeps_only_quads_of_the_graph_and_bumps_the_counter(pair):
    d, g = pair
    assert bumps(lambda: g.bulk_extend([QUAD, (*QUAD, OTHER)]))
    assert len(g) == 1 and not d.has_graph(OTHER)


def test_clear_graph_and_add_graph(pair):
    d, g = pair
    g.add(QUAD)
    assert bumps(lambda: g.clear_graph())
    assert len(g) == 0 and d.has_graph(G)
    with pytest.raises(ValueError):
        g.clear_graph(OTHER)
    assert bumps(lambda: d.add_graph(OTHER))
    assert d.has_graph(OTHER)
    d.default_graph.add(QUAD)
    d.clear_graph()
    assert len(d.default_graph) == 0


def test_graph_names_are_store_wide_even_from_a_graph(pair):
    d, g = pair
    d.add_graph(OTHER)
    assert set(g.named_graphs()) == {G, OTHER}
    assert g.contains_named_graph(OTHER)


def test_quads_for_pattern_and_dump_stay_within_the_graph(pair):
    d, g = pair
    g.add(QUAD)
    d.graph(OTHER).add(QUAD)
    assert len(list(d.quads_for_pattern(None, None, None))) == 2
    assert [q.graph_name for q in g.quads_for_pattern(None, None, None)] == [G]
    with pytest.raises(ValueError):
        list(g.quads_for_pattern(None, None, None, OTHER))
    assert g.dump(format=ox.RdfFormat.N_QUADS).count(b"\n") == 1
    with pytest.raises(ValueError):
        g.dump(format=ox.RdfFormat.N_QUADS, from_graph=OTHER)


def test_persistence_methods_work_from_a_graph(tmp_path):
    g = StarLayerGraph(path=str(tmp_path / "db"))
    g.add(QUAD)
    g.flush()
    g.optimize()
    g.backup(tmp_path / "copy")
    assert len(StarLayerGraph(path=str(tmp_path / "copy"))) == 1


def test_a_write_through_a_wrapped_method_refreshes_a_cached_entailment():
    from starlayer.graph import ENTAILMENT

    g = StarLayerGraph()
    g.load(b"<http://e/A> <http://www.w3.org/2000/01/rdf-schema#subClassOf> <http://e/B> . <http://e/x> a <http://e/A> .", ox.RdfFormat.TURTLE)
    q = "ASK { <http://e/x> a <http://e/C> }"
    assert not g.query(q, entailment=ENTAILMENT.RDFS, infer="changed").askAnswer
    g.bulk_load(b"<http://e/B> <http://www.w3.org/2000/01/rdf-schema#subClassOf> <http://e/C> .", ox.RdfFormat.TURTLE)
    assert g.query(q, entailment=ENTAILMENT.RDFS, infer="changed").askAnswer
