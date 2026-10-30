"""Parser and serializer fixes from the second adversarial hunt (GitHub issue #73)."""

import warnings

import pytest
from rdflib import BNode, Literal, URIRef
from starlayer.graph import StarLayerGraph, TripleTerm

warnings.simplefilter("ignore")
E = "http://e/"


def _g(data, fmt="turtle12"):
    g = StarLayerGraph()
    g.parse(data=data, format=fmt)
    return g


def _round_trip(g, fmt):
    h = StarLayerGraph()
    h.parse(data=g.serialize(format=fmt), format=fmt)
    return h


@pytest.mark.parametrize("fmt", ["turtle12", "trig12"])
@pytest.mark.parametrize(
    "text",
    [
        f"PREFIX : <{E}> :a :p :z .",
        f"prefix : <{E}> :a :p :z .",
        f"BASE <{E}> <a> <p> <z> .",
        f"base <{E}> <a> <p> <z> .",
        f"PREFIX : <{E}>\n:a :p :z .",
        f"@prefix : <{E}> . :a :p :z .",
    ],
)
def test_sparql_style_directive_followed_by_a_triple_on_the_same_line(text, fmt):
    g = _g(text, fmt) if fmt == "turtle12" else StarLayerGraph().parse(data=text, format=fmt)
    assert set(g) == {(URIRef(E + "a"), URIRef(E + "p"), URIRef(E + "z"))}


def test_sparql_style_prefix_with_a_trailing_dot_is_still_accepted():
    assert len(_g(f"PREFIX : <{E}> .\n:a :p :z .")) == 1


@pytest.mark.parametrize("text", ["cr\rx", "a\r\nb", "\r", "trail\r"])
@pytest.mark.parametrize("fmt", ["turtle12", "trig12", "longturtle12", "rdfxml12"])
def test_carriage_return_in_a_literal_survives_a_round_trip(text, fmt):
    g = StarLayerGraph()
    g.add((URIRef(E + "a"), URIRef(E + "p"), Literal(text)))
    assert {str(o) for o in _round_trip(g, fmt).objects()} == {text}


def test_carriage_return_in_a_long_string_is_not_normalised_by_the_parser():
    g = _g(f'<{E}a> <{E}p> """a\rb""" .')
    assert [str(o) for o in g.objects()] == ["a\rb"]


@pytest.mark.parametrize("local", ["x.", "a.b.", "z..", "x#y", "-x"])
@pytest.mark.parametrize("fmt", ["turtle12", "trig12", "longturtle12"])
def test_writer_never_emits_an_invalid_prefixed_name(local, fmt):
    g = StarLayerGraph()
    g.add((URIRef(E + "a"), URIRef(E + "p"), URIRef(E + local)))
    g.add((URIRef(E + "a"), URIRef(E + "p"), URIRef(E + "y")))
    assert set(_round_trip(g, fmt)) == set(g)


def test_xml_lang_predicate_round_trips():
    g = StarLayerGraph()
    g.add((URIRef(E + "s"), URIRef("http://www.w3.org/XML/1998/namespace#lang"), Literal("x")))
    assert set(_round_trip(g, "turtle12")) == set(g)


@pytest.mark.parametrize(
    ("text", "triples"),
    [
        (rf'<{E}s> <{E}p> [ <{E}q> "a\"b" ] .', 2),
        (rf'<{E}s> <{E}p> ( "a\"b" ) .', 3),
        (rf"<{E}s> <{E}p> [ <{E}q> 'a\'b' ] .", 2),
        (f'<{E}s> <{E}p> [ <{E}q> """a]b""" ] .', 2),
        (f'<{E}s> <{E}p> [ <{E}q> "a]b" ] .', 2),
        (f"<{E}s> <{E}p> [ <{E}q> <{E}x]y> ] .", 2),
    ],
)
def test_brackets_and_escapes_inside_strings_do_not_end_a_blank_node_list(text, triples):
    assert len(_g(text)) == triples


def test_escaped_quote_in_a_blank_node_list_round_trips():
    g = StarLayerGraph()
    b = BNode("b")
    g.add((URIRef(E + "s"), URIRef(E + "p"), b))
    g.add((b, URIRef(E + "q"), Literal('a"b')))
    assert g.isomorphic(_round_trip(g, "turtle12"))


def test_blank_node_label_with_an_inner_dot_in_ntriples():
    # a label is scoped to its document and not kept as the node's identifier, so "a.b" read whole is seen by comparing nodes
    g = StarLayerGraph().parse(data=f"_:a.b <{E}p> _:a.b .\n_:a <{E}p> _:a.b .\n", format="nt12")
    assert len(set(g.subjects())) == 2
    assert len(set(g.objects())) == 1
    g = StarLayerGraph().parse(data=f"<{E}s> <{E}p> _:c.\n", format="nt12")
    assert len(g) == 1
    assert all(isinstance(o, BNode) for o in g.objects())


def test_blank_node_inside_a_triple_term_keeps_its_label_in_the_writer():
    b = BNode("b")
    g = StarLayerGraph()
    g.add((URIRef(E + "s"), URIRef(E + "p"), TripleTerm(b, URIRef(E + "p"), URIRef(E + "o"))))
    g.add((URIRef(E + "s"), URIRef(E + "q"), b))
    g.add((b, URIRef(E + "r"), URIRef(E + "x")))
    for fmt in ("turtle12", "trig12", "longturtle12"):
        assert g.isomorphic(_round_trip(g, fmt)), fmt


def test_empty_iri_prefix_and_base_are_declarations():
    assert set(_g(f"BASE <{E}>\nPREFIX : <>\n:a :p :z .")) == {
        (URIRef(E + "a"), URIRef(E + "p"), URIRef(E + "z"))
    }


def test_rdfxml_writer_survives_an_ns_numbered_prefix():
    g = StarLayerGraph()
    g.bind("ns1", E)
    g.add((URIRef(E + "a"), URIRef(E + "p"), Literal("x")))
    assert set(_round_trip(g, "rdfxml12")) == set(g)


def test_rdfxml_writer_rejects_a_predicate_that_cannot_be_a_qname():
    g = StarLayerGraph()
    g.add((URIRef(E + "s"), URIRef(E + "p#"), URIRef(E + "o")))
    with pytest.raises(ValueError, match="QName"):
        g.serialize(format="rdfxml12")
