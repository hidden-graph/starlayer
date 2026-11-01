"""``format="manchester"`` (alias ``omn``) on the Oxigraph wrapper: the existing parser and serializer, store-independent."""

from __future__ import annotations

from starlayer.graph.compare import isomorphic
from starlayer.graph.oxgraph import OxDataset, OxGraph

TEXT = """Prefix: ex: <http://example.org/>
Ontology: <http://example.org/o>
Class: ex:A
    SubClassOf: ex:B
"""


def test_parse_manchester_matches_the_old_class():
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph

    old = StarLayerGraph()
    old.parse(data=TEXT, format="manchester")
    new = OxGraph().parse(data=TEXT, format="manchester")
    assert len(new) == len(old) == 3
    assert isomorphic(new, old)


def test_manchester_round_trip_and_alias_and_file(tmp_path):
    g = OxGraph().parse(data=TEXT, format="omn")
    out = g.serialize(format="manchester")
    assert "Class: <http://example.org/A>" in out and "SubClassOf: <http://example.org/B>" in out
    assert isomorphic(OxGraph().parse(data=out, format="manchester"), g)
    path = tmp_path / "o.omn"
    g.serialize(path, format="manchester")
    assert isomorphic(OxGraph().parse(path), g)  # the extension picks the format
    assert len(OxDataset().parse(data=TEXT, format="manchester")) == 3


def test_rdfxml12_is_an_alias_of_rdf_xml():
    g = OxGraph().parse(data=TEXT, format="manchester")
    assert isomorphic(OxGraph().parse(data=g.serialize(format="rdfxml12"), format="rdfxml12"), g)
