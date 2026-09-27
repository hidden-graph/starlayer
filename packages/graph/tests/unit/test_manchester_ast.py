"""Round-trip tests for starlayergraph.ontology.to_ast_rdf (Manchester Syntax
AST as RDF, mirroring the sibling starsparql package's test_ast_ontology.py).

Verifies text -> parse_manchester_ast -> rdf_ast_to_manchester_ast ->
manchester_ast_to_text -> re-parse_manchester_ast, by compiling *both* the
original text and the re-serialized text through the real, unmodified
manchester_parser.parse_manchester() and comparing the resulting OWL-semantic
triple sets via starlayergraph.compare.isomorphic() - proves structural
faithfulness without requiring byte-identical text (same idiom this project
already uses for its own round-trip proofs elsewhere).
"""

import pytest

from starlayergraph.compare import isomorphic
from starlayergraph.ontology.to_ast_rdf import (
    manchester_ast_to_text,
    parse_manchester_ast,
    rdf_ast_to_manchester_ast,
)
from starlayergraph.parsers.manchester_parser import parse_manchester

HEADER = (
    'Prefix: : <http://example.org/>\n'
    'Prefix: xsd: <http://www.w3.org/2001/XMLSchema#>\n'
    'Prefix: owl: <http://www.w3.org/2002/07/owl#>\n'
)

DOCUMENTS = [
    # Class frame: SubClassOf/EquivalentTo/DisjointWith, multi-item.
    HEADER + """
    Class: Cat
        SubClassOf: Animal, Pet
        EquivalentTo: Feline
        DisjointWith: Dog
    """,
    # SuperClassOf: folds into the same SubClassOf: clause, direction swapped.
    HEADER + """
    Class: Animal
        SuperClassOf: Cat, Dog
    """,
    # DisjointUnionOf:/HasKey: single-axiom clauses.
    HEADER + """
    Class: Pet
        DisjointUnionOf: Cat, Dog, Bird
        HasKey: hasOwner, hasName
    """,
    # Every class-expression construct: And/Or/Not/OneOf/Some/Only/Value/
    # SelfR/Min/Max/Exact, nested.
    HEADER + """
    Class: Weird
        EquivalentTo: (Cat and Pet) or (not Dog), hasOwner some Person,
                      hasOwner only Person, hasStatus value Alive,
                      likes Self, hasLeg min 3, hasLeg max 5, hasLeg exactly 4,
                      {Alice, Bob}
    """,
    # ObjectProperty: Domain/Range/SubPropertyOf/EquivalentTo/DisjointWith/
    # InverseOf/Characteristics/SubPropertyChain, and inverse property expr.
    HEADER + """
    ObjectProperty: hasParent
        Domain: Person
        Range: Person
        SubPropertyOf: hasRelative
        EquivalentTo: hasProgenitor
        DisjointWith: hasSibling
        InverseOf: hasChild
        Characteristics: InverseFunctional, Asymmetric, Irreflexive

    ObjectProperty: hasGrandparent
        SubPropertyChain: hasParent o hasParent
    """,
    # DataProperty: Range with a data-range "or" and Datatype: facets.
    HEADER + """
    DataProperty: hasAge
        Domain: Person
        Range: xsd:integer or xsd:decimal
        Characteristics: Functional

    Datatype: AdultAge
        EquivalentTo: xsd:integer[>= "18"^^xsd:integer]
    """,
    # AnnotationProperty frame.
    HEADER + """
    AnnotationProperty: hasComment
        Domain: Person
        Range: Person
        SubPropertyOf: hasNote
    """,
    # Individual frame: Types/Facts (incl. negative)/SameAs/DifferentFrom,
    # plus frame-level and per-item Annotations:.
    HEADER + """
    Individual: john
        Annotations: rdfs:label "John"
        Types: Person, hasAge value "42"^^xsd:integer
        Facts: Annotations: rdfs:comment "primary" hasParent mary,
               not hasParent bob
        SameAs: johnny
        DifferentFrom: mary
    """,
    # Misc axioms - all six keywords, including n-ary forms.
    HEADER + """
    EquivalentClasses: Cat, Feline, Kitty
    DisjointClasses: Cat, Dog, Bird
    EquivalentProperties: hasParent, hasProgenitor
    DisjointProperties: hasParent, hasSibling
    SameIndividual: john, johnny, jonathan
    DifferentIndividuals: john, mary, bob
    """,
    # Ontology header + Import:, multiple prefixes.
    'Prefix: : <http://example.org/>\n'
    'Prefix: foo: <http://example.org/foo#>\n'
    'Ontology: <http://example.org/onto>\n'
    'Import: <http://example.org/other-onto>\n'
    """
    Class: Thing
    """,
]


@pytest.mark.parametrize('text', DOCUMENTS)
def test_ast_roundtrip_preserves_owl_semantics(text):
    graph, root = parse_manchester_ast(text)
    document = rdf_ast_to_manchester_ast(graph, root)
    rendered = manchester_ast_to_text(document)

    original_triples = parse_manchester(text)
    roundtripped_triples = parse_manchester(rendered)

    assert isomorphic(original_triples, roundtripped_triples), (
        f'round-trip diverged for input:\n{text}\n\nre-rendered as:\n{rendered}'
    )
    assert len(original_triples) > 0  # guard against a vacuously-true empty comparison


def test_ast_roundtrip_is_stable_under_a_second_pass():
    """Encoding the re-rendered text again should reach a semantic fixed
    point (no further drift on a second decode/re-render cycle)."""
    text = DOCUMENTS[4]  # the ObjectProperty/SubPropertyChain document
    graph, root = parse_manchester_ast(text)
    rendered_once = manchester_ast_to_text(rdf_ast_to_manchester_ast(graph, root))

    graph2, root2 = parse_manchester_ast(rendered_once)
    rendered_twice = manchester_ast_to_text(rdf_ast_to_manchester_ast(graph2, root2))

    assert isomorphic(parse_manchester(rendered_once), parse_manchester(rendered_twice))


def test_decoded_document_is_a_plain_namedtuple_tree():
    text = HEADER + 'Class: Cat\n    SubClassOf: Animal\n'
    graph, root = parse_manchester_ast(text)
    document = rdf_ast_to_manchester_ast(graph, root)

    assert document.frames[0].kind == 'Class'
    assert document.frames[0].clauses[0].clause_kind == 'SubClassOf:'
