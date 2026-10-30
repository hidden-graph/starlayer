"""Blank-node labels are scoped to one document; a query sees data parsed through rdflib; triples(context=) (GitHub issue #99)."""

import warnings

import pytest
from rdflib import BNode, Namespace
from starlayer import StarLayerDataset, StarLayerGraph

warnings.simplefilter("ignore")
E = Namespace("http://e/")
P = "@prefix : <http://e/> . "

ONE_TRIPLE = {
    "nt12": "_:b <http://e/p> <http://e/o> .\n",
    "nq12": "_:b <http://e/p> <http://e/o> .\n",
    "turtle12": P + "_:b :p :o .\n",
    "trig12": P + "_:b :p :o .\n",
}


def _subjects(container) -> set:
    return {s for s, _, _ in container.triples((None, None, None))}


@pytest.mark.parametrize("fmt", list(ONE_TRIPLE))
@pytest.mark.parametrize("kind", ["graph", "dataset"])
def test_a_label_in_two_documents_is_two_blank_nodes(fmt, kind):
    container = StarLayerGraph() if kind == "graph" else StarLayerDataset(default_union=True)
    container.parse(data=ONE_TRIPLE[fmt], format=fmt)
    container.parse(data=ONE_TRIPLE[fmt], format=fmt)
    subjects = _subjects(container)
    assert len(subjects) == 2
    assert all(isinstance(s, BNode) for s in subjects)


def test_a_label_in_one_turtle_document_is_one_blank_node():
    g = StarLayerGraph()
    g.parse(data=P + "_:b :p :o . _:b :q :r . :s :t _:b .", format="turtle12")
    assert len(g) == 3
    assert len({n for s, _, o in g for n in (s, o) if isinstance(n, BNode)}) == 1


def test_a_label_is_one_blank_node_across_the_graph_blocks_of_one_trig_document():
    ds = StarLayerDataset()
    ds.parse(data=P + "GRAPH :g1 { _:b :p :o } GRAPH :g2 { _:b :q :r }", format="trig12")
    assert len({s for c in ds.contexts() for s, _, _ in c}) == 1


def test_a_label_is_one_blank_node_in_one_n_quads_document():
    ds = StarLayerDataset()
    ds.parse(data="_:a <http://e/p> _:a .\n_:a <http://e/q> <http://e/r> .\n", format="nq12")
    assert len({n for s, _, o, _ in ds.quads() for n in (s, o) if isinstance(n, BNode)}) == 1


RDFXML = (
    '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:e="http://e/">'
    '<rdf:Description rdf:nodeID="b"><e:p rdf:nodeID="b"/></rdf:Description></rdf:RDF>'
)


def test_rdfxml_node_ids_are_one_blank_node_per_document():
    g = StarLayerGraph()
    g.parse(data=RDFXML, format="rdfxml12")
    (s, _, o), = list(g)
    assert s == o
    g.parse(data=RDFXML, format="rdfxml12")
    assert len(_subjects(g)) == 2


# --- a query after a parse that rdflib itself performs
JSON_LD = '[{"@id":"http://e/z","http://e/p":[{"@id":"http://e/y"}]}]'


def test_a_query_sees_data_added_by_a_json_ld_parse():
    ds = StarLayerDataset(default_union=True)
    ds.add((E.a, E.p, E.b))
    assert len(list(ds.query("SELECT * WHERE { ?s ?p ?o }"))) == 1
    ds.parse(data=JSON_LD, format="json-ld")
    assert len(ds) == 2
    assert len(list(ds.query("SELECT * WHERE { ?s ?p ?o }"))) == 2


def test_a_query_sees_data_added_by_a_single_graph_parse():
    ds = StarLayerDataset(default_union=True)
    ds.add((E.a, E.p, E.b))
    assert len(list(ds.query("SELECT * WHERE { ?s ?p ?o }"))) == 1
    ds.parse(data="<http://e/z> <http://e/p> <http://e/y> .", format="nt12")
    assert len(list(ds.query("SELECT * WHERE { ?s ?p ?o }"))) == 2


# --- triples(context=)
def test_triples_can_be_restricted_to_one_graph():
    ds = StarLayerDataset(default_union=True)
    ds.add((E.a, E.p, E.b))
    named = ds.graph(E.g)
    named.add((E.c, E.p, E.d))
    assert set(ds.triples((None, None, None))) == {(E.a, E.p, E.b), (E.c, E.p, E.d)}
    assert set(ds.triples((None, None, None), context=named)) == {(E.c, E.p, E.d)}
    assert set(ds.triples((None, None, None), context=E.g)) == {(E.c, E.p, E.d)}
    assert set(ds.triples((None, None, None), context=ds.default_graph)) == {(E.a, E.p, E.b)}


def test_a_label_in_two_trix_documents_is_two_blank_nodes():
    doc = '<TriX xmlns="http://www.w3.org/2004/03/trix/trix-1/"><graph><triple><id>b</id><uri>http://e/p</uri><uri>http://e/o</uri></triple></graph></TriX>'
    ds = StarLayerDataset(default_union=True)
    ds.parse(data=doc, format="trix12")
    ds.parse(data=doc, format="trix12")
    assert len(_subjects(ds)) == 2
