"""Negative corpus (N in the plan's P/T/R/O/V/N): malformed input must raise ``ManchesterSyntaxError``,
never mis-parse silently.

The most dangerous failure for a parser is not rejecting good input but quietly accepting bad input and
dropping or reinterpreting part of the document. The ``truncation`` group targets exactly that.
"""

from __future__ import annotations

import pytest
from starlayer.graph.parsers.errors import ManchesterSyntaxError
from starlayer.graph.parsers.manchester_parser import parse_manchester

from .corpus import PRELUDE
from .known_failures import NEGATIVE_FAILURES

NEGATIVE: list[tuple[str, str]] = [
    # --- truncation: tokens the top-level loop does not recognise must not end the document silently
    ("trunc-stray-iri", "Class: A\n<http://example.org/o#stray>\nClass: B\n"),
    ("trunc-stray-string", 'Class: A\n"stray"\nClass: B\n'),
    ("trunc-stray-number", "Class: A\n42\nClass: B\n"),
    ("trunc-stray-punct", "Class: A\n)\nClass: B\n"),
    ("trunc-iri-after-ontology-iri-pair-then-junk", "Ontology: <http://e/o> <http://e/v> <http://e/x>\nClass: B\n"),
    ("trunc-lowercase-frame-keyword", "Class: A\nclass: B\n"),
    # --- structure
    ("unbalanced-open-paren", "Class: A\n  SubClassOf: (B and C\n"),
    ("unbalanced-close-paren", "Class: A\n  SubClassOf: B and C)\n"),
    ("missing-operand-after-and", "Class: A\n  SubClassOf: B and\n"),
    ("missing-operand-after-or", "Class: A\n  SubClassOf: B or\n"),
    ("missing-operand-after-not", "Class: A\n  SubClassOf: not\n"),
    ("missing-filler-after-some", "Class: A\n  SubClassOf: p some\n"),
    ("unknown-frame-keyword", "Foo: A\n"),
    ("frame-without-name", "Class:\n  SubClassOf: B\n"),
    ("clause-without-frame", "SubClassOf: B\n"),
    ("clause-not-allowed-in-frame", "Class: A\n  Domain: B\n"),
    ("object-clause-in-data-frame", "DataProperty: d\n  InverseOf: e\n"),
    ("unknown-characteristic", "ObjectProperty: p\n  Characteristics: Bogus\n"),
    ("data-property-transitive", "DataProperty: d\n  Characteristics: Transitive\n"),
    ("inverse-without-property", "Class: A\n  SubClassOf: inverse some B\n"),
    ("fact-without-value", "Individual: i\n  Facts: p\n"),
    ("empty-enumeration", "Class: A\n  EquivalentTo: {}\n"),
    ("empty-facet-list", "DataProperty: d\n  Range: xsd:integer[]\n"),
    ("trailing-comma-in-list", "Class: A\n  SubClassOf: B,\n"),
    ("misc-single-member", "DisjointClasses: A\n"),
    ("chain-single-property", "ObjectProperty: p\n  SubPropertyChain: q\n"),
    ("disjointunion-single-member", "Class: A\n  DisjointUnionOf: B\n"),
    # --- literals and numbers
    ("unterminated-string", 'Individual: i\n  Facts: d "oops\n'),
    ("cardinality-not-a-number", "Class: A\n  SubClassOf: p min x\n"),
    ("cardinality-negative", "Class: A\n  SubClassOf: p min -1\n"),
    ("cardinality-decimal", "Class: A\n  SubClassOf: p min 1.5\n"),
    ("unknown-facet", "DataProperty: d\n  Range: xsd:integer[approx 5]\n"),
    ("facet-without-value", "DataProperty: d\n  Range: xsd:integer[>=]\n"),
    ("language-tag-without-text", 'Individual: i\n  Facts: d "x"@\n'),
    # --- names and prefixes
    ("unknown-prefix", "Class: nope:A\n"),
    ("unterminated-iri", "Class: <http://example.org/o#A\n"),
    ("prefix-without-iri", "Prefix: ex:\nClass: A\n"),
    ("dead-token-inv", "Class: A\n  SubClassOf: inv p some B\n"),
]

# Which negatives need a declared-names prelude is irrelevant: they must fail before any semantics.
_WITH_PRELUDE = {"unknown-frame-keyword"}


@pytest.mark.manchester_conformance
@pytest.mark.parametrize(("case_id", "text"), NEGATIVE, ids=[c[0] for c in NEGATIVE])
def test_malformed_input_raises(case_id, text, request):
    if case_id in NEGATIVE_FAILURES:
        request.applymarker(pytest.mark.xfail(reason=NEGATIVE_FAILURES[case_id], strict=True))
    full = (PRELUDE + text) if case_id in _WITH_PRELUDE else _PREFIXES + text
    with pytest.raises(ManchesterSyntaxError):
        parse_manchester(full)


_PREFIXES = (
    "Prefix: : <http://example.org/o#>\n"
    "Prefix: xsd: <http://www.w3.org/2001/XMLSchema#>\n"
)
