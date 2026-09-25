"""Unit tests for starlayergraph.serializers.manchester.

The primary correctness check throughout is round-tripping: parse known-good
Manchester text (via the already-tested parse_manchester), serialize it back,
re-parse the result, and assert the two graphs are isomorphic. This checks
two things at once - the serializer's RDF-shape recognition is correct, and
its output is itself genuinely valid, re-parseable Manchester syntax - and
matches the oracle-adjacent verification style used throughout this parser/
serializer's development (see manchester.py's own docstring for the same
technique applied against the real OWL API parser, ad hoc and uncommitted).

A handful of scoped-out reconstructions (SuperClassOf:/SuperPropertyOf:
always come back as SubClassOf:/SubPropertyOf:, onlysome always comes back
expanded, Misc EquivalentClasses:/SameIndividual:/binary DisjointClasses:
always come back as per-frame clauses) are asserted by their actual RDF
shape, not by expecting the identical keyword back - see manchester.py's
docstring for why those specific reconstructions aren't attempted.
"""

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from starlayergraph.compare import isomorphic
from starlayergraph.parsers.manchester_parser import parse_manchester
from starlayergraph.serializers.manchester import serialize_manchester

EX = 'http://example.org/'
HEADER = 'Prefix: : <http://example.org/>\nPrefix: rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n'


def ex(name):
    return URIRef(EX + name)


def parse(body):
    g = Graph()
    for t in parse_manchester(HEADER + body):
        g.add(t)
    g.bind('', EX)
    return g


def round_trip(body):
    """Parse, serialize, re-parse; return (original_graph, serialized_text,
    reparsed_graph) so callers can assert on all three."""
    g1 = parse(body)
    text = serialize_manchester(g1)
    g2 = Graph()
    for t in parse_manchester(text):
        g2.add(t)
    return g1, text, g2


def assert_round_trips(body):
    g1, text, g2 = round_trip(body)
    assert isomorphic(g1, g2), f'not isomorphic:\n{text}'
    return text


class TestFramesRoundTrip:
    def test_class_frame(self):
        assert_round_trips('Class: Animal\nClass: Cat\n    SubClassOf: Animal\n')

    def test_object_property_frame(self):
        assert_round_trips('ObjectProperty: hasFriend\n')

    def test_data_property_frame(self):
        assert_round_trips('DataProperty: hasAge\n')

    def test_annotation_property_frame(self):
        assert_round_trips(
            'Class: Animal\nAnnotationProperty: note\n    Domain: Animal\n    Range: Animal\n'
        )

    def test_individual_frame(self):
        assert_round_trips('Individual: Felix\n')

    def test_datatype_frame(self):
        assert_round_trips('Datatype: PositiveInt\n    EquivalentTo: xsd:integer\n')

    def test_ontology_and_import(self):
        text = assert_round_trips(
            'Ontology: <http://example.org/onto>\n    Import: <http://example.org/other>\n'
        )
        assert 'Ontology:' in text
        assert 'Import:' in text


class TestClassClausesRoundTrip:
    def test_subclassof_multiple(self):
        assert_round_trips(
            'Class: Animal\nClass: Rock\nClass: Cat\n'
            '    SubClassOf: Animal\n    DisjointWith: Rock\n'
        )

    def test_superclassof_comes_back_as_subclassof(self):
        text = assert_round_trips('Class: Animal\nClass: Cat\n    SuperClassOf: Animal\n')
        assert 'SuperClassOf' not in text
        assert 'SubClassOf: :Cat' in text or 'SubClassOf::Cat' in text.replace(' ', '')

    def test_disjointunionof(self):
        assert_round_trips(
            'Class: Dog\nClass: Cat\nClass: Animal\n    DisjointUnionOf: Dog, Cat\n'
        )

    def test_haskey(self):
        assert_round_trips('DataProperty: ssn\nClass: Person\n    HasKey: ssn\n')

    def test_frame_level_annotations(self):
        text = assert_round_trips('Class: A\n    Annotations: rdfs:comment "a class"\n')
        assert 'Annotations:' in text


class TestClassExpressionsRoundTrip:
    def test_intersection_and_complement(self):
        assert_round_trips('Class: A\nClass: B\nClass: C\n    EquivalentTo: A and (not B)\n')

    def test_union(self):
        assert_round_trips('Class: A\nClass: B\nClass: C\n    EquivalentTo: A or B\n')

    def test_nested_or_inside_and_needs_parens_on_the_way_back(self):
        # If the renderer's precedence handling were wrong this would
        # round-trip to a DIFFERENT axiom (A and B) or C instead of
        # A and (B or C) - isomorphism would still hold structurally for
        # *some* graph, just not the intended one; asserting the specific
        # nested shape survives is the real check here.
        g1, text, g2 = round_trip('Class: A\nClass: B\nClass: C\nClass: D\n'
                                   '    EquivalentTo: A and (B or C)\n')
        assert isomorphic(g1, g2)
        node = next(o for s, p, o in g2 if s == ex('D') and p == OWL.equivalentClass)
        assert any(p == OWL.intersectionOf for s, p, o in g2 if s == node)

    def test_enumeration(self):
        assert_round_trips(
            'Individual: Alice\nIndividual: Bob\nClass: C\n    EquivalentTo: {Alice, Bob}\n'
        )

    def test_some_only_restrictions(self):
        assert_round_trips(
            'ObjectProperty: hasFriend\nClass: Person\nClass: C\n'
            '    SubClassOf: hasFriend some Person\n    SubClassOf: hasFriend only Person\n'
        )

    def test_onlysome_comes_back_expanded(self):
        text = assert_round_trips(
            'ObjectProperty: hasChild\nClass: Person\nClass: C\n'
            '    SubClassOf: hasChild onlysome Person\n'
        )
        assert 'onlysome' not in text
        assert ' and ' in text

    def test_value_and_self_restrictions(self):
        assert_round_trips(
            'ObjectProperty: worksWith\nObjectProperty: monitorsItself\nIndividual: Alice\nClass: C\n'
            '    SubClassOf: worksWith value Alice\n    SubClassOf: monitorsItself Self\n'
        )

    def test_unqualified_and_qualified_cardinality(self):
        assert_round_trips(
            'ObjectProperty: hasChild\nClass: Person\nClass: C\n'
            '    SubClassOf: hasChild min 2\n'
            '    SubClassOf: hasChild max 3 Person\n'
            '    SubClassOf: hasChild exactly 1\n'
        )

    def test_inverse_property_expression(self):
        assert_round_trips(
            'ObjectProperty: hasChild\nObjectProperty: hasParent\n'
            '    InverseOf: inverse hasChild\n'
        )


class TestPropertyClausesRoundTrip:
    def test_domain_range_characteristics(self):
        assert_round_trips(
            'Class: Animal\nObjectProperty: hasLegs\n'
            '    Domain: Animal\n    Range: Animal\n    Characteristics: Functional, Symmetric\n'
        )

    def test_data_property_range_is_a_datatype(self):
        assert_round_trips('DataProperty: hasAge\n    Range: xsd:integer\n')

    def test_superpropertyof_comes_back_as_subpropertyof(self):
        text = assert_round_trips(
            'ObjectProperty: hasPet\nObjectProperty: hasCat\n    SuperPropertyOf: hasPet\n'
        )
        assert 'SuperPropertyOf' not in text

    def test_subpropertychain(self):
        assert_round_trips(
            'ObjectProperty: hasParent\nObjectProperty: hasGrandparent\n'
            '    SubPropertyChain: hasParent o hasParent\n'
        )


class TestIndividualClausesRoundTrip:
    def test_types_facts_sameas_differentfrom(self):
        assert_round_trips(
            'Class: Cat\nObjectProperty: hasOwner\nIndividual: Alice\nIndividual: Bob\n'
            'Individual: Kitty\n'
            'Individual: Felix\n'
            '    Types: Cat\n    Facts: hasOwner Alice\n'
            '    SameAs: Kitty\n    DifferentFrom: Bob\n'
        )

    def test_negative_fact_object_and_data_property(self):
        assert_round_trips(
            'ObjectProperty: p\nDataProperty: q\nIndividual: b\nIndividual: a\n'
            '    Facts: not p b, not q 3\n'
        )


class TestDataRangesRoundTrip:
    def test_facet_restriction(self):
        assert_round_trips('DataProperty: hasAge\n    Range: xsd:integer[>= 0, <= 150]\n')

    def test_data_union_and_oneof(self):
        assert_round_trips('DataProperty: hasCode\n    Range: xsd:string or xsd:integer\n')
        assert_round_trips('DataProperty: hasStatus\n    Range: {"a", "b"}\n')


class TestMiscAxiomsRoundTrip:
    def test_disjointclasses_binary_comes_back_as_frame_clause(self):
        g1, text, g2 = round_trip('Class: A\nClass: B\nDisjointClasses: A, B\n')
        assert isomorphic(g1, g2)
        assert (ex('A'), OWL.disjointWith, ex('B')) in g2 or (ex('B'), OWL.disjointWith, ex('A')) in g2

    def test_disjointclasses_nary_is_reconstructed_as_misc_axiom(self):
        text = assert_round_trips('Class: A\nClass: B\nClass: C\nDisjointClasses: A, B, C\n')
        assert 'DisjointClasses:' in text

    def test_disjointproperties_nary_is_reconstructed(self):
        text = assert_round_trips(
            'ObjectProperty: p\nObjectProperty: q\nObjectProperty: r\nDisjointProperties: p, q, r\n'
        )
        assert 'DisjointProperties:' in text

    def test_differentindividuals_nary_is_reconstructed(self):
        text = assert_round_trips(
            'Individual: a\nIndividual: b\nIndividual: c\nDifferentIndividuals: a, b, c\n'
        )
        assert 'DifferentIndividuals:' in text

    def test_equivalentclasses_comes_back_as_frame_clause(self):
        # Not reconstructed as a Misc axiom (RDF-indistinguishable from a
        # per-subject EquivalentTo: chain) - still round-trips correctly.
        assert_round_trips('Class: A\nClass: B\nClass: C\nEquivalentClasses: A, B, C\n')


class TestInlineAxiomAnnotationsRoundTrip:
    def test_subclassof_item_annotated(self):
        text = assert_round_trips(
            'Class: Animal\nClass: Pet\nClass: Cat\n'
            '    SubClassOf: Annotations: rdfs:comment "why" Animal, Pet\n'
        )
        assert 'Annotations: rdfs:comment "why"' in text

    def test_annotation_does_not_leak_to_next_item(self):
        g1, text, g2 = round_trip(
            'Class: Animal\nClass: Pet\nClass: Cat\n'
            '    SubClassOf: Annotations: rdfs:comment "why" Animal, Pet\n'
        )
        assert isomorphic(g1, g2)
        axiom_nodes = [s for s, p, o in g2 if p == RDF.type and o == OWL.Axiom]
        assert len(axiom_nodes) == 1
        assert (axiom_nodes[0], OWL.annotatedTarget, ex('Animal')) in g2
        assert (axiom_nodes[0], OWL.annotatedTarget, ex('Pet')) not in g2

    def test_haskey_annotated(self):
        assert_round_trips(
            'DataProperty: ssn\nClass: Person\n'
            '    HasKey: Annotations: rdfs:comment "why" ssn\n'
        )

    def test_positive_fact_annotated(self):
        assert_round_trips(
            'ObjectProperty: p\nIndividual: b\nIndividual: a\n'
            '    Facts: Annotations: rdfs:comment "why" p b\n'
        )

    def test_negative_fact_annotated(self):
        g1, text, g2 = round_trip(
            'ObjectProperty: p\nIndividual: b\nIndividual: a\n'
            '    Facts: Annotations: rdfs:comment "why" not p b\n'
        )
        assert isomorphic(g1, g2)
        na_node = next(s for s, p, o in g2 if p == RDF.type and o == OWL.NegativePropertyAssertion)
        assert (na_node, RDFS.comment, Literal('why')) in g2


class TestPrefixesAndNames:
    def test_used_prefix_is_declared_and_names_are_compact(self):
        text = assert_round_trips('Class: Animal\nClass: Cat\n    SubClassOf: Animal\n')
        assert 'Prefix: : <http://example.org/>' in text
        assert '<http://example.org/Animal>' not in text
        assert ':Animal' in text

    def test_unbound_namespace_falls_back_to_full_iri(self):
        g = Graph()
        g.add((URIRef('http://unbound.example/X'), RDF.type, OWL.Class))
        text = serialize_manchester(g)
        assert '<http://unbound.example/X>' in text


class TestErrors:
    def test_unrecognized_blank_node_raises(self):
        from rdflib import BNode
        g = Graph()
        subject = ex('Weird')
        blank = BNode()
        g.add((subject, RDF.type, OWL.Class))
        g.add((subject, RDFS.subClassOf, blank))
        # `blank` matches no recognizable class-expression shape (no
        # intersectionOf/unionOf/complementOf/oneOf/Restriction predicate).
        with pytest.raises(ValueError):
            serialize_manchester(g)
