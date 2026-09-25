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

    def test_ontology_import(self):
        t = parse_manchester(
            'Prefix: : <http://example.org/>\n'
            'Ontology: <http://example.org/onto>\n'
            '    Import: <http://example.org/other>\n'
            'Class: Cat\n'
        )
        assert (URIRef(EX + 'onto'), OWL.imports, URIRef(EX + 'other')) in t


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

    def test_superclassof_swaps_subject_and_object(self):
        t = parse('Class: Animal\nClass: Cat\n    SuperClassOf: Animal\n')
        assert (ex('Animal'), RDFS.subClassOf, ex('Cat')) in t

    def test_disjointunionof(self):
        t = parse('Class: Dog\nClass: Cat\nClass: Animal\n    DisjointUnionOf: Dog, Cat\n')
        node = next(o for s, p, o in t if s == ex('Animal') and p == OWL.disjointUnionOf)
        assert (node, RDF.first, ex('Dog')) in t

    def test_haskey(self):
        t = parse('DataProperty: ssn\nClass: Person\n    HasKey: ssn\n')
        node = next(o for s, p, o in t if s == ex('Person') and p == OWL.hasKey)
        assert (node, RDF.first, ex('ssn')) in t

    def test_frame_level_annotations(self):
        t = parse('Class: A\n    Annotations: rdfs:comment "a class"\n')
        assert (ex('A'), RDFS.comment, Literal('a class')) in t


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

    def test_that_is_a_synonym_for_and(self):
        with_and = parse('ObjectProperty: hasPart\nClass: Leg\nObjectProperty: hasNumber\nClass: C\n'
                          '    SubClassOf: hasPart some (Leg and (hasNumber value "4"^^xsd:integer))\n')
        with_that = parse('ObjectProperty: hasPart\nClass: Leg\nObjectProperty: hasNumber\nClass: C\n'
                           '    SubClassOf: hasPart some (Leg that (hasNumber value "4"^^xsd:integer))\n')
        and_intersections = [p for s, p, o in with_and if p == OWL.intersectionOf]
        that_intersections = [p for s, p, o in with_that if p == OWL.intersectionOf]
        assert and_intersections and that_intersections

    def test_onlysome_expands_to_some_and_only(self):
        t = parse('ObjectProperty: hasChild\nClass: Person\nClass: C\n    SubClassOf: hasChild onlysome Person\n')
        some_bnode, some_filler = restriction_for(t, ex('hasChild'), OWL.someValuesFrom)
        only_bnode, only_filler = restriction_for(t, ex('hasChild'), OWL.allValuesFrom)
        assert some_filler == ex('Person') == only_filler
        assert any(p == OWL.intersectionOf for s, p, o in t)

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

    def test_superpropertyof_swaps_subject_and_object(self):
        t = parse('ObjectProperty: hasPet\nObjectProperty: hasCat\n    SuperPropertyOf: hasPet\n')
        assert (ex('hasPet'), RDFS.subPropertyOf, ex('hasCat')) in t

    def test_subpropertychain(self):
        t = parse('ObjectProperty: hasParent\nObjectProperty: hasGrandparent\n'
                   '    SubPropertyChain: hasParent o hasParent\n')
        node = next(o for s, p, o in t if s == ex('hasGrandparent') and p == OWL.propertyChainAxiom)
        assert (node, RDF.first, ex('hasParent')) in t

    def test_property_frame_level_annotations(self):
        t = parse('ObjectProperty: p\n    Annotations: rdfs:label "p"\n')
        assert (ex('p'), RDFS.label, Literal('p')) in t


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

    def test_negative_fact_object_property(self):
        t = parse('ObjectProperty: p\nIndividual: b\nIndividual: a\n    Facts: not p b\n')
        node = next(s for s, pr, o in t if pr == RDF.type and o == OWL.NegativePropertyAssertion)
        assert (node, OWL.sourceIndividual, ex('a')) in t
        assert (node, OWL.assertionProperty, ex('p')) in t
        assert (node, OWL.targetIndividual, ex('b')) in t

    def test_negative_fact_data_property(self):
        t = parse('DataProperty: hasAge\nIndividual: a\n    Facts: not hasAge 3\n')
        node = next(s for s, pr, o in t if pr == RDF.type and o == OWL.NegativePropertyAssertion)
        assert (node, OWL.targetValue, Literal(3, datatype=XSD.integer)) in t

    def test_frame_level_annotations(self):
        t = parse('Individual: Felix\n    Annotations: rdfs:label "Felix the cat"\n')
        assert (ex('Felix'), RDFS.label, Literal('Felix the cat')) in t


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

    def test_equivalentproperties_chains_pairwise(self):
        t = parse('ObjectProperty: p\nObjectProperty: q\nEquivalentProperties: p, q\n')
        assert (ex('p'), OWL.equivalentProperty, ex('q')) in t

    def test_disjointproperties_binary_uses_propertydisjointwith(self):
        t = parse('ObjectProperty: p\nObjectProperty: q\nDisjointProperties: p, q\n')
        assert (ex('p'), OWL.propertyDisjointWith, ex('q')) in t

    def test_disjointproperties_nary_uses_alldisjointproperties(self):
        t = parse('ObjectProperty: p\nObjectProperty: q\nObjectProperty: r\nDisjointProperties: p, q, r\n')
        node = next(s for s, p, o in t if p == RDF.type and o == OWL.AllDisjointProperties)
        assert any(p == OWL.members for s, p, o in t if s == node)


# ---------------------------------------------------------------------------
# Datatype: frames and data ranges
# ---------------------------------------------------------------------------

class TestDatatypesAndDataRanges:
    def test_datatype_frame_declares_type(self):
        t = parse('Datatype: PositiveInt\n')
        assert (ex('PositiveInt'), RDF.type, RDFS.Datatype) in t

    def test_datatype_equivalentto(self):
        t = parse('Datatype: PositiveInt\n    EquivalentTo: xsd:integer\n')
        assert (ex('PositiveInt'), OWL.equivalentClass, XSD.integer) in t

    def test_facet_restriction(self):
        t = parse('DataProperty: hasAge\n    Range: xsd:integer[>= 0, <= 150]\n')
        node = next(o for s, p, o in t if s == ex('hasAge') and p == RDFS.range)
        assert (node, OWL.onDatatype, XSD.integer) in t
        facets = [o for s, p, o in t if p == OWL.withRestrictions and s == node]
        assert facets
        facet_list_node = facets[0]
        first_facet_bnode = next(o for s, p, o in t if s == facet_list_node and p == RDF.first)
        assert (first_facet_bnode, XSD.minInclusive, Literal(0, datatype=XSD.integer)) in t

    def test_data_range_union(self):
        t = parse('DataProperty: hasCode\n    Range: xsd:string or xsd:integer\n')
        node = next(o for s, p, o in t if s == ex('hasCode') and p == RDFS.range)
        assert (node, RDF.type, RDFS.Datatype) in t
        assert any(p == OWL.unionOf for s, p, o in t if s == node)

    def test_data_one_of(self):
        t = parse('DataProperty: hasStatus\n    Range: {"a", "b"}\n')
        node = next(o for s, p, o in t if s == ex('hasStatus') and p == RDFS.range)
        assert any(p == OWL.oneOf for s, p, o in t if s == node)

    def test_datatype_frame_level_annotations(self):
        t = parse('Datatype: PositiveInt\n    Annotations: rdfs:comment "always positive"\n')
        assert (ex('PositiveInt'), RDFS.comment, Literal('always positive')) in t


# ---------------------------------------------------------------------------
# Inline per-axiom Annotations: - distinct from the frame-level clause
# (TestFrames/TestClassClauses etc. above) - annotates one specific item
# inside another clause's list, via owl:Axiom reification.
# ---------------------------------------------------------------------------

class TestInlineAxiomAnnotations:
    def _axiom_node(self, t, subject, pred, obj):
        return next(
            s for s, p, o in t
            if p == RDF.type and o == OWL.Axiom
            and (s, OWL.annotatedSource, subject) in t
            and (s, OWL.annotatedProperty, pred) in t
            and (s, OWL.annotatedTarget, obj) in t
        )

    def test_subclassof_item_annotated(self):
        t = parse('Class: Animal\nClass: Cat\n'
                   '    SubClassOf: Annotations: rdfs:comment "why" Animal\n')
        assert (ex('Cat'), RDFS.subClassOf, ex('Animal')) in t
        node = self._axiom_node(t, ex('Cat'), RDFS.subClassOf, ex('Animal'))
        assert (node, RDFS.comment, Literal('why')) in t

    def test_annotation_does_not_carry_over_to_next_item(self):
        # Confirmed empirically against the OWL API oracle: the
        # Annotations: prefix applies to exactly the one item it precedes.
        t = parse('Class: Animal\nClass: Pet\nClass: Cat\n'
                   '    SubClassOf: Annotations: rdfs:comment "why" Animal, Pet\n')
        assert (ex('Cat'), RDFS.subClassOf, ex('Pet')) in t
        assert not any(
            p == OWL.annotatedTarget and o == ex('Pet') for s, p, o in t
        )

    def test_haskey_whole_clause_annotated(self):
        t = parse('DataProperty: ssn\nClass: Person\n'
                   '    HasKey: Annotations: rdfs:comment "why" ssn\n')
        list_node = next(o for s, p, o in t if s == ex('Person') and p == OWL.hasKey)
        node = self._axiom_node(t, ex('Person'), OWL.hasKey, list_node)
        assert (node, RDFS.comment, Literal('why')) in t

    def test_positive_fact_item_annotated(self):
        t = parse('ObjectProperty: p\nIndividual: b\nIndividual: a\n'
                   '    Facts: Annotations: rdfs:comment "why" p b\n')
        node = self._axiom_node(t, ex('a'), ex('p'), ex('b'))
        assert (node, RDFS.comment, Literal('why')) in t

    def test_negative_fact_annotated_directly_on_its_own_bnode(self):
        # No separate owl:Axiom wrapper - the NegativePropertyAssertion
        # bnode is already the reification-like structure, so the
        # annotation attaches straight to it.
        t = parse('ObjectProperty: p\nIndividual: b\nIndividual: a\n'
                   '    Facts: Annotations: rdfs:comment "why" not p b\n')
        node = next(s for s, p, o in t if p == RDF.type and o == OWL.NegativePropertyAssertion)
        assert (node, RDFS.comment, Literal('why')) in t
        assert not any(p == RDF.type and o == OWL.Axiom for s, p, o in t)

    def test_unannotated_item_gets_no_reification(self):
        t = parse('Class: Animal\nClass: Cat\n    SubClassOf: Animal\n')
        assert not any(p == RDF.type and o == OWL.Axiom for s, p, o in t)


# ---------------------------------------------------------------------------
# Deliberately unsupported constructs - must raise, not mis-parse
# ---------------------------------------------------------------------------

class TestUnsupported:
    def test_swrl_rule_not_supported(self):
        with pytest.raises(ManchesterSyntaxError):
            parse('Rule: DifferentFrom(?x, ?y)\n')

    def test_valuepartition_not_supported(self):
        # Reserved in the OWL API's own keyword enum but every
        # frame/section/axiom/quantifier/connective flag on it is false -
        # not actually wired up as parseable even by the oracle itself.
        with pytest.raises(ManchesterSyntaxError):
            parse('ValuePartition: Speed\n')

    def test_misc_axiom_inline_annotation_not_supported(self):
        # Unlike every other clause (see TestInlineAxiomAnnotations), the
        # six top-level Misc axioms don't support this - their pairwise-
        # chain/AllDisjoint* encoding means one list item doesn't
        # correspond to one axiom triple the way it does everywhere else.
        with pytest.raises(ManchesterSyntaxError):
            parse('Class: A\nClass: B\nClass: C\n'
                  'EquivalentClasses: Annotations: rdfs:comment "why" A, B, C\n')

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
