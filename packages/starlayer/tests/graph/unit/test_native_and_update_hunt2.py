"""Store fixes from the third hunt (GitHub issue #98)."""

import warnings

import pytest
from rdflib import URIRef
from starlayer.graph import StarLayerDataset, StarLayerGraph

warnings.simplefilter("ignore")
E = lambda n: URIRef("http://e/" + n)  # noqa: E731


def test_blank_node_labels_are_local_to_one_update_request():
    g = StarLayerGraph()
    g.update("INSERT DATA { _:a <http://e/p> 1 }")
    g.update("INSERT DATA { _:a <http://e/p> 2 }")
    assert len(set(g.subjects())) == 2


def test_the_same_label_inside_one_request_is_one_node():
    g = StarLayerGraph()
    g.update("INSERT DATA { _:a <http://e/p> 1 . _:a <http://e/q> 2 }")
    assert len(set(g.subjects())) == 1


def test_blank_node_labels_are_local_to_a_request_in_a_dataset_and_a_graph_block():
    d = StarLayerDataset()
    d.update("INSERT DATA { GRAPH <http://e/g> { _:a <http://e/p> 1 } }")
    d.update("INSERT DATA { GRAPH <http://e/g> { _:a <http://e/p> 2 } }")
    assert len(set(d.graph(E("g")).subjects())) == 2


def test_blank_node_inside_a_triple_term_in_insert_data_is_relabelled_consistently():
    g = StarLayerGraph()
    g.update("INSERT DATA { _:r <http://e/p> <<( _:r <http://e/q> 1 )>> }")
    assert len(g) == 1


@pytest.fixture
def oxigraph_store():
    oxrdflib = pytest.importorskip("oxrdflib")
    return oxrdflib.OxigraphStore()


def test_default_union_applies_to_queries_on_a_native_dataset(oxigraph_store):
    union = StarLayerDataset(store=oxigraph_store, backend="rdf-1.2", default_union=True)
    union.get_context(E("g1")).add((E("s"), E("p"), E("o")))
    assert len(list(union.query("SELECT * WHERE { ?s ?p ?o }"))) == 1


def test_a_native_dataset_without_default_union_still_isolates_the_default_graph():
    oxrdflib = pytest.importorskip("oxrdflib")
    isolated = StarLayerDataset(store=oxrdflib.OxigraphStore(), backend="rdf-1.2")
    isolated.get_context(E("g1")).add((E("s"), E("p"), E("o")))
    assert len(list(isolated.query("SELECT * WHERE { ?s ?p ?o }"))) == 0


def test_init_bindings_are_applied_on_a_native_store(oxigraph_store):
    graph = StarLayerGraph(store=oxigraph_store, backend="rdf-1.2")
    graph.add((E("a"), E("p"), E("b")))
    graph.add((E("b"), E("p"), E("a")))
    rows = list(graph.query("select ?s ?o where { ?s <http://e/p> ?o }", initBindings={"s": E("a")}))
    assert [(str(r[0]), str(r[1])) for r in rows] == [("http://e/a", "http://e/b")]
    rows = list(graph.query("select ?s ?o where { ?s <http://e/p> ?o }", initBindings={"o": E("a")}))
    assert [(str(r[0]), str(r[1])) for r in rows] == [("http://e/b", "http://e/a")]


def test_inject_init_bindings_skips_strings_comments_iris_and_a_construct_template():
    from starlayer.graph.backends.native import inject_init_bindings

    values = " VALUES (?s) { (<http://e/a>) } "
    binding = {"s": E("a")}
    assert inject_init_bindings("SELECT * { ?s ?p ?o }", binding) == "SELECT * {" + values + " ?s ?p ?o }"
    construct = inject_init_bindings("CONSTRUCT { ?s <http://e/q> ?o } WHERE { ?s <http://e/p> ?o }", binding)
    assert construct == "CONSTRUCT { ?s <http://e/q> ?o } WHERE {" + values + " ?s <http://e/p> ?o }"
    tricky = inject_init_bindings('SELECT ?s { ?s <http://e/p#x> "a { WHERE {" . # WHERE {\n ?s ?q ?o }', binding)
    assert tricky.startswith("SELECT ?s {" + values)
