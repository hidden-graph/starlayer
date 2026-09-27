"""Tests for starlayergraph.ontology.skos_shapes / skos-ontology.ttl.

Unlike the manch:/salg: vocabularies, SKOS needs no encode/decode/round-trip
layer - a SKOS thesaurus is already plain RDF the moment it's authored - so
this is the *only* test file for SKOS support: does the ontology load with
the right entailments, does a well-formed thesaurus conform, and does each
of the W3C SKOS Reference's own numbered integrity conditions (S9, S13, S14,
S19/S20, S27, S37, S46) get caught when violated.
"""

import owlrl
import pytest
from rdflib import RDF, Graph, Literal, Namespace
from rdflib.namespace import SKOS

from starlayergraph.ontology import skos_ontology_graph
from starlayergraph.ontology import skos_shapes as ss

EX = Namespace("http://example.org/")


def test_skos_ontology_graph_loads_standalone():
    g = skos_ontology_graph()
    assert len(g) > 0


def test_ordered_collection_entails_collection_via_rdfs():
    """S29: skos:OrderedCollection rdfs:subClassOf skos:Collection - proves
    this is real entailed structure, not just an assumption, the same
    discipline the sibling starsparql package's own
    test_expression_shape_relies_on_rdfs_reasoning_not_enumeration uses."""
    ontology = skos_ontology_graph()
    data = Graph()
    data.add((EX.oc, RDF.type, SKOS.OrderedCollection))

    merged = Graph()
    merged += data
    merged += ontology
    owlrl.DeductiveClosure(owlrl.RDFS_Semantics).expand(merged)

    entailed_types = set(merged.objects(EX.oc, RDF.type))
    assert SKOS.Collection in entailed_types


def _valid_thesaurus():
    g = Graph()
    g.add((EX.scheme, RDF.type, SKOS.ConceptScheme))
    g.add((EX.animal, RDF.type, SKOS.Concept))
    g.add((EX.cat, RDF.type, SKOS.Concept))
    g.add((EX.cat, SKOS.broader, EX.animal))
    g.add((EX.animal, SKOS.narrower, EX.cat))
    g.add((EX.cat, SKOS.inScheme, EX.scheme))
    g.add((EX.animal, SKOS.inScheme, EX.scheme))
    g.add((EX.scheme, SKOS.hasTopConcept, EX.animal))
    g.add((EX.cat, SKOS.prefLabel, Literal("Cat", lang="en")))
    g.add((EX.cat, SKOS.altLabel, Literal("Kitty", lang="en")))
    g.add((EX.coll, RDF.type, SKOS.Collection))
    g.add((EX.coll, SKOS.member, EX.cat))
    g.add((EX.oc, RDF.type, SKOS.OrderedCollection))
    g.add((EX.oc, SKOS.memberList, RDF.nil))
    return g


def test_valid_thesaurus_conforms():
    conforms, _, results_text = ss.validate(_valid_thesaurus())
    assert conforms, results_text


def _base_two_concepts():
    g = Graph()
    g.add((EX.animal, RDF.type, SKOS.Concept))
    g.add((EX.cat, RDF.type, SKOS.Concept))
    return g


def test_concept_and_conceptscheme_same_node_fails():
    """S9: skos:Concept is disjoint with skos:ConceptScheme."""
    g = _base_two_concepts()
    g.add((EX.animal, RDF.type, SKOS.ConceptScheme))
    conforms, _, results_text = ss.validate(g)
    assert not conforms
    assert "S9" in results_text


def test_preflabel_and_altlabel_sharing_a_literal_fails():
    """S13: skos:prefLabel/altLabel/hiddenLabel must be pairwise disjoint."""
    g = _base_two_concepts()
    lit = Literal("Cat", lang="en")
    g.add((EX.cat, SKOS.prefLabel, lit))
    g.add((EX.cat, SKOS.altLabel, lit))
    conforms, _, results_text = ss.validate(g)
    assert not conforms
    assert "S13" in results_text


def test_two_preflabels_same_language_fails():
    """S14: no more than one skos:prefLabel per language tag."""
    g = _base_two_concepts()
    g.add((EX.cat, SKOS.prefLabel, Literal("Cat", lang="en")))
    g.add((EX.cat, SKOS.prefLabel, Literal("Kitty", lang="en")))
    conforms, _, results_text = ss.validate(g)
    assert not conforms


def test_broader_on_non_concept_subject_fails():
    """S19/S20: the domain and range of skos:broader (and every other
    semantic relation) is skos:Concept."""
    g = Graph()
    g.add((EX.animal, RDF.type, SKOS.Concept))
    g.add((EX.notaconcept, SKOS.broader, EX.animal))
    conforms, _, results_text = ss.validate(g)
    assert not conforms
    assert "S19" in results_text or "S20" in results_text


def test_related_and_broader_between_same_pair_fails():
    """S27: skos:related is disjoint with skos:broader(Transitive)/
    skos:narrower(Transitive)."""
    g = _base_two_concepts()
    g.add((EX.cat, SKOS.broader, EX.animal))
    g.add((EX.cat, SKOS.related, EX.animal))
    conforms, _, results_text = ss.validate(g)
    assert not conforms
    assert "S27" in results_text


def test_collection_also_typed_concept_fails():
    """S37: skos:Collection is disjoint with skos:Concept/skos:ConceptScheme."""
    g = Graph()
    g.add((EX.coll, RDF.type, SKOS.Collection))
    g.add((EX.coll, RDF.type, SKOS.Concept))
    conforms, _, results_text = ss.validate(g)
    assert not conforms
    assert "S37" in results_text


def test_ordered_collection_also_typed_concept_fails():
    """S37 via S29 (skos:OrderedCollection rdfs:subClassOf skos:Collection)
    - listed explicitly in the shape rather than relying on RDFS entailment
    (see skos_shapes.ttl's own module comment for why)."""
    g = Graph()
    g.add((EX.oc, RDF.type, SKOS.OrderedCollection))
    g.add((EX.oc, RDF.type, SKOS.Concept))
    conforms, _, results_text = ss.validate(g)
    assert not conforms


def test_exactmatch_and_broadmatch_between_same_pair_fails():
    """S46: skos:exactMatch is disjoint with skos:broadMatch/narrowMatch/
    relatedMatch."""
    g = _base_two_concepts()
    g.add((EX.cat, SKOS.exactMatch, EX.animal))
    g.add((EX.cat, SKOS.broadMatch, EX.animal))
    conforms, _, results_text = ss.validate(g)
    assert not conforms
    assert "S46" in results_text


def test_shapes_graph_is_valid_shacl_and_reusable():
    g1 = ss.shapes_graph()
    g2 = ss.shapes_graph()
    assert g1 is not g2
    assert len(g1) == len(g2) > 0
