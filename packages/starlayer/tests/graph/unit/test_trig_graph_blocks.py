"""TriG graph blocks without the GRAPH keyword (GitHub issue #47), checked against rdflib's TriG parser."""

import warnings

import pytest
from rdflib import BNode, Dataset, URIRef
from starlayer.graph import StarLayerDataset

warnings.simplefilter("ignore")
PREFIX = "@prefix ex: <http://e/> .\n"
E = lambda n: URIRef("http://e/" + n)  # noqa: E731

FORMS = {
    "GRAPH iri": "GRAPH <http://g/one> { ex:a ex:p 1 }",
    "iri": "<http://g/one> { ex:a ex:p 1 }",
    "prefixed name": "ex:one { ex:a ex:p 1 }",
    "bnode label": "_:b { ex:a ex:p 1 }",
    "default": "{ ex:a ex:p 1 }",
    "GRAPH prefixed": "GRAPH ex:one { ex:a ex:p 1 }",
}


def _shape(dataset, graph_of):
    """(graph kind or name, subject) pairs, so the two parsers can be compared without blank node labels."""
    out = set()
    for s, _p, _o, g in dataset.quads():
        ident = graph_of(g)
        kind = "default" if str(ident) == "urn:x-rdflib:default" else ("bnode" if isinstance(ident, BNode) else str(ident))
        out.add((kind, str(s)))
    return out


@pytest.mark.parametrize("label", list(FORMS))
def test_block_form_gives_the_same_quads_as_rdflib(label):
    text = PREFIX + FORMS[label]
    ours = StarLayerDataset()
    ours.parse(data=text, format="trig12")
    theirs = Dataset()
    theirs.parse(data=text, format="trig")
    assert _shape(ours, lambda g: g.identifier) == _shape(theirs, lambda g: g)


def test_anonymous_graph_label():
    ds = StarLayerDataset()
    ds.parse(data=PREFIX + "[] { ex:a ex:p 1 }", format="trig12")
    quads = list(ds.quads())
    assert len(quads) == 1
    assert isinstance(quads[0][3].identifier, BNode)


def test_mixed_forms_in_one_document():
    ds = StarLayerDataset()
    ds.parse(
        data=PREFIX + "ex:x ex:y ex:z .\n<http://g/1> { ex:a ex:p 1 }\nGRAPH ex:two { ex:b ex:p 2 }\n{ ex:c ex:p 3 }",
        format="trig12",
    )
    assert _shape(ds, lambda g: g.identifier) == {
        ("default", "http://e/x"),
        ("default", "http://e/c"),
        ("http://g/1", "http://e/a"),
        ("http://e/two", "http://e/b"),
    }


def test_sparql_style_prefix_before_a_bare_block_is_not_a_graph_label():
    ds = StarLayerDataset()
    ds.parse(data="PREFIX ex: <http://x/>\n{ ex:a ex:p 1 }", format="trig12")
    assert _shape(ds, lambda g: g.identifier) == {("default", "http://x/a")}


def test_an_annotation_inside_a_block_is_not_a_block():
    ds = StarLayerDataset()
    ds.parse(data=PREFIX + "<http://g/one> { ex:a ex:p 1 {| ex:r 2 |} }", format="trig12")
    assert len(list(ds.quads())) == 3


def test_prefix_declared_between_blocks_applies_to_the_next_block():
    ds = StarLayerDataset()
    ds.parse(data=PREFIX + "<http://g/1> { ex:a ex:p 1 }\n@prefix y: <http://y/> .\ny:g { y:b y:p 2 }", format="trig12")
    assert _shape(ds, lambda g: g.identifier) == {("http://g/1", "http://e/a"), ("http://y/g", "http://y/b")}


def test_the_writers_output_reads_back():
    ds = StarLayerDataset()
    ds.add((E("a"), E("p"), E("b")))
    ds.graph(E("g")).add((E("c"), E("p"), E("d")))
    again = StarLayerDataset()
    again.parse(data=ds.serialize(format="trig12"), format="trig12")
    assert _shape(again, lambda g: g.identifier) == _shape(ds, lambda g: g.identifier)
