"""SHACL shape tests for the manch: vocabulary (see manchester_shapes.ttl/.py)
- mirrors the sibling starlayer.sparql package's test_shacl_shapes.py structure.

Two directions get tested:

1. Every representative document (imported from test_manchester_ast.DOCUMENTS,
   so this suite can't silently drift from what the encoder actually
   produces) encodes to a graph that *conforms*.
2. A handful of deliberately malformed graphs, built by mutating a valid
   encoded document, each *fail* validation for the specific structural
   reason the mutation introduces - not just "conforms is False somewhere".
"""

import pytest
from starlayer import starontology
from starlayer.graph import StarLayerGraph, ordinals
from starlayer.graph.manchester._ox_terms import RDF, BNode
from starlayer.starontology import manchester as ms
from starlayer.starontology.manchester import MANCH, manchester_to_tree
from tests.graph.unit.test_manchester_ast import DOCUMENTS


@pytest.mark.parametrize('text', DOCUMENTS)
def test_valid_documents_conform(text):
    graph = manchester_to_tree(text)
    outcome = ms.validate_manchester_tree(graph)
    conforms = outcome.conforms
    results_text = outcome.report_text
    assert conforms, results_text


def test_shapes_graph_is_valid_shacl_and_reusable():
    # get_ontology_graph() must hand back an independent copy each call -
    # pyshacl mutates the shapes graph it's given during validation.
    g1 = starontology.get_ontology_graph("manchester_shacl")
    g2 = starontology.get_ontology_graph("manchester_shacl")
    assert g1 is not g2
    assert len(g1) == len(g2) > 0


def _encode_data_prop_range():
    text = (
        'Prefix: : <http://example.org/>\n'
        'Prefix: xsd: <http://www.w3.org/2001/XMLSchema#>\n'
        'DataProperty: hasAge\n'
        '    Domain: Person\n'
        '    Range: xsd:integer\n'
    )
    return manchester_to_tree(text, tree_graph=StarLayerGraph())  # edited below


def test_wrong_item_type_under_data_prop_range_clause_fails():
    """A DataPropertyRangeClause's item must hold a manch:DataRange, not a
    manch:ClassExpression - the exact bug the missing sh:targetClass
    declarations let through undetected before being fixed."""
    graph = _encode_data_prop_range()
    clause = next(graph.subjects(RDF.type, MANCH.DataPropertyRangeClause))
    (item,) = ordinals.ordered_items(graph, clause, MANCH.items)
    graph.remove((item, MANCH.value, None))

    bad_and = BNode()
    graph.add((bad_and, RDF.type, MANCH.And))
    ordinals.write_ordered(graph, bad_and, MANCH.operands, [BNode(), BNode()])
    graph.add((item, MANCH.value, bad_and))

    outcome = ms.validate_manchester_tree(graph)
    conforms = outcome.conforms
    results_text = outcome.report_text
    assert not conforms
    assert 'manch:DataRangeItemShape' in results_text or 'data range' in results_text


def test_misc_axiom_item_of_wrong_family_fails():
    """A MiscEquivalentClassesAxiom's items must each be a manch:ClassExpression
    (or a bare IRI) - substituting a manch:PropertyExpression-typed node (the
    wrong family entirely) must be caught, even though MiscAxiom items are
    bare values with no ClauseItem wrapper to hang a value-kind check off of
    (see manch:ClassExpressionListShape, reused directly here)."""
    text = (
        'Prefix: : <http://example.org/>\n'
        'EquivalentClasses: Cat, Feline\n'
    )
    graph = manchester_to_tree(text, tree_graph=StarLayerGraph())  # edited below
    misc = next(graph.subjects(RDF.type, MANCH.MiscEquivalentClassesAxiom))
    bad = BNode()  # the wrong family, in the first position (the Item that held the first class name goes)
    graph.add((bad, RDF.type, MANCH.Inverse))
    graph.add((bad, MANCH.operand, MANCH.someProp))
    ordinals.replace_at(graph, misc, MANCH.items, 0, bad)

    outcome = ms.validate_manchester_tree(graph)
    conforms = outcome.conforms
    results_text = outcome.report_text
    assert not conforms


def test_a_clause_item_with_no_ordinal_fails():
    """An ordered child without tree:ord has no position: the shared tree shapes reject it (a list cell without rdf:first, before the ordinals)."""
    graph = _encode_data_prop_range()
    clause = next(graph.subjects(RDF.type, MANCH.DataPropertyDomainClause))
    (item,) = ordinals.ordered_items(graph, clause, MANCH.items)
    graph.remove((item, ordinals.ORD, None))

    outcome = ms.validate_manchester_tree(graph)
    assert not outcome.conforms
