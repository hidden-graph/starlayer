"""Dataset core fixes: graph-name identity, union triples(), native quads() and the native default graph in
serializer output (GitHub issues #99 and #98). Plain rdflib is the oracle where it has the same call."""

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


def test_default_union_triples_yields_a_triple_in_several_graphs_once():
    def counts(d):
        d.graph(E("g1")).add((E("a"), E("p"), E("b")))
        d.graph(E("g2")).add((E("a"), E("p"), E("b")))
        d.graph(E("g2")).add((E("a"), E("p"), E("c")))
        return len(d), len(list(d.triples((None, None, None)))), len(list(d.query("select * {?s ?p ?o}")))

    assert counts(StarLayerDataset(default_union=True)) == counts(Dataset(default_union=True)) == (2, 2, 2)


def test_native_quads_restore_a_triple_term_like_the_in_memory_store(native_dataset):
    tt = TripleTerm(E("a"), E("p"), Literal("x"))
    for d in (StarLayerDataset(), native_dataset()):
        d.get_context(E("g1")).add((E("s"), E("p"), tt))
        assert [q[2] for q in d.quads()] == [tt]


@pytest.mark.parametrize("text, expected", [("1e-50f", "0"), ("0.1f", "0.1"), ("1.5f", "1.5"), ("16777217f", "16777216"), ("1e-5f", "1e-05")])
def test_manchester_float_lexical_form_is_single_precision(text, expected):
    import struct

    from rdflib.namespace import XSD
    from starlayer.graph.parsers.manchester_parser import parse_manchester

    head = "Prefix: : <http://ex.org/>\nOntology: <http://ex.org/o>\nIndividual: a\n Facts: d "
    lits = [o for _, _, o in parse_manchester(head + text + "\n") if isinstance(o, Literal) and o.datatype == XSD.float]
    assert [str(o) for o in lits] == [expected]
    # reads back as the single-precision value the source text means
    def single(x):
        return struct.unpack(">f", struct.pack(">f", float(x)))[0]

    assert single(expected) == single(text[:-1])


def test_native_serializers_include_the_default_graph(native_dataset):
    d = native_dataset()
    d.add((E("s"), E("p"), E("o")))
    d.get_context(E("g1")).add((E("s"), E("p"), E("o2")))
    assert "<http://e/s> <http://e/p> <http://e/o> ." in d.serialize(format="nq12")
    assert "ns1:o ." in d.serialize(format="trig12")
    assert "http://e/o</uri>" in d.serialize(format="trix12")
    assert len(list(d.quads())) == 2
