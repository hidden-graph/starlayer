"""test_unbind_prefix: unbind on rdflib stores (oxrdflib, SimpleMemory) under the old class; deleted with it at D1."""

import pytest
from starlayer.graph import StarLayerGraph


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
