"""RDFC canonicalization of graphs with triple terms and of StarLayerDataset (GitHub issue #103)."""

import warnings

from rdflib import BNode, Literal, URIRef
from starlayer.graph import StarLayerDataset, StarLayerGraph, TripleTerm
from starlayer.graph.rdfc import rdfc10_hash, to_canonical_nquads

warnings.simplefilter("ignore")
E = lambda n: URIRef("http://e/" + n)  # noqa: E731


def _graph(tt):
    g = StarLayerGraph()
    g.add((E("a"), E("p"), tt))
    return g


def test_a_ground_triple_term_canonicalizes():
    g = _graph(TripleTerm(E("s"), E("q"), E("o")))
    assert len(rdfc10_hash(g)) == 64
    assert to_canonical_nquads(g)


def test_a_triple_term_with_a_blank_node_canonicalizes_and_is_relabelling_invariant():
    def build(label):
        g = StarLayerGraph()
        g.add((E("a"), E("p"), TripleTerm(BNode(label), E("q"), Literal("x"))))
        g.add((BNode(label), E("r"), E("z")))
        return g

    assert rdfc10_hash(build("b1")) == rdfc10_hash(build("other"))


def test_nested_triple_terms_canonicalize():
    inner = TripleTerm(E("s"), E("q"), E("o"))
    assert len(rdfc10_hash(_graph(TripleTerm(E("x"), E("y"), inner)))) == 64


def test_different_triple_terms_hash_differently():
    one = rdfc10_hash(_graph(TripleTerm(E("s"), E("q"), E("o"))))
    two = rdfc10_hash(_graph(TripleTerm(E("s"), E("q"), E("o2"))))
    assert one != two


def test_a_starlayer_dataset_with_a_named_graph_canonicalizes():
    ds = StarLayerDataset()
    ds.graph(E("g")).add((E("a"), E("p"), Literal("x")))
    text = to_canonical_nquads(ds)
    assert text == '<http://e/a> <http://e/p> "x" <http://e/g> .\n'
