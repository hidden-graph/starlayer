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
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.graph.parsers._ox_terms import RDF, BNode
from starlayer.starontology import manchester as ms
from starlayer.starontology.manchester import MANCH, manchester_parse_to_tree
from tests.graph.unit.test_manchester_ast import DOCUMENTS


@pytest.mark.parametrize('text', DOCUMENTS)
def test_valid_documents_conform(text):
    graph = manchester_parse_to_tree(text)
    conforms, _, results_text = ms.manchester_validate(graph)
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
    return manchester_parse_to_tree(text, graph=StarLayerGraph())  # edited below


def test_wrong_item_type_under_data_prop_range_clause_fails():
    """A DataPropRangeClause's item must hold a manch:DataRange, not a
    manch:ClassExpression - the exact bug the missing sh:targetClass
    declarations let through undetected before being fixed."""
    graph = _encode_data_prop_range()
    clause = next(graph.subjects(RDF.type, MANCH.DataPropRangeClause))
    items_list = next(graph.objects(clause, MANCH.items))
    item = graph.value(items_list, RDF.first)
    old_value = next(graph.objects(item, MANCH.value))
    graph.remove((item, MANCH.value, old_value))

    bad_and = BNode()
    graph.add((bad_and, RDF.type, MANCH.And))
    ops = ms._build_rdf_list(graph, [MANCH.ClassExpression])
    graph.add((bad_and, MANCH.operands, ops))
    graph.remove((item, MANCH.value, None))
    graph.add((item, MANCH.value, bad_and))

    conforms, _, results_text = ms.manchester_validate(graph)
    assert not conforms
    assert 'manch:DataRangeItemListShape' in results_text or 'data range' in results_text


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
    graph = manchester_parse_to_tree(text, graph=StarLayerGraph())  # edited below
    misc = next(graph.subjects(RDF.type, MANCH.MiscEquivalentClassesAxiom))
    items_list = next(graph.objects(misc, MANCH.items))

    bad = BNode()
    graph.add((bad, RDF.type, MANCH.Inverse))
    graph.add((bad, MANCH.operand, MANCH.someProp))
    graph.remove((items_list, RDF.first, None))  # the first cell of the list now holds `bad`
    graph.add((items_list, RDF.first, bad))

    conforms, _, results_text = ms.manchester_validate(graph)
    assert not conforms


def test_broken_mid_chain_rdf_list_fails():
    """A rdf:List missing rdf:first partway through must fail the generic
    WellFormedListShape check - not just at the head."""
    graph = _encode_data_prop_range()
    clause = next(graph.subjects(RDF.type, MANCH.DataPropDomainClause))
    items_list = next(graph.objects(clause, MANCH.items))
    rest = next(graph.objects(items_list, RDF.rest), None)

    extra = BNode()
    graph.add((items_list, RDF.rest, extra))
    if rest is not None:
        graph.add((extra, RDF.rest, rest))
    # extra deliberately has no rdf:first - a broken mid-chain cell.

    conforms, _, results_text = ms.manchester_validate(graph)
    assert not conforms
