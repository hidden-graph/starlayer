"""Regression tests for the SKOS findings of GitHub issue #101 (third hunt).

Oracle: the SKOS Reference (https://www.w3.org/TR/skos-reference/). S23 (related is symmetric), S25/S26
(narrower and narrowerTransitive are the inverses of broader and broaderTransitive), S27 (related is
disjoint with broaderTransitive), S44 (exactMatch is symmetric and transitive), S46 (exactMatch is
disjoint with broadMatch and relatedMatch), S13/S14 (labels), S36 (every memberList item is a member).
"""

import pytest
from rdflib import Graph
from starlayer.starontology.skos import skos_validate

HEAD = (
    '@prefix skos: <http://www.w3.org/2004/02/skos/core#> . @prefix : <http://ex/> .\n'
    + ''.join(f':{n} a skos:Concept ; skos:prefLabel "{n}"@en .\n' for n in 'abc')
)


def _conforms(body):
    return skos_validate(Graph().parse(data=HEAD + body, format='turtle'))[0]


@pytest.mark.parametrize('body', [
    ':a skos:related :b . :a skos:broader :b .',  # asserted directly (always caught)
    ':a skos:related :b . :b skos:broader :a .',
    ':a skos:broader :b . :b skos:related :a .',
    ':a skos:related :b . :b skos:narrower :a .',
    ':a skos:related :b . :b skos:narrowerTransitive :a .',
    ':a skos:related :c . :a skos:broader :b . :b skos:broader :c .',  # broaderTransitive is transitive
    ':a skos:exactMatch :b . :a skos:broadMatch :b .',
    ':a skos:exactMatch :b . :b skos:broadMatch :a .',
    ':a skos:exactMatch :b . :b skos:narrowMatch :a .',
    ':a skos:exactMatch :b . :b skos:relatedMatch :a .',
    ':a skos:exactMatch :b . :b skos:exactMatch :c . :a skos:broadMatch :c .',  # exactMatch is transitive
])
def test_entailed_disjointness_conflicts_are_reported(body):
    assert not _conforms(body)


@pytest.mark.parametrize('body', [
    ':a skos:related :b . :c skos:broader :a .',
    ':a skos:related :b . :a skos:broader :c .',
    ':a skos:exactMatch :b . :a skos:broadMatch :c .',
    ':a skos:broader :b . :b skos:broader :c . :a skos:related :a2 .',
])
def test_unrelated_relations_still_conform(body):
    assert _conforms(body + '\n:a2 a skos:Concept ; skos:prefLabel "a2"@en .')


def test_plain_literal_labels_are_allowed():
    body = ':d a skos:Concept ; skos:prefLabel "Dog" ; skos:altLabel "Hound" ; skos:hiddenLabel "dg" .'
    assert _conforms(body)


def test_non_literal_pref_label_is_still_rejected():
    assert not _conforms(':d a skos:Concept ; skos:prefLabel 5 .')
    assert not _conforms(':d a skos:Concept ; skos:prefLabel :a .')


def test_ordered_collection_with_only_a_member_list_conforms():
    assert _conforms(':o a skos:OrderedCollection ; skos:memberList ( :a :b ) .')
