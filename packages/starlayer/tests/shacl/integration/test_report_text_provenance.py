"""``ValidationResult.report_text`` only makes statements it has data for: a
``Provenance:`` line appears when the report knows the thing it states, and the
whole block is left out when nothing is known (no "Not specified" placeholders)."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl import validate

pyshacl = pytest.importorskip("pyshacl")

_SHAPES = """
    @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
    ex:S a sh:NodeShape ; sh:targetClass ex:P ; sh:property [ sh:path ex:n ; sh:minCount 1 ] .
"""
_CONFORMING = "@prefix ex: <http://example.org/> . ex:a a ex:P ; ex:n 'x' ."
_NOT_CONFORMING = "@prefix ex: <http://example.org/> . ex:a a ex:P ."
_DATA_IRI = "http://example.org/data1"
_SHAPES_IRI = "http://example.org/shapes1"


def _validate(data_ttl: str, **kwargs):
    data = StarLayerGraph()
    data.parse(data=data_ttl, format="turtle")
    shapes = StarLayerGraph()
    shapes.parse(data=_SHAPES, format="turtle")
    return validate(data, shapes, **kwargs)


def test_with_no_graph_identities_there_is_no_provenance_block():
    text = _validate(_CONFORMING).report_text
    assert "Provenance" not in text and "Not specified" not in text
    assert text.startswith("Validation Report\nConforms: True")


def test_only_the_data_graph_line_appears_when_only_the_data_graph_is_known():
    text = _validate(_CONFORMING, data_graph_iri=_DATA_IRI).report_text
    assert "Used Data Graph: ex:data1" in text
    assert (
        "Used Shapes Graph" not in text
        and "conformsTo" not in text
        and "Not specified" not in text
    )


def test_both_identities_give_both_lines_and_the_conforms_to_statement():
    text = _validate(
        _CONFORMING, data_graph_iri=_DATA_IRI, shapes_graph_iri=_SHAPES_IRI
    ).report_text
    assert "Used Data Graph: ex:data1" in text
    assert "Used Shapes Graph: ex:shapes1" in text
    assert "ex:data1 sh:conformsTo ex:shapes1 ." in text


def test_a_non_conforming_result_makes_no_conforms_to_statement():
    result = _validate(
        _NOT_CONFORMING, data_graph_iri=_DATA_IRI, shapes_graph_iri=_SHAPES_IRI
    )
    assert result.conforms is False
    assert "Used Data Graph: ex:data1" in result.report_text
    assert (
        "conformsTo" not in result.report_text
        and "Not specified" not in result.report_text
    )
