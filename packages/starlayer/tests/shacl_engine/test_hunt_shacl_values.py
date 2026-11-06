"""Regression tests from the SHACL-engine values bug hunt (terms, XSD values, fidelity, text, ill-formed data)."""

from __future__ import annotations

import warnings

import pytest

pytest.importorskip("pyoxigraph")

import pyoxigraph as ox  # noqa: E402
from starlayer.shacl_engine import api, validate  # noqa: E402
from starlayer.shacl_engine import xsd_values as xv  # noqa: E402
from starlayer.shacl_engine.oxigraph_view import OxigraphGraph  # noqa: E402
from starlayer.shacl_engine.terms import StarLayerFidelityWarning  # noqa: E402

PRE = (
    "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.org/> . "
    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
)
XSD = "http://www.w3.org/2001/XMLSchema#"


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


# --- integers and date/time components over 4300 digits (CPython's int() string limit) -------------------------------


def test_huge_integer_validates():
    big = "1" * 5000
    o, _w = _run(
        PRE + f"ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:minInclusive 5 ] .\nex:a ex:p {big} ."
    )
    assert o.conforms


def test_huge_integer_is_well_formed_and_compares():
    lit = ox.Literal("1" * 5000, datatype=ox.NamedNode(XSD + "integer"))
    assert xv.well_formed(lit)
    assert xv.compare(lit, ox.Literal("5", datatype=ox.NamedNode(XSD + "integer"))) == 1


@pytest.mark.parametrize(
    "lex, dt",
    [("1" + "0" * 5000 + "-01-01T00:00:00Z", "dateTime"), ("P" + "9" * 5000 + "Y", "duration"), ("P" + "9" * 5000 + "D", "dayTimeDuration")],
)
def test_huge_date_time_components_do_not_raise(lex, dt):
    lit = ox.Literal(lex, datatype=ox.NamedNode(XSD + dt))
    xv.well_formed(lit)
    xv.compare(lit, lit)


def test_huge_integer_violation_report_text_renders():
    big = "1" * 5000
    o, _w = _run(
        PRE + f"ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:maxInclusive 5 ] .\nex:a ex:p {big} ."
    )
    assert not o.conforms
    assert big in o.report_text


@pytest.mark.parametrize("lex", ["QUJ=", "AB==", "QR=="])
def test_base64_non_canonical_final_sextet_is_ill_formed(lex):
    assert not xv.well_formed(ox.Literal(lex, datatype=ox.NamedNode(XSD + "base64Binary")))
    g = OxigraphGraph.from_text(
        PRE + f'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:datatype xsd:base64Binary ] .\nex:a ex:p "{lex}"^^xsd:base64Binary .'
    )
    assert not validate(g, g).conforms


@pytest.mark.parametrize("lex", ["QUI=", "QQ==", "QUJD", "", "AA==", "/w=="])
def test_base64_canonical_forms_stay_well_formed(lex):
    assert xv.well_formed(ox.Literal(lex, datatype=ox.NamedNode(XSD + "base64Binary")))
