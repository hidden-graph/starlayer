"""Leftovers of GitHub issues #72 (triple-term encoding, isomorphism, skolemize), #75 (native dirLangString
and blank-node labels) and #83 (resolve_imports, RDF closure)."""

import warnings

import pytest
from rdflib import BNode, URIRef
from starlayer.graph import StarLayerGraph

warnings.simplefilter("ignore")
E = lambda n: URIRef("http://e/" + n)  # noqa: E731


@pytest.fixture
def native():
    ox = pytest.importorskip("pyoxigraph")
    OxigraphStore = pytest.importorskip("oxrdflib").OxigraphStore
    return lambda: StarLayerGraph(store=OxigraphStore(store=ox.Store()), backend="rdf-1.2")


# --- #72 ---











# --- #75 ---





@pytest.mark.parametrize("label", ["a b", "a<b", 'a"b', "a\\b", "a|b", "a{b", "a`b", "a^b", "a\nb", "a%20b"])
def test_native_blank_node_label_that_is_not_iri_safe(native, label):
    g = native()
    g.add((E("s"), E("p"), BNode(label)))
    assert list(g.objects(E("s"), E("p"))) == [BNode(label)]
    assert g.value(E("s"), E("p")) == BNode(label)


def test_native_addn_with_an_unsafe_blank_node_label(native):
    g = native()
    g.addN([(E("s"), E("p"), BNode("x y"), g)])
    assert len(g) == 1


# --- #83 ---



