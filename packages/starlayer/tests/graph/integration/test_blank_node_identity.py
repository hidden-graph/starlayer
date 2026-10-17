"""Blank-node identity through a store: the same behaviour on every engine.

A blank node's label is only meaningful inside the response that carried it
(SPARQL 1.1 Query Results JSON sec 3.2.2). Oxigraph happens to return stable
ids; Fuseki numbers them per response (b0, b1, ...), so two different nodes can
carry the same label in successive queries. On an engine like that this
library stores blank nodes as skolem IRIs, turns them back into BNodes on the
way out, and rewrites isBLANK / isIRI / ORDER BY so they still behave as for
real blank nodes (graph/backends/skolem_semantics.py).

These tests run against an in-process Oxigraph always, and against the Oxigraph
and Fuseki servers when they are running. They are the focused regression for
what the W3C store matrix found (lists losing elements, merged annotations).
"""

from __future__ import annotations

import pytest
import requests
from rdflib import BNode, Literal, URIRef
from rdflib.graph import DATASET_DEFAULT_GRAPH_ID
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore
from starlayer.graph.graph import StarLayerGraph

EX = "http://example.org/"
REIFIES = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")

_SERVERS = {
    "oxigraph-http": ("http://localhost:7878", "http://localhost:7878/query", "http://localhost:7878/update"),
    "fuseki-http": ("http://localhost:3030/$/ping", "http://localhost:3030/starlayergraph/query", "http://localhost:3030/starlayergraph/update"),
}


def _up(name: str) -> bool:
    try:
        return requests.get(_SERVERS[name][0], timeout=2).status_code == 200
    except Exception:
        return False


@pytest.fixture(params=["in-process", *_SERVERS])
def new_graph(request):
    """A factory for a fresh, empty default-graph StarLayerGraph on the engine."""
    name = request.param
    if name == "in-process":
        pytest.importorskip("oxrdflib")
        pyoxigraph = pytest.importorskip("pyoxigraph")
        from oxrdflib import OxigraphStore

        def make():
            return StarLayerGraph(store=OxigraphStore(store=pyoxigraph.Store()), backend="rdf-1.2")

        yield make
        return
    if not _up(name):
        pytest.skip(f"{name} not running")
    _, query_url, update_url = _SERVERS[name]

    def clear():
        requests.post(update_url, data="CLEAR SILENT DEFAULT",
                      headers={"Content-Type": "application/sparql-update"}, timeout=10).raise_for_status()

    def make():
        clear()
        store = SPARQLUpdateStore(query_endpoint=query_url, update_endpoint=update_url)
        return StarLayerGraph(store=store, identifier=DATASET_DEFAULT_GRAPH_ID, backend="rdf-1.2")

    yield make
    clear()


def _ttl(body: str) -> str:
    return f"@prefix ex: <{EX}> .\n{body}"


def test_two_lists_sharing_a_value_are_read_back_correctly(new_graph):
    """Fuseki labels the first and second cell of a list 'b0' in successive
    queries; Graph.items() used to read that as a cycle and raise."""
    g = new_graph()
    g.parse(data=_ttl('ex:a ex:p ( "big" "small" ) .\nex:b ex:p ( "big" ) .'), format="turtle12")
    head_a = next(g.objects(URIRef(EX + "a"), URIRef(EX + "p")))
    head_b = next(g.objects(URIRef(EX + "b"), URIRef(EX + "p")))
    assert [str(x) for x in g.items(head_a)] == ["big", "small"]
    assert [str(x) for x in g.items(head_b)] == ["big"]


def test_two_reifiers_of_one_triple_keep_their_own_annotations(new_graph):
    """One triple, two anonymous reifiers. They look identical from outside
    (both reify the same triple term), and on Fuseki used to be merged: each
    reported the other's annotation too."""
    g = new_graph()
    g.parse(data=_ttl("ex:alice ex:knows ex:bob {| ex:confidence 0.9 |} {| ex:source ex:wikipedia |} ."),
            format="turtle12")
    per_reifier = []
    for reifier, _, _tt in g.triples((None, REIFIES, None)):
        confidence = sorted(str(x) for x in g.objects(reifier, URIRef(EX + "confidence")))
        source = sorted(str(x).rsplit("/", 1)[-1] for x in g.objects(reifier, URIRef(EX + "source")))
        per_reifier.append((tuple(confidence), tuple(source)))
    assert sorted(per_reifier) == [((), ("wikipedia",)), (("0.9",), ())]


def test_a_blank_node_with_no_such_triple_returns_nothing(new_graph):
    """An empty answer is a legitimate answer: it must not fall back to a
    look-alike node's values."""
    g = new_graph()
    g.parse(data=_ttl("ex:s ex:p [ ex:q 1 ] , [ ex:r 2 ] ."), format="turtle12")
    nodes = list(g.objects(URIRef(EX + "s"), URIRef(EX + "p")))
    assert len(nodes) == 2
    with_q = [n for n in nodes if list(g.objects(n, URIRef(EX + "q")))]
    with_r = [n for n in nodes if list(g.objects(n, URIRef(EX + "r")))]
    assert len(with_q) == 1 and len(with_r) == 1 and with_q != with_r
    assert list(g.objects(with_q[0], URIRef(EX + "r"))) == []


def test_order_by_puts_blank_nodes_before_iris_before_literals(new_graph):
    """SPARQL 1.1 sec 15.1: blank nodes, then IRIs, then literals."""
    g = new_graph()
    g.parse(data=_ttl('ex:s1 ex:p "lit" .\nex:s2 ex:p ex:iri .\nex:s3 ex:p [ ex:q 1 ] .'), format="turtle12")
    rows = [row[0] for row in g.query(f"SELECT ?x WHERE {{ ?s <{EX}p> ?x }} ORDER BY ?x")]
    assert [type(r) for r in rows] == [BNode, URIRef, Literal]
    rows = [row[0] for row in g.query(f"SELECT ?x WHERE {{ ?s <{EX}p> ?x }} ORDER BY DESC(?x)")]
    assert [type(r) for r in rows] == [Literal, URIRef, BNode]


def test_isblank_and_isiri_see_blank_nodes_as_blank(new_graph):
    g = new_graph()
    g.parse(data=_ttl('ex:s1 ex:p "lit" .\nex:s2 ex:p ex:iri .\nex:s3 ex:p [ ex:q 1 ] .'), format="turtle12")

    def count(flt):
        result = g.query(f"SELECT (COUNT(*) AS ?n) WHERE {{ ?s <{EX}p> ?x FILTER({flt}) }}")
        return int(next(iter(result))[0])

    assert count("isBLANK(?x)") == 1
    assert count("!isBLANK(?x)") == 2
    assert count("isIRI(?x)") == 1
    assert count("isLiteral(?x)") == 1
