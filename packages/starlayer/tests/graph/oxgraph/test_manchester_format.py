"""``format="manchester"`` (alias ``omn``) on the Oxigraph wrapper: the existing parser and serializer, store-independent."""

from __future__ import annotations

import pyoxigraph as ox
from starlayer.graph.compare import isomorphic
from starlayer.graph.oxgraph import OxDataset, OxGraph

TEXT = """Prefix: ex: <http://example.org/>
Ontology: <http://example.org/o>
Class: ex:A
    SubClassOf: ex:B
"""


def test_parse_manchester_gives_the_ontology_class_and_subclass_triples():
    # the expected triples are what the old class gave for the same text (3 triples)
    new = OxGraph().parse(data=TEXT, format="manchester")
    ex, rdf_type = (lambda n: ox.NamedNode("http://example.org/" + n)), ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
    owl = lambda n: ox.NamedNode("http://www.w3.org/2002/07/owl#" + n)  # noqa: E731
    assert set(new) == {
        (ex("o"), rdf_type, owl("Ontology")),
        (ex("A"), rdf_type, owl("Class")),
        (ex("A"), ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#subClassOf"), ex("B")),
    }


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
