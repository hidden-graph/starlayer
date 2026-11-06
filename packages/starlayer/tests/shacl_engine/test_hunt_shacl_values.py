"""Regression tests from the SHACL-engine values bug hunt (terms, XSD values, fidelity, text, ill-formed data)."""

from __future__ import annotations

import warnings

import pytest

pytest.importorskip("pyoxigraph")

from starlayer.shacl_engine import api, validate  # noqa: E402
from starlayer.shacl_engine.oxigraph_view import OxigraphGraph  # noqa: E402
from starlayer.shacl_engine.terms import StarLayerFidelityWarning  # noqa: E402

PRE = (
    "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.org/> . "
    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
)


def _run(ttl):
    g = OxigraphGraph.from_text(ttl)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        o = validate(g, g)
    return o, [x for x in w if issubclass(x.category, StarLayerFidelityWarning)]


# --- fidelity: date/time/duration datatypes -------------------------------------------------------------------------


def test_fidelity_warns_for_datetimestamp_datatype():
    o, w = _run(
        PRE + 'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:datatype xsd:dateTimeStamp ] .\n'
        'ex:a ex:p "2000-01-01T00:00:00Z"^^xsd:dateTimeStamp .'
    )
    assert w and o.warnings


@pytest.mark.parametrize(
    "lex, dt",
    [("2000-01-01T00:00:00.0Z", "dateTime"), ("24:00:00", "time"), ("PT60S", "duration"), ("PT60S", "dayTimeDuration"), ("P12M", "yearMonthDuration")],
)
def test_fidelity_warns_for_rewritten_temporal_literal(lex, dt):
    o, w = _run(
        PRE + 'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:pattern "x" ] .\n'
        f'ex:a ex:p "{lex}"^^xsd:{dt} .'
    )
    assert w and o.warnings


# --- fidelity: SPARQL-based constraints -----------------------------------------------------------------------------


def test_fidelity_warns_for_sh_sparql():
    data = OxigraphGraph.from_text(PRE + 'ex:a ex:p "04"^^xsd:integer .')
    shapes = OxigraphGraph.from_text(
        PRE + 'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:select """PREFIX ex: <http://example.org/>\n'
        'SELECT $this ?value WHERE { $this ex:p ?value . FILTER(STR(?value) = "04") }""" ] .'
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = api.validate(data, shapes)
    assert [w for w in caught if issubclass(w.category, StarLayerFidelityWarning)]
    assert out.warnings
