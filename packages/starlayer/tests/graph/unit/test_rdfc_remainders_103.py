"""Leftovers of issue #103 (RDFC and compare): datasets with triple terms,
dataset comparison, method/function agreement, language-tag case, the
collision with the internal namespace, hash-algorithm validation."""

import warnings

import pytest
from rdflib import BNode, Dataset, Graph, Literal, Namespace, URIRef
from rdflib.namespace import XSD
from starlayer.graph import StarLayerDataset, StarLayerGraph
from starlayer.graph.compare import (
    graph_diff,
    isomorphic,
    to_canonical_hash,
    to_isomorphic,
)
from starlayer.graph.rdfc import rdfc10_hash, to_canonical_nquads

E = Namespace("http://e/")
_TT = "urn:starlayer:canon-tt#"


@pytest.fixture(autouse=True)
def _quiet():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield


def _tt_dataset(label: str) -> StarLayerDataset:
    ds = StarLayerDataset()
    ds.parse(
        data="<http://e/g> { <http://e/s> <http://e/q> <<( _:" + label + " <http://e/p> <http://e/o> )>> . }",
        format="trig12",
    )
    return ds


def test_dataset_with_triple_term_canonicalizes():
    text = to_canonical_nquads(_tt_dataset("x"))
    assert text.count("<http://e/g> .") == 4  # the quad and the three decomposition edges, all in the graph
    assert rdfc10_hash(_tt_dataset("x")) == rdfc10_hash(_tt_dataset("other"))


def test_dataset_isomorphism_counts_graph_names_and_triple_terms():
    assert isomorphic(_tt_dataset("x"), _tt_dataset("y"))
    d1, d2 = Dataset(), Dataset()
    d1.graph(URIRef("http://e/g1")).add((E.s, E.p, Literal("x")))
    d2.graph(URIRef("http://e/g2")).add((E.s, E.p, Literal("x")))
    assert isomorphic(d1, d1)
    assert not isomorphic(d1, d2)
    assert to_canonical_hash(d1) != to_canonical_hash(d2)


def test_graph_diff_and_to_isomorphic_reject_a_dataset_clearly():
    d = Dataset()
    with pytest.raises(TypeError, match="dataset"):
        graph_diff(d, d)
    with pytest.raises(TypeError, match="dataset"):
        to_isomorphic(d)


def test_isomorphic_method_agrees_with_function_on_xsd_string():
    a, b = StarLayerGraph(), StarLayerGraph()
    a.add((E.a, E.p, Literal("x", datatype=XSD.string)))
    b.add((E.a, E.p, Literal("x")))
    assert a.isomorphic(b) is isomorphic(a, b) is True


def test_language_tag_case_does_not_change_the_canonical_form():
    g1, g2 = Graph(), Graph()
    g1.add((E.a, E.p, Literal("x", lang="en-US")))
    g2.add((E.a, E.p, Literal("x", lang="EN-us")))
    assert to_canonical_nquads(g1) == to_canonical_nquads(g2)
    assert rdfc10_hash(g1) == rdfc10_hash(g2)


def test_a_blank_node_with_the_internal_edges_is_not_a_triple_term():
    c = StarLayerGraph()
    c.parse(data="<http://e/s1> <http://e/q> <<( <http://e/a> <http://e/p> <http://e/o> )>> .", format="turtle12")
    d = Graph()
    n = BNode()
    d.add((E.s1, E.q, n))
    for k, v in (("subject", E.a), ("predicate", E.p), ("object", E.o)):
        d.add((n, URIRef(_TT + k), v))
    assert not isomorphic(c, d)
    assert rdfc10_hash(c) != rdfc10_hash(d)


@pytest.mark.parametrize("name", ["new", "__name__", "algorithms_available", "foo", "shake_128", 5])
def test_bad_hash_algorithm_is_a_value_error(name):
    with pytest.raises(ValueError, match="Unsupported hash algorithm"):
        rdfc10_hash(Graph(), name)
