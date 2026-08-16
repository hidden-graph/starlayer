"""Confirms starlayergraph/__init__.py's import-time patches for two confirmed
plain-rdflib SPARQL arithmetic bugs actually take effect against real
Graph().query() calls - see starlayergraph/query/operator_patches.py for the
root-cause writeups.
"""

import starlayergraph  # noqa: F401  (import-time patch application under test)
from rdflib import XSD, Graph


def _eval(query: str):
    return list(Graph().query(query))[0][0]


class TestMultiplicativeExpressionTypePromotion:
    def test_integer_times_integer_stays_integer(self) -> None:
        result = _eval("SELECT (6 * 7 AS ?r) WHERE {}")
        assert str(result) == "42"
        assert result.datatype == XSD.integer

    def test_integer_times_decimal_promotes_to_decimal(self) -> None:
        result = _eval("SELECT (6 * 7.5 AS ?r) WHERE {}")
        assert str(result) == "45.0"
        assert result.datatype == XSD.decimal

    def test_integer_times_double_promotes_to_double(self) -> None:
        result = _eval("SELECT (2 * 3e0 AS ?r) WHERE {}")
        assert result.datatype == XSD.double

    def test_addition_still_stays_integer_unaffected_by_patch(self) -> None:
        result = _eval("SELECT (6 + 7 AS ?r) WHERE {}")
        assert str(result) == "13"
        assert result.datatype == XSD.integer


class TestDecimalResultLexicalForm:
    def test_division_of_two_integers_gets_canonical_decimal_form(self) -> None:
        result = _eval("SELECT (84 / 2 AS ?r) WHERE {}")
        assert str(result) == "42.0"
        assert result.datatype == XSD.decimal

    def test_division_with_existing_fraction_is_unaffected(self) -> None:
        result = _eval("SELECT (84 / 5 AS ?r) WHERE {}")
        assert str(result) == "16.8"

    def test_ceil_gets_canonical_decimal_form(self) -> None:
        result = _eval("SELECT (CEIL(3.2) AS ?r) WHERE {}")
        assert str(result) == "4.0"
        assert result.datatype == XSD.decimal

    def test_floor_gets_canonical_decimal_form(self) -> None:
        result = _eval("SELECT (FLOOR(3.7) AS ?r) WHERE {}")
        assert str(result) == "3.0"
        assert result.datatype == XSD.decimal

    def test_round_gets_canonical_decimal_form(self) -> None:
        result = _eval("SELECT (ROUND(3.5) AS ?r) WHERE {}")
        assert str(result) == "4.0"
        assert result.datatype == XSD.decimal

    def test_abs_is_unaffected_by_patch(self) -> None:
        result = _eval("SELECT (ABS(-5) AS ?r) WHERE {}")
        assert str(result) == "5"
        assert result.datatype == XSD.integer
