"""Unit tests for starlayergraph.parsers.manchester_parser.

Grouped by construct: frames, each class-expression form, each Misc axiom,
and the constructs this parser deliberately doesn't support yet (must raise
ManchesterSyntaxError, not silently mis-parse). RDF-mapping correctness for
the bulk of these cases was cross-checked during development against the
real OWL API's ManchesterOWLSyntaxOntologyParser (an external, uncommitted
oracle - see the module docstring) via starlayergraph.compare.isomorphic();
these tests assert the same shapes directly, with no external dependency.
"""

import pytest
from rdflib import BNode, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starlayergraph.parsers.errors import ManchesterSyntaxError
from starlayergraph.parsers.manchester_parser import parse_manchester

EX = 'http://example.org/'
HEADER = 'Prefix: : <http://example.org/>\nPrefix: xsd: <http://www.w3.org/2001/XMLSchema#>\n'


def ex(name):
    return URIRef(EX + name)


def parse(body):
    return parse_manchester(HEADER + body)


def restriction_for(triples, prop, pred):
    """Find the owl:Restriction bnode with owl:onProperty=prop and the
    given predicate set, returning (bnode, object)."""
    for s, p, o in triples:
        if p == pred and (s, OWL.onProperty, prop) in triples:
            return s, o
    raise AssertionError(f'no restriction found for {prop} / {pred}')


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------

class TestFrames:
    def test_class_frame_declares_type(self):
        t = parse('Class: Cat\n')
        assert (ex('Cat'), RDF.type, OWL.Class) in t

    def test_object_property_frame_declares_type(self):
        t = parse('ObjectProperty: hasFriend\n')
        assert (ex('hasFriend'), RDF.type, OWL.ObjectProperty) in t

    def test_data_property_frame_declares_type(self):
        t = parse('DataProperty: hasAge\n')
        assert (ex('hasAge'), RDF.type, OWL.DatatypeProperty) in t

    def test_annotation_property_frame_declares_type(self):
        t = parse('AnnotationProperty: note\n')
        assert (ex('note'), RDF.type, OWL.AnnotationProperty) in t

    def test_individual_frame_declares_named_individual(self):
        t = parse('Individual: Felix\n')
        assert (ex('Felix'), RDF.type, OWL.NamedIndividual) in t

    def test_ontology_header_emits_ontology_triple_and_sets_base(self):
        t = parse_manchester(
            'Prefix: : <http://example.org/>\n'
            'Ontology: <http://example.org/onto>\n'
            'Class: Cat\n'
        )
        assert (URIRef(EX + 'onto'), RDF.type, OWL.Ontology) in t

    def test_full_iri_name_not_requiring_a_prefix(self):
        t = parse_manchester(f'Class: <{EX}Cat>\n')
        assert (ex('Cat'), RDF.type, OWL.Class) in t

    def test_bare_name_uses_default_prefix(self):
        t = parse('Class: Cat\n')
        assert (ex('Cat'), RDF.type, OWL.Class) in t


# ---------------------------------------------------------------------------
# Class: clauses
# ---------------------------------------------------------------------------

class TestClassClauses:
    def test_subclassof(self):
        t = parse('Class: Animal\nClass: Cat\n    SubClassOf: Animal\n')
        assert (ex('Cat'), RDFS.subClassOf, ex('Animal')) in t

    def test_equivalentto(self):
        t = parse('Class: Cat\nClass: Kitty\n    EquivalentTo: Cat\n')
        assert (ex('Kitty'), OWL.equivalentClass, ex('Cat')) in t

    def test_disjointwith(self):
        t = parse('Class: Cat\nClass: Dog\n    DisjointWith: Cat\n')
        assert (ex('Dog'), OWL.disjointWith, ex('Cat')) in t

    def test_multiple_clauses_on_one_frame(self):
        t = parse(
            'Class: Animal\nClass: Rock\n'
            'Class: Cat\n'
            '    SubClassOf: Animal\n'
            '    DisjointWith: Rock\n'
        )
        assert (ex('Cat'), RDFS.subClassOf, ex('Animal')) in t
        assert (ex('Cat'), OWL.disjointWith, ex('Rock')) in t


# ---------------------------------------------------------------------------
# Class expressions
# ---------------------------------------------------------------------------

class TestClassExpressions:
    def test_intersection(self):
        t = parse('Class: A\nClass: B\nClass: C\n    EquivalentTo: A and B\n')
        node = next(o for s, p, o in t if s == ex('C') and p == OWL.equivalentClass)
        first = next(o for s, p, o in t if s == node and p == OWL.intersectionOf)
        assert (first, RDF.first, ex('A')) in t

    def test_union(self):
        t = parse('Class: A\nClass: B\nClass: C\n    EquivalentTo: A or B\n')
        node = next(o for s, p, o in t if s == ex('C') and p == OWL.equivalentClass)
        assert any(p == OWL.unionOf for s, p, o in t if s == node)

    def test_complement(self):
        t = parse('Class: A\nClass: C\n    EquivalentTo: not A\n')
        node = next(o for s, p, o in t if s == ex('C') and p == OWL.equivalentClass)
        assert (node, OWL.complementOf, ex('A')) in t

    def test_parenthesised_grouping(self):
        t = parse('Class: A\nClass: B\nClass: D\nClass: C\n    EquivalentTo: A and (B or D)\n')
        c_node = next(o for s, p, o in t if s == ex('C') and p == OWL.equivalentClass)
        assert (c_node, RDF.type, OWL.Class) in t
        list_head = next(o for s, p, o in t if s == c_node and p == OWL.intersectionOf)
        second = next(o for s, p, o in t if p == RDF.rest and (list_head, RDF.rest, o) in t)
        or_node = next(o for s, p, o in t if s == second and p == RDF.first)
        assert any(p == OWL.unionOf for s, p, o in t if s == or_node)

    def test_enumeration(self):
        t = parse('Individual: Alice\nIndividual: Bob\nClass: C\n    EquivalentTo: {Alice, Bob}\n')
        node = next(o for s, p, o in t if s == ex('C') and p == OWL.equivalentClass)
        assert any(p == OWL.oneOf for s, p, o in t if s == node)

    def test_some_restriction(self):
        t = parse('ObjectProperty: hasFriend\nClass: Person\nClass: C\n    SubClassOf: hasFriend some Person\n')
        bnode, filler = restriction_for(t, ex('hasFriend'), OWL.someValuesFrom)
        assert filler == ex('Person')

    def test_only_restriction(self):
        t = parse('ObjectProperty: hasFriend\nClass: Person\nClass: C\n    SubClassOf: hasFriend only Person\n')
        bnode, filler = restriction_for(t, ex('hasFriend'), OWL.allValuesFrom)
        assert filler == ex('Person')

    def test_value_restriction(self):
        t = parse('ObjectProperty: worksWith\nIndividual: Alice\nClass: C\n    SubClassOf: worksWith value Alice\n')
        bnode, filler = restriction_for(t, ex('worksWith'), OWL.hasValue)
        assert filler == ex('Alice')

    def test_self_restriction(self):
        t = parse('ObjectProperty: likes\nClass: C\n    SubClassOf: likes Self\n')
        bnode, filler = restriction_for(t, ex('likes'), OWL.hasSelf)
        assert filler == Literal(True)

    def test_unqualified_min_cardinality(self):
        t = parse('ObjectProperty: hasChild\nClass: C\n    SubClassOf: hasChild min 2\n')
        bnode, n = restriction_for(t, ex('hasChild'), OWL.minCardinality)
        assert n == Literal(2, datatype=XSD.nonNegativeInteger)

    def test_qualified_max_cardinality(self):
        t = parse('ObjectProperty: hasChild\nClass: Person\nClass: C\n    SubClassOf: hasChild max 3 Person\n')
        bnode, n = restriction_for(t, ex('hasChild'), OWL.maxQualifiedCardinality)
        assert n == Literal(3, datatype=XSD.nonNegativeInteger)
        assert (bnode, OWL.onClass, ex('Person')) in t

    def test_exactly_cardinality(self):
        t = parse('ObjectProperty: hasLegs\nClass: C\n    SubClassOf: hasLegs exactly 4\n')
        bnode, n = restriction_for(t, ex('hasLegs'), OWL.cardinality)
        assert n == Literal(4, datatype=XSD.nonNegativeInteger)

    def test_cardinality_immediately_followed_by_next_clause(self):
        # Regression: an unqualified `exactly 4` at the end of a SubClassOf:
        # list, directly followed by the next clause keyword, previously
        # mis-consumed that keyword as an attempted filler class expression.
        t = parse(
            'ObjectProperty: hasLegs\nClass: Rock\n'
            'Class: Cat\n'
            '    SubClassOf: hasLegs exactly 4\n'
            '    DisjointWith: Rock\n'
        )
        assert (ex('Cat'), OWL.disjointWith, ex('Rock')) in t

    def test_inverse_property_expression(self):
        t = parse('ObjectProperty: hasChild\nObjectProperty: hasParent\n    InverseOf: inverse hasChild\n')
        node = next(o for s, p, o in t if s == ex('hasParent') and p == OWL.inverseOf)
        assert (node, OWL.inverseOf, ex('hasChild')) in t


# ---------------------------------------------------------------------------
# ObjectProperty / DataProperty clauses
# ---------------------------------------------------------------------------

class TestPropertyClauses:
    def test_domain_and_range(self):
        t = parse('Class: Animal\nObjectProperty: hasLegs\n    Domain: Animal\n    Range: Animal\n')
        assert (ex('hasLegs'), RDFS.domain, ex('Animal')) in t
        assert (ex('hasLegs'), RDFS.range, ex('Animal')) in t

    def test_data_property_range_is_a_bare_datatype(self):
        t = parse('DataProperty: hasAge\n    Range: xsd:integer\n')
        assert (ex('hasAge'), RDFS.range, XSD.integer) in t

    def test_subpropertyof(self):
        t = parse('ObjectProperty: hasPet\nObjectProperty: hasCat\n    SubPropertyOf: hasPet\n')
        assert (ex('hasCat'), RDFS.subPropertyOf, ex('hasPet')) in t

    def test_characteristics(self):
        t = parse('ObjectProperty: hasSpouse\n    Characteristics: Symmetric, Functional\n')
        assert (ex('hasSpouse'), RDF.type, OWL.SymmetricProperty) in t
        assert (ex('hasSpouse'), RDF.type, OWL.FunctionalProperty) in t

    def test_unknown_characteristic_raises(self):
        with pytest.raises(ManchesterSyntaxError):
            parse('ObjectProperty: p\n    Characteristics: Bogus\n')

    def test_inverseof(self):
        t = parse('ObjectProperty: hasChild\nObjectProperty: hasParent\n    InverseOf: hasChild\n')
        assert (ex('hasParent'), OWL.inverseOf, ex('hasChild')) in t


# ---------------------------------------------------------------------------
# Individual: clauses
# ---------------------------------------------------------------------------

class TestIndividualClauses:
    def test_types(self):
        t = parse('Class: Cat\nIndividual: Felix\n    Types: Cat\n')
        assert (ex('Felix'), RDF.type, ex('Cat')) in t

    def test_facts_with_object_value(self):
        t = parse('ObjectProperty: hasParent\nIndividual: Tom\nIndividual: Felix\n    Facts: hasParent Tom\n')
        assert (ex('Felix'), ex('hasParent'), ex('Tom')) in t

    def test_facts_with_bare_numeric_literal(self):
        t = parse('DataProperty: hasAge\nIndividual: Felix\n    Facts: hasAge 3\n')
        assert (ex('Felix'), ex('hasAge'), Literal(3, datatype=XSD.integer)) in t

    def test_facts_with_quoted_typed_literal(self):
        t = parse('DataProperty: hasAge\nIndividual: Felix\n    Facts: hasAge "3"^^xsd:integer\n')
        assert (ex('Felix'), ex('hasAge'), Literal('3', datatype=XSD.integer)) in t

    def test_sameas(self):
        t = parse('Individual: Felix\nIndividual: Kitty\n    SameAs: Felix\n')
        assert (ex('Kitty'), OWL.sameAs, ex('Felix')) in t

    def test_differentfrom(self):
        t = parse('Individual: Felix\nIndividual: Rex\n    DifferentFrom: Felix\n')
        assert (ex('Rex'), OWL.differentFrom, ex('Felix')) in t

    def test_negative_fact_not_supported(self):
        with pytest.raises(ManchesterSyntaxError):
            parse('ObjectProperty: p\nIndividual: a\nIndividual: b\n    Facts: not p b\n')


# ---------------------------------------------------------------------------
# Top-level Misc axioms
# ---------------------------------------------------------------------------

class TestMiscAxioms:
    def test_equivalentclasses_chains_pairwise(self):
        t = parse('Class: A\nClass: B\nClass: C\nEquivalentClasses: A, B, C\n')
        assert (ex('A'), OWL.equivalentClass, ex('B')) in t
        assert (ex('B'), OWL.equivalentClass, ex('C')) in t

    def test_disjointclasses_binary_uses_disjointwith(self):
        t = parse('Class: A\nClass: B\nDisjointClasses: A, B\n')
        assert (ex('A'), OWL.disjointWith, ex('B')) in t
        assert not any(p == OWL.members for _, p, _ in t)

    def test_disjointclasses_nary_uses_alldisjointclasses(self):
        t = parse('Class: A\nClass: B\nClass: C\nDisjointClasses: A, B, C\n')
        node = next(s for s, p, o in t if p == RDF.type and o == OWL.AllDisjointClasses)
        assert any(p == OWL.members for s, p, o in t if s == node)

    def test_sameindividual_chains_pairwise(self):
        t = parse('Individual: A\nIndividual: B\nSameIndividual: A, B\n')
        assert (ex('A'), OWL.sameAs, ex('B')) in t

    def test_differentindividuals_binary_uses_differentfrom(self):
        t = parse('Individual: A\nIndividual: B\nDifferentIndividuals: A, B\n')
        assert (ex('A'), OWL.differentFrom, ex('B')) in t

    def test_differentindividuals_nary_uses_alldifferent(self):
        t = parse('Individual: A\nIndividual: B\nIndividual: C\nDifferentIndividuals: A, B, C\n')
        node = next(s for s, p, o in t if p == RDF.type and o == OWL.AllDifferent)
        assert any(p == OWL.members for s, p, o in t if s == node)


# ---------------------------------------------------------------------------
# Deliberately unsupported constructs - must raise, not mis-parse
# ---------------------------------------------------------------------------

class TestUnsupported:
    def test_datatype_frame(self):
        with pytest.raises(ManchesterSyntaxError):
            parse('Datatype: xsd:int\n')

    def test_disjointunionof(self):
        with pytest.raises(ManchesterSyntaxError):
            parse('Class: A\nClass: B\nClass: C\n    DisjointUnionOf: B, C\n')

    def test_haskey(self):
        with pytest.raises(ManchesterSyntaxError):
            parse('ObjectProperty: p\nClass: A\n    HasKey: p\n')

    def test_annotations_clause(self):
        with pytest.raises(ManchesterSyntaxError):
            parse('Class: A\n    Annotations: rdfs:comment "x"\n')

    def test_undeclared_default_prefix(self):
        with pytest.raises(ManchesterSyntaxError):
            parse_manchester('Class: A\n')

    def test_unknown_prefix(self):
        with pytest.raises(ManchesterSyntaxError):
            parse('Class: foo:A\n')

    def test_unterminated_iri(self):
        with pytest.raises(ManchesterSyntaxError):
            parse_manchester('Prefix: : <http://example.org/\nClass: A\n')

    def test_unterminated_string(self):
        with pytest.raises(ManchesterSyntaxError):
            parse('DataProperty: p\nIndividual: a\n    Facts: p "unterminated\n')


# ---------------------------------------------------------------------------
# StarLayerGraph.parse(format='manchester') wiring
# ---------------------------------------------------------------------------

class TestGraphIntegration:
    def test_parses_into_starlayer_graph(self):
        g = StarLayerGraph()
        g.parse(data=HEADER + 'Class: Animal\nClass: Cat\n    SubClassOf: Animal\n', format='manchester')
        assert (ex('Cat'), RDFS.subClassOf, ex('Animal')) in g

    def test_omn_is_an_alias(self):
        g = StarLayerGraph()
        g.parse(data=HEADER + 'Class: Cat\n', format='omn')
        assert (ex('Cat'), RDF.type, OWL.Class) in g
