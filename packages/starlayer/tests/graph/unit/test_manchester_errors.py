"""Manchester syntax and OWL-in-RDF errors are classified by cause (step A, stage 5): malformed text is a ``FormatError`` of kind
``"manchester"``, RDF that is not valid OWL a ``FormatError`` of kind ``"owl"``, nesting past the stack an ``ExecutionError`` of kind
``"nesting"``, a graph Manchester syntax cannot write an ``ExecutionError`` of kind ``"unsupported"``."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.errors import ExecutionError, FormatError, StarLayerError
from starlayer.graph import StarLayerGraph
from starlayer.graph.manchester._ox_terms import OWL, RDF, RDFS
from starlayer.graph.manchester.parser import parse_manchester
from starlayer.graph.manchester.serializer import serialize_manchester
from starlayer.starontology import manchester as M

H = 'Prefix: : <http://e/>\n'


def test_syntax_error_carries_reason_and_line():
    with pytest.raises(FormatError) as caught:
        parse_manchester(H + 'Class: A\n SubClassOf: nope:B\n')
    error = caught.value
    assert error.kind == 'manchester' and isinstance(error, StarLayerError) and not isinstance(error, (ValueError, SyntaxError))
    assert error.line == 3 and error.why and 'nope:B' in str(error) and str(error).startswith('at line 3:\nBad syntax (')


def test_tokenizer_error_has_a_document_position():
    text = H + 'Class: A\n Annotations: :p "open'
    with pytest.raises(FormatError) as caught:
        parse_manchester(text)
    error = caught.value
    assert error.pos == text.index('"open') and (error.line, error.col) == (3, text.splitlines()[2].index('"open') + 1)


def test_swrl_rule_is_a_manchester_format_error_with_context():
    with pytest.raises(FormatError, match='SWRL rules') as caught:
        parse_manchester(H + 'Rule: :A(?x) -> :B(?x)\n')
    assert caught.value.kind == 'manchester' and caught.value.context == 'SWRL Rule: unsupported'


def test_deep_nesting_is_an_execution_error():
    text = H + 'Class: A\n  SubClassOf: ' + '(' * 5000 + 'B' + ')' * 5000 + '\n'
    with pytest.raises(ExecutionError) as caught:
        parse_manchester(text)
    assert caught.value.kind == 'nesting' and 'nested too deeply' in str(caught.value) and not isinstance(caught.value, FormatError)


def test_unrecognized_tree_node_is_a_manchester_format_error():
    g = M.manchester_to_tree(H + 'Class: :A\n SubClassOf: :p some :B\n')
    for restriction in list(g.subjects(RDF.type, M.MANCH.Some)):
        g.remove((restriction, RDF.type, M.MANCH.Some))
    with pytest.raises(FormatError) as caught:
        M.tree_to_manchester(g)
    assert caught.value.kind == 'manchester' and caught.value.context == 'manch: tree'


def test_a_second_document_is_a_value_error():
    g = M.manchester_to_tree(H + 'Class: :A\n')
    with pytest.raises(ValueError, match='already holds'):
        M.manchester_to_tree(H + 'Class: :B\n', tree_graph=g)


def test_graph_without_a_document_is_a_value_error():
    with pytest.raises(ValueError, match='manch:OntologyDocument'):
        M.tree_to_manchester(StarLayerGraph())


def test_unrecognized_class_expression_is_an_owl_format_error():
    g = StarLayerGraph()
    a = ox.NamedNode('http://e/A')
    g.add((a, RDF.type, OWL.Class))
    g.add((a, RDFS.subClassOf, ox.BlankNode()))
    with pytest.raises(FormatError) as caught:
        serialize_manchester(g)
    assert caught.value.kind == 'owl' and caught.value.context


def test_restriction_without_property_is_an_owl_format_error():
    g = StarLayerGraph()
    a, r = ox.NamedNode('http://e/A'), ox.BlankNode()
    g.add((a, RDF.type, OWL.Class))
    g.add((a, RDFS.subClassOf, r))
    g.add((r, RDF.type, OWL.Restriction))
    with pytest.raises(FormatError, match='onProperty') as caught:
        serialize_manchester(g)
    assert caught.value.kind == 'owl'


def test_render_gap_is_an_unsupported_execution_error():
    g = StarLayerGraph()
    a = ox.NamedNode('http://e/A')
    g.add((a, RDF.type, OWL.Class))
    g.add((a, RDFS.label, ox.Literal('x', language='en', direction=ox.BaseDirection.LTR)))
    with pytest.raises(ExecutionError) as caught:
        serialize_manchester(g)
    assert caught.value.kind == 'unsupported' and caught.value.context
