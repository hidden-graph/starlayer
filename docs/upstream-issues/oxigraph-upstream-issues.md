# Oxigraph Upstream Issues

*Last reviewed: 2026-08-08*

Bugs found in [Oxigraph](https://github.com/oxigraph/oxigraph) (the native `rdf-1.2` backend's primary SPARQL-star HTTP engine option - see `starlayergraph/backends/native.py`'s own module docstring: this repo does zero query/data rewriting for either native-backend engine, so what the engine accepts and returns is exactly what a client sees) while cross-checking findings from the downstream `starsparql` project's adversarial round-trip test battery (`tests/test_adversarial_roundtrip.py`, built specifically to try to falsify that project's "round-trip preserves semantics" claim). Confirmed against Oxigraph `0.5.9`.

Same entry structure/conventions as `rdflib-upstream-issues.md` (see that file's "How To Use" section) - `##`/`###` headings pastable directly into a GitHub issue.

## Status Summary

| # | Issue | Reporting upstream? |
| --- | --- | --- |
| 1 | ~~Nested-subject triple term pattern returns `HTTP 500` even when matching data exists~~ | **No — retracted, see below** |
| 2 | SPARQL `=` panics the whole engine on *any* `dirLangString`-typed term (crashes the process, not a catchable error) | **Yes — pending** |

One issue pending upstream report (Issue 2). One investigated and retracted (see Issue 1) — not a bug in Oxigraph.

## Entries

| # | Title | Found | Status |
| --- | --- | --- | --- |
| 1 | Nested-subject triple term pattern returns `HTTP 500` | 2026-08-08 | Retracted 2026-08-08 — invalid input, not a bug |
| 2 | SPARQL `=` panics on any `dirLangString` term | 2026-10-16 | Confirmed live, pending upstream report |

## Issue 2 - SPARQL `=` panics the engine on *any* `rdf:dirLangString`-typed term (crashes the whole process, not a catchable SPARQL error) (found 2026-10-16, scope corrected same day)

A runnable version of everything in this entry - both the working baselines and the crash cases, with real captured output for each - lives at `oxigraph_dirlangstring_crash_repro.ipynb` (same folder).

### How this was found, and how the scope was narrowed

First found while answering a direct question - "have we run all the tests with an oxigraph embedded?" - by forcing `starlayer.graph`'s own `set_default_representation(embedded_oxigraph_store)` as the global default for every bare `StarLayerGraph()`/`StarLayerDataset()` construction across the entire test suite, then running the full `pytest` suite. The suite aborted entirely (`Fatal Python error: Aborted`, `SIGABRT`) partway through, at `tests/graph/unit/test_dirlangstring.py::test_strlangdir_constructs_matching_value` - a query filtering on `?t = STRLANGDIR(...)`.

**The initial write-up of this issue wrongly scoped it to `STRLANGDIR()` specifically** - corrected the same day by testing several narrower variants directly against bare `pyoxigraph`, one at a time, rather than assuming the first repro's own shape was the real trigger:

| Scenario | Crashes? |
| --- | --- |
| Construct a `dirLangString` via `STRLANGDIR()`, no comparison | No |
| Read a stored `dirLangString` value, no comparison | No |
| `sameTerm(?t, ?t)` on a stored `dirLangString` value | No |
| `FILTER(?t = ?t)` - self-equality on one stored value | **Crashes** |
| `FILTER(?t1 = ?t2)` - two independently stored values | **Crashes** |
| `STRLANGDIR(...) = STRLANGDIR(...)` - no stored data at all | **Crashes** |
| A stored value `=` a `STRLANGDIR()`-constructed one (the original repro) | **Crashes** |

**The real trigger is SPARQL `=` (value equality) applied to a `dirLangString` term, full stop** - unconditionally, regardless of whether either side is stored data or a `STRLANGDIR()` construction, and even for the most trivial case (a value compared against itself). `sameTerm()` (exact RDF-term equality, a different SPARQL operator with no per-datatype value-equality dispatch) is unaffected.

### Repro

```python
import pyoxigraph as ox
store = ox.Store()
store.update('INSERT DATA { <http://example.org/a> <http://example.org/title> "hi"@en--ltr }')
list(store.query('SELECT ?s WHERE { ?s <http://example.org/title> ?t . FILTER(?t = ?t) }'))
```

No `STRLANGDIR()`, no StarLayer code, no second value to compare against - the minimal case is a single stored `dirLangString` value compared against itself.

### What happens

A hard process abort, not a Python exception - cannot be caught with `try`/`except`, and takes down the entire process (a whole `pytest` run, in the case that first surfaced this):

```
thread '<unnamed>' panicked at lib/spareval/src/dataset.rs:350:27:
internal error: entered unreachable code
```

### Confirmed against both the embedded binding and the standalone server - same bug, two different released versions

- **Embedded**: `pyoxigraph` `0.5.11` (the version this project's `oxigraph-embedded` extra currently pins `>=0.5` to) - the exact panic above, via the Python binding directly.
- **HTTP/remote**: the project's own local test server, `ghcr.io/oxigraph/oxigraph` (image pulled 2026-06-18, server reports itself as `oxigraph 0.5.9`) - the identical query, sent as an HTTP `POST` to `/query` against a graph-scoped version of the same data, crashed the **server process itself** (confirmed via `docker ps` showing `Exited (133)` - `133` = `128 + SIGABRT`, the same signal as the embedded case). The client sees `requests.exceptions.ConnectionError` / `RemoteDisconnected` with no SPARQL-level error response at all, since the server died before it could write one. Recovered with a plain `docker restart`.

Same root defect in both: an `unreachable!()` in `spareval`'s per-datatype value-equality dispatch (`op:RDFterm-equal`), missing a case for `rdf:dirLangString` - present across at least two released versions (`0.5.9` through `0.5.11`), not something fixed in between.

### Exact root cause, found by reading the live upstream source directly (still present on `main`, not yet fixed in unreleased code either)

`lib/spareval/src/dataset.rs`'s `impl PartialEq for ExpressionTerm` has an explicit match arm for every one of the enum's ~20 variants *except* `DirLangStringLiteral` - it falls through to the catch-all `(_, _) => unreachable!()` at the end of the match. Confirmed this is a narrow, surgical omission rather than a deeper design gap: the sibling `impl Hash for ExpressionTerm`, a few lines below in the same file, *does* correctly handle `DirLangStringLiteral` (`(value, language, direction).hash(state)`) - the variant was wired into `Hash` but the matching `PartialEq` arm was never added alongside it. A one-line fix:

```rust
(
    Self::DirLangStringLiteral { value: lv, language: ll, direction: ld },
    Self::DirLangStringLiteral { value: rv, language: rl, direction: rd },
) => lv == rv && ll == rl && ld == rd,
```

Checked directly against `main` via the GitHub API (not just the two released versions already tested) - the gap is still there in current unreleased development, not something already fixed and awaiting a release.

### Not yet reported upstream - checked via `gh search issues`/`gh search prs` against `oxigraph/oxigraph`

Searched for `dirLangString`, `DirLangStringLiteral`, `BaseDirection`, `STRLANGDIR`, `spareval` + `dirLang`, `entered unreachable code`, `RDFterm-equal`, and `direction literal`, across both issues and PRs, open and closed. No existing report matches - this appears to be a genuinely new finding, not a duplicate.

### Confirmed as Oxigraph-specific, not a spec ambiguity: Apache Jena Fuseki handles every scenario correctly

Ran the identical scenario table against this project's own local Fuseki test server (`atomgraph/fuseki:6.1.0`, Apache Jena 6.1.0/ARQ) - both via raw HTTP (SPARQL 1.1 Protocol, matching how Oxigraph's own HTTP server was tested above) and via `StarLayerGraph(store=SPARQLUpdateStore(...), backend="rdf-1.2")` (this project's own native-representation code path, not bypassing it). Every single case - construction, plain read, `sameTerm()`, self-equality (`?t = ?t`), and `?t = STRLANGDIR(...)` - returned a correct `200`/`204` result with no crash, through either access path, with the server staying healthy throughout (confirmed via `/$/ping` before and after). Rules out "the SPARQL 1.2 spec is ambiguous here and both engines reasonably disagree" - Jena/ARQ implements `dirLangString` value-equality correctly; this is specifically a gap in Oxigraph's `spareval` crate.

### Impact on this project

This is the reason `starlayer.graph`'s own test suite does **not** run with `set_default_representation(embedded_oxigraph_store)` configured globally - `tests/graph/unit/test_dirlangstring.py`'s own `TestSparqlFunctions` class exercises exactly this comparison, and does so correctly (and safely) today only because the suite's default representation remains the non-native, tt:HASH-encoded `rdf-1.1` backend (plain `rdflib.Memory` store, no Oxigraph involved at all) unless a test opts into a native/Oxigraph-backed graph explicitly. A caller who *does* configure the embedded-Oxigraph global default and then relies on `=`-based equality anywhere over `dirLangString` data (not just via `STRLANGDIR()`) will hit this crash today - not yet worked around or guarded against in this project's own code, since there is no safe way to catch a process abort from Python; `sameTerm()` is a viable workaround where exact-term rather than value equality is acceptable. Not otherwise designed around yet - flagged here as a known, confirmed limitation pending upstream resolution.

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

The downstream `starsparql` project's own `CLAUDE.md` (finding #20) documents building a grammar extension that deliberately *permits* a triple term to nest in subject position when used in ordinary query-pattern position (as opposed to `BIND`/`FILTER`/`VALUES` expression position) - and cites the official W3C SPARQL 1.2 test suite's own `PositiveSyntaxTest` fixtures (`syntax-triple-terms-positive/compound-tripleterm-subject.rq`, `nested-tripleterm-02.rq`) as confirming this is legal syntax. Those fixtures do contain exactly this shape (`<<( <<(:x ?R :z)>> :p <<(:a :b [])>> )>>`) and are indeed labeled `PositiveSyntaxTest`. This, plus data appearing to load successfully for the same shape via `StarLayerGraph.parse()`, looked like enough to distinguish this from an earlier, similar-looking Oxigraph finding that had been investigated and correctly declined as "a query that can never match real data either way" (see the note in `fuseki-upstream-issues.md`'s Issue 1 "Status" section).

### Why that reasoning was wrong

Went to the actual RDF 1.2 Turtle spec grammar directly (`https://www.w3.org/TR/rdf12-turtle/#grammar-production-tripleTerm`) rather than trusting either project's notes:

```
tripleTerm ::= '<<(' ttSubject verb ttObject ')>>'
ttSubject  ::= iri | BlankNode
ttObject   ::= iri | BlankNode | literal | tripleTerm
```

`ttSubject` has no `tripleTerm` alternative at all - a triple term's subject can only ever be an IRI or blank node, **unconditionally**, with no carve-out for query-pattern position vs. expression position. `ttObject` explicitly does allow `tripleTerm` - that asymmetry is stated flatly in the grammar itself.

**The error in the original reasoning: conflating "SPARQL's grammar successfully parses this text" with "this represents a valid RDF 1.2 term."** A `PositiveSyntaxTest` most plausibly asserts only the former. SPARQL's own pattern grammar is very likely more permissive than the strict `ttSubject` data-model rule (a context-free grammar often can't cheaply enforce a position-dependent restriction like "only in this specific nesting position," so query-pattern parsing may accept a broader shape than what can ever correspond to real, valid data) - while a pattern using this shape can still never match any actual valid RDF 1.2 data, since no such data could ever exist. That is exactly the reasoning the earlier, correctly-declined Oxigraph finding used. This turned out to be the same case, not a different one.

The "data loads successfully" claim doesn't hold up either: a direct, careful standalone reproduction of `StarLayerGraph.parse()` on this exact data shape raised `Turtle12SyntaxError` ("nesting a triple term is only legal in object position"), consistent with the spec. The one run where it appeared to succeed (inside the full `starsparql` pytest suite) is the anomaly that would need its own explanation, not evidence the data is valid - not pursued further here since it doesn't change the conclusion.

### Actual likely explanation for Oxigraph's behavior

Oxigraph is very plausibly just correctly rejecting a query pattern that can never match any valid RDF 1.2 data, the same as the earlier declined finding. The `HTTP 500` (rather than a `400` or a clean empty result) may still be a legitimate, minor API-design complaint, but that's the same "status-code/API-taste question, not a correctness bug" framing the earlier finding already used - not worth a separate report.

### Real, separate finding this surfaced

The downstream `starsparql` project's own `grammar12.py` had a genuine bug of its own: it was deliberately widened (finding #20) to *accept* nested-subject triple terms in query-pattern position, which the real RDF 1.2 grammar does not permit at all. Confirmed as a real gap specifically because Oxigraph rejects this shape while that project's own native execution path did not - fixed in that project directly (a hard validation "blocker" added at triple-term construction time, rejecting a nested triple term in subject/predicate position unconditionally), not here. This file is Oxigraph-specific and has nothing further to report as a result of this investigation - no issue currently stands against Oxigraph.
