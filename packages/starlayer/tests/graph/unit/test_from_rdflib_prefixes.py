"""``from_rdflib`` keeps the prefixes the data uses, not the thirty rdflib binds to every graph."""

from __future__ import annotations

import pytest

rdflib = pytest.importorskip("rdflib")

from starlayer.graph import StarLayerDataset, StarLayerGraph  # noqa: E402

TTL = """
@prefix ex: <http://example.org/> .
@prefix unused: <http://unused.example/> .
ex:a ex:p "x" ; ex:q 1 ; ex:r "d"^^<http://www.w3.org/2001/XMLSchema#date> .
"""


def test_a_graph_keeps_only_the_prefixes_its_data_uses():
    r = rdflib.Graph()
    r.parse(data=TTL, format="turtle")
    assert len(dict(r.namespaces())) > 20  # rdflib's defaults, used or not
    g = StarLayerGraph.from_rdflib(r)
    assert set(g.prefixes) == {"ex", "xsd"}  # xsd: the date datatype; unused: and the other defaults are gone


def test_a_dataset_keeps_only_the_prefixes_its_data_uses():
    r = rdflib.Dataset()
    r.graph(rdflib.URIRef("http://example.org/g")).parse(data=TTL, format="turtle")
    d = StarLayerDataset.from_rdflib(r)
    assert set(d.prefixes) == {"ex", "xsd"}
