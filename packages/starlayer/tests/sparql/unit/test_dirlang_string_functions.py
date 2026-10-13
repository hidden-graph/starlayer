"""Verify RDF 1.2 Query sec 17.4.3's "Functions on Strings" family
(STRLEN/SUBSTR/UCASE/LCASE/STRSTARTS/STRENDS/CONTAINS/STRBEFORE/STRAFTER/
CONCAT/REGEX/REPLACE/ENCODE_FOR_URI) correctly accept and propagate
dirLangString ("text"@lang--dir) values, plus the directly-adjacent
DATATYPE()/hasLANG()/hasLANGDIR()/STRLANGDIR() fixes found alongside them.

Found 2026-10-13 via a retrospective check of which W3C SPARQL 1.2 suite
categories this project fetches at all: `lang-basedir` (the category
covering exactly this function family) was never fetched, and every one
of these 14 functions turned out to reject a dirLangString value outright
- rdflib's own stock evalfns all call `operators.string()`, which raises
for any literal whose datatype isn't `xsd:string`, and a dirLangString is
internally stored with a non-standard `dirlang:` datatype IRI (see
`starlayer.graph.model.encoding`). Fixed by routing all 14 (13 here;
`langMATCHES` needs no fix - see `custom_functions.py`'s own module
comment) through dedicated custom functions registered in
`starlayer.graph.query.custom_functions`, intercepted during
`lower_rdf11._lower_expr`'s own dispatch.

Execution-level tests throughout (run the real query, compare the actual
result), not structural/parse-only ones - this package's own documented
testing discipline (`CLAUDE.md`'s "Testing discipline" section) already
caught two real bugs this exact shape of gap would otherwise hide.
"""

from __future__ import annotations

from rdflib import Literal
from rdflib.namespace import RDF, XSD
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.graph.model.dirlangstring import DirLangString
from starlayer.sparql.lower_rdf11 import (
    RDF_DIRLANGSTRING,
    query_to_rdf11,
    rdf11_to_query,
)
from starlayer.sparql.parse12 import prepare_query_12


def _ask(query_text: str) -> bool:
    graph = StarLayerGraph()
    prepared = prepare_query_12(query_text)
    rdf_graph, root = query_to_rdf11(prepared)
    query_object = rdf11_to_query(rdf_graph, root)
    return graph.query(query_object).askAnswer


def _select_one(query_text: str):
    """Run a `SELECT (... AS ?v) WHERE {}`-shaped query, return ?v's value
    (None if unbound) from the one expected result row."""
    graph = StarLayerGraph()
    prepared = prepare_query_12(query_text)
    rdf_graph, root = query_to_rdf11(prepared)
    query_object = rdf11_to_query(rdf_graph, root)
    rows = list(graph.query(query_object).bindings)
    assert len(rows) == 1
    row = dict(rows[0])
    assert len(row) == 1
    return next(iter(row.values()))


class TestArgumentCompatibilityAndPropagation:
    """STRSTARTS/STRENDS/CONTAINS/STRBEFORE/STRAFTER's shared
    argument-compatibility table (sec 17.4.3's own intro) and
    SUBSTR/STRBEFORE/STRAFTER/REPLACE/UCASE/LCASE's "same kind as arg1"
    propagation rule - the part of this retrofit most likely to hide a
    subtle bug, so covered directly rather than only through the full
    SELECT-list fixtures below."""

    def test_strstarts_dirlangstring_same_lang_and_dir_is_compatible(self):
        assert _ask('ASK { FILTER(STRSTARTS("abc"@en--ltr, "ab"@en--ltr)) }') is True

    def test_strstarts_dirlangstring_vs_plain_is_compatible(self):
        assert _ask('ASK { FILTER(STRSTARTS("abc"@en--ltr, "ab")) }') is True

    def test_strstarts_plain_vs_dirlangstring_is_not_compatible(self):
        # Spec's own table: "abc" | "b"@en--ltr -> no (an error, not false).
        assert _select_one('SELECT (STRSTARTS("abc", "a"@en--ltr) AS ?v) WHERE {}') is None

    def test_strstarts_dirlangstring_different_dir_is_not_compatible(self):
        assert _select_one('SELECT (STRSTARTS("abc"@en--ltr, "a"@en) AS ?v) WHERE {}') is None

    def test_strends_dirlangstring_same_lang_and_dir(self):
        assert _ask('ASK { FILTER(STRENDS("abc"@en--ltr, "bc"@en--ltr)) }') is True

    def test_contains_dirlangstring_same_lang_and_dir(self):
        assert _ask('ASK { FILTER(CONTAINS("abc"@en--ltr, "b"@en--ltr)) }') is True

    def test_contains_incompatible_args_is_unbound_not_a_crash(self):
        # The original bug report for this retrofit: this used to crash
        # with a bare Python TypeError instead of leaving ?v unbound.
        assert _select_one('SELECT (CONTAINS("abc", "b"@en--ltr) AS ?v) WHERE {}') is None

    def test_strbefore_propagates_dirlangstring_kind_on_match(self):
        result = _select_one('SELECT (STRBEFORE("abcd"@en--ltr, "cd"@en--ltr) AS ?v) WHERE {}')
        assert result == DirLangString("ab", "en", "ltr")

    def test_strbefore_no_match_is_plain_empty_literal_not_same_kind(self):
        result = _select_one('SELECT (STRBEFORE("abc"@en--ltr, "xyz"@en--ltr) AS ?v) WHERE {}')
        assert result == Literal("") and result.datatype is None and result.language is None

    def test_strafter_propagates_dirlangstring_kind_on_match(self):
        result = _select_one('SELECT (STRAFTER("abcd"@en--ltr, "ab"@en--ltr) AS ?v) WHERE {}')
        assert result == DirLangString("cd", "en", "ltr")

    def test_substr_propagates_dirlangstring_kind(self):
        result = _select_one('SELECT (SUBSTR("foobar"@en--ltr, 4, 1) AS ?v) WHERE {}')
        assert result == DirLangString("b", "en", "ltr")

    def test_substr_two_arg_form_without_length(self):
        result = _select_one('SELECT (SUBSTR("foobar", 4) AS ?v) WHERE {}')
        assert result == Literal("bar")

    def test_ucase_propagates_dirlangstring_kind(self):
        result = _select_one('SELECT (UCASE("foo"@en--ltr) AS ?v) WHERE {}')
        assert result == DirLangString("FOO", "en", "ltr")

    def test_lcase_propagates_langstring_kind(self):
        result = _select_one('SELECT (LCASE("BAR"@en) AS ?v) WHERE {}')
        assert result == Literal("bar", lang="en")

    def test_strlen_of_dirlangstring_counts_codepoints_not_the_tag(self):
        result = _select_one('SELECT (STRLEN("chat"@en--ltr) AS ?v) WHERE {}')
        assert result == Literal(4)


class TestConcat:
    """RDF 1.2 Query sec 17.4.3.10's own 3-way propagation rule - every
    branch, not just the ones the W3C lang-basedir/concat.rq fixture
    happens to exercise."""

    def test_zero_args_is_plain_empty_string(self):
        result = _select_one("SELECT (CONCAT() AS ?v) WHERE {}")
        assert result == Literal("") and result.datatype is None

    def test_one_dirlangstring_arg_is_unchanged(self):
        result = _select_one('SELECT (CONCAT("abc"@en--ltr) AS ?v) WHERE {}')
        assert result == DirLangString("abc", "en", "ltr")

    def test_same_lang_and_dir_propagates_dirlangstring(self):
        result = _select_one('SELECT (CONCAT("a"@en--ltr, "b"@en--ltr) AS ?v) WHERE {}')
        assert result == DirLangString("ab", "en", "ltr")

    def test_same_lang_different_dir_falls_back_to_plain(self):
        result = _select_one('SELECT (CONCAT("a"@en--ltr, "b"@en--rtl) AS ?v) WHERE {}')
        assert result == Literal("ab") and result.datatype is None and result.language is None

    def test_same_lang_one_undirected_falls_back_to_plain(self):
        result = _select_one('SELECT (CONCAT("a"@en--ltr, "b"@en) AS ?v) WHERE {}')
        assert result == Literal("ab") and result.datatype is None

    def test_same_lang_no_dir_at_all_propagates_langstring(self):
        result = _select_one('SELECT (CONCAT("a"@en, "b"@en) AS ?v) WHERE {}')
        assert result == Literal("ab", lang="en")

    def test_different_lang_falls_back_to_plain(self):
        result = _select_one('SELECT (CONCAT("a"@en--ltr, "b"@fr--ltr) AS ?v) WHERE {}')
        assert result == Literal("ab") and result.datatype is None

    def test_rejects_non_string_literal_argument(self):
        assert _select_one("SELECT (CONCAT(1, \"a\") AS ?v) WHERE {}") is None


class TestRegexReplaceEncodeForUri:
    def test_regex_matches_dirlangstring_text(self):
        assert _ask('ASK { FILTER(REGEX("hello"@en--ltr, "^he")) }') is True

    def test_regex_with_flags_still_works(self):
        assert _ask('ASK { FILTER(REGEX("HELLO", "^he", "i")) }') is True

    def test_regex_plain_text_unaffected(self):
        assert _ask('ASK { FILTER(REGEX("hello", "^h")) }') is True
        assert _ask('ASK { FILTER(REGEX("hello", "^z")) }') is False

    def test_replace_propagates_dirlangstring_kind(self):
        result = _select_one('SELECT (REPLACE("abcd"@en--ltr, "b", "Z") AS ?v) WHERE {}')
        assert result == DirLangString("aZcd", "en", "ltr")

    def test_replace_with_flags_still_works(self):
        result = _select_one('SELECT (REPLACE("abab", "B", "Z", "i") AS ?v) WHERE {}')
        assert result == Literal("aZaZ")

    def test_encode_for_uri_of_dirlangstring_is_plain_xsd_string(self):
        result = _select_one('SELECT (ENCODE_FOR_URI("a b"@en--ltr) AS ?v) WHERE {}')
        assert result == Literal("a%20b")


class TestDatatypeUcaseOfDirLangString:
    def test_datatype_reports_real_rdf_dirlangstring_not_internal_encoding(self):
        # The original bug: this leaked starlayer.graph's own internal
        # dirlang: encoding IRI instead of the real rdf:dirLangString.
        result = _select_one('SELECT (DATATYPE("abc"@en--ltr) AS ?v) WHERE {}')
        assert result == RDF_DIRLANGSTRING

    def test_datatype_of_plain_literal_unaffected(self):
        assert _select_one('SELECT (DATATYPE("abc") AS ?v) WHERE {}') == XSD.string

    def test_datatype_of_langstring_unaffected(self):
        assert _select_one('SELECT (DATATYPE("abc"@en) AS ?v) WHERE {}') == RDF.langString


class TestHasLangAndHasLangdirOnNonLiterals:
    """RDF 1.2 Query sec 17.4.2.10/.11: hasLANG()/hasLANGDIR() must return
    false for a non-literal RDF term, not error - unlike LANG()/LANGDIR()
    themselves, which both do error on one. Found broken 2026-10-13
    alongside the string-function retrofit: DATATYPE() (which both of
    these build on internally) raises for a non-literal, and that error
    was propagating all the way up uncaught."""

    def test_haslang_of_iri_is_false_not_unbound(self):
        assert _select_one("SELECT (hasLANG(<http://example/>) AS ?v) WHERE {}") == Literal(False)

    def test_haslangdir_of_iri_is_false_not_unbound(self):
        assert _select_one("SELECT (hasLANGDIR(<http://example/>) AS ?v) WHERE {}") == Literal(False)

    def test_haslang_of_dirlangstring_is_still_true(self):
        assert _select_one('SELECT (hasLANG("abc"@en--ltr) AS ?v) WHERE {}') == Literal(True)

    def test_langdir_of_iri_still_errors(self):
        # Confirms the COALESCE-based fix above is scoped to hasLANG/
        # hasLANGDIR specifically - LANGDIR() itself must still error on a
        # non-literal, per the same spec section's own example table.
        assert _select_one("SELECT (LANGDIR(<http://example/>) AS ?v) WHERE {}") is None


class TestStrlangdirValidation:
    """STRLANGDIR()'s own construction-time validation - found incomplete
    2026-10-13 alongside the string-function retrofit (only the direction
    argument was ever checked)."""

    def test_rejects_empty_language_tag(self):
        assert _select_one('SELECT (STRLANGDIR("abc", "", "ltr") AS ?v) WHERE {}') is None

    def test_rejects_uppercase_direction(self):
        # RDF 1.2 Query sec 17.4.2.17's own example table:
        # STRLANGDIR("abc", "en", "LTR") -> error - direction is
        # case-sensitive, unlike language (still case-folded below).
        assert _select_one('SELECT (STRLANGDIR("abc", "en", "LTR") AS ?v) WHERE {}') is None

    def test_rejects_iri_as_lexical_form(self):
        assert _select_one('SELECT (STRLANGDIR(<http://example/x>, "en", "ltr") AS ?v) WHERE {}') is None

    def test_accepts_valid_args_and_lowercases_language(self):
        result = _select_one('SELECT (STRLANGDIR("abc", "EN", "ltr") AS ?v) WHERE {}')
        assert result == DirLangString("abc", "en", "ltr")
