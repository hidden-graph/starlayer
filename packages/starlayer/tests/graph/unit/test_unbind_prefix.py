"""``unbind(prefix)`` on a graph and a dataset (GitHub issue #44)."""

import warnings

import pytest
from rdflib import URIRef
from starlayer.graph import StarLayerDataset, StarLayerGraph

warnings.simplefilter("ignore")
E = lambda n: URIRef("http://e/" + n)  # noqa: E731


def _graph():
    g = StarLayerGraph()
    g.bind("ex", "http://e/")
    g.add((E("a"), E("p"), E("b")))
    return g


def test_unbind_removes_the_binding_and_reports_it():
    g = _graph()
    assert g.unbind("ex") is True
    assert "ex" not in dict(g.namespaces())
    assert g.unbind("ex") is False  # already gone


def test_the_writers_stop_using_the_prefix():
    g = _graph()
    assert "ex:a" in g.serialize(format="turtle12")
    g.unbind("ex")
    assert "ex:" not in g.serialize(format="turtle12")


def test_the_namespace_can_be_bound_again_under_the_same_or_another_prefix():
    g = _graph()
    g.unbind("ex")
    g.bind("ex", "http://e/")
    assert dict(g.namespaces())["ex"] == URIRef("http://e/")
    g.unbind("ex")
    g.bind("other", "http://e/")
    assert "other:a" in g.serialize(format="turtle12")


def test_other_prefixes_are_untouched():
    g = _graph()
    g.bind("x", "http://x/")
    g.unbind("ex")
    assert dict(g.namespaces())["x"] == URIRef("http://x/")


def test_unknown_prefix_is_a_noop():
    assert _graph().unbind("nope") is False


def test_a_dataset_unbind_reaches_every_graph_handle():
    ds = StarLayerDataset()
    ds.bind("ex", "http://e/")
    handle = ds.graph(URIRef("http://g"))
    assert "ex" in dict(handle.namespaces())
    assert ds.unbind("ex") is True
    assert "ex" not in dict(handle.namespaces())
    assert "ex" not in dict(ds.namespaces())


def test_an_in_process_oxigraph_store_can_unbind():
    oxrdflib = pytest.importorskip("oxrdflib")
    g = StarLayerGraph(store=oxrdflib.OxigraphStore(), backend="rdf-1.2")
    g.bind("ex", "http://e/")
    assert g.unbind("ex") is True
    assert "ex" not in dict(g.namespaces())


def test_a_store_that_cannot_unbind_says_so():
    from rdflib.plugins.stores.memory import SimpleMemory

    g = StarLayerGraph(store=SimpleMemory())
    g.bind("ex", "http://e/")
    with pytest.raises(NotImplementedError, match="reduce_prefixes"):
        g.unbind("ex")
