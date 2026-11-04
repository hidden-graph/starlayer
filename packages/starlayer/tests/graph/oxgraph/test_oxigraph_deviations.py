"""Where Oxigraph (pyoxigraph 0.5.13) departs from SPARQL 1.1 / XPath, seen through ``OxGraph`` / ``OxDataset``.

Each test states the outcome the specification gives and is a strict expected failure: it fails today because Oxigraph does
something else, and it XPASSes (a failure, ``strict=True``) when a release fixes it, which is the signal to delete the xfail and
revisit the row in ``docs/working/non-spec-behaviour.md``. The wrapper adds no client-side patch. The write-ups, with the bare
pyoxigraph reproductions, are sections 6 to 9 of ``docs/working/oxigraph-upstream-issues.md``. Nothing is posted anywhere.

A test lists every deviation it knows in its failure message; a release that fixes only some keeps the test an expected
failure, so the document says which cases a release must fix before the xfail goes.
"""

from __future__ import annotations

import pytest
from starlayer.graph.oxgraph import OxDataset, OxGraph

P = "PREFIX : <urn:> "


def _value(g: OxGraph, expr: str):
    """The value of ``expr`` (a SPARQL expression) as ``str``, or ``None`` when it is an error (unbound)."""
    (row,) = list(g.query(f"SELECT ({expr} AS ?r) {{}}"))
    term = row["r"]
    return None if term is None else term.value


@pytest.mark.xfail(strict=True, reason="Oxigraph REPLACE/REGEX do not follow the XPath rules (oxigraph-upstream-issues.md section 6)")
def test_replace_and_regex_follow_xpath():
    g = OxGraph()
    # (expression, what fn:replace / fn:matches give: None is an error, which SPARQL leaves unbound)
    cases = [
        ("REPLACE('abc', 'x*', '-')", None),  # a pattern that matches the empty string: FORX0003
        ("REPLACE('abc', '', '-')", None),  # same
        ("REPLACE('abc', 'b', '$')", None),  # '$' not followed by a digit: FORX0004
        (r"REPLACE('abc', 'b', '\\x')", None),  # '\' not followed by '\' or '$': FORX0004
        (r"REPLACE('abc', 'b', '\\$')", "a$c"),  # '\$' is a literal '$'
        (r"REGEX('a b', '\\bb')", None),  # \b is not in the XSD regular-expression dialect: FORX0002
        (r"REGEX('abc', '\\p{IsBasicLatin}+')", "true"),  # block escapes are in the dialect
    ]
    wrong = {expr: (_value(g, expr), want) for expr, want in cases if _value(g, expr) != want}
    assert not wrong, f"(got, XPath gives) per expression: {wrong}"


@pytest.mark.xfail(strict=True, reason="Oxigraph does not order xsd:boolean with < > <= >= (oxigraph-upstream-issues.md section 7)")
def test_boolean_ordering_false_before_true():
    g = OxGraph()
    cases = {"false < true": "true", "true > false": "true", "false <= true": "true", "true >= false": "true",
             "true < false": "false", "true < true": "false"}  # SPARQL 1.1 section 17.3: op:boolean-less-than / -greater-than
    wrong = {expr: (_value(g, expr), want) for expr, want in cases.items() if _value(g, expr) != want}
    assert not wrong, f"(got, spec gives) per expression: {wrong}"


@pytest.mark.xfail(strict=True, reason="Oxigraph's !(:p|^:q) is a set; the spec translation is a bag (oxigraph-upstream-issues.md section 8)")
def test_negated_property_set_with_both_directions_is_a_bag():
    g = OxGraph()
    g.parse(data="@prefix : <urn:> . :a :p :b . :b :q :c . :c :p :d . :d :p :a . :x :p :b . :a :r :b .", format="turtle")

    def rows(pattern: str) -> list[tuple[str, str]]:
        return sorted((r["s"].value, r["o"].value) for r in g.query(f"{P}SELECT ?s ?o {{ {pattern} }}"))

    # SPARQL 1.1 section 18.2 (translation of negated property sets): !(:p|^:q) is !(:p) UNION ^!(:q), a bag
    assert rows("?s !(:p|^:q) ?o") == rows("{ ?s !(:p) ?o } UNION { ?s ^!(:q) ?o }")


@pytest.mark.xfail(strict=True, reason="Oxigraph COPY / ADD from an absent graph do not raise without SILENT (oxigraph-upstream-issues.md section 9)")
def test_copy_and_add_of_an_absent_graph_fail_without_silent():
    silent_ones = []
    for op in ("COPY", "ADD"):
        ds = OxDataset()
        ds.update(f"{P}INSERT DATA {{ GRAPH :g1 {{ :a :p :b }} }}")
        try:
            ds.update(f"{P}{op} :nope TO :g1")
        except Exception:  # noqa: BLE001  the type is not the point, only that it fails like MOVE, CLEAR and DROP do
            continue
        silent_ones.append(op)
    assert not silent_ones, f"no error from {silent_ones}, as there is for MOVE / CLEAR / DROP of an absent graph"
