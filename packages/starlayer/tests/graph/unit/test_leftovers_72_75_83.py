"""Leftovers of GitHub issues #72 (triple-term encoding, isomorphism, skolemize), #75 (native dirLangString
and blank-node labels) and #83 (resolve_imports, RDF closure)."""

import warnings

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF
from starlayer.graph import DirLangString, StarLayerGraph, TripleTerm
from starlayer.graph.graph.entailment_regimes import ENTAILMENT

warnings.simplefilter("ignore")
E = lambda n: URIRef("http://e/" + n)  # noqa: E731


@pytest.fixture
def native():
    ox = pytest.importorskip("pyoxigraph")
    OxigraphStore = pytest.importorskip("oxrdflib").OxigraphStore
    return lambda: StarLayerGraph(store=OxigraphStore(store=ox.Store()), backend="rdf-1.2")


# --- #72 ---

def test_remove_of_last_use_drops_the_triple_term_and_its_encoding():
    tt = TripleTerm(E("a"), E("p"), E("b"))
    g = StarLayerGraph()
    g.add((E("s"), E("q"), tt))
    g.remove((E("s"), E("q"), tt))
    g.add((E("s"), E("p"), E("o")))
    h = StarLayerGraph()
    h.add((E("s"), E("p"), E("o")))
    assert g.isomorphic(h) and h.isomorphic(g)
    assert list(g.triple_terms()) == [] and not g.has_triple_term(E("a"), E("p"), E("b"))
    assert len(list(Graph.triples(g, (None, None, None)))) == 1


def test_remove_keeps_a_triple_term_still_used_and_cascades_to_nested_terms():
    inner = TripleTerm(E("a"), E("p"), E("b"))
    outer = TripleTerm(E("x"), E("r"), inner)
    g = StarLayerGraph()
    g.add((E("s1"), E("q"), outer))
    g.add((E("s2"), E("q"), outer))
    g.remove((E("s1"), E("q"), outer))
    assert g.has_triple_term(E("x"), E("r"), inner)
    g.remove((E("s2"), E("q"), outer))
    assert list(g.triple_terms()) == []
    assert len(list(Graph.triples(g, (None, None, None)))) == 0


def test_isomorphic_ignores_language_tag_case():
    g, h = StarLayerGraph(), StarLayerGraph()
    g.add((E("s"), E("p"), Literal("a", lang="en")))
    h.add((E("s"), E("p"), Literal("a", lang="EN")))
    assert g.isomorphic(h)
    g, h = StarLayerGraph(), StarLayerGraph()
    g.add((E("s"), E("p"), TripleTerm(E("a"), E("b"), Literal("a", lang="en"))))
    h.add((E("s"), E("p"), TripleTerm(E("a"), E("b"), Literal("a", lang="EN"))))
    assert g.isomorphic(h)


def test_skolemize_replaces_blank_nodes_inside_triple_terms_consistently():
    b = BNode("x1")
    g = StarLayerGraph()
    g.add((E("x"), E("s"), b))
    g.add((E("y"), E("s"), TripleTerm(E("q"), E("r"), b)))
    sk = g.skolemize()
    (skolem,) = [o for _, _, o in sk.triples((E("x"), E("s"), None))]
    assert isinstance(skolem, URIRef)
    (tt,) = [o for _, _, o in sk.triples((E("y"), E("s"), None))]
    assert tt == TripleTerm(E("q"), E("r"), skolem)
    assert sk.de_skolemize().isomorphic(g)


def test_skolemize_triple_term_subject_position():
    g = StarLayerGraph()
    g.add((E("x"), E("s"), TripleTerm(BNode("x1"), E("b"), E("c"))))
    (tt,) = [o for _, _, o in g.skolemize().triples((None, None, None))]
    assert isinstance(tt.subject, URIRef)


# --- #75 ---

def test_dirlangstring_with_uppercase_tag_in_a_query_pattern_matches():
    g = StarLayerGraph()
    g.add((E("b"), E("p"), DirLangString("x", "en", "ltr")))
    assert g.query('ASK {?s <http://e/p> "x"@EN--ltr}').askAnswer
    assert len(list(g.query('SELECT * {?s <http://e/p> "x"@EN--ltr}'))) == 1


@pytest.mark.parametrize("text", ["a\nb", "a\rb", "a\r\nb"])
def test_native_dirlangstring_with_line_breaks_round_trips(native, text):
    g = native()
    g.add((E("s"), E("p"), DirLangString(text, "en", "ltr")))
    assert list(g.objects(E("s"), E("p"))) == [DirLangString(text, "en", "ltr")]


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

def test_resolve_imports_follows_imports_declared_on_a_different_ontology_iri():
    a = StarLayerGraph()
    a.add((E("A"), RDF.type, OWL.Ontology))
    a.add((E("A"), OWL.imports, E("B")))

    def loader(iri):
        h = StarLayerGraph()
        if iri == E("B"):
            h.add((E("B-ont"), RDF.type, OWL.Ontology))
            h.add((E("B-ont"), OWL.imports, E("C")))
            h.add((E("x"), E("p"), E("y")))
            return h
        if iri == E("C"):
            h.add((E("z"), E("p"), E("w")))
            return h
        return None

    r = a.resolve_imports(loader=loader)
    assert (E("z"), E("p"), E("w")) in r
    assert set(r.resolve_imports(loader=loader)) == set(r)


def test_infer_rdf_is_a_closure():
    g = StarLayerGraph()
    g.add((E("a"), E("p"), E("b")))
    f = g.infer(ENTAILMENT.RDF)
    assert (RDF.type, RDF.type, RDF.Property) in f
    assert set(f.infer(ENTAILMENT.RDF)) == set(f)
