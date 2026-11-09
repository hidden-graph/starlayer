"""Regression tests for the Manchester serializer bug hunt.

The oracle for the serializer is its own documented bar: ``parse_manchester`` output written by
``serialize_manchester`` and parsed again is isomorphic, or the writer raises ``ValueError``.
"""

import pyoxigraph as ox
import pytest
from starlayer.graph.compare import isomorphic
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.graph.parsers._ox_terms import OWL, RDF, URIRef
from starlayer.graph.parsers.manchester_parser import parse_manchester
from starlayer.graph.serializers.manchester import serialize_manchester

P = 'Prefix: : <http://e/o#>\nPrefix: rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n'


def _graph(triples):
    g = StarLayerGraph()
    g.extend(triples)
    return g


def _round_trip(text, prefix=P):
    g = _graph(parse_manchester(prefix + text))
    out = serialize_manchester(g)
    return g, _graph(parse_manchester(out)), out


def _assert_round_trip(text, prefix=P):
    g, g2, out = _round_trip(text, prefix)
    assert isomorphic(g, g2), f'{len(g)} triples in, {len(g2)} after:\n{out}'


def test_negative_fact_annotation_of_annotation_round_trips():
    _assert_round_trip('Individual: :a Facts: Annotations: Annotations: :x "n" :y "v" not :p :b\n')


# --- serializer: entities that have no frame -----------------------------------------------------

@pytest.mark.parametrize('text', [
    'EquivalentClasses: :A, :B\n',
    'EquivalentClasses: :A, :B, :C\n',
    'DisjointClasses: :A, :B\n',
    'EquivalentProperties: :p, :q\n',
    'DisjointProperties: :p, :q\n',
    'SameIndividual: :a, :b\n',
    'DifferentIndividuals: :a, :b\n',
    'EquivalentClasses: Annotations: rdfs:label "n" :A, :B\n',
    'EquivalentProperties: inverse :p, :q\n',
])
def test_misc_axiom_over_undeclared_entities_round_trips(text):
    _assert_round_trip(text)


def test_misc_axiom_with_one_declared_entity_round_trips():
    _assert_round_trip('Class: :A\nEquivalentClasses: :A, :B\n')


def test_gci_round_trips():
    _assert_round_trip('Class: :A\nClass: :B\nClass: :A SuperClassOf: :p some :B\n'
                       'EquivalentClasses: :p only :B, :A\n')


def test_gci_with_annotation_round_trips():
    _assert_round_trip('Class: :A\nClass: :A SuperClassOf: Annotations: rdfs:label "x" :p some :B\n')


# --- serializer: blank-node individuals ----------------------------------------------------------

def test_blank_node_individual_round_trips():
    g, g2, out = _round_trip('Individual: _:b\n  Types: :C\n')
    assert 'Types' in out
    assert isomorphic(g, g2)


def test_blank_node_individual_with_facts_round_trips():
    _assert_round_trip('Individual: _:b\n  Types: :C\n  Facts: :p :x, :q _:c\nIndividual: _:c\n  Types: :D\n')


def test_blank_node_fact_object_round_trips():
    _assert_round_trip('Individual: :a\n Facts: :p _:b2\n')


def test_blank_node_same_as_round_trips():
    _assert_round_trip('Individual: :a\n SameAs: _:b\n')


def test_blank_node_different_individuals_round_trips():
    _assert_round_trip('DifferentIndividuals: _:a, _:b, :c\n')


def test_anonymous_individual_annotation_value_round_trips():
    _assert_round_trip('Individual: :i\n  Annotations: rdfs:label _:b\n')


# --- serializer: ontology header -----------------------------------------------------------------

def test_version_iri_and_ontology_annotations_round_trip():
    g, g2, out = _round_trip('Ontology: <http://x/o> <http://x/o/1>\n  Annotations: rdfs:label "o"\n')
    assert '<http://x/o/1>' in out
    assert isomorphic(g, g2)


def test_ontology_annotation_with_nested_annotation_round_trips():
    _assert_round_trip('Ontology: <http://x/o>\n  Import: <http://x/i>\n'
                       '  Annotations: Annotations: rdfs:comment "c" rdfs:label "o"\n')


def test_anonymous_ontology_import_round_trips():
    g, g2, out = _round_trip('Ontology:\n Import: <http://x/y>\nClass: <http://x/A>\n', prefix='')
    assert 'http://x/y' in out
    assert isomorphic(g, g2)


# --- serializer: annotations ---------------------------------------------------------------------

@pytest.mark.parametrize('kw, members', [
    ('DisjointClasses', ':A, :B, :C'),
    ('DisjointProperties', ':p, :q, :r'),
    ('DifferentIndividuals', ':a, :b, :c'),
])
def test_nary_misc_axiom_annotations_round_trip(kw, members):
    _assert_round_trip(f'{kw}: Annotations: rdfs:label "n" {members}\n')


def test_nary_misc_axiom_with_nested_annotation_round_trips():
    _assert_round_trip('DisjointClasses: Annotations: Annotations: rdfs:comment "c" rdfs:label "n" :A, :B, :C\n')


def test_annotation_of_annotation_round_trips():
    _assert_round_trip('Class: :A\nClass: :B\nClass: :A\n  SubClassOf: Annotations: Annotations: rdfs:label "n" rdfs:label "y" :B\n')


def test_three_level_annotation_nesting_round_trips():
    _assert_round_trip('Class: :A\nClass: :B\nClass: :A\n  SubClassOf: Annotations: Annotations: Annotations: '
                       'rdfs:comment "c" rdfs:label "n" rdfs:label "y" :B\n')


def test_frame_annotation_with_nested_annotation_round_trips():
    _assert_round_trip('Class: :A\n  Annotations: Annotations: rdfs:comment "c" rdfs:label "n"\n')


def test_differently_annotated_copies_of_one_axiom_are_all_written():
    g, g2, out = _round_trip('Class: :A\n  SubClassOf: Annotations: rdfs:comment "first" :B, '
                             'Annotations: rdfs:comment "second" :B\nClass: :B\n')
    assert 'first' in out
    assert 'second' in out
    assert isomorphic(g, g2)


def test_differently_annotated_types_and_facts_round_trip():
    _assert_round_trip('Individual: :i\n  Types: Annotations: rdfs:comment "a" :C, Annotations: rdfs:comment "b" :C\n'
                       '  Facts: Annotations: rdfs:comment "a" :p :x, Annotations: rdfs:comment "b" :p :x\n')


# --- serializer: values and expressions ----------------------------------------------------------

def test_lang_range_facet_round_trips():
    _assert_round_trip('DataProperty: :d\n Range: string[langRange "en"]\n')


def test_direction_tagged_literal_is_not_written_as_a_plain_language_literal():
    g = StarLayerGraph()
    a = ox.NamedNode('http://ex.org/A')
    g.add((a, RDF.type, OWL.Class))
    g.add((a, ox.NamedNode('http://www.w3.org/2000/01/rdf-schema#label'),
           ox.Literal('x', language='en', direction=ox.BaseDirection.LTR)))
    with pytest.raises(ValueError, match='direction'):
        serialize_manchester(g)


def test_triple_term_value_raises_value_error():
    a = ox.NamedNode('http://ex.org/A')
    ap = ox.NamedNode('http://ex.org/ap')
    g = StarLayerGraph()
    g.add((a, RDF.type, OWL.Class))
    g.add((ap, RDF.type, OWL.AnnotationProperty))
    g.add((a, ap, ox.Triple(a, ap, a)))
    with pytest.raises(ValueError, match='Triple'):
        serialize_manchester(g)


@pytest.mark.parametrize('expr', [
    'A and (B and C)', '(A and B) and C', '(B or C) or D', 'B or (C or D)', 'not (A and (B and C))',
    '(p some A) and ((p only B) and (q some C))',
])
def test_nested_same_operator_class_expressions_round_trip(expr):
    _assert_round_trip(f'Class: X\n  EquivalentTo: {expr}\n', prefix='Prefix: : <http://ex.org/>\n')


def test_nested_same_operator_data_ranges_round_trip():
    _assert_round_trip('Datatype: :D\n  EquivalentTo: (integer and integer) and integer\n'
                       'Datatype: :E\n  EquivalentTo: integer or (integer or string)\n')


def test_all_different_with_distinct_members_is_written():
    ttl = ('@prefix : <http://ex.org/> . @prefix owl: <http://www.w3.org/2002/07/owl#> .\n'
           ':a a owl:NamedIndividual . :b a owl:NamedIndividual . :c a owl:NamedIndividual .\n'
           '[] a owl:AllDifferent ; owl:distinctMembers (:a :b :c) .\n')
    g = StarLayerGraph()
    g.parse(data=ttl, format='turtle')
    out = serialize_manchester(g)
    assert 'DifferentIndividuals' in out
    g2 = _graph(parse_manchester(out))
    for s in ('a', 'b', 'c'):
        assert (URIRef('http://ex.org/' + s), RDF.type, OWL.NamedIndividual) in g2


# --- serializer: punning -------------------------------------------------------------------------

def test_punned_class_and_individual_with_restriction_superclass_round_trips():
    _assert_round_trip('Class: :A SubClassOf: :p some :B\nIndividual: :A Types: :C\n')


def test_punned_class_and_individual_with_facts_round_trips():
    _assert_round_trip('Class: :A SubClassOf: :B\nIndividual: :A Types: :C Facts: :p :x\n')
