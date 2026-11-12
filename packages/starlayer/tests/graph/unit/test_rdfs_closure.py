"""The native RDFS closure behind ``infer(ENTAILMENT.RDFS)`` equals owlrl's ``RDFS_Semantics`` (the oracle) on the graphs StarLayer feeds it."""

import random
import warnings

import pyoxigraph as ox
import pytest
from starlayer.graph import ENTAILMENT
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.graph.oxgraph.helpers import entailment
from starlayer.graph.oxgraph.helpers.rdfs_closure import rdfs_delta

warnings.simplefilter("ignore")
pytest.importorskip("owlrl")

PRE = "@prefix : <http://e/> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . @prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
RDFS_REGIME = frozenset({entailment.RDFS_REGIME})


def _oracle(g):
    return entailment._owlrl_delta(g, RDFS_REGIME)


def _graph(ttl):
    g = StarLayerGraph()
    g.parse(data=PRE + ttl, format="turtle12")
    return g


def _assert_same(g):
    native = rdfs_delta(g.triples())
    oracle = _oracle(g)
    assert native == oracle, (sorted(map(str, native - oracle))[:5], sorted(map(str, oracle - native))[:5])


GRAPHS = {
    "empty": "",
    "chain": ":A rdfs:subClassOf :B . :B rdfs:subClassOf :C . :C rdfs:subClassOf :A . :x a :A .",
    "domain_range": ":p rdfs:domain :A ; rdfs:range :B ; rdfs:subPropertyOf :q . :q rdfs:range rdfs:Literal . :x :p :y . :x :lit 'a', 4 .",
    "subproperty_cycle": ":p rdfs:subPropertyOf :q . :q rdfs:subPropertyOf :p . :a :p :b . :p rdfs:domain :D .",
    "schema_terms": "rdfs:subClassOf rdfs:domain :Z . :Z a rdfs:Class . :M a rdfs:ContainerMembershipProperty . :T a rdfs:Datatype . :a :M :b .",
    "containers": "[] rdf:_1 :a ; rdf:_2 :b . rdf:_1 rdfs:range :R . :a a :K .",
    "bnodes_literals": "_:b rdfs:subPropertyOf [] . _:b :p 'x'@en . :p rdfs:range :R . :q :p 'v' . :a :p _:b .",
    "literal_class": ":p rdfs:range 'weird' . :a :p :b . :b rdfs:subClassOf :C .",
    "triple_terms": ":r rdf:reifies <<( :s :p :o )>> . :p rdfs:domain :D . :q :p <<( :a :b <<( :c :d :e )>> )>> .",
    "property_of_property": ":sub rdfs:subPropertyOf rdfs:subPropertyOf . :a :sub :b .",
}


@pytest.mark.parametrize("name", GRAPHS)
def test_native_closure_equals_owlrl(name):
    _assert_same(_graph(GRAPHS[name]))


def test_the_shacl_vocabulary_and_a_shapes_graph_close_identically():
    from starlayer import starontology

    g = StarLayerGraph()
    g.extend(list(starontology.get_ontology_graph("shacl_vocabulary").triples((None, None, None))))
    g.parse(
        data=PRE
        + "@prefix sh: <http://www.w3.org/ns/shacl#> . :S a sh:NodeShape ; sh:targetClass :C ; sh:property [ sh:path :p ; sh:minCount 1 ; sh:group :G ; sh:or ( [ sh:class :D ] [ sh:datatype :T ] ) ] .",
        format="turtle12",
    )
    _assert_same(g)


def test_infer_uses_the_native_closure_in_every_mode_and_for_rdf_plus_rdfs(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("owlrl was used")

    monkeypatch.setattr(entailment, "_owlrl_delta", refuse)
    g = _graph(GRAPHS["domain_range"])
    delta = g.infer(ENTAILMENT.RDFS, mode="delta")
    assert (ox.NamedNode("http://e/x"), ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), ox.NamedNode("http://e/A")) in delta.triples()
    assert len(g.infer(ENTAILMENT.RDFS, mode="full")) == len(g) + len(delta)
    combined = g.infer([ENTAILMENT.RDF, ENTAILMENT.RDFS], mode="delta")
    assert set(delta.triples()) <= set(combined.triples())
    n = len(g)
    g.infer(ENTAILMENT.RDFS, mode="in-place")
    assert len(g) == n + len(delta)


_NAMES = [ox.NamedNode("http://e/" + n) for n in "abcdp"]
_SCHEMA = [ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#" + n) for n in ("subClassOf", "subPropertyOf", "domain", "range", "Class", "Datatype", "Literal", "ContainerMembershipProperty", "member")]
_RDFT = [ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#" + n) for n in ("type", "Property", "_1")]
_NODES = _NAMES + _SCHEMA + _RDFT + [ox.BlankNode("b1"), ox.BlankNode("b2"), ox.Literal("x"), ox.Literal("y", language="en")]
_PREDS = _NAMES + _SCHEMA[:4] + _RDFT[:1] + _RDFT[2:]


@pytest.mark.parametrize("seed", range(300))
def test_random_graphs_close_identically(seed):
    rng = random.Random(seed)
    g = StarLayerGraph()
    rows = [(rng.choice(_NODES), rng.choice(_PREDS), rng.choice(_NODES)) for _ in range(rng.randint(0, 14))]
    g.extend([t for t in rows if not isinstance(t[0], ox.Literal)])
    _assert_same(g)
