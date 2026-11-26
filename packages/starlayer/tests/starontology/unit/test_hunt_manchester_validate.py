"""validate_manchester_tree must reject a tree tree_to_manchester cannot decode."""

import pytest
from starlayer.graph.manchester._ox_terms import URIRef
from starlayer.starontology.manchester import (
    manchester_to_tree,
    tree_to_manchester,
    validate_manchester_tree,
)

TREE_ORD = URIRef('https://github.com/hidden-graph/starlayer/ns/tree#ord')
TREE_VALUE = URIRef('https://github.com/hidden-graph/starlayer/ns/tree#value')
P = 'Prefix: : <http://e/>\n'


def _conforms_or_decodes(tree):
    conforms = validate_manchester_tree(tree).conforms
    if conforms:
        tree_to_manchester(tree)  # must not raise for a tree the validator accepts
    return conforms


def test_unknown_facet_iri_is_rejected():
    tree = manchester_to_tree(P + 'DataProperty: :d Range: integer[>= 5]\n')
    for s, p, o in list(tree):
        if str(p).endswith('#facet>'):
            tree.remove((s, p, o))
            tree.add((s, p, URIRef('http://z/notAFacet')))
    assert not _conforms_or_decodes(tree)


def test_unknown_object_property_characteristic_is_rejected():
    tree = manchester_to_tree(P + 'ObjectProperty: :p Characteristics: Transitive\n')
    for s, p, o in list(tree):
        if str(o).endswith('#TransitiveProperty>') and 'manchester-ast' in str(p):
            tree.remove((s, p, o))
            tree.add((s, p, URIRef('http://z/notACharacteristic')))
    assert not _conforms_or_decodes(tree)


def test_unknown_data_property_characteristic_is_rejected():
    tree = manchester_to_tree(P + 'DataProperty: :d Characteristics: Functional\n')
    for s, p, o in list(tree):
        if str(o).endswith('#FunctionalProperty>') and 'manchester-ast' in str(p):
            tree.remove((s, p, o))
            tree.add((s, p, URIRef('http://z/notACharacteristic')))
    assert not _conforms_or_decodes(tree)


@pytest.mark.parametrize('text, member', [
    ('Class: :A DisjointUnionOf: :B, :C\n', '<http://e/B>'),
    ('Class: :A HasKey: :p, :q\n', '<http://e/p>'),
    ('ObjectProperty: :r SubPropertyChain: :p o :q\n', '<http://e/p>'),
])
def test_single_axiom_member_without_an_ordinal_is_rejected(text, member):
    """A member of ``manch:values`` is a tree:Item and needs its tree:ord (a list cell without rdf:first, before the ordinals)."""
    tree = manchester_to_tree(P + text)
    items = [s for s, p, o in tree if p == TREE_VALUE and str(o) == member]
    assert len(items) == 1, items
    tree.remove((items[0], TREE_ORD, None))
    assert not _conforms_or_decodes(tree)


@pytest.mark.parametrize('text', [
    'Class: :A DisjointUnionOf: :B, :C\n',
    'Class: :A HasKey: :p, :q\n',
    'ObjectProperty: :r SubPropertyChain: :p o :q\n',
    'DataProperty: :d Range: string[langRange "en"] Characteristics: Functional\n',
    'ObjectProperty: :p Characteristics: Functional, Transitive, Symmetric\n',
])
def test_valid_trees_still_conform(text):
    assert validate_manchester_tree(manchester_to_tree(P + text)).conforms
