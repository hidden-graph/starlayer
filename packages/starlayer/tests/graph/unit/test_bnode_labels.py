"""``serialize(bnode_labels="short")``: blank nodes written as _:b0, _:b1, ..., stably, for the output only."""

import re

import pytest
from starlayer.graph import StarLayerDataset, StarLayerGraph, isomorphic

TTL = "@prefix ex: <http://example.org/> . ex:a ex:p _:x . _:x ex:q ex:b . ex:c ex:p _:x . ex:d ex:r [ ex:s 1 ] ."


def _graph():
    g = StarLayerGraph()
    g.parse(data=TTL, format="turtle")
    return g


def _labels(text):
    return sorted(set(re.findall(r"_:(\w+)", text)))


@pytest.mark.parametrize("fmt", ["turtle", "nt"])
def test_blank_nodes_get_short_labels_and_the_same_every_time(fmt):
    g = _graph()
    text = g.serialize(format=fmt, bnode_labels="short")
    assert _labels(text) == ["b0", "b1"]
    assert text == g.serialize(format=fmt, bnode_labels="short") == _graph().serialize(format=fmt, bnode_labels="short")


def test_the_default_keeps_the_long_ids_and_the_graph_is_not_changed():
    g = _graph()
    before = {t for t in g.triples()}
    assert all(len(label) > 16 for label in _labels(g.serialize(format="turtle")))
    g.serialize(format="turtle", bnode_labels="short")
    assert {t for t in g.triples()} == before


def test_the_output_is_the_same_graph_up_to_blank_node_names():
    g = _graph()
    again = StarLayerGraph()
    again.parse(data=g.serialize(format="turtle", bnode_labels="short"), format="turtle")
    assert isomorphic(g, again)


def test_pretty_and_datasets_and_blank_nodes_inside_triple_terms():
    assert set(_labels(_graph().serialize(format="turtle", pretty=True, bnode_labels="short"))) <= {"b0", "b1"}
    d = StarLayerDataset()
    d.parse(data="<urn:g> { _:x <urn:p> _:y }", format="trig")
    assert _labels(d.serialize(format="trig", bnode_labels="short")) == ["b0", "b1"]
    t = StarLayerGraph()
    t.parse(data="_:x <urn:p> <<( _:y <urn:q> <urn:o> )>> .", format="turtle")
    assert _labels(t.serialize(format="turtle", bnode_labels="short")) == ["b0", "b1"]


def test_a_graph_without_blank_nodes_is_written_as_before_and_other_values_are_refused():
    g = StarLayerGraph()
    g.parse(data="<urn:a> <urn:p> <urn:b> .", format="turtle")
    assert g.serialize(format="nt", bnode_labels="short") == g.serialize(format="nt")
    with pytest.raises(ValueError, match="bnode_labels"):
        g.serialize(bnode_labels="long")


def test_the_blank_nodes_of_the_basic_encoding_get_short_labels_too():
    g = StarLayerGraph()
    g.parse(data="<urn:a> <urn:says> <<( <urn:b> <urn:knows> <urn:c> )>> .", format="turtle")
    flat = g.serialize(format="nt", rdf_version="1.1", bnode_labels="short")
    assert _labels(flat) == ["b0"]
    assert _labels(g.serialize(format="turtle", rdf_version="1.1", bnode_labels="short", pretty=True)) == []  # written inline as [ ... ]
