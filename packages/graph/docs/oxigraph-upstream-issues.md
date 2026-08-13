# Oxigraph Upstream Issues

*Last reviewed: 2026-08-08*

Bugs found in [Oxigraph](https://github.com/oxigraph/oxigraph) (the native `rdf-1.2` backend's primary SPARQL-star HTTP engine option - see `starlayergraph/backends/native.py`'s own module docstring: this repo does zero query/data rewriting for either native-backend engine, so what the engine accepts and returns is exactly what a client sees) while cross-checking findings from the downstream `starsparql` project's adversarial round-trip test battery (`tests/test_adversarial_roundtrip.py`, built specifically to try to falsify that project's "round-trip preserves semantics" claim). Confirmed against Oxigraph `0.5.9`.

Same entry structure/conventions as `docs/rdflib-upstream-issues.md` (see that file's "How To Use" section) - `##`/`###` headings pastable directly into a GitHub issue.

## Status Summary

| # | Issue | Reporting upstream? |
| --- | --- | --- |
| 1 | ~~Nested-subject triple term pattern returns `HTTP 500` even when matching data exists~~ | **No — retracted, see below** |

No issues currently pending upstream report. One investigated and retracted (see Issue 1) — not a bug in Oxigraph.

## Entries

| # | Title | Found | Status |
| --- | --- | --- | --- |
| 1 | Nested-subject triple term pattern returns `HTTP 500` | 2026-08-08 | Retracted 2026-08-08 — invalid input, not a bug |

## Issue 1 - RETRACTED: "Nested-subject triple term pattern returns `HTTP 500`" (found 2026-08-08, retracted same day)

**This is not an Oxigraph bug.** Recorded here, in full, specifically so this mistake doesn't get rediscovered and re-written in a future session — the reasoning that first made it look like a real bug is exactly the trap worth documenting.

### What was originally claimed

A query pattern with a triple term nested inside another triple term's *subject* position -

```sparql
PREFIX : <http://example/>
SELECT * WHERE { ?s ?p <<( <<( :a :b :c )>> :d :e )>> . }
```

- returns `HTTP 500` (`The SPARQL dataset returned a triple term that is not a valid RDF 1.2 term`) from Oxigraph, and was believed to be valid RDF 1.2 syntax that Oxigraph was incorrectly rejecting.

### Why it looked valid (and was believed distinct from an earlier, correctly-declined Oxigraph finding)

The downstream `starsparql` project's own `CLAUDE.md` (finding #20) documents building a grammar extension that deliberately *permits* a triple term to nest in subject position when used in ordinary query-pattern position (as opposed to `BIND`/`FILTER`/`VALUES` expression position) - and cites the official W3C SPARQL 1.2 test suite's own `PositiveSyntaxTest` fixtures (`syntax-triple-terms-positive/compound-tripleterm-subject.rq`, `nested-tripleterm-02.rq`) as confirming this is legal syntax. Those fixtures do contain exactly this shape (`<<( <<(:x ?R :z)>> :p <<(:a :b [])>> )>>`) and are indeed labeled `PositiveSyntaxTest`. This, plus data appearing to load successfully for the same shape via `StarLayerGraph.parse()`, looked like enough to distinguish this from an earlier, similar-looking Oxigraph finding that had been investigated and correctly declined as "a query that can never match real data either way" (see the note in `docs/fuseki-upstream-issues.md`'s Issue 1 "Status" section).

### Why that reasoning was wrong

Went to the actual RDF 1.2 Turtle spec grammar directly (`https://www.w3.org/TR/rdf12-turtle/#grammar-production-tripleTerm`) rather than trusting either project's notes:

```
tripleTerm ::= '<<(' ttSubject verb ttObject ')>>'
ttSubject  ::= iri | BlankNode
ttObject   ::= iri | BlankNode | literal | tripleTerm
```

`ttSubject` has no `tripleTerm` alternative at all - a triple term's subject can only ever be an IRI or blank node, **unconditionally**, with no carve-out for query-pattern position vs. expression position. `ttObject` explicitly does allow `tripleTerm` - that asymmetry is stated flatly in the grammar itself.

**The error in the original reasoning: conflating "SPARQL's grammar successfully parses this text" with "this represents a valid RDF 1.2 term."** A `PositiveSyntaxTest` most plausibly asserts only the former. SPARQL's own pattern grammar is very likely more permissive than the strict `ttSubject` data-model rule (a context-free grammar often can't cheaply enforce a position-dependent restriction like "only in this specific nesting position," so query-pattern parsing may accept a broader shape than what can ever correspond to real, valid data) - while a pattern using this shape can still never match any actual valid RDF 1.2 data, since no such data could ever exist. That is exactly the reasoning the earlier, correctly-declined Oxigraph finding used. This turned out to be the same case, not a different one.

The "data loads successfully" claim doesn't hold up either: a direct, careful standalone reproduction of `StarLayerGraph.parse()` on this exact data shape raised `TurtleSyntaxError` ("nesting a triple term is only legal in object position"), consistent with the spec. The one run where it appeared to succeed (inside the full `starsparql` pytest suite) is the anomaly that would need its own explanation, not evidence the data is valid - not pursued further here since it doesn't change the conclusion.

### Actual likely explanation for Oxigraph's behavior

Oxigraph is very plausibly just correctly rejecting a query pattern that can never match any valid RDF 1.2 data, the same as the earlier declined finding. The `HTTP 500` (rather than a `400` or a clean empty result) may still be a legitimate, minor API-design complaint, but that's the same "status-code/API-taste question, not a correctness bug" framing the earlier finding already used - not worth a separate report.

### Real, separate finding this surfaced

The downstream `starsparql` project's own `grammar12.py` had a genuine bug of its own: it was deliberately widened (finding #20) to *accept* nested-subject triple terms in query-pattern position, which the real RDF 1.2 grammar does not permit at all. Confirmed as a real gap specifically because Oxigraph rejects this shape while that project's own native execution path did not - fixed in that project directly (a hard validation "blocker" added at triple-term construction time, rejecting a nested triple term in subject/predicate position unconditionally), not here. This file is Oxigraph-specific and has nothing further to report as a result of this investigation - no issue currently stands against Oxigraph.
