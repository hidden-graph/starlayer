"""``literal`` (a term from a Python value), ``to_python`` (a literal's value) and ``parse_term`` (a term from Turtle text)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pyoxigraph as ox
import pytest
from starlayer.graph import XSD, literal, parse_term, to_python

CASES = [
    (True, XSD.boolean, "true"),
    (False, XSD.boolean, "false"),
    (5, XSD.integer, "5"),
    (-7, XSD.integer, "-7"),
    (2.5, XSD.double, "2.5"),
    (Decimal("1.50"), XSD.decimal, "1.50"),
    (dt.datetime(2026, 1, 2, 3, 4, 5), XSD.dateTime, "2026-01-02T03:04:05"),
    (dt.date(2026, 1, 2), XSD.date, "2026-01-02"),
    (dt.time(1, 2, 3), XSD.time, "01:02:03"),
    ("text", XSD.string, "text"),
]


@pytest.mark.parametrize(("value", "datatype", "lexical"), CASES)
def test_a_python_value_is_typed_by_its_python_type_and_reads_back(value, datatype, lexical):
    term = literal(value)
    assert term == ox.Literal(lexical, datatype=datatype) and to_python(term) == value


def test_text_with_a_datatype_a_language_and_a_direction():
    assert literal("5", XSD.long) == ox.Literal("5", datatype=XSD.long)
    assert literal("5", "http://www.w3.org/2001/XMLSchema#long") == ox.Literal("5", datatype=XSD.long)
    assert literal(5, XSD.long) == ox.Literal("5", datatype=XSD.long)
    assert literal("a", lang="en") == ox.Literal("a", language="en")
    assert literal("a", lang="ar", direction="rtl") == ox.Literal("a", language="ar", direction=ox.BaseDirection.RTL)
    assert literal("a", XSD.string, lang="en") == ox.Literal("a", language="en")  # xsd:string is what a plain string already is
    with pytest.raises(ValueError, match="not both"):
        literal("5", XSD.integer, lang="en")  # the datatype cannot be kept, so it is an error, not dropped
    with pytest.raises(ValueError, match="language"):
        literal("a", direction="ltr")
    with pytest.raises(ValueError, match="direction"):
        literal("a", lang="en", direction="up")


def test_special_floats_use_the_xsd_spellings():
    assert literal(float("nan")).value == "NaN" and literal(float("inf")).value == "INF" and literal(float("-inf")).value == "-INF"
    assert to_python(literal(float("inf"))) == float("inf")


def test_other_datatypes_and_language_strings_read_back_as_their_text():
    assert to_python(ox.Literal("x", language="en")) == "x"
    assert to_python(ox.Literal("P1D", datatype=XSD.duration)) == "P1D"
    assert to_python(ox.Literal("v", datatype=ox.NamedNode("urn:custom"))) == "v"
    assert to_python(ox.Literal("1", datatype=XSD.int)) == 1 and to_python(ox.Literal("1", datatype=XSD.boolean)) is True
    assert to_python(ox.Literal("2026-01-02T03:04:05Z", datatype=XSD.dateTime)) == dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.timezone.utc)


def test_an_ill_formed_literal_and_a_non_literal_are_errors():
    with pytest.raises(ValueError, match="not a valid integer"):
        to_python(ox.Literal("abc", datatype=XSD.integer))
    with pytest.raises(ValueError, match="not a valid boolean"):
        to_python(ox.Literal("yes", datatype=XSD.boolean))
    with pytest.raises(TypeError):
        to_python(ox.NamedNode("urn:x"))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("<http://e/x>", ox.NamedNode("http://e/x")),
        ('"a"', ox.Literal("a")),
        ('"a"@en', ox.Literal("a", language="en")),
        ('"a"@ar--rtl', ox.Literal("a", language="ar", direction=ox.BaseDirection.RTL)),
        ('"1"^^<http://www.w3.org/2001/XMLSchema#integer>', ox.Literal("1", datatype=XSD.integer)),
        ("5", ox.Literal("5", datatype=XSD.integer)),
        ("true", ox.Literal("true", datatype=XSD.boolean)),
        ("_:b0", ox.BlankNode("b0")),
        ("<<( <urn:s> <urn:p> <urn:o> )>>", ox.Triple(ox.NamedNode("urn:s"), ox.NamedNode("urn:p"), ox.NamedNode("urn:o"))),
        ("  <http://e/x>  ", ox.NamedNode("http://e/x")),
    ],
)
def test_parse_term_reads_one_turtle_term(text, expected):
    assert parse_term(text) == expected


def test_parse_term_resolves_prefixed_names_only_with_prefixes():
    prefixes = {"ex": "http://e/", "xsd": "http://www.w3.org/2001/XMLSchema#"}
    assert parse_term("ex:alice", prefixes) == ox.NamedNode("http://e/alice")
    assert parse_term('"1"^^xsd:integer', prefixes) == ox.Literal("1", datatype=XSD.integer)
    with pytest.raises(ValueError, match="not a term"):
        parse_term("ex:alice")


@pytest.mark.parametrize("text", ["", "   ", "a b", "<urn:a> <urn:b>", '"x"@en, "y"', "<not an iri>", "{|", None])
def test_parse_term_refuses_what_is_not_exactly_one_term(text):
    with pytest.raises(ValueError):
        parse_term(text)
