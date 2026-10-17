"""``ValidationResult.report_text`` agrees with ``report_graph``: a ``Provenance:`` line
appears only when the report knows the thing it states (the whole block is left out when
nothing is known, with no "Not specified" placeholders), and its ``Conforms:`` line matches
the recomputed conformance."""

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


_SEVERITY_SHAPES = """
    @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
    ex:S a sh:NodeShape ; sh:targetClass ex:P ;
        sh:property [ sh:path ex:n ; sh:minCount 1 ; sh:severity {severity} ] .
"""


def _validate_with_severity(severity: str, **kwargs):
    data = StarLayerGraph()
    data.parse(data=_NOT_CONFORMING, format="turtle")
    shapes = StarLayerGraph()
    shapes.parse(data=_SEVERITY_SHAPES.format(severity=severity), format="turtle")
    return validate(data, shapes, **kwargs)


@pytest.mark.parametrize("severity", ["sh:Debug", "sh:Trace"])
def test_a_debug_or_trace_only_result_does_not_block_conformance_in_the_text_either(
    severity,
):
    """SHACL 1.2's lowest severities never block conformance. pySHACL does not know them and
    renders ``Conforms: False``; the text is corrected to match ``conforms`` and the graph."""
    result = _validate_with_severity(severity)
    assert result.conforms is True
    assert result.report_text.splitlines()[1] == "Conforms: True"
    assert "Results (1)" in result.report_text  # the result itself is still listed


@pytest.mark.parametrize(
    "severity, kwargs, expected",
    [
        ("sh:Violation", {}, False),
        ("sh:Warning", {}, False),
        ("sh:Info", {}, False),
        ("sh:Warning", {"allow_warnings": True}, True),
        ("sh:Info", {"allow_infos": True}, True),
    ],
)
def test_the_conforms_line_always_matches_the_result(severity, kwargs, expected):
    result = _validate_with_severity(severity, **kwargs)
    assert result.conforms is expected
    assert result.report_text.splitlines()[1] == f"Conforms: {expected}"
