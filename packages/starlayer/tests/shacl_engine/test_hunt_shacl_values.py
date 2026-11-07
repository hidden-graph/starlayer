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


def test_float_parsing_rounds_once():
    # 1 + 2**-24 + 1e-32 is just above the binary32 midpoint, so the nearest float is 1 + 2**-23, not 1.0
    a = ox.Literal("1.00000005960464477539062500000001", datatype=ox.NamedNode(XSD + "float"))
    b = ox.Literal("1.00000011920928955078125", datatype=ox.NamedNode(XSD + "float"))
    assert xv.compare(a, b) == 0
    assert xv.parse(a).value == 1 + 2**-23


@pytest.mark.parametrize(
    "lex, expected",
    [("3.4028235e38", 3.4028234663852886e38), ("3.4028236e38", float("inf")), ("3.5e38", float("inf")), ("1e-46", 0.0),
     ("1.4e-45", 1.401298464324817e-45), ("-0", -0.0), ("0.1", 0.10000000149011612), ("1e999999999", float("inf")), ("1e-999999999", 0.0)],
)
def test_float_parsing_edges(lex, expected):
    assert xv.parse(ox.Literal(lex, datatype=ox.NamedNode(XSD + "float"))).value == expected


def test_integer_promoted_to_float_rounds_once():
    n = 2**60 + 2**36 + 1  # just above the midpoint between the floats 2**60 and 2**60 + 2**37
    up = 2**60 + 2**37
    c = xv.compare(ox.Literal(str(n), datatype=ox.NamedNode(XSD + "integer")), ox.Literal(str(up), datatype=ox.NamedNode(XSD + "float")))
    assert c == 0


def test_overlay_literal_safety_check_is_thread_safe():
    import threading

    from starlayer.shacl_engine import overlay_oxigraph as ov

    def lits(k):
        return [ox.Literal(("+" if i % 2 else "") + str(k * 100000 + i), datatype=ox.NamedNode(XSD + "integer")) for i in range(1500)]

    errors, wrong = [], []

    def work(ls):
        for lit in ls:
            try:
                ok = ov.literal_survives_store(lit)
            except BaseException as e:  # noqa: BLE001
                errors.append(type(e).__name__)
                return
            if ok != (not lit.value.startswith("+")):
                wrong.append(lit.value)

    ts = [threading.Thread(target=work, args=(lits(k),)) for k in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errors and not wrong


# --- pre-binding (inject_everywhere) ---------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["has-values", "a1values", "my-construct", "my-where", "has_values"])
def test_prebinding_reaches_nested_group_after_keyword_like_local_name(name):
    g = OxigraphGraph.from_text(f"@prefix ex: <http://e/> . ex:n ex:{name} 1 .")
    q = f"PREFIX ex: <http://e/> SELECT ?x WHERE {{ ?x ex:{name} ?v . {{ FILTER(bound(?this)) }} }}"
    assert len(g.query(q, {"this": ox.NamedNode("http://e/a")})) == 1


def test_prebinding_with_a_sparql_12_annotation_block():
    g = OxigraphGraph.from_text("<http://e/a> <http://e/p> <http://e/b> {| <http://e/q> 1 |} .", format="turtle")
    q = "SELECT ?o ?z WHERE { ?this <http://e/p> ?o {| <http://e/q> ?z |} }"
    base = g.query(q)
    assert len(base) == 1
    assert g.query(q, {"this": ox.NamedNode("http://e/a")}) == base


def test_prebinding_with_construct_where_short_form():
    g = OxigraphGraph.from_text("@prefix ex: <http://e/> . ex:a ex:p ex:b . ex:c ex:p ex:d .")
    a = ox.NamedNode("http://e/a")
    full = g.query("PREFIX ex:<http://e/> CONSTRUCT { ?this ex:p ?o } WHERE { ?this ex:p ?o }", {"this": a})
    short = g.query("PREFIX ex:<http://e/> CONSTRUCT WHERE { ?this ex:p ?o }", {"this": a})
    assert len(full) == 1
    assert short == full


def test_union_view_sparql_counts_a_triple_held_in_two_graphs_once():
    n = ox.NamedNode
    shapes = OxigraphGraph.from_text(
        PRE.replace("http://example.org/", "http://e/")
        + 'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:select "SELECT $this ?value WHERE { $this <http://e/p> ?value }" ; sh:message "has p" ] .'
    )
    st = ox.Store()
    for g in (n("http://e/g1"), n("http://e/g2")):
        st.add(ox.Quad(n("http://e/a"), n("http://e/p"), n("http://e/b"), g))
    data = OxigraphGraph(st)
    assert len(data) == 1
    assert len(validate(data, shapes).results) == 1
    assert data.query("SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }")[0]["c"].value == "1"


# --- lone surrogates in IRIs and literals (the ill-formed-term policy) -----------------------------------------------


def _surrogate_case(obj, mode):
    from rdflib import Graph, URIRef
    from starlayer.shacl_engine.terms import TermError

    shapes = Graph().parse(
        data="@prefix ex: <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
        "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .",
        format="turtle",
    )
    g = Graph()
    g.add((URIRef("http://e/a"), URIRef("http://e/p"), obj))
    try:
        return api.validate(g, shapes, invalid_terms=mode)
    except TermError:
        return "TermError"


@pytest.mark.parametrize("which", ["iri", "literal", "lang_literal", "typed_literal"])
def test_lone_surrogate_strict_is_a_term_error(which):
    assert _surrogate_case(_surrogate_term(which), "error") == "TermError"


@pytest.mark.parametrize("which", ["iri", "literal", "lang_literal", "typed_literal"])
def test_lone_surrogate_lenient_validates(which):
    out = _surrogate_case(_surrogate_term(which), "lenient")
    assert out != "TermError" and out.conforms


@pytest.mark.parametrize("which", ["iri", "literal", "lang_literal", "typed_literal"])
def test_lone_surrogate_stand_in_maps_back(which):
    from starlayer.graph.oxgraph._rdflib_bridge import (
        engine_to_foreign,
        foreign_to_engine,
    )
    from starlayer.shacl_engine.terms import term_policy

    term = _surrogate_term(which)
    with term_policy("lenient"):
        back = engine_to_foreign(foreign_to_engine(term))
    assert back == term
    assert getattr(back, "language", None) == getattr(term, "language", None)
    assert getattr(back, "datatype", None) == getattr(term, "datatype", None)


def _surrogate_term(which):
    from rdflib import Literal, URIRef

    return {
        "iri": URIRef("http://e/\ud800"),
        "literal": Literal("a\ud800b"),
        "lang_literal": Literal("a\ud800b", lang="en"),
        "typed_literal": Literal("a\ud800b", datatype=URIRef("http://e/dt")),
    }[which]
