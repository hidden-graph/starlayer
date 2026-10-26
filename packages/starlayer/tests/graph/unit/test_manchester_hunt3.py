"""Regression tests for the Manchester syntax findings of GitHub issue #101 (third hunt).

The oracle is the OWL 2 Manchester syntax note's grammar (https://www.w3.org/TR/owl2-manchester-syntax/):
one ontology per document, ``languageTag`` non-empty, ``description2List`` with two or more members,
``literal`` without a boolean form, and the round trip parse -> serialize -> parse being stable.
"""

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from starlayer.graph import StarLayerGraph
from starlayer.graph.compare import isomorphic
from starlayer.graph.parsers.errors import ManchesterSyntaxError
from starlayer.graph.parsers.manchester_parser import parse_manchester
from starlayer.starontology.manchester import (
    manchester_parse_to_tree,
    manchester_tree_to_owl,
    manchester_tree_to_text,
)

H = 'Prefix: : <http://ex.org/>\nOntology: <http://ex.org/o>\n'
EX = 'http://ex.org/'


# --- one Ontology: header per document ---------------------------------------------------------

@pytest.mark.parametrize('text', [
    'Prefix: : <http://ex.org/>\nOntology: <http://a>\nClass: :A\nOntology: <http://b>\n Import: <http://c>\n',
    'Ontology: <http://a>\nOntology: <http://b>\n',
])
def test_second_ontology_header_is_a_syntax_error(text):
    with pytest.raises(ManchesterSyntaxError):
        parse_manchester(text)
    with pytest.raises(ManchesterSyntaxError):
        manchester_parse_to_tree(text)


# --- language tags -------------------------------------------------------------------------------

@pytest.mark.parametrize('tag', ['', '123', 'en-'])
def test_bad_language_tag_is_a_syntax_error(tag):
    text = H + f'Individual: i\n  Facts: d "x"@{tag}\n'
    with pytest.raises(ManchesterSyntaxError):
        parse_manchester(text)
    with pytest.raises(ManchesterSyntaxError):
        manchester_parse_to_tree(text)


def test_good_language_tag_still_parses():
    triples = parse_manchester(H + 'Individual: i\n  Facts: d "x"@en-GB\n')
    assert (URIRef(EX + 'i'), URIRef('http://d'), Literal('x', lang='en-GB')) not in triples  # d is relative
    assert any(o == Literal('x', lang='en-GB') for _, _, o in triples)


# --- true / false are simple names, not xsd:boolean ----------------------------------------------

def test_true_is_an_individual_name_for_an_object_property():
    triples = parse_manchester(H + 'ObjectProperty: p\nIndividual: i\n  Facts: p true\n')
    assert (URIRef(EX + 'i'), URIRef(EX + 'p'), URIRef(EX + 'true')) in triples
    assert not any(isinstance(o, Literal) for _, _, o in triples)


def test_true_is_a_name_when_the_property_is_undeclared():
    triples = parse_manchester(H + 'Individual: i\n  Facts: p false\n')
    assert (URIRef(EX + 'i'), URIRef(EX + 'p'), URIRef(EX + 'false')) in triples


def test_true_in_a_value_restriction_on_an_object_property_is_a_name():
    triples = parse_manchester(H + 'ObjectProperty: p\nClass: A\n  SubClassOf: p value true\n')
    assert any(o == URIRef(EX + 'true') for _, _, o in triples)
    assert not any(isinstance(o, Literal) for _, _, o in triples)


def test_true_stays_a_boolean_for_a_declared_data_property():
    triples = parse_manchester(H + 'DataProperty: d\nIndividual: i\n  Facts: d true\n')
    assert (URIRef(EX + 'i'), URIRef(EX + 'd'), Literal(True)) in triples


# --- xsd:float lexical forms ---------------------------------------------------------------------

def test_overflowing_float_is_INF():
    triples = parse_manchester(H + 'Individual: a\n Facts: d 1e400f, d -1e400f\n')
    floats = {str(o) for _, _, o in triples if isinstance(o, Literal) and o.datatype == XSD.float}
    assert floats == {'INF', '-INF'}


def test_ordinary_float_is_unchanged():
    triples = parse_manchester(H + 'Individual: a\n Facts: d 1.5f\n')
    assert any(o == Literal('1.5', datatype=XSD.float) for _, _, o in triples)


# --- axioms with fewer than two members ----------------------------------------------------------

@pytest.mark.parametrize('line', [
    'EquivalentClasses: A', 'DisjointClasses: A', 'EquivalentProperties: p', 'DisjointProperties: p',
    'SameIndividual: i', 'DifferentIndividuals: i',
])
def test_single_member_misc_axiom_is_a_syntax_error(line):
    with pytest.raises(ManchesterSyntaxError):
        parse_manchester(H + line + '\n')
    with pytest.raises(ManchesterSyntaxError):
        manchester_parse_to_tree(H + line + '\n')


# --- empty tree, deep nesting --------------------------------------------------------------------

def test_empty_graph_is_not_a_bare_stopiteration():
    with pytest.raises(ValueError, match='manch:Document'):
        manchester_tree_to_text(Graph())
    with pytest.raises(ValueError, match='manch:Document'):
        manchester_tree_to_owl(Graph())


def test_deeply_nested_expression_is_a_syntax_error():
    depth = 5000
    text = H + 'Class: A\n  SubClassOf: ' + '(' * depth + 'B' + ')' * depth + '\n'
    with pytest.raises(ManchesterSyntaxError):
        parse_manchester(text)
    with pytest.raises(ManchesterSyntaxError):
        manchester_parse_to_tree(text)
    nots = 'not ' * depth
    with pytest.raises(ManchesterSyntaxError):
        parse_manchester(H + 'Class: A\n  SubClassOf: ' + nots + 'B\n')


# --- serializer: data fillers --------------------------------------------------------------------

def _round_trip(text):
    g1 = StarLayerGraph()
    g1.parse(data=text, format='manchester')
    out = g1.serialize(format='manchester')
    g2 = StarLayerGraph()
    g2.parse(data=out, format='manchester')
    assert isomorphic(g1, g2), out
    return out


@pytest.mark.parametrize('restriction', [
    'q only {1, 2}',
    'q some {"a", "b"}',
    'q some xsd:integer[> 3]',
    'q some xsd:integer[>= 1, < 10]',
    'q some not xsd:integer',
    'q only (xsd:integer or xsd:string)',
    'q some (xsd:integer[> 3] and not xsd:integer[> 9])',
    'q exactly 2 xsd:integer[> 3]',
    'q min 1 xsd:string',
    'q max 3 (not xsd:integer)',
])
def test_data_restrictions_round_trip(restriction):
    _round_trip(f'Prefix: : <http://ex.org/>\nPrefix: xsd: <http://www.w3.org/2001/XMLSchema#>\n'
                f'Ontology: <http://ex.org/o>\nDataProperty: q\nClass: A\n SubClassOf: {restriction}\n')


def test_literal_one_of_filler_is_rendered_as_literals():
    out = _round_trip(H + 'DataProperty: q\nClass: A\n SubClassOf: q only {1, 2}\n')
    assert '<1>' not in out
    assert '"1"^^' in out
