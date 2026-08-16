"""
Unit tests for starlayergraph.model.triple.TripleTerm's own constructor
validation (independent of any parser/backend that might construct one).
"""

import pytest
from rdflib import BNode, Literal, URIRef
from starlayergraph.model.triple import TripleTerm

EX = 'http://example.org/'


def ex(local):
    return URIRef(EX + local)


class TestValidConstruction:
    def test_iri_subject(self):
        TripleTerm(ex('s'), ex('p'), ex('o'))

    def test_blank_node_subject(self):
        TripleTerm(BNode(), ex('p'), ex('o'))

    def test_literal_object_allowed(self):
        TripleTerm(ex('s'), ex('p'), Literal('x'))

    def test_blank_node_object_allowed(self):
        TripleTerm(ex('s'), ex('p'), BNode())

    def test_nested_triple_term_object_allowed(self):
        TripleTerm(ex('s'), ex('p'), TripleTerm(ex('a'), ex('b'), ex('c')))


class TestInvalidSubject:
    """RDF 1.2: ttSubject ::= iri | BlankNode - never a Literal, never
    itself a triple term. Widened from only rejecting a nested TripleTerm
    to the full rule after a live Fuseki 5.5.0 bug (a Literal-valued
    `subject` argument to TRIPLE() is silently accepted, not rejected -
    see docs/fuseki-upstream-issues.md Issue 1) let an equally-invalid
    TripleTerm object be constructed with no error at all when decoding a
    native-backend query result."""

    def test_literal_subject_rejected(self):
        with pytest.raises(ValueError, match='subject'):
            TripleTerm(Literal('x'), ex('p'), ex('o'))

    def test_nested_triple_term_subject_rejected(self):
        with pytest.raises(ValueError, match='subject'):
            TripleTerm(TripleTerm(ex('a'), ex('b'), ex('c')), ex('p'), ex('o'))


class TestInvalidPredicate:
    """RDF 1.2: verb ::= iri - a triple term's predicate must be an IRI,
    never a Literal, BlankNode, or another triple term."""

    def test_literal_predicate_rejected(self):
        with pytest.raises(ValueError, match='predicate'):
            TripleTerm(ex('s'), Literal('x'), ex('o'))

    def test_blank_node_predicate_rejected(self):
        with pytest.raises(ValueError, match='predicate'):
            TripleTerm(ex('s'), BNode(), ex('o'))

    def test_triple_term_predicate_rejected(self):
        with pytest.raises(ValueError, match='predicate'):
            TripleTerm(ex('s'), TripleTerm(ex('a'), ex('b'), ex('c')), ex('o'))
