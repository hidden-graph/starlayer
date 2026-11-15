"""``g.ox``: Oxigraph's own store methods on the graph and the dataset. A writer keeps the write counter, a reader leaves it, and a graph acts on its own graph only."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph import NamedNode, StarLayerDataset, StarLayerGraph
from starlayer.graph.execution import union

TTL = b"<http://e/s> <http://e/p> <http://e/o> ."
G = NamedNode("http://e/g")
OTHER = NamedNode("http://e/other")
S, P, OBJ = NamedNode("http://e/a"), NamedNode("http://e/b"), NamedNode("http://e/c")
QUAD = ox.Quad(S, P, OBJ, G)
OTHER_QUAD = ox.Quad(S, P, OBJ, OTHER)


@pytest.fixture
def pair():
    d = StarLayerDataset()
    return d, d.graph(G)


def bumps(call):
    before = union.current()
    call()
    return union.current() > before


def test_load_goes_to_the_named_graph_and_bumps_the_counter(pair):
    d, g = pair
    assert bumps(lambda: g.ox.load(TTL, ox.RdfFormat.TURTLE, to_graph=G))
    assert len(g) == 1 and len(d.default_graph) == 0


def test_a_dataset_loads_where_oxigraph_would(pair):
    d, g = pair
    assert bumps(lambda: d.ox.bulk_load(TTL, ox.RdfFormat.TURTLE))
    assert len(d.default_graph) == 1 and len(g) == 0
    d.ox.load(TTL, ox.RdfFormat.TURTLE, to_graph=G)
    assert len(g) == 1


def test_a_graph_will_not_load_into_another_graph_or_a_quad_format(pair):
    _, g = pair
    with pytest.raises(ValueError):
        g.ox.load(TTL, ox.RdfFormat.TURTLE, to_graph=OTHER)
    with pytest.raises(ValueError):  # no to_graph is the default graph, not this one
        g.ox.load(TTL, ox.RdfFormat.TURTLE)
    with pytest.raises(ValueError):  # a quad format can carry any graph
        g.ox.load(b"<http://e/s> <http://e/p> <http://e/o> <http://e/other> .", ox.RdfFormat.N_QUADS, to_graph=G)
    assert len(g) == 0


def test_a_default_graph_loads_without_naming_it():
    g = StarLayerGraph()
    g.ox.load(TTL, ox.RdfFormat.TURTLE)
    assert len(g) == 1


def test_add_extend_remove_take_quads_and_keep_to_the_graph(pair):
    d, g = pair
    assert bumps(lambda: g.ox.add(QUAD))
    assert len(g) == 1
    with pytest.raises(ValueError):
        g.ox.add(OTHER_QUAD)
    assert bumps(lambda: g.ox.extend([ox.Quad(S, P, NamedNode("http://e/d"), G)]))
    with pytest.raises(ValueError):
        g.ox.extend([QUAD, OTHER_QUAD])
    with pytest.raises(ValueError):
        g.ox.bulk_extend([OTHER_QUAD])
    assert bumps(lambda: g.ox.bulk_extend([ox.Quad(S, P, NamedNode("http://e/e"), G)]))
    assert bumps(lambda: g.ox.remove(QUAD))
    with pytest.raises(ValueError):
        g.ox.remove(OTHER_QUAD)
    assert len(g) == 2 and not d.has_graph(OTHER)
    d.ox.add(OTHER_QUAD)  # a dataset writes to any graph
    assert d.has_graph(OTHER)


def test_the_rdflib_style_add_is_not_oxigraphs(pair):
    _, g = pair
    g.add((S, P, OBJ))  # a triple, into the graph
    assert len(g) == 1
    with pytest.raises(TypeError):
        g.ox.add((S, P, OBJ))  # Oxigraph's add takes a quad


def test_clear_is_refused_on_a_graph_and_clears_everything_on_a_dataset(pair):
    d, g = pair
    g.add((S, P, OBJ))
    with pytest.raises(ValueError):
        g.ox.clear()
    assert len(g) == 1
    assert bumps(lambda: d.ox.clear())
    assert len(d) == 0


def test_clear_graph_add_graph_remove_graph(pair):
    d, g = pair
    g.add((S, P, OBJ))
    assert bumps(lambda: g.ox.clear_graph(G))
    assert len(g) == 0 and d.has_graph(G)
    with pytest.raises(ValueError):
        g.ox.clear_graph(OTHER)
    with pytest.raises(ValueError):
        g.ox.add_graph(OTHER)
    with pytest.raises(ValueError):
        g.ox.remove_graph(OTHER)
    assert bumps(lambda: d.ox.add_graph(OTHER))
    assert d.has_graph(OTHER)
    d.default_graph.add((S, P, OBJ))
    d.ox.clear_graph(ox.DefaultGraph())
    assert len(d.default_graph) == 0
    d.graph(OTHER).add((S, P, OBJ))
    assert bumps(lambda: g.ox.remove_graph(G))
    assert not d.has_graph(G) and len(d.graph(OTHER)) == 1


def test_graph_names_are_store_wide_and_do_not_move_the_counter(pair):
    d, g = pair
    d.ox.add_graph(OTHER)
    assert not bumps(lambda: set(g.ox.named_graphs()))
    assert set(g.ox.named_graphs()) == {G, OTHER}
    assert g.ox.contains_named_graph(OTHER)


def test_quads_for_pattern_and_dump_must_name_the_graph(pair):
    d, g = pair
    g.add((S, P, OBJ))
    d.graph(OTHER).add((S, P, OBJ))
    assert len(list(d.ox.quads_for_pattern(None, None, None, None))) == 2
    assert [q.graph_name for q in g.ox.quads_for_pattern(None, None, None, G)] == [G]
    assert not bumps(lambda: list(g.ox.quads_for_pattern(None, None, None, graph_name=G)))
    with pytest.raises(ValueError):  # no graph would read every graph
        g.ox.quads_for_pattern(None, None, None)
    with pytest.raises(ValueError):
        g.ox.quads_for_pattern(None, None, None, OTHER)
    assert g.ox.dump(format=ox.RdfFormat.N_QUADS, from_graph=G).count(b"\n") == 1
    with pytest.raises(ValueError):
        g.ox.dump(format=ox.RdfFormat.N_QUADS)
    with pytest.raises(ValueError):
        g.ox.dump(format=ox.RdfFormat.N_QUADS, from_graph=OTHER)


def test_query_on_a_graph_reads_that_graph_only(pair):
    d, g = pair
    g.add((S, P, OBJ))
    d.graph(OTHER).add((S, P, NamedNode("http://e/z")))
    text = "SELECT ?o WHERE { ?s ?p ?o }"
    assert [r["o"] for r in g.ox.query(text, default_graph=[G])] == [OBJ]
    with pytest.raises(ValueError):
        g.ox.query(text)  # Oxigraph's default graph is not this graph
    with pytest.raises(ValueError):
        g.ox.query(text, default_graph=[OTHER])
    with pytest.raises(ValueError):
        g.ox.query(text, use_default_graph_as_union=True)
    assert len(list(d.ox.query(text, use_default_graph_as_union=True))) == 2


def test_persistence_methods_work_from_a_graph(tmp_path):
    g = StarLayerGraph(path=str(tmp_path / "db"))
    g.add((S, P, OBJ))
    g.ox.flush()
    g.ox.optimize()
    g.ox.backup(tmp_path / "copy")
    assert len(StarLayerGraph(path=str(tmp_path / "copy"))) == 1


def test_a_write_through_ox_refreshes_a_cached_entailment():
    from starlayer.graph import ENTAILMENT

    g = StarLayerGraph()
    g.ox.load(b"<http://e/A> <http://www.w3.org/2000/01/rdf-schema#subClassOf> <http://e/B> . <http://e/x> a <http://e/A> .", ox.RdfFormat.TURTLE)
    q = "ASK { <http://e/x> a <http://e/C> }"
    assert not g.query(q, entailment=ENTAILMENT.RDFS, infer="changed").askAnswer
    g.ox.bulk_load(b"<http://e/B> <http://www.w3.org/2000/01/rdf-schema#subClassOf> <http://e/C> .", ox.RdfFormat.TURTLE)
    assert g.query(q, entailment=ENTAILMENT.RDFS, infer="changed").askAnswer


def test_remove_graph_is_on_the_dataset_and_on_ox(pair):
    d, g = pair
    g.add((S, P, OBJ))
    d.remove_graph(g)  # the dataset's own: a name or a graph
    assert not d.has_graph(G)
    g.add((S, P, OBJ))
    assert bumps(lambda: d.ox.remove_graph(G))  # Oxigraph's: a name
    assert not d.has_graph(G)
    d.default_graph.add((S, P, OBJ))
    d.ox.remove_graph(ox.DefaultGraph())
    assert len(d.default_graph) == 0


def test_only_oxigraphs_store_methods_are_on_ox(pair):
    d, _ = pair
    with pytest.raises(AttributeError):
        _ = d.ox.nope
    with pytest.raises(AttributeError):
        _ = d.ox.read_only  # makes a store: StarLayerDataset.read_only(path)
    assert "load" in dir(d.ox) and "triples" not in dir(d.ox)
    for name in ("load", "bulk_load", "bulk_extend", "contains_named_graph", "quads_for_pattern", "dump", "flush", "optimize", "backup"):
        assert not hasattr(d, name), name


def test_read_only_opens_an_existing_store_for_reading(tmp_path):
    path = str(tmp_path / "db")
    w = StarLayerGraph(path=path)
    w.add((S, P, OBJ))
    w.ox.flush()
    del w
    r = StarLayerGraph.read_only(path)
    assert len(r) == 1
    with pytest.raises(RuntimeError):
        r.add((S, P, NamedNode("http://e/d")))
    del r
    ds = StarLayerDataset.read_only(path)
    assert len(ds.default_graph) == 1


def test_graph_level_forms_of_the_graph_methods(pair):
    d, g = pair
    assert bumps(lambda: d.add_graph(OTHER))
    assert d.has_graph(OTHER)
    assert set(d.named_graphs()) == {G, OTHER}  # ds.graph(G) listed G already
    g.add((S, P, OBJ))
    assert set(g.named_graphs()) >= {OTHER}
    d.graph(OTHER).add((S, P, OBJ))
    assert bumps(lambda: d.clear_graph(OTHER))
    assert d.has_graph(OTHER) and len(d.graph(OTHER)) == 0
    d.default_graph.add((S, P, OBJ))
    d.clear_graph()
    assert len(d.default_graph) == 0
    assert bumps(lambda: g.remove_graph())
    assert not d.has_graph(G) and d.has_graph(OTHER)
    plain = StarLayerGraph()
    plain.add((S, P, OBJ))
    plain.remove_graph()
    assert len(plain) == 0
