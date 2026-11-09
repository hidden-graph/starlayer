"""manchester_validate must reject a tree manchester_tree_to_text cannot decode."""

import pytest
from starlayer.graph.parsers._ox_terms import RDF, URIRef
from starlayer.starontology.manchester import (
    manchester_parse_to_tree,
    manchester_tree_to_text,
    manchester_validate,
)

P = 'Prefix: : <http://e/>\n'


def _conforms_or_decodes(tree):
    conforms = manchester_validate(tree)[0]
    if conforms:
        manchester_tree_to_text(tree)  # must not raise for a tree the validator accepts
    return conforms


def test_unknown_facet_iri_is_rejected():
    tree = manchester_parse_to_tree(P + 'DataProperty: :d Range: integer[>= 5]\n')
    for s, p, o in list(tree):
        if str(p).endswith('#facetPredicate>'):
            tree.remove((s, p, o))
            tree.add((s, p, URIRef('http://z/notAFacet')))
    assert not _conforms_or_decodes(tree)


def test_unknown_object_property_characteristic_is_rejected():
    tree = manchester_parse_to_tree(P + 'ObjectProperty: :p Characteristics: Transitive\n')
    for s, p, o in list(tree):
        if str(o).endswith('#TransitiveProperty>') and 'manchester-ast' in str(p):
            tree.remove((s, p, o))
            tree.add((s, p, URIRef('http://z/notACharacteristic')))
    assert not _conforms_or_decodes(tree)


def test_unknown_data_property_characteristic_is_rejected():
    tree = manchester_parse_to_tree(P + 'DataProperty: :d Characteristics: Functional\n')
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
def test_single_axiom_list_cell_without_rdf_first_is_rejected(text, member):
    tree = manchester_parse_to_tree(P + text)
    cells = [(s, p, o) for s, p, o in tree if p == RDF.first and str(o) == member]
    assert len(cells) == 1, cells
    tree.remove(cells[0])
    assert not _conforms_or_decodes(tree)


@pytest.mark.parametrize('text', [
    'Class: :A DisjointUnionOf: :B, :C\n',
    'Class: :A HasKey: :p, :q\n',
    'ObjectProperty: :r SubPropertyChain: :p o :q\n',
    'DataProperty: :d Range: string[langRange "en"] Characteristics: Functional\n',
    'ObjectProperty: :p Characteristics: Functional, Transitive, Symmetric\n',
])
def test_valid_trees_still_conform(text):
    assert manchester_validate(manchester_parse_to_tree(P + text))[0]
