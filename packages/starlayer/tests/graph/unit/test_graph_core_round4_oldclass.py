"""test_graph_core_round4: dataset tests over oxrdflib stores and rdflib terms (old class); deleted with it at D1."""

import warnings

import pytest
from rdflib import BNode, Dataset, Literal, URIRef
from starlayer.graph import StarLayerDataset, TripleTerm

warnings.simplefilter("ignore")
E = lambda n: URIRef("http://e/" + n)  # noqa: E731


@pytest.fixture
def native_dataset():
    ox = pytest.importorskip("pyoxigraph")
    OxigraphStore = pytest.importorskip("oxrdflib").OxigraphStore
    return lambda **kw: StarLayerDataset(store=OxigraphStore(store=ox.Store()), backend="rdf-1.2", **kw)


def test_uriref_and_bnode_graph_names_with_the_same_text_are_two_graphs():
    def shape(d):
        d.graph(URIRef("abc")).add((E("a"), E("p"), E("1")))
        d.graph(BNode("abc")).add((E("a"), E("p"), E("2")))
        return sorted((type(c.identifier).__name__, len(c)) for c in d.contexts() if len(c))

    assert shape(StarLayerDataset()) == shape(Dataset()) == [("BNode", 1), ("URIRef", 1)]


def test_native_quads_restore_a_triple_term_like_the_in_memory_store(native_dataset):
    tt = TripleTerm(E("a"), E("p"), Literal("x"))
    for d in (StarLayerDataset(), native_dataset()):
        d.get_context(E("g1")).add((E("s"), E("p"), tt))
        assert [q[2] for q in d.quads()] == [tt]


def test_native_serializers_include_the_default_graph(native_dataset):
    d = native_dataset()
    d.add((E("s"), E("p"), E("o")))
    d.get_context(E("g1")).add((E("s"), E("p"), E("o2")))
    assert "<http://e/s> <http://e/p> <http://e/o> ." in d.serialize(format="nq12")
    assert "ns1:o ." in d.serialize(format="trig12")
    assert len(list(d.quads())) == 2
