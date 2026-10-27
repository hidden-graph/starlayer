"""Parser and serializer bugs found by the adversarial hunt (GitHub issues #55 to #61 and #64).

For valid RDF 1.1 input the oracle is rdflib's own parser: StarLayer must produce an isomorphic graph.
"""

import pytest
import rdflib
from rdflib import Graph, Literal, URIRef
from rdflib.compare import isomorphic
from starlayer.graph import StarLayerDataset, StarLayerGraph
from starlayer.graph.parsers.errors import Turtle12SyntaxError

E = "http://e/"


def _rdf_term(triple):
    return tuple(
        Literal(str(x)) if isinstance(x, Literal) and x.datatype == rdflib.XSD.string and not x.language else x for x in triple
    )


def _starlayer(text: str, fmt: str = "turtle12") -> Graph:
    g = StarLayerGraph()
    g.parse(data=text, format=fmt)
    out = Graph()
    for t in g:
        out.add(t)
    return out


def _rdflib(text: str, fmt: str = "turtle") -> Graph:
    return Graph().parse(data=text, format=fmt)


def _agrees(text: str) -> None:
    assert isomorphic(_starlayer(text), _rdflib(text)), text


# --- #64 a '.' that ends a statement is not part of a name that follows it
@pytest.mark.parametrize(
    "text",
    [
        "@prefix ex: <http://e/> . ex:a ex:p 'x' .ex:b ex:p 'y' .",
        "@prefix ex: <http://e/> . ex:a ex:p <http://e/o> .ex:b ex:p 'y' .",
        "@prefix ex: <http://e/> . ex:a ex:p [ ex:q 1 ] .ex:b ex:p 'y' .",
        "@prefix ex: <http://e/> . ex:a ex:p ( 1 2 ) .ex:b ex:p 'y' .",
        "@prefix ex: <http://e/> . ex:a ex:p 'x'.ex:b ex:p 'y' .",
        "@prefix ex: <http://e/> . ex:a ex:p ex:o .ex:b ex:p 'y' .",
    ],
)
def test_a_statement_end_followed_directly_by_a_name_still_ends_the_statement(text) -> None:
    _agrees(text)


@pytest.mark.parametrize(
    "text",
    [
        "@prefix ex: <http://e/> . ex:a ex:p 1.5 .",
        "@prefix ex: <http://e/> . ex:thing.py ex:p ex:builtins.str .",
        "@prefix ex: <http://e/> . ex:a ex:p 'x' . ex:b ex:p 'y' .",
    ],
)
def test_dots_inside_numbers_and_names_still_belong_to_them(text) -> None:
    _agrees(text)


# --- #56 a prefix declared again applies from there on, not to the whole document
def test_a_redefined_prefix_applies_only_to_what_follows() -> None:
    text = "@prefix ex: <http://e/> . ex:a ex:b ex:c . @prefix ex: <http://f/> . ex:a ex:b ex:c ."
    _agrees(text)
    assert len(_starlayer(text)) == 2


def test_a_redefined_sparql_style_prefix_applies_only_to_what_follows() -> None:
    _agrees("PREFIX ex: <http://e/>\nex:a ex:b ex:c .\nPREFIX ex: <http://f/>\nex:a ex:b ex:c .")


def test_a_redefined_prefix_in_trig_applies_only_to_what_follows() -> None:
    text = (
        "@prefix ex: <http://e/> .\nGRAPH <http://g/1> { ex:a ex:b ex:c }\n"
        "@prefix ex: <http://f/> .\nGRAPH <http://g/2> { ex:a ex:b ex:c }\nex:d ex:e ex:f ."
    )
    d = StarLayerDataset()
    d.parse(data=text, format="trig12")
    ref = rdflib.Dataset()
    ref.parse(data=text, format="trig")
    got = {(str(c.identifier), str(s), str(o)) for c in d.contexts() for s, _, o in c}
    want = {(str(c.identifier), str(s), str(o)) for c in ref.graphs() for s, _, o in c}
    assert got == want and len(got) == 3


def test_a_graph_name_uses_the_prefix_in_effect_at_that_point() -> None:
    text = "@prefix g: <http://g1/> . GRAPH g:one { <http://e/a> <http://e/p> 1 } @prefix g: <http://g2/> . GRAPH g:one { <http://e/b> <http://e/p> 2 }"
    d = StarLayerDataset()
    d.parse(data=text, format="trig12")
    assert {str(c.identifier) for c in d.contexts() if len(c)} == {"http://g1/one", "http://g2/one"}


# --- #60 a relative IRI in a prefix declaration is resolved against the base
def test_a_relative_prefix_iri_is_resolved_against_base() -> None:
    _agrees("@base <http://e/d/> . @prefix r: <sub/> . r:a r:b r:c .")


def test_a_relative_sparql_style_prefix_iri_is_resolved_against_base() -> None:
    _agrees("BASE <http://e/d/>\nPREFIX r: <sub/>\nr:a r:b r:c .")


def test_a_prefix_iri_follows_the_base_in_effect_where_it_is_declared() -> None:
    _agrees("@base <http://e/one/> . @prefix r: <x/> . @base <http://e/two/> . @prefix s: <x/> . r:a r:b s:c .")


# --- #61 an undeclared prefix is an error, not a made-up IRI
@pytest.mark.parametrize("text", ["zz:a zz:p 'x' .", "@prefix ex: <http://e/> . ex:a ex:p zz:b .", "@prefix ex: <http://e/> . ex:a ex:p 'x'^^zz:t ."])
def test_an_undeclared_prefix_is_a_syntax_error(text) -> None:
    with pytest.raises(Turtle12SyntaxError, match="zz"):
        _starlayer(text)


def test_an_undeclared_prefix_in_a_trig_graph_block_is_a_syntax_error() -> None:
    with pytest.raises(Turtle12SyntaxError, match="zz"):
        StarLayerDataset().parse(data="GRAPH <http://g> { zz:a zz:p zz:b }", format="trig12")


def test_a_prefix_is_not_visible_before_it_is_declared() -> None:
    with pytest.raises(Turtle12SyntaxError, match="ex"):
        _starlayer("ex:a ex:b ex:c . @prefix ex: <http://e/> .")


# --- #59 escapes in IRIs and in the local part of a prefixed name
def test_uchar_escapes_in_an_iri_are_decoded() -> None:
    _agrees(r"<http://e/a> <http://e/p> <http://e/\U00000063> , <http://e/d> .")


@pytest.mark.parametrize("local", [r"c\.d", r"c\~x", r"a\-b", r"a\_b", r"a\!b", r"a\$b", r"a\&b", r"a\'b", r"a\(b\)", r"a\*b", r"a\+b", r"a\,b", r"a\;b", r"a\=b", r"a\/b", r"a\?b", r"a\#b", r"a\@b", r"a\%b"])
def test_pn_local_escapes_are_removed(local) -> None:
    _agrees(f"@prefix ex: <http://e/> . ex:a ex:p ex:{local} .")


def test_a_percent_sequence_in_a_local_name_is_kept_as_written() -> None:
    _agrees("@prefix ex: <http://e/> . ex:a ex:p ex:b%20c .")


# --- #57 N-Triples / N-Quads: a literal may end in an escaped backslash
@pytest.mark.parametrize("lit", [r'"x\\"', r'"\\"', r'"a\\b\\"', r'"x\\"@en', r'"x\\"^^<http://www.w3.org/2001/XMLSchema#string>', r'"x\""', r'"x\\\""'])
def test_ntriples_literals_ending_in_backslash_or_quote_escapes(lit) -> None:
    text = f"<http://e/a> <http://e/p> {lit} .\n"
    assert isomorphic(_starlayer(text, "nt12"), _rdflib(text, "nt"))


def test_nquads_literal_ending_in_an_escaped_backslash() -> None:
    text = r'<http://e/a> <http://e/p> "x\\" <http://e/g> .' + "\n"
    d = StarLayerDataset()
    d.parse(data=text, format="nq12")
    assert [str(o) for _, _, o, _ in d.quads()] == ["x\\"]


@pytest.mark.parametrize("value", ["x\\", "\\", "a\\b\\", 'q"', 'a"\\', "tab\t", "nl\n", "é\\"])
def test_ntriples_serializer_output_round_trips(value) -> None:
    g = StarLayerGraph()
    g.add((URIRef(E + "a"), URIRef(E + "p"), Literal(value)))
    back = StarLayerGraph()
    back.parse(data=g.serialize(format="nt12"), format="nt12")
    # "x" and "x"^^xsd:string are the same RDF term (RDF 1.1 Concepts 3.3); rdflib keeps them apart, so compare as RDF does
    assert {_rdf_term(t) for t in back} == {_rdf_term(t) for t in g}


# --- a collection as the subject of a statement (it used to become a made-up IRI of the collection's text)
@pytest.mark.parametrize(
    "statement",
    ["( 1 2 ) :q 123 .", "() :q 123 .", "( :x ) :q 1 ; :r 2 .", "( ( 1 ) 2 ) :q 3 .", "( [ :a :b ] 2 ) :q 3 .", ":s :p ( 1 2 ) ."],
)
def test_a_collection_as_a_subject(statement) -> None:
    _agrees("@prefix : <http://e/> . " + statement)


def test_reified_triples_inside_a_collection_are_elements_not_text() -> None:
    g = StarLayerGraph()
    g.parse(data="@prefix : <http://e/> . :s :p :o1 . :s :p :o2 . ( <<:s :p :o1>> <<:s :p :o2>> ) :q 123 .", format="turtle12")
    assert len(list(g.triple_terms())) == 2 and not any("<<" in str(t) for t in g)


# --- #55 the Turtle/TriG writers must not lose blank nodes that nothing named reaches (self-loops, cycles, lists in them)
from rdflib import RDF, BNode  # noqa: E402

P_ = URIRef(E + "p")
B1, B2, B3 = BNode("x"), BNode("y"), BNode("z")


def _bnode_graphs():
    """name -> list of triples; each has a blank node reachable from no named node, or one only an unreachable node points at."""
    a = URIRef(E + "a")
    return {
        "self-loop": [(B1, P_, B1), (a, P_, URIRef(E + "b"))],
        "two-cycle": [(B1, P_, B2), (B2, P_, B1)],
        "three-cycle with a tail": [(B1, P_, B2), (B2, P_, B3), (B3, P_, B1), (B3, P_, Literal("t"))],
        "cycle pointing out to a named node": [(B1, P_, B2), (B2, P_, B1), (B2, P_, a)],
        "node only a self-loop points at": [(B1, P_, B1), (B1, P_, B2), (B2, P_, Literal("leaf"))],
        "only blank nodes": [(B1, P_, Literal("v"))],
        "list in an unreachable node": [(B1, P_, B1), (B1, P_, B2), (B2, RDF.first, Literal(1)), (B2, RDF.rest, B3), (B3, RDF.first, Literal(2)), (B3, RDF.rest, RDF.nil)],
        "reachable inline node (the normal case)": [(a, P_, B1), (B1, P_, Literal("v"))],
    }


@pytest.mark.parametrize("fmt", ["turtle12", "longturtle12"])
@pytest.mark.parametrize("name", list(_bnode_graphs()))
def test_the_turtle_writers_keep_unreachable_blank_nodes(name, fmt) -> None:
    g = StarLayerGraph()
    for t in _bnode_graphs()[name]:
        g.add(t)
    text = g.serialize(format=fmt)
    back = StarLayerGraph()
    back.parse(data=text, format="turtle12")
    original, parsed = Graph(), Graph()
    for t in g:
        original.add(t)
    for t in back:
        parsed.add(t)
    assert len(parsed) == len(original), text
    assert isomorphic(original, parsed), text


@pytest.mark.parametrize("name", list(_bnode_graphs()))
def test_the_trig_writer_keeps_unreachable_blank_nodes(name) -> None:
    d = StarLayerDataset()
    graph = d.graph(URIRef("http://g/one"))
    for t in _bnode_graphs()[name]:
        graph.add(t)
    back = StarLayerDataset()
    back.parse(data=d.serialize(format="trig12"), format="trig12")
    original, parsed = Graph(), Graph()
    for t in graph:
        original.add(t)
    for c in back.contexts():
        if str(c.identifier) == "http://g/one":
            for t in c:
                parsed.add(t)
    assert isomorphic(original, parsed), d.serialize(format="trig12")


# --- #58 a multi-line literal ending in quotes
@pytest.mark.parametrize(
    "value",
    ['a\n"""q"""', 'a\n"', 'a\n""', 'a\n"""', 'a\n""""', 'a\n"""""', 'line1\nline2"', 'x\n"""\\', "a\n'''", 'a\n"b"\n"'],
)
@pytest.mark.parametrize("fmt", ["turtle12", "longturtle12"])
def test_a_multi_line_literal_ending_in_quotes_round_trips(value, fmt) -> None:
    g = StarLayerGraph()
    g.add((URIRef(E + "a"), P_, Literal(value)))
    text = g.serialize(format=fmt)
    back = StarLayerGraph()
    back.parse(data=text, format="turtle12")
    assert [str(o) for _, _, o in back] == [value], text


def test_a_multi_line_literal_ending_in_quotes_round_trips_in_trig() -> None:
    d = StarLayerDataset()
    d.graph(URIRef("http://g/one")).add((URIRef(E + "a"), P_, Literal('a\n"""q"""')))
    back = StarLayerDataset()
    back.parse(data=d.serialize(format="trig12"), format="trig12")
    assert ['a\n"""q"""'] == [str(o) for c in back.contexts() for _, _, o in c]
