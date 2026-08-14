# W3C SHACL 1.2 Test Suite - Issues to Report

*Last reviewed: 2026-08-01*

Issues found in the official SHACL 1.2 test suite (https://github.com/w3c/data-shapes, `gh-pages` branch, `shacl12-test-suite/` directory - vendored into this repo at `tests/vendor/shacl12-test-suite/`, see that directory's own `VENDORED_FROM.md` for the exact pinned commit) while integrating it against `starshacl` (`docs/w3c-shacl12-test-suite-plan.md`). Unlike `docs/pyshacl-upstream-issues.md` (bugs in the `pyshacl` *library*) and `starlayergraph`'s own `docs/rdflib-upstream-issues.md` (bugs in the `rdflib` *library*), this file tracks issues in the *test suite itself* - a fixture whose own expected result doesn't follow from the specification it's meant to test.

## How To Use

Same convention as the two library-issue documents: each entry's `##`/`###` structure can be pasted directly into a GitHub issue against `w3c/data-shapes` with minimal editing (title = the `##` heading; body = `### Description` through `### Suggested fix`; `### Status` is doc-only tracking).

## Status Summary

| # | Fixture | Reporting upstream? |
| --- | --- | --- |
| 1 | `node-expr/shnex-sparql/seconds.ttl` (`seconds-example`) expects a zero-padded `xsd:decimal` lexical form with no basis in `SECONDS()`'s own specification | **Yes** (not yet filed) |

## Issue 1 - `seconds-example`'s expected result requires zero-padding `SECONDS()`'s numeric output, which nothing in SPARQL/XPath's specification requires (found 2026-08-01)

**Fixture:** `tests/node-expr/shnex-sparql/seconds.ttl` (`<seconds-example>`, `sht:EvalNodeExpr`)

### Description

The fixture:

```turtle
<seconds-example>
  rdf:type sht:EvalNodeExpr ;
  rdfs:label "Test of a sparql:seconds expression based on the shnex-sparql:example" ;
  mf:action [
    sht:nodeExpr [
      sparql:seconds ( "2023-12-25T10:30:00"^^xsd:dateTime ) ;
    ] ;
  ] ;
  mf:result ( "00"^^xsd:decimal ) ;
  mf:status sht:approved ;
.
```

`sparql:seconds` wraps SPARQL 1.1's `SECONDS()` function, specified (via XPath and XQuery Functions and Operators' `fn:seconds-from-dateTime`) to return the seconds component of a `dateTime` as an `xs:decimal` *numeric value* - not a substring of the input's own lexical form. Nothing in that specification requires, or even suggests, that the result be zero-padded to two digits when displayed. The input dateTime here happens to write its seconds component as `"00"` (two characters, matching common ISO 8601 style), and the fixture's expected result appears to have been derived by echoing that substring back rather than by computing the actual specified numeric value's own natural lexical form.

### Expected behavior (per spec)

`SECONDS("2023-12-25T10:30:00"^^xsd:dateTime)` should return the `xs:decimal` value zero. The specification does not mandate a specific *lexical form* for that value beyond what `xs:decimal`'s own value space implies - `"0"`, `"0.0"` (XSD 1.1's actual canonical form - a decimal point with a digit on each side is required), or any other lexically-valid-but-value-equal spelling would all correctly represent "zero seconds." Nothing in the spec justifies specifically `"00"`.

### Actual behavior (fixture's expectation)

`mf:result ( "00"^^xsd:decimal )` - checked against three independent SPARQL engines evaluating the identical function call:

| Engine | Result |
| --- | --- |
| rdflib 7.6.0 (`Builtin_SECONDS`) | `"0"^^xsd:decimal` |
| Apache Jena ARQ (via Fuseki 5.5+) | `"0"^^xsd:decimal` |
| Oxigraph (native SPARQL engine) | `"0"^^xsd:decimal` |

All three independently-implemented, unrelated engines agree with each other and disagree with the fixture. None produces `"00"`, and none produces the true XSD canonical form `"0.0"` either - all three treat `SECONDS()`'s result as an ordinary computed numeric value with no special zero-padding, which is exactly what the specification describes.

### Suspected root cause

The fixture's expected result was very likely authored by taking the seconds substring directly from the input `dateTime`'s own lexical form (`"...T10:30:00"` → `"00"`) rather than by computing what `SECONDS()`'s own specified semantics (a numeric decimal value) actually produce. This conflates "the seconds field as written in the source document" with "the numeric value SECONDS() returns" - two different things whenever the input dateTime isn't already zero-padded to exactly two seconds digits (or has a fractional-seconds component, which `SECONDS()` is specified to include but a fixed two-character substring extraction cannot represent).

### Impact

Any conformant `sparql:seconds`/`SECONDS()` implementation that correctly follows the specification (returns the numeric value with an ordinary, unpadded lexical form) fails this specific fixture - not because the implementation is wrong, but because the fixture's own expected value doesn't follow from the specification it's meant to test. Confirmed via three independent engines producing the identical (and spec-consistent) "wrong" answer.

### Suggested fix

Change `mf:result` from `( "00"^^xsd:decimal )` to `( "0"^^xsd:decimal )` (or, if the intent is specifically to test that RDF 1.2's literal term-equality is honored, `( 0 )` / an explicit statement that value-equality rather than exact lexical-form equality is what's being checked for this particular fixture - unlike, say, `distinct-termEquality`/`remove-list-from-list` elsewhere in this same test suite, where exact lexical-form preservation *is* the specific, deliberate thing under test and the input document itself already writes the non-canonical form being checked for).

### Status

Found 2026-08-01 while triaging `starshacl`'s remaining W3C SHACL 1.2 test suite failures (`starShacl`'s `tests/w3c_shacl12/known_failures.py`). Reporting upstream planned, not yet filed against `w3c/data-shapes`. Left as a permanent, `strict=True` xfail in `starshacl`'s own test suite in the meantime (`tests/w3c_shacl12/known_failures.py`'s `seconds-example` entry) - not patched around, since patching any of `starshacl`'s three constituent SPARQL engines (rdflib, and by extension Fuseki/Oxigraph parity) to zero-pad `SECONDS()`'s output would make their behavior *less* spec-compliant, not more.
