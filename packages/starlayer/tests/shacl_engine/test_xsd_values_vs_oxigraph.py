"""Cross-check of ``xsd_values`` against a second implementation: Oxigraph's SPARQL engine (Rust, ``oxsdatatypes``).

Three questions, each over a generated corpus (``xsd_oracle_corpus.py``):

* well-formedness: ``xv.well_formed("lex"^^T)`` vs whether Oxigraph's cast ``xsd:T("lex")`` produces a value;
* ordering and equality: ``xv.compare(a, b)`` vs Oxigraph's ``<``, ``=``, ``>`` (an unbound result is a SPARQL error: incomparable);
* effective boolean value: ``xv.ebv`` vs ``IF(?x, ...)`` (which takes the EBV of ``?x``).

Every disagreement was decided against the specification (XSD 1.1 Part 2, XPath Functions and Operators 3.1, SPARQL 1.2 Query
section 17) and is either a fix in ``xsd_values`` or a documented, asserted difference in ``OXIGRAPH_DIFFERENCES`` below: the test
fails when a difference appears that is not listed AND when a listed one disappears (so an Oxigraph upgrade that fixes one is noticed).
The write-up with the clauses is in docs/working/shacl-engine-term-model-spike.md.
"""

from __future__ import annotations

import itertools

import pyoxigraph as ox
import pytest
from starlayer.shacl_engine import xsd_values as xv
from tests.shacl_engine import xsd_oracle_corpus as C

XSD = C.XSD
_STORE = ox.Store()


def sparql_term(lex: str, datatype: str | None = None) -> str:
    """A SPARQL term for a literal (the N-Triples form is valid SPARQL)."""
    return str(ox.Literal(lex, datatype=ox.NamedNode(datatype)) if datatype else ox.Literal(lex))  # str-ok: N-Triples form wanted


def lit(datatype: str, lex: str) -> ox.Literal:
    return ox.Literal(lex, datatype=ox.NamedNode(XSD + datatype))


def _rows(query: str) -> list[list[ox.Term | None]]:
    result = _STORE.query(query)
    names = list(result.variables)
    return [[sol[v] for v in names] for sol in result]


def oxigraph_cast(local: str, lexes: list[str]) -> list[str | None] | None:
    """The lexical value of ``xsd:<local>("lex")`` for each lex in Oxigraph, ``None`` for an error; ``None`` overall when the
    cast function is not implemented."""
    values = " ".join(f"({i} {sparql_term(lex)})" for i, lex in enumerate(lexes))
    try:
        rows = _rows(f"SELECT ?i ?r WHERE {{ VALUES (?i ?s) {{ {values} }} BIND(<{XSD}{local}>(?s) AS ?r) }}")
    except RuntimeError:
        return None
    out: list[str | None] = [None] * len(lexes)
    for i, r in rows:
        out[int(i.value)] = None if r is None else r.value
    return out


def oxigraph_compare(pairs: list[tuple[ox.Literal, ox.Literal]]) -> list[tuple[bool | None, bool | None, bool | None]]:
    """``(a < b, a = b, a > b)`` for each pair in Oxigraph; ``None`` is a SPARQL error."""
    values = " ".join(f"({i} {a!s} {b!s})" for i, (a, b) in enumerate(pairs))  # str-ok: N-Triples form wanted
    rows = _rows(
        f"SELECT ?i (?a < ?b AS ?lt) (?a = ?b AS ?eq) (?a > ?b AS ?gt) WHERE {{ VALUES (?i ?a ?b) {{ {values} }} }}"
    )
    out: list = [None] * len(pairs)
    for i, lt, eq, gt in rows:
        out[int(i.value)] = tuple(None if x is None else x.value == "true" for x in (lt, eq, gt))
    return out


def oxigraph_ebv(lits: list[ox.Literal]) -> list[bool | None]:
    values = " ".join(f"({i} {x!s})" for i, x in enumerate(lits))  # str-ok: N-Triples form wanted
    rows = _rows(f"SELECT ?i (IF(?x, true, false) AS ?b) WHERE {{ VALUES (?i ?x) {{ {values} }} }}")
    out: list[bool | None] = [None] * len(lits)
    for i, b in rows:
        out[int(i.value)] = None if b is None else b.value == "true"
    return out


# ---- corpus per datatype ------------------------------------------------------------------------------------------------------


def lexicals(datatype: str) -> list[str]:
    if datatype in C.INTEGER_RANGES:
        out = list(C.INTEGER_SHAPES)
        lo, hi = C.INTEGER_RANGES[datatype]
        for bound in (lo, hi):
            if bound is not None:
                out += [str(bound + d) for d in (-2, -1, 0, 1, 2)] + [f"+{bound}", f"{bound:+d}", f"0{bound}" if bound >= 0 else f"-0{-bound}"]
        return out
    return {
        "decimal": C.DECIMAL_SHAPES,
        "float": C.FLOAT_SHAPES,
        "double": C.FLOAT_SHAPES,
        "boolean": C.BOOLEAN_SHAPES,
        "dateTime": C.with_zones(C.DATETIME_BASES),
        "date": C.with_zones(C.DATE_BASES),
        "time": C.with_zones(C.TIME_BASES),
        "gYear": C.with_zones(C.GYEAR_BASES),
        "gYearMonth": C.with_zones(C.GYEARMONTH_BASES),
        "gMonth": C.with_zones(C.GMONTH_BASES),
        "gMonthDay": C.with_zones(C.GMONTHDAY_BASES),
        "gDay": C.with_zones(C.GDAY_BASES),
        "duration": C.DURATION_SHAPES,
        "yearMonthDuration": C.YM_DURATION_SHAPES,
        "dayTimeDuration": C.DT_DURATION_SHAPES,
        "hexBinary": C.BINARY_HEX,
        "base64Binary": C.BINARY_B64,
    }[datatype]


CASTABLE = ["integer", "decimal", "float", "double", "boolean", "dateTime", "date", "time", "gYear", "gYearMonth", "gMonth", "gMonthDay", "gDay", "duration", "yearMonthDuration", "dayTimeDuration"]  # fmt: skip
SPEC_ONLY = [t for t in C.INTEGER_RANGES if t != "integer"] + ["hexBinary", "base64Binary"]


def well_formedness_differences() -> dict[tuple[str, str], tuple[bool, bool]]:
    """``{(datatype, lexical): (xsd_values, oxigraph)}`` for every lexical form the two disagree on."""
    out = {}
    for dt in CASTABLE:
        lexes = lexicals(dt)
        cast = oxigraph_cast(dt, lexes)
        assert cast is not None, f"Oxigraph has no xsd:{dt} cast: the corpus assumes it has"
        for lex, got in zip(lexes, cast, strict=True):
            ours, theirs = xv.well_formed(lit(dt, lex)), got is not None
            if ours != theirs:
                out[(dt, lex)] = (ours, theirs)
    return out


def _families() -> dict[str, list[tuple[str, str]]]:
    return {
        "numeric": C.NUMERIC_VALUES,
        "string": C.STRING_VALUES,
        "boolean": C.BOOLEAN_VALUES,
        "dateTime": C.DATETIME_VALUES,
        "date": C.DATE_VALUES,
        "time": C.TIME_VALUES,
        "gYear": C.GYEAR_VALUES,
        "gYearMonth": C.GYEARMONTH_VALUES,
        "gMonth": C.GMONTH_VALUES,
        "gMonthDay": C.GMONTHDAY_VALUES,
        "gDay": C.GDAY_VALUES,
        "duration": C.DURATION_VALUES,
        "hex": C.HEX_VALUES,
        "base64": C.B64_VALUES,
    }


def _expected(ours: int | None) -> tuple[bool, bool, bool]:
    """The ``(<, =, >)`` truth values a ``compare`` result stands for. SHACL only asks whether a comparison is *true*
    (``sh:minInclusive`` ... "is not true" is a violation), so a SPARQL error and ``false`` are the same here; ``None``
    (incomparable: NaN, the XSD partial orders) is neither less, equal nor greater."""
    if ours is None:
        return (False, False, False)
    return (ours < 0, ours == 0, ours > 0)


def comparison_differences() -> dict[tuple[str, str, str, str], tuple]:
    """``{(dt_a, lex_a, dt_b, lex_b): (xsd_values triple, oxigraph triple)}`` for every pair the two disagree on."""
    out = {}
    for values in _families().values():
        lits = [lit(dt, lex) for dt, lex in values]
        pairs = list(itertools.product(range(len(lits)), repeat=2))
        theirs = oxigraph_compare([(lits[i], lits[j]) for i, j in pairs])
        for (i, j), got in zip(pairs, theirs, strict=True):
            ours = _expected(xv.compare(lits[i], lits[j]))
            got = tuple(x is True for x in got)
            if ours != got:
                out[(*values[i], *values[j])] = (ours, got)
    return out


def ebv_differences() -> dict[tuple[str, str], tuple]:
    out = {}
    corpus = []
    for dt in ("integer", "decimal", "float", "double", "boolean", "string", "byte", "unsignedLong"):
        corpus += [(dt, x) for x in (lexicals(dt) if dt not in ("string",) else C.STRING_SHAPES)]
    corpus += [("dateTime", "2020-01-01T00:00:00Z"), ("date", "2020-01-01"), ("duration", "PT0S"), ("hexBinary", "00"), ("anyURI", "a"), ("anyURI", "")]
    corpus += [("http://example.org/unknown", x) for x in ("", "x", "0", "1")]
    lits = [lit(dt, x) if not dt.startswith("http") else ox.Literal(x, datatype=ox.NamedNode(dt)) for dt, x in corpus]
    lits += [ox.Literal("x"), ox.Literal(""), ox.Literal("x", language="en"), ox.Literal("", language="en")]
    corpus += [("simple", "x"), ("simple", ""), ("@en", "x"), ("@en", "")]
    theirs = oxigraph_ebv(lits)
    for key, term, got in zip(corpus, lits, theirs, strict=True):
        ours = xv.ebv(term)
        if ours != got:
            out[key] = (ours, got)
    return out


# ---- the documented differences -------------------------------------------------------------------------------------------------
#
# Each rule names a class of disagreement, says who is right and why. A disagreement that no rule covers fails the test; so does a
# rule that covers none (the difference is gone: delete the rule, and celebrate).

import re  # noqa: E402

_DIGITS19 = re.compile(r"[0-9]{19}")
_NONSTANDARD_SPECIAL = re.compile(r"[+-]?(inf|infinity|nan)\Z", re.IGNORECASE)
_STANDARD_SPECIAL = {"INF", "+INF", "-INF", "NaN"}


def _collapsed(lex: str) -> str:
    return re.sub(r"[ \t\n\r]+", " ", lex).strip(" ")


def wf_rule(datatype: str, lex: str, ours: bool, theirs: bool) -> str | None:
    if ours and not theirs:
        if _collapsed(lex) != lex and not _DIGITS19.search(lex):
            return "whitespace-collapse"  # XSD 1.1 4.3.6: whiteSpace=collapse precedes the lexical mapping; Oxigraph is stricter
        if _DIGITS19.search(lex):
            return "arbitrary-precision"  # XSD 1.1 only requires 18 digits (5.4); Oxigraph's integer / decimal / seconds are fixed width
        if datatype == "gMonthDay" and lex.startswith("--02-29"):
            return "gMonthDay-feb-29"  # XSD 1.1 3.3.12: --02-29 is valid (leap-year reference); Oxigraph rejects it
    if not ours and theirs:
        if datatype in ("float", "double") and _NONSTANDARD_SPECIAL.match(_collapsed(lex)) and _collapsed(lex) not in _STANDARD_SPECIAL:
            return "float-special-spellings"  # XSD 1.1 3.3.4/3.3.5: only INF, +INF, -INF, NaN; Oxigraph accepts Rust's f64 spellings
        if datatype == "duration" and lex.rstrip().endswith("T"):
            return "duration-empty-time-part"  # XSD 1.1 3.3.6.2 duTimeFrag needs a component after T; Oxigraph accepts "P1DT"
    return None


WF_RULES = {"whitespace-collapse", "arbitrary-precision", "gMonthDay-feb-29", "float-special-spellings", "duration-empty-time-part"}


def castable_type(datatype: str) -> str:
    return "integer" if datatype in C.INTEGER_RANGES else datatype


_REJECTED: dict[str, set[str]] = {}


def oxigraph_rejects(datatype: str, lex: str) -> bool:
    """Does Oxigraph's cast to this datatype's family error on ``lex``? Computed once per family over the whole corpus."""
    fam = castable_type(datatype)
    if fam not in CASTABLE:
        return False
    if fam not in _REJECTED:
        every = {x for dt, x in (v for vals in _families().values() for v in vals) if castable_type(dt) == fam}
        every |= set(lexicals(fam)) | {x for dt in C.INTEGER_RANGES if fam == "integer" for x in lexicals(dt)}
        ordered = sorted(every)
        cast = oxigraph_cast(fam, ordered)
        _REJECTED[fam] = {x for x, got in zip(ordered, cast, strict=True) if got is None}
    return lex in _REJECTED[fam]


def cmp_rule(a: tuple[str, str], b: tuple[str, str], ours: tuple, theirs: tuple) -> str | None:
    if oxigraph_rejects(*a) or oxigraph_rejects(*b):
        return "operand-rejected-by-oxigraph"  # one operand is a well-formedness difference above: Oxigraph has no value for it
    if a[0] == "boolean" and b[0] == "boolean" and theirs == (False, False, False) and ours[0] != ours[2]:
        return "boolean-less-than"  # SPARQL 1.1 17.3 maps xsd:boolean `<` to op:boolean-less-than (false < true); Oxigraph raises an error
    return None


CMP_RULES = {"operand-rejected-by-oxigraph", "boolean-less-than"}


def ebv_rule(key: tuple[str, str], ours: bool | None, theirs: bool | None) -> str | None:
    dt, lex = key
    if dt in ("float", "double") and _NONSTANDARD_SPECIAL.match(_collapsed(lex)) and _collapsed(lex) not in _STANDARD_SPECIAL:
        return "float-special-spellings"
    if oxigraph_rejects(dt, lex) and theirs is None:
        # ill-formed (or beyond Oxigraph's width): SPARQL 1.1 17.2.2 says the EBV of an ill-formed boolean or numeric is false,
        # not an error; Oxigraph raises. A well-formed one that Oxigraph cannot hold (whitespace, big) is the WF rule again.
        return "ebv-of-unrepresentable-literal"
    if dt in C.INTEGER_RANGES and dt != "integer" and ours is False and theirs is True:
        # SPARQL 1.1 17.2.2: an ill-formed numeric has EBV false; "128"^^xsd:byte is ill-formed (XSD 1.1 3.4.20 maxInclusive 127).
        # Oxigraph has no range facets for the derived integer types and treats the literal as the integer 128.
        return "derived-integer-range-facets"
    return None


EBV_RULES = {"float-special-spellings", "ebv-of-unrepresentable-literal", "derived-integer-range-facets"}


# ---- the tests ------------------------------------------------------------------------------------------------------------------


def _classify(diffs: dict, rule, rules: set[str], what: str) -> None:
    unexplained = {k: v for k, v in diffs.items() if rule(k, v) is None}
    assert not unexplained, f"{what}: {len(unexplained)} disagreement(s) with Oxigraph not covered by a documented rule, e.g. {list(unexplained.items())[:5]}"
    used = {rule(k, v) for k, v in diffs.items()}
    assert used == rules, f"{what}: documented rules that no longer occur (Oxigraph changed?): {rules - used}"


def test_oxigraph_supports_the_cast_functions_the_corpus_needs():
    for dt in CASTABLE:
        assert oxigraph_cast(dt, lexicals(dt)[:1]) is not None, dt


def test_well_formedness_agrees_with_oxigraph_except_where_documented():
    diffs = well_formedness_differences()
    _classify(diffs, lambda k, v: wf_rule(k[0], k[1], *v), WF_RULES, "well-formedness")
    total = sum(len(lexicals(dt)) for dt in CASTABLE)
    assert total > 1000 and len(diffs) < total // 10


def test_comparisons_agree_with_oxigraph_except_where_documented():
    diffs = comparison_differences()
    _classify(diffs, lambda k, v: cmp_rule(k[:2], k[2:], *v), CMP_RULES, "comparison")


def test_ebv_agrees_with_oxigraph_except_where_documented():
    _classify(ebv_differences(), lambda k, v: ebv_rule(k, *v), EBV_RULES, "effective boolean value")


@pytest.mark.parametrize("datatype", sorted(C.INTEGER_RANGES))
def test_derived_integer_ranges_at_and_beyond_the_bounds(datatype):
    """Oxigraph has no cast for the derived integer types, so the oracle is the XSD 1.1 facet table itself (3.4.13-3.4.26)."""
    lo, hi = C.INTEGER_RANGES[datatype]
    for n in range(-3, 4):
        for bound in (lo, hi):
            if bound is None:
                continue
            value = bound + n
            inside = (lo is None or value >= lo) and (hi is None or value <= hi)
            assert xv.well_formed(lit(datatype, str(value))) is inside, (datatype, value)
    assert xv.well_formed(lit(datatype, "0")) is ((lo is None or lo <= 0) and (hi is None or hi >= 0))


def test_the_differences_that_are_xsd_values_fixes_hold():
    """Behaviours the cross-check made us change, pinned independently of Oxigraph."""
    # numeric type promotion (F&O 6.2; SPARQL 17.3): decimal 0.1 = double 0.1e0, integer 2^53+1 = double 2^53
    assert xv.compare(lit("decimal", "0.1"), lit("double", "0.1")) == 0
    assert xv.compare(lit("integer", "9007199254740993"), lit("double", "9007199254740992")) == 0
    assert xv.compare(lit("integer", "9007199254740993"), lit("decimal", "9007199254740992")) == 1  # exact within decimal
    assert xv.compare(lit("float", "16777217"), lit("integer", "16777216")) == 0
    # xsd:time 24:00:00 is the time of day 00:00:00 (XSD 1.1 3.3.14), not the end of the day
    assert xv.compare(lit("time", "24:00:00"), lit("time", "00:00:00")) == 0
    assert xv.compare(lit("dateTime", "2020-01-01T24:00:00Z"), lit("dateTime", "2020-01-02T00:00:00Z")) == 0
    # EBV of an ill-formed boolean / numeric is false, of other ill-typed or unknown datatypes an error (SPARQL 17.2.2)
    assert xv.ebv(lit("integer", "abc")) is False and xv.ebv(lit("boolean", "yes")) is False
    assert xv.ebv(lit("date", "nope")) is None
    # hexBinary / anyURI equality is RDFterm-equal in SPARQL: the same term only
    assert xv.compare(lit("hexBinary", "0A"), lit("hexBinary", "0a")) is None
    assert xv.compare(lit("hexBinary", "0A"), lit("hexBinary", "0A")) == 0
    # duration seconds may be ".5" or "1." (XSD 1.1 unsignedDecimalPtNumeral)
    assert xv.well_formed(lit("duration", "PT.5S")) and xv.well_formed(lit("duration", "PT1.S"))
    assert not xv.well_formed(lit("duration", "P1DT"))
    assert xv.well_formed(lit("gMonthDay", "--02-29")) and not xv.well_formed(lit("gMonthDay", "--02-30"))
