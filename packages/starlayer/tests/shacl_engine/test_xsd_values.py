"""Unit tests for ``shacl_engine/xsd_values.py`` (pure-Python XSD value space over pyoxigraph literals), including a
cross-check against rdflib's own literal values on every well-formed case and on the W3C SHACL 1.2 fixtures."""

from __future__ import annotations

import itertools
from decimal import Decimal
from pathlib import Path

import pyoxigraph as ox
import pytest
from rdflib import Graph, Literal, URIRef
from starlayer.shacl_engine import xsd_values as xv

XSD = "http://www.w3.org/2001/XMLSchema#"


def lit(lex: str, dt: str | None = None, lang: str | None = None) -> ox.Literal:
    if lang:
        return ox.Literal(lex, language=lang)
    return ox.Literal(lex, datatype=ox.NamedNode(XSD + dt)) if dt else ox.Literal(lex)


INTEGER_RANGE = {
    "byte": (-128, 127), "short": (-32768, 32767), "int": (-(2**31), 2**31 - 1), "long": (-(2**63), 2**63 - 1),
    "unsignedByte": (0, 255), "unsignedShort": (0, 65535), "unsignedInt": (0, 2**32 - 1),
    "unsignedLong": (0, 2**64 - 1), "nonNegativeInteger": (0, None), "positiveInteger": (1, None),
    "nonPositiveInteger": (None, 0), "negativeInteger": (None, -1), "integer": (None, None),
}  # fmt: skip


@pytest.mark.parametrize("dt,bounds", INTEGER_RANGE.items())
def test_integer_derived_types_range_checked(dt, bounds):
    lo, hi = bounds
    probes = [0, 1, -1, 127, 128, -128, -129, 255, 256, 2**31, -(2**31) - 1, 2**63, 2**64 - 1, 2**64, 10**30, -(10**30)]
    for n in probes + [x for x in (lo, hi) if x is not None]:
        ok = (lo is None or n >= lo) and (hi is None or n <= hi)
        assert xv.well_formed(lit(str(n), dt)) is ok, (dt, n)
        assert (xv.parse(lit(str(n), dt)) is not None) is ok
        if ok:
            assert xv.parse(lit(str(n), dt)).value == n


@pytest.mark.parametrize("lex,ok", [("04", True), ("+4", True), ("-0", True), (" 4 ", True), ("4.0", False), ("", False),
                                    ("1e3", False), ("0x10", False), ("1_0", False), ("٣", False), ("--4", False)])  # fmt: skip
def test_integer_lexical(lex, ok):
    assert xv.well_formed(lit(lex, "integer")) is ok


@pytest.mark.parametrize("lex,ok", [("4.0", True), (".5", True), ("5.", True), ("-.5", True), ("1e3", False),
                                    ("INF", False), ("NaN", False), ("", False), (".", False)])  # fmt: skip
def test_decimal_lexical(lex, ok):
    assert xv.well_formed(lit(lex, "decimal")) is ok
    if ok:
        assert xv.parse(lit(lex, "decimal")).value == Decimal(lex)


def test_float_double():
    for dt in ("float", "double"):
        assert xv.parse(lit("INF", dt)).value == float("inf")
        assert xv.parse(lit("-INF", dt)).value == float("-inf")
        assert xv.parse(lit("NaN", dt)).value != xv.parse(lit("NaN", dt)).value
        assert xv.well_formed(lit("1.5E3", dt)) and xv.parse(lit("1.5E3", dt)).value == 1500.0
        for bad in ("inf", "nan", "1e", "e3", "", "+NaN", "1.5f"):
            assert not xv.well_formed(lit(bad, dt)), bad
    assert xv.parse(lit("0.1", "float")).value != 0.1  # binary32 rounding
    assert xv.parse(lit("1e39", "float")).value == float("inf")
    assert xv.parse(lit("1e39", "double")).value == 1e39
    assert xv.compare(lit("NaN", "double"), lit("NaN", "double")) is None
    assert xv.compare(lit("INF", "double"), lit("1", "integer")) == 1


@pytest.mark.parametrize("lex,ok", [("true", True), ("false", True), ("1", True), ("0", True), ("TRUE", False),
                                    ("none", False), ("yes", False), ("", False)])  # fmt: skip
def test_boolean(lex, ok):
    assert xv.well_formed(lit(lex, "boolean")) is ok


def test_numeric_comparison_across_types():
    c = xv.compare
    assert c(lit("1", "integer"), lit("1.0", "decimal")) == 0
    assert c(lit("1", "int"), lit("2", "double")) == -1
    # F&O 6.2 / SPARQL 17.3: the decimal is promoted to double, so they are equal (found by the Oxigraph cross-check)
    assert c(lit("0.1", "decimal"), lit("0.1", "double")) == 0
    assert c(lit("3", "byte"), lit("2", "unsignedLong")) == 1
    assert c(lit("300", "byte"), lit("1", "integer")) is None  # ill-formed
    assert c(lit("1", "integer"), lit("1")) is None
    assert c(lit("true", "boolean"), lit("1", "integer")) is None


def test_string_boolean_compare_and_langs():
    c = xv.compare
    assert c(lit("a"), lit("b")) == -1 and c(lit("b", "string"), lit("b")) == 0
    assert c(lit("a", lang="en"), lit("b", lang="en")) is None
    assert c(lit("false", "boolean"), lit("1", "boolean")) == -1
    assert c(lit("1", "boolean"), lit("true", "boolean")) == 0
    assert xv.parse(lit("x", lang="en")) is None and xv.well_formed(lit("x", lang="en"))
    assert xv.well_formed(lit("x", "token")) and not xv.well_formed(lit(" x", "token"))
    assert not xv.well_formed(lit("a\tb", "normalizedString"))
    assert xv.well_formed(lit("en-GB", "language")) and not xv.well_formed(lit("en_GB", "language"))
    assert xv.well_formed(lit("zz", "hexBinary")) is False and xv.well_formed(lit("0aFF", "hexBinary"))
    assert xv.well_formed(lit("SGk=", "base64Binary")) and not xv.well_formed(lit("SGk", "base64Binary"))
    assert xv.well_formed(lit("anything at all", "unknownType")) and not xv.known_datatype(XSD + "unknownType")
    assert xv.well_formed(ox.Literal("zzz", datatype=ox.NamedNode("http://example.com/dt")))


def test_datetime_lexical():
    ok = ["2000-01-01T00:00:00", "2000-01-01T24:00:00", "2000-01-01T12:30:15.5Z", "2000-01-01T12:00:00+14:00",
          "-0001-01-01T00:00:00", "0000-01-01T00:00:00", "12345-01-01T00:00:00", "2000-02-29T00:00:00"]  # fmt: skip
    bad = ["2001-02-29T00:00:00", "2000-13-01T00:00:00", "2000-01-01", "2000-01-01T24:00:01", "2000-01-01T25:00:00",
           "2000-01-01T00:00:60", "2000-01-01T00:00:00+14:01", "2000-01-01T00:00:00+15:00", "00-01-01T00:00:00",
           "2000-1-1T00:00:00", "2000-01-01T00:00", "2000-01-01 00:00:00"]  # fmt: skip
    for s in ok:
        assert xv.well_formed(lit(s, "dateTime")), s
    for s in bad:
        assert not xv.well_formed(lit(s, "dateTime")), s
    assert xv.compare(lit("2000-01-01T24:00:00", "dateTime"), lit("2000-01-02T00:00:00", "dateTime")) == 0
    assert not xv.well_formed(lit("2000-01-01T00:00:00", "dateTimeStamp"))
    assert xv.well_formed(lit("2000-01-01T00:00:00Z", "dateTimeStamp"))


def test_other_timeline_types():
    good = {"date": ["2000-01-01", "2000-01-01Z", "2000-01-01-05:00"], "time": ["12:00:00", "24:00:00", "00:00:00.123+01:00"],
            "gYear": ["2000", "-0044", "20000", "2000Z"], "gYearMonth": ["2000-02", "2000-12Z"],
            "gMonth": ["--02", "--12Z"], "gMonthDay": ["--02-29", "--12-31"], "gDay": ["---01", "---31Z"]}  # fmt: skip
    bad = {"date": ["2000-02-30", "2000-01", "20000101"], "time": ["12:00", "25:00:00"], "gYear": ["200", "2000-01"],
           "gYearMonth": ["2000-13"], "gMonth": ["--13", "-02"], "gMonthDay": ["--02-30", "--13-01"], "gDay": ["---32", "--01"]}  # fmt: skip
    for dt, xs in good.items():
        for s in xs:
            assert xv.well_formed(lit(s, dt)), (dt, s)
    for dt, xs in bad.items():
        for s in xs:
            assert not xv.well_formed(lit(s, dt)), (dt, s)


def test_timezone_partial_order():
    c = xv.compare
    dt = lambda s: lit(s, "dateTime")  # noqa: E731
    assert c(dt("2000-01-01T12:00:00Z"), dt("2000-01-01T13:00:00+01:00")) == 0
    assert c(dt("2000-01-01T12:00:00Z"), dt("2000-01-01T12:00:00+01:00")) == 1
    assert c(dt("2000-01-01T12:00:00"), dt("2000-01-01T12:00:01")) == -1
    # with vs without timezone: ordered only when more than 14 hours apart
    assert c(dt("2000-01-01T00:00:00Z"), dt("2000-01-01T12:00:00")) is None
    assert c(dt("2000-01-01T12:00:00"), dt("2000-01-01T00:00:00Z")) is None
    assert c(dt("2000-01-01T00:00:00Z"), dt("2000-01-02T00:00:01")) == -1
    assert c(dt("2000-01-02T00:00:01"), dt("2000-01-01T00:00:00Z")) == 1
    assert c(dt("2000-01-01T00:00:00Z"), dt("2000-01-01T00:00:00")) is None  # never equal
    # exactly 14h: still incomparable
    assert c(dt("2000-01-01T00:00:00Z"), dt("2000-01-01T14:00:00")) is None
    d = lambda s: lit(s, "date")  # noqa: E731
    assert c(d("2000-01-01"), d("2000-01-02")) == -1 and c(d("2000-01-01Z"), d("2000-01-01")) is None
    assert c(d("2000-01-01Z"), d("2000-01-31")) == -1
    assert c(dt("2000-01-01T00:00:00"), d("2000-01-01")) is None  # different kinds
    assert c(lit("12:00:00Z", "time"), lit("13:00:00+01:00", "time")) == 0
    assert c(lit("2000", "gYear"), lit("2001", "gYear")) == -1
    assert c(lit("--02", "gMonth"), lit("--03", "gMonth")) == -1
    assert c(lit("---05", "gDay"), lit("---04", "gDay")) == 1
    assert c(lit("--02-29", "gMonthDay"), lit("--03-01", "gMonthDay")) == -1
    assert c(lit("2000-02", "gYearMonth"), lit("2000-02", "gYearMonth")) == 0
    assert c(lit("-0001-01-01T00:00:00", "dateTime"), lit("0000-01-01T00:00:00", "dateTime")) == -1


def test_durations():
    c = xv.compare
    du = lambda s, t="duration": lit(s, t)  # noqa: E731
    assert xv.well_formed(du("P1Y2M3DT4H5M6.5S")) and xv.well_formed(du("-P1D")) and xv.well_formed(du("PT0S"))
    for bad in ("P", "PT", "P1DT", "1Y", "P1.5Y", "P-1Y", "P1H", "PT1Y"):
        assert not xv.well_formed(du(bad)), bad
    assert not xv.well_formed(du("P1D", "yearMonthDuration")) and xv.well_formed(du("P1Y", "yearMonthDuration"))
    assert not xv.well_formed(du("P1Y", "dayTimeDuration")) and xv.well_formed(du("P1DT1H", "dayTimeDuration"))
    assert c(du("PT24H"), du("P1D")) == 0
    assert c(du("P1D"), du("P2D")) == -1
    assert c(du("P1Y"), du("P12M")) == 0
    assert c(du("P1M"), du("P30D")) is None  # XSD 1.1 3.3.6.2 example: incomparable
    assert c(du("P1Y"), du("P365D")) is None
    assert c(du("P1Y"), du("P400D")) == -1
    assert c(du("P1M", "yearMonthDuration"), du("P2M", "yearMonthDuration")) == -1


def test_term_equal():
    assert xv.term_equal(ox.NamedNode("http://e/a"), ox.NamedNode("http://e/a"))
    assert not xv.term_equal(lit("1", "integer"), lit("01", "integer"))  # same value, different term
    assert xv.value_equal(lit("1", "integer"), lit("01", "integer"))
    assert xv.term_equal(lit("x"), lit("x", "string"))
    assert xv.term_equal(lit("x", lang="en-GB"), lit("x", lang="en-gb"))
    assert not xv.term_equal(lit("x", lang="en"), lit("x"))
    assert not xv.term_equal(lit("x"), ox.NamedNode("http://e/x"))


# ---- cross-check against rdflib --------------------------------------------------------------------------------------

_SAMPLES = (
    [(str(n), dt) for dt in INTEGER_RANGE for n in (-300, -129, -128, -1, 0, 1, 5, 127, 128, 255, 256, 70000, 2**40)]
    + [(s, "decimal") for s in ("0", "1.0", "-2.50", ".5", "123456789012345678901234567890.123", "+7")]
    + [(s, dt) for dt in ("float", "double") for s in ("0", "1.5", "-2e3", "1E-2", "INF", "-INF", "NaN", "3.14159")]
    + [(s, "boolean") for s in ("true", "false", "1", "0")]
    + [(s, "dateTime") for s in ("2000-01-01T00:00:00", "2000-01-01T00:00:00Z", "2000-06-01T12:30:00+02:00",
                                 "1999-12-31T23:59:59.5", "2010-03-04T05:06:07-05:00")]  # fmt: skip
    + [(s, "date") for s in ("2000-01-01", "2000-01-01Z", "1999-12-31", "2000-02-29", "2000-01-02+05:00")]
    + [(s, "time") for s in ("00:00:00", "12:00:00Z", "13:00:00+01:00", "23:59:59.25", "09:30:00")]
    + [(s, "string") for s in ("a", "b", "")]
)


def _rdflib_lit(lex: str, dt: str) -> Literal:
    return Literal(lex, datatype=URIRef(XSD + dt), normalize=False)


@pytest.mark.parametrize("lex,dt", _SAMPLES)
def test_agrees_with_rdflib_on_well_formed(lex, dt):
    mine = xv.parse(lit(lex, dt))
    theirs = _rdflib_lit(lex, dt)
    if mine is None:
        return  # rdflib is less strict in places (int() accepts "1_0"); only the well-formed side is cross-checked
    assert theirs.ill_typed is not True, (lex, dt)
    py = theirs.toPython()
    if mine.kind == xv.NUMERIC:
        if isinstance(py, float) and py != py:
            assert mine.value != mine.value
        else:
            assert mine.value == py or (dt == "float" and abs(mine.value - py) < 1e-6 * max(1, abs(py))), (lex, dt)
    elif mine.kind == xv.BOOLEAN:
        assert mine.value is py


def _pairs(kinds):
    items = [(lex, dt) for lex, dt in _SAMPLES if dt in kinds]
    return list(itertools.combinations(items, 2))


@pytest.mark.parametrize("kinds", [("integer", "long", "decimal", "double", "int"), ("dateTime",), ("date",), ("time",), ("string",)])
def test_order_agrees_with_rdflib(kinds):
    """For every pair rdflib can order (no TypeError from naive-vs-aware), the ordering must be the same; where we say
    incomparable and rdflib orders them the pair must be the naive/aware case rdflib mishandles."""
    checked = 0
    for (la, da), (lb, db) in _pairs(kinds):
        a, b = lit(la, da), lit(lb, db)
        mine = xv.compare(a, b)
        x, y = _rdflib_lit(la, da).toPython(), _rdflib_lit(lb, db).toPython()
        if isinstance(x, float) and x != x or isinstance(y, float) and y != y:
            assert mine is None
            continue
        try:
            theirs = (x > y) - (x < y) if (x < y or x > y or x == y) else None
        except TypeError:
            continue
        if mine is None:
            if xv.parse(a) is None or xv.parse(b) is None:
                continue  # out of the derived type's range: ill-formed here, rdflib has no range facet
            # only the XSD 1.1 mixed-timezone gap is allowed to differ (rdflib raises there, handled above)
            assert da in ("dateTime", "date", "time"), (la, da, lb, db)
            continue
        assert mine == theirs, (la, da, lb, db, mine, theirs)
        checked += 1
    assert checked > 0


FIXTURES = Path(__file__).resolve().parents[1] / "shacl" / "vendor" / "shacl12-test-suite" / "tests"


def _fixture_literals():
    seen: dict[tuple[str, str], None] = {}
    for path in sorted(FIXTURES.rglob("*.ttl")):
        g = Graph()
        try:
            g.parse(path, format="turtle")
        except Exception:  # noqa: BLE001 - a few fixtures use SHACL-1.2 syntax rdflib's parser rejects
            continue
        for _, _, o in g:
            if isinstance(o, Literal) and o.datatype is not None and not o.language:
                seen[(str(o), str(o.datatype))] = None
    return list(seen)


def test_w3c_fixture_literals_agree_with_rdflib():
    lits = _fixture_literals()
    assert len(lits) > 50
    compared = 0
    for lex, dt in lits:
        l = ox.Literal(lex, datatype=ox.NamedNode(dt))  # noqa: E741
        theirs = Literal(lex, datatype=URIRef(dt), normalize=False)
        mine = xv.parse(l)
        if mine is None:
            continue
        compared += 1
        assert theirs.ill_typed is not True, (lex, dt)
        if mine.kind in (xv.NUMERIC, xv.BOOLEAN) and not (isinstance(mine.value, float) and mine.value != mine.value):
            py = theirs.toPython()
            assert mine.value == py or dt.endswith("float"), (lex, dt, mine.value, py)
    assert compared > 30
    # every literal the engine's suite marks ill-formed that rdflib also flags is ill-formed here
    for lex, dt in lits:
        if Literal(lex, datatype=URIRef(dt), normalize=False).ill_typed is True and dt.startswith(XSD):
            assert not xv.well_formed(ox.Literal(lex, datatype=ox.NamedNode(dt))) or not xv.known_datatype(dt), (lex, dt)
