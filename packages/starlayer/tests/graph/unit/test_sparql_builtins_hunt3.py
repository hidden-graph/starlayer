"""SPARQL builtin and expression-error fixes from the second bug hunt
(GitHub issue #76). Each test is a repro from the issue; the expected values
come from SPARQL 1.1/1.2 Query (sections 17.2 error handling, 17.3 operator
mapping, 17.4 functions, 18.6 aggregates), not from plain rdflib. See
``starlayer/graph/query/builtin_error_patches.py``.
"""

from __future__ import annotations

import pytest
from rdflib import Literal, URIRef
from starlayer import StarLayerGraph
from starlayer.graph.query.version_directive import strip_version_directive

PRE = "PREFIX : <http://e/> PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> "
XSD_NS = "http://www.w3.org/2001/XMLSchema#"


def rows(query: str, data: str | None = None) -> list[dict]:
    g = StarLayerGraph()
    if data:
        g.update(PRE + "INSERT DATA { " + data + " }")
    res = g.query(PRE + query)
    return [{str(v): row[i] for i, v in enumerate(res.vars)} for row in res]


def value(query: str, data: str | None = None):
    """The single projected value of a one-row, one-column SELECT."""
    (row,) = rows(query, data)
    (val,) = row.values()
    return val


def lit(text: str, datatype: str | None = None) -> Literal:
    return Literal(text, datatype=URIRef(XSD_NS + datatype) if datatype else None)


class TestIn:
    def test_in_uses_value_equality(self) -> None:
        assert value("SELECT (1 IN (1.0, 2) AS ?x) {}") == Literal(True)

    def test_not_in_uses_value_equality(self) -> None:
        assert value("SELECT (1 NOT IN (1.0, 2) AS ?x) {}") == Literal(False)

    def test_filter_in_matches_both_numeric_forms(self) -> None:
        out = rows("SELECT ?o { :s :p ?o FILTER(?o IN (1)) }", ":s :p 1, 1.0")
        assert {str(r["o"]) for r in out} == {"1", "1.0"}

    def test_filter_not_in_excludes_equal_values(self) -> None:
        out = rows("SELECT ?o { :s :p ?o FILTER(?o NOT IN (1, 2)) }", ":s :p 1, 1.0, 3")
        assert [str(r["o"]) for r in out] == ["3"]

    def test_in_error_in_list_without_match_is_error(self) -> None:
        assert value("SELECT (2 IN (1/0, 1) AS ?x) {}") is None

    def test_in_match_wins_over_error(self) -> None:
        assert value("SELECT (1 IN (1/0, 1) AS ?x) {}") == Literal(True)

    def test_not_in_error_in_list_is_error(self) -> None:
        assert value("SELECT (2 NOT IN (1/0, 1) AS ?x) {}") is None

    def test_error_and_false_is_false(self) -> None:
        assert value("SELECT (1/0 && false AS ?x) {}") == Literal(False)

    def test_error_and_true_is_error(self) -> None:
        assert value("SELECT (1/0 && true AS ?x) {}") is None


class TestSubstr:
    @pytest.mark.parametrize(
        ("expr", "expected"),
        [
            ('SUBSTR("abc", 0, 2)', "a"),
            ('SUBSTR("abc", -1, 3)', "a"),
            ('SUBSTR("abcdef", 0, 3)', "ab"),
            ('SUBSTR("abcdef", -1, 4)', "ab"),
            ('SUBSTR("abc", 0)', "abc"),
            ('SUBSTR("abc", 2)', "bc"),
            ('SUBSTR("abc", 2, 1)', "b"),
            ('SUBSTR("abc", 5, 2)', ""),
            ('SUBSTR("abc", 1, 0)', ""),
            ('SUBSTR("abc", 1, -2)', ""),
        ],
    )
    def test_position_arithmetic(self, expr: str, expected: str) -> None:
        assert str(value(f"SELECT ({expr} AS ?x) {{}}")) == expected

    def test_keeps_language_tag(self) -> None:
        assert value('SELECT (SUBSTR("abc"@en, 0, 2) AS ?x) {}') == Literal("a", lang="en")

    def test_non_integer_start_is_error(self) -> None:
        assert value('SELECT (SUBSTR("abcdef", 1.5, 2) AS ?x) {}') is None


class TestTimezone:
    def test_minutes_of_offset_are_kept(self) -> None:
        got = value('SELECT (TIMEZONE("2020-01-02T03:04:05-05:30"^^xsd:dateTime) AS ?x) {}')
        assert str(got) == "-PT5H30M"
        assert str(got.datatype) == XSD_NS + "dayTimeDuration"

    def test_whole_hours(self) -> None:
        assert str(value('SELECT (TIMEZONE("2020-01-02T03:04:05+14:00"^^xsd:dateTime) AS ?x) {}')) == "PT14H"

    def test_positive_offset_with_minutes(self) -> None:
        assert str(value('SELECT (TIMEZONE("2020-01-02T03:04:05+05:45"^^xsd:dateTime) AS ?x) {}')) == "PT5H45M"

    def test_no_timezone_is_error(self) -> None:
        assert value('SELECT (TIMEZONE("2020-01-02T03:04:05"^^xsd:dateTime) AS ?x) {}') is None


class TestAggregateErrors:
    DATA = ':s :p 1, 1.0, "a"'

    def test_sum_over_mixed_values_is_unbound_and_count_survives(self) -> None:
        (row,) = rows("SELECT (SUM(?o) AS ?sm) (COUNT(*) AS ?n) { :s :p ?o }", self.DATA)
        assert row["sm"] is None
        assert row["n"] == Literal(3)

    def test_avg_over_non_numeric_is_unbound(self) -> None:
        assert value("SELECT (AVG(?o) AS ?a) { :s :p ?o }", self.DATA) is None

    def test_min_and_max_do_not_raise(self) -> None:
        (row,) = rows("SELECT (MIN(?o) AS ?mn) (MAX(?o) AS ?mx) { :s :p ?o }", self.DATA)
        assert row["mn"] is not None and row["mx"] is not None

    def test_having_drops_only_the_erroring_group(self) -> None:
        out = rows(
            "SELECT ?s { ?s :p ?o } GROUP BY ?s HAVING (SUM(?o) > 5)",
            ':bad :p 1, "a" . :good :p 10',
        )
        assert [str(r["s"]) for r in out] == ["http://e/good"]

    def test_error_is_per_group(self) -> None:
        out = rows(
            "SELECT ?s (SUM(?o) AS ?t) { ?s :p ?o } GROUP BY ?s ORDER BY ?s",
            ':bad :p 1, "a" . :good :p 10, 5',
        )
        assert out[0]["t"] is None
        assert out[1]["t"] == Literal(15)

    def test_numeric_sum_unchanged(self) -> None:
        assert value("SELECT (SUM(?o) AS ?t) { :s :p ?o }", ":s :p 1, 2.5") == Literal("3.5", datatype=URIRef(XSD_NS + "decimal"))

    def test_distinct_sum_over_non_numeric_is_unbound(self) -> None:
        assert value("SELECT (SUM(DISTINCT ?o) AS ?t) { :s :p ?o }", self.DATA) is None


class TestEmptyValues:
    def test_no_rows_gives_no_solutions(self) -> None:
        assert rows("SELECT * { VALUES ?a { } }") == []

    def test_no_rows_multiple_variables(self) -> None:
        assert rows("SELECT * { VALUES (?a ?b) { } }") == []

    def test_no_variables_no_rows(self) -> None:
        assert rows("SELECT * { VALUES () { } }") == []

    def test_no_variables_one_empty_row_gives_one_solution(self) -> None:
        assert rows("SELECT * { VALUES () { () } }") == [{}]

    def test_no_variables_two_rows(self) -> None:
        assert len(rows("SELECT * { VALUES () { () () } }")) == 2

    def test_empty_values_joined_with_pattern_removes_everything(self) -> None:
        assert rows("SELECT * { ?s :p ?o VALUES ?a { } }", ":s :p 1") == []

    def test_empty_row_values_joined_with_pattern_keeps_it(self) -> None:
        assert len(rows("SELECT * { ?s :p ?o VALUES () { () } }", ":s :p 1")) == 1


class TestStringConstructors:
    def test_strlang_invalid_tag_is_unbound_under_coalesce(self) -> None:
        assert value('SELECT (COALESCE(STRLANG("a", "!!"), "fallback") AS ?x) {}') == Literal("fallback")

    def test_strlang_invalid_tag_does_not_abort_other_rows(self) -> None:
        out = rows('SELECT ?t { VALUES ?t { "en" "!!" } FILTER(STRLANG("a", ?t) = "a"@en) }')
        assert [str(r["t"]) for r in out] == ["en"]

    def test_strlang_with_direction_suffix_is_unbound(self) -> None:
        assert value('SELECT (STRLANG("abc", "en--ltr") AS ?x) {}') is None

    def test_strlang_space_in_tag_is_unbound_and_rest_survives(self) -> None:
        (row,) = rows('SELECT (STRLANG("a", "e n") AS ?b) (1 AS ?c) {}')
        assert row["b"] is None and row["c"] == Literal(1)

    def test_strlang_valid_tag_still_works(self) -> None:
        assert value('SELECT (STRLANG("a", "en") AS ?x) {}') == Literal("a", lang="en")

    def test_strdt_non_iri_datatype_is_unbound(self) -> None:
        assert value('SELECT (STRDT("a", 1) AS ?x) {}') is None

    def test_strdt_string_datatype_is_unbound(self) -> None:
        assert value('SELECT (STRDT("a", "http://x") AS ?x) {}') is None

    def test_strdt_language_tagged_lexical_form_is_unbound(self) -> None:
        assert value('SELECT (STRDT("a"@en, xsd:string) AS ?x) {}') is None

    def test_strdt_iri_datatype_still_works(self) -> None:
        assert value('SELECT (STRDT("5", xsd:integer) AS ?x) {}') == Literal(5)

    def test_strlangdir_language_tagged_lexical_form_is_unbound(self) -> None:
        assert value('SELECT (STRLANGDIR("a"@en, "fr", "ltr") AS ?x) {}') is None

    def test_strlangdir_plain_lexical_form_still_works(self) -> None:
        assert str(value('SELECT (STRLANGDIR("a", "fr", "ltr") AS ?x) {}')) == "a"


class TestOrderingOfMixedTypes:
    def test_string_greater_than_integer_is_error(self) -> None:
        assert value('SELECT ("x" > 1 AS ?r) {}') is None

    def test_integer_less_than_string_is_error(self) -> None:
        assert value('SELECT (1 < "x" AS ?r) {}') is None

    def test_boolean_against_integer_is_error(self) -> None:
        assert value("SELECT (true < 2 AS ?r) {}") is None

    def test_if_over_mixed_comparison_is_error(self) -> None:
        out = rows('SELECT ?o (IF(?o > 1, "big", "small") AS ?z) { :c :q ?o }', ':c :q "x"')
        assert out[0]["z"] is None

    def test_filter_over_mixed_comparison_removes_the_row(self) -> None:
        assert rows('SELECT * { FILTER("x" > 1) }') == []

    def test_same_class_comparisons_unchanged(self) -> None:
        assert value('SELECT ("a" < "b" AS ?r) {}') == Literal(True)
        assert value("SELECT (2 > 1.5 AS ?r) {}") == Literal(True)
        assert value("SELECT (false < true AS ?r) {}") == Literal(True)

    def test_equality_across_types_is_not_an_ordering_error(self) -> None:
        assert value('SELECT ("x" != 1 AS ?r) {}') == Literal(True)


class TestDoubleDivision:
    def test_double_divided_by_zero_is_infinity(self) -> None:
        got = value("SELECT (1e0 / 0 AS ?r) {}")
        assert str(got) == "INF"
        assert str(got.datatype) == XSD_NS + "double"

    def test_negative_double_divided_by_zero(self) -> None:
        assert str(value("SELECT (-1e0 / 0 AS ?r) {}")) == "-INF"

    def test_zero_double_divided_by_zero_is_nan(self) -> None:
        assert str(value("SELECT (0e0 / 0 AS ?r) {}")) == "NaN"

    def test_integer_divided_by_double_zero_is_infinity(self) -> None:
        assert str(value("SELECT (1 / 0e0 AS ?r) {}")) == "INF"

    def test_decimal_division_by_zero_is_still_an_error(self) -> None:
        assert value("SELECT (1.0 / 0 AS ?r) {}") is None

    def test_integer_division_by_zero_is_still_an_error(self) -> None:
        assert value("SELECT (1 / 0 AS ?r) {}") is None

    def test_double_cast_of_inf_has_valid_lexical_form(self) -> None:
        assert str(value('SELECT (xsd:double("INF") AS ?x) {}')) == "INF"


class TestIllTypedLiterals:
    def test_arithmetic_on_ill_typed_integer_is_error(self) -> None:
        assert value('SELECT ("abc"^^xsd:integer + 1 AS ?x) {}') is None

    def test_is_numeric_is_false_for_ill_typed(self) -> None:
        assert value('SELECT (isNumeric("a"^^xsd:integer) AS ?x) {}') == Literal(False)
        assert value('SELECT (isNumeric("a"^^xsd:double) AS ?x) {}') == Literal(False)

    def test_is_numeric_is_true_for_well_typed(self) -> None:
        assert value("SELECT (isNumeric(5) AS ?x) {}") == Literal(True)

    def test_unary_minus_on_ill_typed_is_error(self) -> None:
        assert value('SELECT (-"abc"^^xsd:integer AS ?x) {}') is None

    @pytest.mark.parametrize("fn", ["DAY", "YEAR", "MONTH", "HOURS", "MINUTES", "SECONDS", "TIMEZONE", "TZ"])
    def test_datetime_accessors_on_ill_typed_datetime_are_errors(self, fn: str) -> None:
        got = value(f'SELECT (COALESCE({fn}("x"^^xsd:dateTime), "err") AS ?x) {{}}')
        assert got == Literal("err")

    def test_nonexistent_date_is_an_error(self) -> None:
        assert value('SELECT (COALESCE(DAY("2020-02-30T00:00:00"^^xsd:dateTime), "err") AS ?x) {}') == Literal("err")

    def test_day_of_valid_datetime_unchanged(self) -> None:
        assert value('SELECT (DAY("2020-02-17T00:00:00"^^xsd:dateTime) AS ?x) {}') == Literal(17)


class TestSelectStarScope:
    DATA = ":a :p :b . :b :p :c"

    def test_filter_exists_variable_is_not_projected(self) -> None:
        g = StarLayerGraph()
        g.update(PRE + "INSERT DATA { " + self.DATA + " }")
        res = g.query(PRE + "SELECT * { ?s :p ?o FILTER EXISTS { ?o :p ?zz } }")
        assert sorted(str(v) for v in res.vars) == ["o", "s"]
        assert len(list(res)) == 1

    def test_filter_not_exists_variable_is_not_projected(self) -> None:
        g = StarLayerGraph()
        g.update(PRE + "INSERT DATA { " + self.DATA + " }")
        res = g.query(PRE + "SELECT * { ?s :p ?o FILTER NOT EXISTS { ?o :p ?zz } }")
        assert sorted(str(v) for v in res.vars) == ["o", "s"]

    def test_optional_variable_is_still_projected(self) -> None:
        g = StarLayerGraph()
        g.update(PRE + "INSERT DATA { " + self.DATA + " }")
        res = g.query(PRE + "SELECT * { ?s :p ?o OPTIONAL { ?o :p ?zz } }")
        assert sorted(str(v) for v in res.vars) == ["o", "s", "zz"]

    def test_describe_star_describes_bound_resources(self) -> None:
        g = StarLayerGraph()
        g.update(PRE + "INSERT DATA { :a :r :b . :b :x 1 . :z :x 2 }")
        res = g.query(PRE + "DESCRIBE * WHERE { ?s :r ?o }")
        triples = {(str(s), str(p)) for s, p, _ in res.graph}
        assert ("http://e/a", "http://e/r") in triples
        assert ("http://e/b", "http://e/x") in triples
        assert ("http://e/z", "http://e/x") not in triples


class TestVersionDirectiveScanner:
    def test_header_comment_before_version(self) -> None:
        assert strip_version_directive('# hello\nVERSION "1.2"\nSELECT * {?s ?p ?o}') == ("SELECT * {?s ?p ?o}", "1.2")

    def test_comment_between_prologue_declarations(self) -> None:
        text, label = strip_version_directive('PREFIX : <http://a/> # c\nVERSION "1.2"\nSELECT * {}')
        assert label == "1.2"
        assert text == "PREFIX : <http://a/> SELECT * {}"

    def test_query_with_header_comment_and_version_runs(self) -> None:
        assert list(StarLayerGraph().query('# hello\nVERSION "1.2"\nSELECT * {?s ?p ?o}')) == []

    def test_escaped_quote_is_part_of_the_label(self) -> None:
        assert strip_version_directive('VERSION "a\\"b" SELECT * {}') == ("SELECT * {}", 'a"b')

    def test_triple_quoted_label_is_left_for_the_parser(self) -> None:
        text = 'VERSION """1.2""" SELECT * {}'
        assert strip_version_directive(text) == (text, None)

    def test_version_text_in_a_trailing_comment_is_not_a_directive(self) -> None:
        text = 'SELECT * {} # VERSION "1.2"'
        assert strip_version_directive(text) == (text, None)

    def test_single_quoted_label(self) -> None:
        assert strip_version_directive("VERSION '1.2' SELECT * {}") == ("SELECT * {}", "1.2")


class TestDirectionalLanguageTagCase:
    def test_same_term_ignores_case_of_tag(self) -> None:
        assert value('SELECT (sameTerm("a"@en--rtl, "a"@EN--rtl) AS ?x) {}') == Literal(True)

    def test_equals_ignores_case_of_tag(self) -> None:
        assert value('SELECT ("a"@en--rtl = "a"@EN--rtl AS ?x) {}') == Literal(True)

    def test_different_direction_is_not_same(self) -> None:
        assert value('SELECT (sameTerm("a"@en--rtl, "a"@en--ltr) AS ?x) {}') == Literal(False)

    def test_not_equals(self) -> None:
        assert value('SELECT ("a"@en--rtl != "a"@EN--rtl AS ?x) {}') == Literal(False)

    def test_plain_language_literal_case_still_ignored(self) -> None:
        assert value('SELECT (sameTerm("abc"@en, "abc"@EN) AS ?x) {}') == Literal(True)


class TestSerializeServiceSilent:
    def test_silent_is_written(self) -> None:
        from starlayer.sparql.parse12 import prepare_query_12
        from starlayer.sparql.serialize12 import _translate_algebra_12

        text = _translate_algebra_12(prepare_query_12("SELECT * { SERVICE SILENT <http://e/sv> { ?s ?p ?o } }"))
        assert "SERVICE SILENT <http://e/sv>" in text

    def test_plain_service_has_no_silent(self) -> None:
        from starlayer.sparql.parse12 import prepare_query_12
        from starlayer.sparql.serialize12 import _translate_algebra_12

        text = _translate_algebra_12(prepare_query_12("SELECT * { SERVICE <http://e/sv> { ?s ?p ?o } }"))
        assert "SILENT" not in text
        assert "SERVICE <http://e/sv>" in text
