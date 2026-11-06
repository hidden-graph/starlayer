"""XSD value-space helpers over pyoxigraph literals: the single place a Rust port must re-implement.

pyoxigraph (like Rust ``oxrdf``) keeps exactly the lexical form and datatype it is given and has no value logic. This
module supplies the value logic the engine needs and nothing else: lexical-to-value mapping with well-formedness
(``parse``, ``well_formed``), and the value ordering and equality SPARQL / SHACL use (``compare``, ``value_equal``).
No rdflib import. Pure Python, standard library only.

Specs: XML Schema Part 2 Datatypes 1.1 (XSD) for lexical spaces, facets and the date/time and duration partial orders;
SPARQL 1.1 Query section 17.3 (operator mapping, ``=`` and ``<``) for which pairs are comparable; RDF 1.2 Concepts
section 3.3 (literal value, ill-typed literals) for the term/value split. Rust port notes: ``Decimal`` maps to
``rust_decimal``/``bigdecimal`` (XSD decimal and integer need arbitrary precision for the unsigned/long ranges only up
to 128 bits, but ``xsd:integer`` itself is unbounded: use ``num-bigint``), floats map to ``f32``/``f64``.
"""

from __future__ import annotations

import binascii
import re
import struct
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Any

import pyoxigraph as ox

XSD = "http://www.w3.org/2001/XMLSchema#"
RDF_LANG_STRING = "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString"
RDF_DIR_LANG_STRING = "http://www.w3.org/1999/02/22-rdf-syntax-ns#dirLangString"

# Value kinds ("comparison families"): two values are only ordered within one kind (SPARQL 1.1 17.3, XPath F&O 1.1
# section 10.4 for the date and time kinds).
STRING, BOOLEAN, NUMERIC, DATETIME, DATE, TIME = "string", "boolean", "numeric", "dateTime", "date", "time"
GYEAR, GYEARMONTH, GMONTH, GMONTHDAY, GDAY = "gYear", "gYearMonth", "gMonth", "gMonthDay", "gDay"
DURATION, BINARY, ANYURI = "duration", "binary", "anyURI"

_TIMELINE_KINDS = frozenset({DATETIME, DATE, TIME, GYEAR, GYEARMONTH, GMONTH, GMONTHDAY, GDAY})
_UNORDERED_KINDS = frozenset({BINARY, ANYURI})  # equality only


@dataclass(frozen=True, slots=True)
class Value:
    """A parsed literal. ``kind`` is the comparison family, ``datatype`` the literal's datatype IRI.

    ``value`` is: ``int`` / ``Decimal`` / ``float`` (numeric), ``bool``, ``str``, ``bytes`` (binary), a ``Decimal`` count
    of seconds since 0000-01-01T00:00:00 on the proleptic Gregorian calendar, local time, for the timeline kinds
    (with ``tz`` the offset in minutes or ``None``), or ``(months, seconds)`` for durations.
    """

    kind: str
    datatype: str
    value: Any
    tz: int | None = None


# --------------------------------------------------------------------------------------------------------------------
# Lexical-space helpers
# --------------------------------------------------------------------------------------------------------------------

def _collapse(lex: str) -> str:
    """whiteSpace=collapse for every non-string datatype (XSD 1.1 section 4.3.6): trim, and squeeze inner runs."""
    return re.sub(r"[ \t\n\r]+", " ", lex).strip(" ")


_INT_RE = re.compile(r"[+-]?[0-9]+\Z")
_DEC_RE = re.compile(r"[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)\Z")
_FLOAT_RE = re.compile(r"([+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?|[+-]?INF|NaN)\Z")

_INTEGER_RANGES: dict[str, tuple[int | None, int | None]] = {
    "integer": (None, None),
    "nonPositiveInteger": (None, 0),
    "negativeInteger": (None, -1),
    "long": (-(2**63), 2**63 - 1),
    "int": (-(2**31), 2**31 - 1),
    "short": (-(2**15), 2**15 - 1),
    "byte": (-(2**7), 2**7 - 1),
    "nonNegativeInteger": (0, None),
    "unsignedLong": (0, 2**64 - 1),
    "unsignedInt": (0, 2**32 - 1),
    "unsignedShort": (0, 2**16 - 1),
    "unsignedByte": (0, 2**8 - 1),
    "positiveInteger": (1, None),
}


def _int(digits: str) -> int:
    """``int()`` of an ASCII digit string of any length (CPython's int(str) refuses more than 4300 digits; xsd:integer and
    the date/time year and duration components are unbounded). Decimal's conversion has no such limit."""
    return int(digits) if len(digits) <= 4000 else int(Decimal(digits))


def _parse_integer(lex: str, name: str) -> int | None:
    """xsd:integer and the 12 derived types: lexical ``[+-]?[0-9]+`` (XSD 1.1 3.4.13) and the range facets (3.4.14-3.4.26)."""
    s = _collapse(lex)
    if not _INT_RE.match(s):
        return None
    n = _int(s)
    lo, hi = _INTEGER_RANGES[name]
    if (lo is not None and n < lo) or (hi is not None and n > hi):
        return None
    return n


def _parse_decimal(lex: str) -> Decimal | None:
    """xsd:decimal: lexical ``[+-]?(d+(.d*)?|.d+)`` (XSD 1.1 3.3.3); no exponent, no INF/NaN."""
    s = _collapse(lex)
    if not _DEC_RE.match(s):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:  # pragma: no cover - guarded by the regex
        return None


def _parse_float(lex: str, single: bool) -> float | None:
    """xsd:float / xsd:double (XSD 1.1 3.3.4, 3.3.5): decimal with optional exponent, ``INF``, ``-INF``, ``+INF``, ``NaN``.
    Out-of-range magnitudes round to INF (the IEEE round-to-nearest mapping); xsd:float is rounded to binary32."""
    s = _collapse(lex)
    if not _FLOAT_RE.match(s):
        return None
    if s.endswith("INF"):
        return float("-inf") if s[0] == "-" else float("inf")
    if s == "NaN":
        return float("nan")
    x = float(s)
    if single and x == x and x not in (float("inf"), float("-inf")):
        try:
            x = struct.unpack("f", struct.pack("f", x))[0]
        except OverflowError:
            x = float("inf") if x > 0 else float("-inf")
    return x


def _parse_boolean(lex: str) -> bool | None:
    """xsd:boolean (XSD 1.1 3.3.2): lexical space ``true``, ``false``, ``1``, ``0``."""
    s = _collapse(lex)
    if s in ("true", "1"):
        return True
    if s in ("false", "0"):
        return False
    return None


_LANG_RE = re.compile(r"[a-zA-Z]{1,8}(-[a-zA-Z0-9]{1,8})*\Z")
_NMTOKEN_RE = re.compile(r"[\w.:\-]+\Z")
_NAME_RE = re.compile(r"[^\W\d\-.][\w.:\-]*\Z")
_NCNAME_RE = re.compile(r"[^\W\d\-.][\w.\-]*\Z")


def _parse_string_like(lex: str, name: str) -> str | None:
    """xsd:string and the string-derived types (XSD 1.1 3.3.1, 3.4.1-3.4.9). Name/NCName/NMTOKEN use the Python
    ``\\w`` approximation of the XML name classes; the engine never relies on those being exact."""
    if name == "string":
        return lex
    if name == "normalizedString":
        return lex if not re.search(r"[\t\n\r]", lex) else None
    s = _collapse(lex)  # token and everything below it collapse whitespace
    if name == "token":
        return lex if lex == s and not re.search(r"[\t\n\r]|  ", lex) else None
    if lex != s:
        return None
    if name == "language":
        return s if _LANG_RE.match(s) else None
    if name == "NMTOKEN":
        return s if _NMTOKEN_RE.match(s) else None
    if name == "Name":
        return s if _NAME_RE.match(s) else None
    if name in ("NCName", "ID", "IDREF", "ENTITY"):
        return s if _NCNAME_RE.match(s) else None
    return None


def _parse_hex(lex: str) -> bytes | None:
    """xsd:hexBinary (XSD 1.1 3.3.15): an even number of hex digits."""
    s = _collapse(lex)
    if len(s) % 2 or not re.fullmatch(r"[0-9a-fA-F]*", s):
        return None
    return binascii.unhexlify(s)


def _parse_base64(lex: str) -> bytes | None:
    """xsd:base64Binary (XSD 1.1 3.3.16): base64 with optional inner spaces; length a multiple of 4 after removing them."""
    s = _collapse(lex).replace(" ", "")
    if len(s) % 4 or not re.fullmatch(r"[A-Za-z0-9+/]*={0,2}", s):
        return None
    try:
        return binascii.a2b_base64(s)
    except binascii.Error:
        return None


# ---- calendar -------------------------------------------------------------------------------------------------------

_YEAR = r"(?P<y>-?(?:[1-9][0-9]{3,}|0[0-9]{3}))"
_MONTH = r"(?P<mo>0[1-9]|1[0-2])"
_DAY = r"(?P<d>0[1-9]|[12][0-9]|3[01])"
_TIME = r"(?P<h>[01][0-9]|2[0-3]):(?P<mi>[0-5][0-9]):(?P<s>[0-5][0-9](?:\.[0-9]+)?)"
_EOD = r"(?P<eod>24:00:00(?:\.0+)?)"
_TZ = r"(?P<tz>Z|[+-](?:(?:0[0-9]|1[0-3]):[0-5][0-9]|14:00))?"

_TIMELINE_RE = {
    DATETIME: re.compile(rf"{_YEAR}-{_MONTH}-{_DAY}T(?:{_TIME}|{_EOD}){_TZ}\Z"),
    DATE: re.compile(rf"{_YEAR}-{_MONTH}-{_DAY}{_TZ}\Z"),
    TIME: re.compile(rf"(?:{_TIME}|{_EOD}){_TZ}\Z"),
    GYEAR: re.compile(rf"{_YEAR}{_TZ}\Z"),
    GYEARMONTH: re.compile(rf"{_YEAR}-{_MONTH}{_TZ}\Z"),
    GMONTH: re.compile(rf"--{_MONTH}{_TZ}\Z"),
    GMONTHDAY: re.compile(rf"--{_MONTH}-{_DAY}{_TZ}\Z"),
    GDAY: re.compile(rf"---{_DAY}{_TZ}\Z"),
}


def _is_leap(y: int) -> bool:
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_in_month(y: int, m: int) -> int:
    return 29 if m == 2 and _is_leap(y) else (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[m - 1]


def _days_from_civil(y: int, m: int, d: int) -> int:
    """Days from 0000-01-01 (proleptic Gregorian, astronomical year numbering, year 0 exists) to y-m-d."""
    y -= m <= 2
    era = y // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468 + 719528  # 719528 = days from 0000-01-01 to 1970-01-01


def _tz_minutes(tz: str | None) -> int | None:
    if tz is None:
        return None
    if tz == "Z":
        return 0
    sign = -1 if tz[0] == "-" else 1
    return sign * (int(tz[1:3]) * 60 + int(tz[4:6]))


def _parse_timeline(lex: str, kind: str, datatype: str) -> Value | None:
    """The date/time datatypes (XSD 1.1 3.3.7-3.3.14): the seven-property model reduced to a local timeline position
    plus an optional offset. ``24:00:00`` is the next day's midnight; the g* types and ``time`` use the reference
    year 1972 (a leap year) so month-day values compare, as in XSD 1.1 appendix E / F&O 10.4."""
    m = _TIMELINE_RE[kind].match(_collapse(lex))
    if not m:
        return None
    g = m.groupdict()
    year = _int(g["y"]) if g.get("y") is not None else 1972
    month = int(g["mo"]) if g.get("mo") is not None else (12 if kind == GDAY else 1)
    if kind in (TIME, GDAY, GMONTH, GMONTHDAY):
        year = 1972
    if kind == TIME:
        month = 12
    day = int(g["d"]) if g.get("d") is not None else (31 if kind == TIME else 1)
    if kind == GDAY:
        month = 12
    if day > _days_in_month(year, month):
        return None
    if kind in (GYEAR, GYEARMONTH, GMONTH):
        day = 1
    seconds = Decimal(0)
    if g.get("eod"):
        # 24:00:00 is the next day's midnight for dateTime / date-bearing kinds; for xsd:time the value is the time of
        # day 00:00:00 (XSD 1.1 3.3.14: hour 24 is normalised to 0 and the day part is dropped)
        seconds = Decimal(0) if kind == TIME else Decimal(86400)
    elif g.get("h") is not None:
        seconds = Decimal(int(g["h"]) * 3600 + int(g["mi"]) * 60) + Decimal(g["s"])
    total = Decimal(_days_from_civil(year, month, day) * 86400) + seconds
    return Value(kind, datatype, total, _tz_minutes(g["tz"]))


_DUR_RE = re.compile(
    r"(?P<neg>-)?P(?:(?P<Y>[0-9]+)Y)?(?:(?P<M>[0-9]+)M)?(?:(?P<D>[0-9]+)D)?"
    r"(?P<T>T(?:(?P<H>[0-9]+)H)?(?:(?P<Mi>[0-9]+)M)?(?:(?P<S>[0-9]+(?:\.[0-9]*)?|\.[0-9]+)S)?)?\Z"
)


def _parse_duration(lex: str, datatype: str, ym: bool, dt: bool) -> Value | None:
    """xsd:duration, xsd:yearMonthDuration, xsd:dayTimeDuration (XSD 1.1 3.3.6, 3.4.26, 3.4.27): value = (months, seconds)."""
    m = _DUR_RE.match(_collapse(lex))
    if not m:
        return None
    g = m.groupdict()
    if not any(g[k] for k in ("Y", "M", "D", "H", "Mi", "S")):
        return None
    if g["T"] == "T" and not any(g[k] for k in ("H", "Mi", "S")):
        return None  # "PT" and "P1DT" have a T with nothing after it
    if ym and any(g[k] for k in ("D", "H", "Mi", "S", "T")):
        return None
    if dt and any(g[k] for k in ("Y", "M")):
        return None
    sign = -1 if g["neg"] else 1
    months = sign * (_int(g["Y"] or "0") * 12 + _int(g["M"] or "0"))
    secs = sign * (
        Decimal(_int(g["D"] or "0") * 86400 + _int(g["H"] or "0") * 3600 + _int(g["Mi"] or "0") * 60) + Decimal(g["S"] or "0")
    )
    return Value(DURATION, datatype, (months, secs))


# --------------------------------------------------------------------------------------------------------------------
# parse / well_formed
# --------------------------------------------------------------------------------------------------------------------

_PARSERS: dict[str, Any] = {}


def _register() -> None:
    for name in _INTEGER_RANGES:
        _PARSERS[XSD + name] = lambda lex, dt, n=name: _wrap(_parse_integer(lex, n), NUMERIC, dt)
    _PARSERS[XSD + "decimal"] = lambda lex, dt: _wrap(_parse_decimal(lex), NUMERIC, dt)
    _PARSERS[XSD + "float"] = lambda lex, dt: _wrap(_parse_float(lex, True), NUMERIC, dt)
    _PARSERS[XSD + "double"] = lambda lex, dt: _wrap(_parse_float(lex, False), NUMERIC, dt)
    _PARSERS[XSD + "boolean"] = lambda lex, dt: _wrap(_parse_boolean(lex), BOOLEAN, dt)
    for name in ("string", "normalizedString", "token", "language", "NMTOKEN", "Name", "NCName", "ID", "IDREF", "ENTITY"):
        _PARSERS[XSD + name] = lambda lex, dt, n=name: _wrap(_parse_string_like(lex, n), STRING, dt)
    _PARSERS[XSD + "anyURI"] = lambda lex, dt: Value(ANYURI, dt, _collapse(lex))
    _PARSERS[XSD + "hexBinary"] = lambda lex, dt: _wrap(_parse_hex(lex), BINARY, dt)
    _PARSERS[XSD + "base64Binary"] = lambda lex, dt: _wrap(_parse_base64(lex), BINARY, dt)
    for name, kind in (
        ("dateTime", DATETIME), ("dateTimeStamp", DATETIME), ("date", DATE), ("time", TIME), ("gYear", GYEAR),
        ("gYearMonth", GYEARMONTH), ("gMonth", GMONTH), ("gMonthDay", GMONTHDAY), ("gDay", GDAY),
    ):  # fmt: skip
        _PARSERS[XSD + name] = lambda lex, dt, k=kind, n=name: _stamp(_parse_timeline(lex, k, dt), n)
    _PARSERS[XSD + "duration"] = lambda lex, dt: _parse_duration(lex, dt, False, False)
    _PARSERS[XSD + "yearMonthDuration"] = lambda lex, dt: _parse_duration(lex, dt, True, False)
    _PARSERS[XSD + "dayTimeDuration"] = lambda lex, dt: _parse_duration(lex, dt, False, True)


def _wrap(v: Any, kind: str, datatype: str) -> Value | None:
    return None if v is None else Value(kind, datatype, v)


def _stamp(v: Value | None, name: str) -> Value | None:
    """xsd:dateTimeStamp (XSD 1.1 3.4.28) is dateTime with a required timezone."""
    if v is not None and name == "dateTimeStamp" and v.tz is None:
        return None
    return v


_register()


def known_datatype(datatype: str) -> bool:
    """Whether this module has a lexical-to-value mapping for ``datatype`` (an IRI string)."""
    return datatype in _PARSERS


@lru_cache(maxsize=1 << 16)
def _parse_cached(lex: str, datatype: str) -> Value | None:
    fn = _PARSERS.get(datatype)
    return None if fn is None else fn(lex, datatype)


def parse(literal: ox.Literal) -> Value | None:
    """Lexical-to-value mapping of a literal (RDF 1.2 Concepts 3.3 "literal value"; XSD 1.1 lexical mappings).

    ``None`` for an ill-formed literal, an unknown datatype, and any language-tagged literal (rdf:langString has no
    value space beyond the term itself)."""
    if literal.language is not None:
        return None
    return _parse_cached(literal.value, literal.datatype.value)


def well_formed(literal: ox.Literal) -> bool:
    """RDF 1.2 Concepts 3.3: a literal is ill-typed iff its datatype is recognised and its lexical form is not in the
    lexical space. Unknown datatypes and language-tagged literals are well-formed (nothing to check)."""
    if literal.language is not None:
        return True
    dt = literal.datatype.value
    return dt not in _PARSERS or _parse_cached(literal.value, dt) is not None


def numeric(literal: Any) -> int | Decimal | float | None:
    """The Python number of a well-formed numeric literal (``bool`` excluded), else ``None``."""
    if not isinstance(literal, ox.Literal):
        return None
    v = parse(literal)
    return v.value if v is not None and v.kind == NUMERIC else None


# --------------------------------------------------------------------------------------------------------------------
# compare / equality
# --------------------------------------------------------------------------------------------------------------------

_FOURTEEN_HOURS = Decimal(14 * 3600)


def _cmp(x: Any, y: Any) -> int | None:
    if x != x or y != y:  # NaN is unordered (and Decimal < NaN would raise)
        return None
    if x < y:
        return -1
    if x > y:
        return 1
    if x == y:
        return 0
    return None  # NaN


def _compare_timeline(a: Value, b: Value) -> int | None:
    """XSD 1.1 3.3.7.? order relation on date/time values: both with or both without a timezone compare directly;
    otherwise P < Q only if P < Q with offset +14:00 and P > Q only if P > Q with offset -14:00, else incomparable."""
    if a.tz is None and b.tz is None:
        return _cmp(a.value, b.value)
    if a.tz is not None and b.tz is not None:
        return _cmp(a.value - a.tz * 60, b.value - b.tz * 60)
    if a.tz is not None:  # a has a timezone, b has none
        au = a.value - a.tz * 60
        if au < b.value - _FOURTEEN_HOURS:
            return -1
        if au > b.value + _FOURTEEN_HOURS:
            return 1
        return None
    r = _compare_timeline(b, a)
    return None if r is None else -r


# XSD 1.1 3.3.6.2: the four reference dateTimes of the duration order relation.
_DUR_REFS = ((1696, 9, 1), (1697, 2, 1), (1903, 3, 1), (1903, 7, 1))


def _add_duration(ref: tuple[int, int, int], months: int, secs: Decimal) -> Decimal:
    y, m, d = ref
    total = y * 12 + (m - 1) + months
    y, m = divmod(total, 12)
    return Decimal(_days_from_civil(y, m + 1, d) * 86400) + secs


def _compare_duration(a: Value, b: Value) -> int | None:
    """XSD 1.1 3.3.6.2: P < Q iff P+R < Q+R for each of four reference dateTimes R; equal iff equal for all four;
    otherwise incomparable."""
    results = {_cmp(_add_duration(r, *a.value), _add_duration(r, *b.value)) for r in _DUR_REFS}
    return results.pop() if len(results) == 1 else None


_NUMERIC_DATATYPES = frozenset({XSD + n for n in (*_INTEGER_RANGES, "decimal", "float", "double")})
_NUMERIC_RANK = {XSD + "float": 2, XSD + "double": 3}


def _promote(a: Value, b: Value) -> tuple[Any, Any]:
    """XPath F&O 3.1 6.2 / SPARQL 17.3 (op:numeric-equal, -less-than): operands of different numeric types are promoted
    to the higher of integer < decimal < float < double before comparing, so ``9007199254740993`` and
    ``9007199254740992e0`` are equal and ``0.1`` (decimal) equals ``0.1e0`` (double). Integer and decimal compare exactly."""
    ra, rb = _NUMERIC_RANK.get(a.datatype, 0), _NUMERIC_RANK.get(b.datatype, 0)
    top = max(ra, rb)
    if top == 0 or ra == rb:
        return a.value, b.value
    return _to_float(a.value, top == 2), _to_float(b.value, top == 2)


def _to_float(x: Any, single: bool) -> float:
    try:
        f = float(x)
    except OverflowError:
        f = float("inf") if x > 0 else float("-inf")
    if single and f == f and f not in (float("inf"), float("-inf")):
        try:
            f = struct.unpack("f", struct.pack("f", f))[0]
        except OverflowError:
            f = float("inf") if f > 0 else float("-inf")
    return f


def compare(a: ox.Literal, b: ox.Literal) -> int | None:
    """Value ordering of two literals as SPARQL 1.1 17.3 (``<`` and ``=`` operator mapping) and XSD 1.1 define it.

    Returns -1, 0, 1, or ``None`` when the pair is incomparable: an ill-formed or unknown-datatype or language-tagged
    operand, operands of different kinds (numeric vs string, dateTime vs date, ...), NaN, date/times with and without a
    timezone that are more than 14 hours apart is decided, closer ones incomparable (XSD 1.1 partial order), durations
    whose four reference-date comparisons disagree, and kinds with equality only (binary, anyURI: 0 or ``None``).
    Numeric operands of different datatypes compare by exact value (integer < decimal < float promotion is exact)."""
    if not (isinstance(a, ox.Literal) and isinstance(b, ox.Literal)):
        return None
    va, vb = parse(a), parse(b)
    if va is None or vb is None or va.kind != vb.kind:
        return None
    kind = va.kind
    if kind == NUMERIC:
        return _cmp(*_promote(va, vb))
    if kind in (STRING, BOOLEAN):
        return _cmp(va.value, vb.value)
    if kind in _TIMELINE_KINDS:
        return _compare_timeline(va, vb)
    if kind == DURATION:
        return _compare_duration(va, vb)
    if kind in _UNORDERED_KINDS:
        # SPARQL 1.2 17.3: `=` on these is RDFterm-equal (same term or a type error), so only the same lexical form
        # (after whitespace collapse) is equal; "0A" and "0a" are the same hexBinary value but not the same term.
        return 0 if (a.datatype == b.datatype and _collapse(a.value) == _collapse(b.value)) else None
    return None  # pragma: no cover


def ebv(literal: ox.Literal) -> bool | None:
    """SPARQL 1.1 17.2.2 effective boolean value of a literal; ``None`` is the type error: an xsd:boolean is its value, a
    simple/xsd:string literal is true iff non-empty, a numeric is true iff not zero and not NaN, an ill-formed boolean or
    numeric is false (17.2.2), anything else is an error. Language-tagged strings are errors."""
    if literal.language is not None:
        return None
    dt = literal.datatype.value
    if dt == XSD + "string":
        return len(literal.value) > 0
    v = _parse_cached(literal.value, dt)
    if v is None:
        # SPARQL 1.1 17.2.2: "The EBV of any literal whose type is xsd:boolean or numeric is false if the lexical form
        # is not valid for that datatype"; any other datatype is a type error
        return False if (dt == XSD + "boolean" or dt in _NUMERIC_DATATYPES) else None
    if v.kind == BOOLEAN:
        return bool(v.value)
    if v.kind == NUMERIC:
        return not (v.value != v.value or v.value == 0)
    return None


def value_equal(a: ox.Literal, b: ox.Literal) -> bool:
    """SPARQL ``=`` on literals of known datatype (17.4.1.7 RDFterm-equal falls back to term equality otherwise):
    value-equal iff ``compare`` gives 0. Not used by SHACL's term-based comparisons, but by SPARQL-style functions."""
    return compare(a, b) == 0


def term_equal(a: Any, b: Any) -> bool:
    """RDF term equality (RDF 1.2 Concepts 3.3, 3.4): same kind and, for literals, the same lexical form, datatype,
    language tag (compared case-insensitively, RDF 1.2 3.3) and base direction. pyoxigraph's ``==`` already is term
    equality except that language tags compare as stored."""
    if a == b:
        return True
    if isinstance(a, ox.Literal) and isinstance(b, ox.Literal) and a.language and b.language:
        return (
            a.value == b.value and a.language.lower() == b.language.lower() and a.direction == b.direction
        )
    return False
