"""The reification methods all take an optional argument and then answer for everything: reifiers(tt), reified_triples(reifier), annotations(tt)."""

import pyoxigraph as ox
from starlayer.graph import Namespace, StarLayerDataset, StarLayerGraph

EX = Namespace("http://example.org/")
T1 = ox.Triple(EX.a, EX.p, EX.b)
T2 = ox.Triple(EX.a, EX.q, EX.b)


def _graph():
    g = StarLayerGraph()
    g.add_reification(EX.r1, T1)
    g.add_reification(EX.r2, T1)
    g.add_reification(EX.r2, T2)
    g.add((EX.r1, EX.source, EX.hr))
    g.add((EX.r2, EX.source, EX.crm))
    g.add((EX.x, EX.p, EX.y))  # not reified
    return g


def test_reifiers_of_a_triple_term_and_of_all():
    g = _graph()
    assert set(g.reifiers()) == {EX.r1, EX.r2}
    assert set(g.reifiers(T1)) == {EX.r1, EX.r2} and set(g.reifiers(tt=T2)) == {EX.r2}
    assert set(g.reifiers(predicate=EX.source, object=EX.crm)) == {EX.r2}


def test_reified_triples_of_a_reifier_and_of_all():
    g = _graph()
    assert set(g.reified_triples(EX.r1)) == {T1} and set(g.reified_triples(EX.r2)) == {T1, T2}
    assert set(g.reified_triples()) == {T1, T2} and len(list(g.reified_triples())) == 2  # each once
    assert list(g.reified_triples(EX.x)) == []


def test_annotations_of_a_triple_term_and_of_all():
    g = _graph()
    assert set(g.annotations(T2)) == {(EX.r2, EX.source, EX.crm)}
    assert set(g.annotations()) == {(EX.r1, EX.source, EX.hr), (EX.r2, EX.source, EX.crm)}
    assert all(p != ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies") for _, p, _ in g.annotations())


def test_the_dataset_versions_keep_the_graph_each_triple_came_from():
    ds = StarLayerDataset()
    ds.graph(EX.g1).extend(_graph().triples())
    ds.graph(EX.g2).add_reification(EX.r3, T2)
    assert len(ds.reified_triples()) == 4  # r1 and r2 reify T1, r2 and r3 reify T2: four rdf:reifies triples
    assert {t[2] for t in ds.reified_triples(EX.r3).triples()} == {T2}
    assert len(ds.annotations()) == 2 and len(ds.annotations(T2)) == 1
    assert set(ds.reifiers(T2).graph(EX.g2).subjects()) == {EX.r3} and set(ds.reifiers(T2).graph(EX.g1).subjects()) == {EX.r2}
