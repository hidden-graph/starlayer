# W3C SPARQL 1.2 Test Suite - Issues to Report

*Last reviewed: 2026-08-15*

Issues found in the official SPARQL 1.2 test suite (https://github.com/w3c/rdf-tests, `main` branch, `sparql/sparql12/` directory) while validating `starsparql`'s own RDF 1.2 triple-term handling against it. Unlike `packages/graph/docs/rdflib-upstream-issues.md`/`oxigraph-upstream-issues.md`/`fuseki-upstream-issues.md` (bugs in a SPARQL *engine*), this file tracks issues in the *test suite itself* - a fixture whose own expected result (or, here, its own maturity-classification label) doesn't follow from the specification it's meant to test. Same convention as `packages/shacl/docs/w3c-shacl12-test-suite-issues.md` (a sibling package's identically-purposed file) - each entry's `##`/`###` structure can be pasted directly into a GitHub issue against `w3c/rdf-tests` with minimal editing.

## How To Use

Title = the `##` heading; body = `### Description` through `### Suggested fix`; `### Status` is doc-only tracking, not part of the issue body.

## Status Summary

| # | Fixtures | Reporting upstream? |
| --- | --- | --- |
| 1 | `syntax-triple-terms-positive/{basic-tripleterm-01,basic-tripleterm-03,bnode-tripleterm-01,bnode-tripleterm-02,bnode-tripleterm-03,compound-tripleterm-subject,nested-tripleterm-02}` - 7 `mf:PositiveSyntaxTest`s whose query text constructs an explicit triple term directly as an ordinary pattern's *subject*, which RDF 1.2 Concepts' own triple-formation rules never permit | **Yes** (not yet filed) |

## Issue 1 - Seven `PositiveSyntaxTest` fixtures construct a triple term directly as a pattern's subject, which RDF 1.2 Concepts never permits (found 2026-08-15)

**Fixtures:** all under `sparql/sparql12/syntax-triple-terms-positive/`, all `rdf:type mf:PositiveSyntaxTest`:

- `basic-tripleterm-01.rq` - `<<( :a :b :c )>> :p1 :o1.`
- `basic-tripleterm-03.rq` - `<<( ?s ?p ?o )>> ?Y ?Z .`
- `bnode-tripleterm-01.rq` - `<<(_:a :p :o )>> :q 456 .`
- `bnode-tripleterm-02.rq` - `<<(:s :p _:a )>> :q 456 .`
- `bnode-tripleterm-03.rq` - `<<([] :p [] )>> :q :z .`
- `compound-tripleterm-subject.rq` - first triple: `<<(:x ?R :z )>> :p <<(:a :b ?C )>> .` (the other two triples in this fixture separately, and correctly, also test the different, already-known `compound`-nesting case - see below)
- `nested-tripleterm-02.rq` - constructs the same subject-position shape as part of a larger nested expression

### Description

Every fixture above constructs an explicit, parenthesized triple term (`<<( s p o )>>`) directly as the **subject** of an ordinary triple pattern - not nested inside another triple term (that is a separate, already-understood illegal case these same two files also correctly test as `NegativeSyntaxTest`s / via `compound-tripleterm-subject`'s *other* lines), just an everyday `<<( s p o )>> :pred :obj .` statement. All seven are labeled `mf:PositiveSyntaxTest`.

Per RDF 1.2 Concepts' own normative triple-formation rules (https://www.w3.org/TR/rdf12-concepts/#section-triple-terms, quoted directly):

> "If s is an IRI or a blank node, p is an IRI, and o is an RDF triple, then (s, p, o) is an RDF triple."

That is the *only* rule admitting a triple term anywhere in a triple, and it only ever permits one as `o` (the object). Every triple-formation rule - this one and the ordinary one - requires `s` to be an IRI or a blank node, full stop. A triple term can never legally be a subject.

### Expected behavior (per spec)

None of the seven fixtures above can ever represent valid RDF 1.2 data - no conformant implementation validating RDF 1.2 semantics (not just SPARQL's surface grammar) should accept the graph they'd construct, since no such graph could ever exist.

The suite itself demonstrates awareness of exactly this distinction elsewhere in the *same* `syntax-triple-terms-positive/` manifest:

- **`subject-tripleterm.rq`** (also `PositiveSyntaxTest`) deliberately tests the *legal* alternative to putting something triple-term-shaped in subject position: the RDF 1.2 **reifier shorthand** (`<<s p o>>`/`<<s p o ~ r>>`, no parens). That shorthand desugars to an ordinary triple where the *reifier* (an auto-generated or explicit blank node/IRI) substitutes into the subject position, with the actual triple term only ever appearing as the object of a separate `rdf:reifies` triple - exactly the shape RDF 1.2 Concepts permits. `subject-tripleterm.rq`'s own text uses this shorthand form specifically, confirming the suite's authors know the distinction and test the legal side of it.
- **`compound-tripleterm.rq`** (also `PositiveSyntaxTest`, no `-subject` suffix) is the same general shape as `compound-tripleterm-subject.rq` but keeps every triple term strictly in object position - the deliberate "control" fixture demonstrating the same construct done correctly.

This makes the seven fixtures above look like the one place this suite's own subject/object distinction wasn't carried through consistently, not a deliberate test of something legal.

### Actual behavior (fixture's expectation)

`mf:PositiveSyntaxTest` asserts the query text should parse without error. A conformant implementation enforcing RDF 1.2 Concepts' own triple-formation rules at the semantic level (not just SPARQL's surface grammar, which - as `starsparql`'s own investigation confirmed - can parse this text without difficulty, since the *grammar* alone can't distinguish "syntactically well-formed" from "semantically valid RDF 1.2") will reject all seven, the same way a live Oxigraph instance was independently confirmed (in the course of this same investigation - see `starsparql/triple_term.py`'s own `InvalidTripleTermError` docstring) to reject the narrower nested-triple-term-in-subject-position case with `HTTP 500`.

### Suspected root cause

Likely an oversight carried from the original SPARQL 1.2 syntax test authoring: these fixtures appear to have been written to exercise "does a triple term parse in *every* term position" without separately checking each position's own RDF 1.2 data-validity rules - `subject-tripleterm.rq`/`compound-tripleterm.rq` show that check *was* done carefully elsewhere in the same manifest, just not consistently across all cases using the raw `<<( )>>` form specifically in subject position.

### Impact

Any conformant SPARQL 1.2 implementation that validates RDF 1.2 semantics (not just SPARQL surface grammar) fails all seven fixtures - not because the implementation is wrong, but because the fixtures' own expected classification (`PositiveSyntaxTest`) doesn't follow from RDF 1.2 Concepts' own rules. Confirmed via independent evidence: a live Oxigraph instance already rejects the narrower nested-subject variant of this same underlying issue with `HTTP 500` (see `starsparql/triple_term.py`'s `InvalidTripleTermError` docstring for the investigation), and `starsparql` itself previously (mistakenly) treated these very fixtures as evidence the shape should be accepted before this issue was found - a real, demonstrated risk of the current labeling propagating the same mistake to other implementations that consult this suite.

### Suggested fix

Either:

1. Reclassify all seven as `mf:NegativeSyntaxTest`s, if the intent is to test that this exact shape is rejected by an RDF-1.2-semantics-aware implementation, **or**
2. If the intent is genuinely to test only SPARQL-grammar-level parseability independent of RDF 1.2 data-validity (a legitimate, separate concern from what `NegativeSyntaxTest`/`PositiveSyntaxTest` usually implies) - state that scope explicitly in each fixture's own `rdfs:label`/a comment, since as currently labeled it reads as an ordinary data-validity claim, not a narrower grammar-only one.

Either way, `subject-tripleterm.rq` (in the same manifest) is a ready-made model for how to test the *legal* version of a similar-looking subject-position construct, so the suite ends up with clear, paired coverage of both the legal (reifier-shorthand) and illegal (raw triple-term) subject-position forms - the same pairing it already has for nesting depth via `compound-tripleterm.rq`/`compound-tripleterm-subject.rq`.

### Status

Found 2026-08-15 during a `starshacl`/`starsparql` shapes-completeness audit session, via a user directly challenging this project's own prior claim ("a triple term as the subject of a regular triple pattern is completely legal") with a specific, correct counter-claim grounded in the spec. That challenge led to fetching RDF 1.2 Concepts' actual normative text, confirming the counter-claim, and finding this project's own `starsparql/triple_term.py` had the identical gap - fixed in the same session (`_reject_triple_term_pattern_subjects`, a post-translation hard backstop covering both the SPARQL-text-parsing path and the RDF-decode path independently). Fixing `starsparql`'s own validator is what surfaced the full scope of affected W3C fixtures (initially two were known; a systematic re-run against the whole `syntax-triple-terms-positive/` manifest after the fix found five more). Not yet filed upstream against `w3c/rdf-tests`.
