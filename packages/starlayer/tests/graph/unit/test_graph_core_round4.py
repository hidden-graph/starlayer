"""Dataset core fixes: graph-name identity, union triples(), native quads() and the native default graph in
serializer output (GitHub issues #99 and #98). Plain rdflib is the oracle where it has the same call."""

import warnings

import pyoxigraph as ox
import pytest
from rdflib import Literal as RdLiteral
from starlayer.graph.oxgraph import OxDataset

warnings.simplefilter("ignore")
E = lambda n: ox.NamedNode("http://e/" + n)  # noqa: E731


def Literal(value):  # noqa: N802
    return ox.Literal(value)


def TripleTerm(s, p, o):  # noqa: N802
    return ox.Triple(s, p, o)


def test_iri_and_bnode_graph_names_with_the_same_text_are_two_graphs():
    d = OxDataset()
    d.graph(ox.NamedNode("urn:abc")).add((E("a"), E("p"), E("1")))
    d.graph(ox.BlankNode("abc")).add((E("a"), E("p"), E("2")))
    names = sorted((type(q.graph_name).__name__, q.object.value) for q in d.quads())
    assert names == [("BlankNode", "http://e/2"), ("NamedNode", "http://e/1")]


def test_default_union_triples_yields_a_triple_in_several_graphs_once():
    def counts(d):
        d.graph(E("g1")).add((E("a"), E("p"), E("b")))
        d.graph(E("g2")).add((E("a"), E("p"), E("b")))
        d.graph(E("g2")).add((E("a"), E("p"), E("c")))
        return len(d), len(list(d.triples((None, None, None)))), len(list(d.query("select * {?s ?p ?o}")))

    assert counts(OxDataset(default_union=True)) == (2, 2, 2)


def test_quads_restore_a_triple_term():
    tt = TripleTerm(E("a"), E("p"), Literal("x"))
    d = OxDataset()
    d.graph(E("g1")).add((E("s"), E("p"), tt))
    assert [q.object for q in d.quads()] == [tt]


@pytest.mark.parametrize("text, expected", [("1e-50f", "0"), ("0.1f", "0.1"), ("1.5f", "1.5"), ("16777217f", "16777216"), ("1e-5f", "1e-05")])
def test_manchester_float_lexical_form_is_single_precision(text, expected):
    import struct

    from rdflib.namespace import XSD
    from starlayer.graph.parsers.manchester_parser import parse_manchester

    head = "Prefix: : <http://ex.org/>\nOntology: <http://ex.org/o>\nIndividual: a\n Facts: d "
    lits = [o for _, _, o in parse_manchester(head + text + "\n") if isinstance(o, RdLiteral) and o.datatype == XSD.float]
    assert [str(o) for o in lits] == [expected]
    # reads back as the single-precision value the source text means
    def single(x):
        return struct.unpack(">f", struct.pack(">f", float(x)))[0]

    assert single(expected) == single(text[:-1])


def test_serializers_include_the_default_graph():
    d = OxDataset()
    d.add((E("s"), E("p"), E("o")))
    d.graph(E("g1")).add((E("s"), E("p"), E("o2")))
    assert "<http://e/s> <http://e/p> <http://e/o> ." in d.serialize(format="nq12")
    assert "<http://e/o>" in d.serialize(format="trig12") or "http://e/o ." in d.serialize(format="trig12")
    assert len(list(d.quads())) == 2
