"""Round-trip tests for starontology.manchester (Manchester Syntax as a
syntax tree in RDF, mirroring the sibling starlayer.sparql package's
test_ast_ontology.py).

Verifies text -> manchester_parse_to_tree -> manchester_tree_to_text -> re-parse, by
compiling *both* the original text and the re-serialized text through the
real, unmodified manchester_parser.parse_manchester() and comparing the
resulting OWL-semantic triple sets via starlayer.graph.compare.isomorphic()
- proves structural faithfulness without requiring byte-identical text
(same idiom this project already uses for its own round-trip proofs
elsewhere).

The decode-only half of the pipeline (``_tree_to_document``) is private -
editing is meant to happen on the tree-RDF itself, not on a Python object
in between (see the module's own docstring) - so this file only reaches
for it directly in the one test that specifically verifies that internal
shape (``test_decoded_document_is_a_plain_namedtuple_tree``).
"""

import pytest

from starlayer.graph.compare import isomorphic
from starlayer.starontology.manchester import manchester_parse_to_tree, manchester_tree_to_owl, manchester_tree_to_text
from starlayer.starontology.manchester import _find_root, _tree_to_document
from starlayer.graph.parsers.manchester_parser import parse_manchester

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
    graph = manchester_parse_to_tree(text)
    rendered = manchester_tree_to_text(graph)

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
    graph = manchester_parse_to_tree(text)
    rendered_once = manchester_tree_to_text(graph)

    graph2 = manchester_parse_to_tree(rendered_once)
    rendered_twice = manchester_tree_to_text(graph2)

    assert isomorphic(parse_manchester(rendered_once), parse_manchester(rendered_twice))


def test_decoded_document_is_a_plain_namedtuple_tree():
    """White-box: _tree_to_document is private (editing happens on the
    tree-RDF, not this intermediate object - see the module's own
    docstring), but this still verifies its internal shape directly."""
    text = HEADER + 'Class: Cat\n    SubClassOf: Animal\n'
    graph = manchester_parse_to_tree(text)
    document = _tree_to_document(graph, _find_root(graph))

    assert document.frames[0].kind == 'Class'
    assert document.frames[0].clauses[0].clause_kind == 'SubClassOf:'


@pytest.mark.parametrize('text', DOCUMENTS)
def test_tree_to_owl_matches_compiling_the_text_directly(text):
    graph = manchester_parse_to_tree(text)
    assert isomorphic(manchester_tree_to_owl(graph), parse_manchester(text))
