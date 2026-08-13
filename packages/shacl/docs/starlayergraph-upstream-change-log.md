# StarLayer Upstream Change Log

*Last reviewed: 2026-08-01*

Track proposed StarLayerGraph enhancements discovered during starshacl rebuild work.

## How To Use

For each candidate change, add one entry with:
- Title
- Motivation
- starshacl impact
- Temporary workaround in starshacl
- Proposed StarLayerGraph API/behavior change
- Validation/tests needed
- Upstream status (`draft`, `proposed`, `accepted`, `implemented`)

## Entries

## 2026-07-03 - Candidate: Reuse StarLayerGraph SPARQL features for SHACL-SPARQL

Motivation:
- starshacl SHACL-SPARQL execution can likely reuse existing StarLayerGraph query rewriting/binding behavior instead of duplicating logic.

starshacl impact:
- reduces duplicate SPARQL rewrite/restore logic
- improves consistency between graph query behavior and SHACL-SPARQL behavior

Temporary workaround in starshacl:
- maintain internal SPARQL rewrite/execution path until integration is complete.

Proposed StarLayerGraph API/behavior change:
- expose a stable API surface for SPARQL 1.2 rewrite and triple-term binding/restoration suitable for external engine integration.

Validation/tests needed:
- parity fixtures for SHACL-SPARQL constraints with triple-term bindings
- regression tests for variable restoration and target selection semantics

Upstream status:
- implemented. `TripleTermAdapter.encode_graph()` (starshacl) now returns `_SparqlAwareEncodedGraph`, whose `.query()` decodes back to a real `StarLayerGraph` and delegates to its existing `.query()` implementation instead of duplicating rewrite/restore logic. See `starshacl/adapters.py` and `tests/integration/test_sparql_shacl_integration.py`.

## 2026-07-15 - Fixed: `StarLayerGraph.query()` didn't encode TripleTerm-valued `initBindings`

Motivation:
- `StarLayerGraph.query()` decoded `TripleTerm` values in outbound SELECT results (`_restore()`) but never encoded inbound `initBindings` before matching, unlike every other read path in the class (which calls `_coerce_tt_read()` first). A `TripleTerm`-valued binding (e.g. `$this` bound to a triple-term focus node) silently matched zero rows instead of the correct data.

starshacl impact:
- blocked triple-term-valued `$this`/`$value` bindings in `sh:sparql` constraints and `sh:construct` rules from working at all.

Temporary workaround in starshacl:
- none needed; fixed directly in `starlayer_graph.py`.

Proposed StarLayerGraph API/behavior change:
- `query()` now calls a new `_encode_init_bindings()` helper (mirroring `_coerce_tt_read()`) on `initBindings` before delegating to the underlying store; unregistered triple terms resolve to a fresh `BNode` (correct "zero rows" semantics, not an error).

Validation/tests needed:
- `tests/unit/test_sparql12_query.py::TestQ16` (registered and unregistered triple-term bindings)

Upstream status:
- implemented (this repo, `starlayergraph/graph/starlayer_graph.py`)

## 2026-07-15 - Fixed: CONSTRUCT templates couldn't mint a not-yet-registered triple-term value

Motivation:
- A ground `<<( s p o )>>` in a CONSTRUCT template only resolved if that exact triple-term value was already registered elsewhere in the graph (i.e. already used as a value somewhere) - the rewriter only knew how to *match* existing support triples, never to *mint* a new one. This blocks the common "reify this fact I just matched" SHACL-AF rule idiom.

starshacl impact:
- `sh:construct` SHACL-AF rules that build a brand-new triple term from a plain fact silently produced no output.

Temporary workaround in starshacl:
- none needed; fixed directly in `sparql12_to_11.py`.

Proposed StarLayerGraph API/behavior change:
- For `CONSTRUCT { template } WHERE { where }` queries specifically: rewrite the WHERE clause first (so already-matchable content registers normally), then rewrite the template with a new `state.in_construct_template` flag; any triple-term content-key that's new at that point gets a computed `BIND(<tt-hash-fn>(s, p, o) AS tt_var)` (a new registered SPARQL custom function replicating `_intern_tt`'s hash) spliced into the WHERE clause, since a CONSTRUCT template can't itself contain a BIND. See `_try_split_construct_where`/`_rewrite_construct_query` in `sparql12_to_11.py`.

Validation/tests needed:
- `tests/unit/test_sparql12_to_11.py`, full suite regression (existing `TestQ14` CONSTRUCT tests unaffected)

Upstream status:
- implemented (this repo, `starlayergraph/query/sparql12_to_11.py`)

## 2026-07-15 - Fixed: accessor functions and `isTripleTerm()` only recognized `?var`, not `$var`

Motivation:
- `SUBJECT()`/`PREDICATE()`/`OBJECT()` and `isTripleTerm()` regexes only matched `?var` syntax. `$var` is equally valid SPARQL and is the sigil convention SHACL-SPARQL constraints use for `$this`/`$value`, so combining those bindings with accessor functions failed to parse.

starshacl impact:
- SHACL-SPARQL constraints using the conventional `$this`/`$value` form together with `PREDICATE()`/`isTripleTerm()` etc. produced invalid rewritten SPARQL.

Proposed StarLayerGraph API/behavior change:
- Widened the relevant regexes (`_TRIPLE_FUNC_RE`, `_IS_TT_RE`, `_BIND_ACCESSOR_RE`, `_T`, `_TILDE_RE`) from `\?` to `[?$]`. Substitution logic already used captured text verbatim, so no other changes were needed.

Validation/tests needed:
- `tests/unit/test_sparql12_to_11.py::test_rewrite_accepts_dollar_sigil_for_accessor_functions`, `test_rewrite_accepts_dollar_sigil_for_is_triple_term`

Upstream status:
- implemented (this repo, `starlayergraph/query/sparql12_to_11.py`)

## 2026-07-15 - Fixed: nested triple term (object position) crashed / lost fidelity on restore

Motivation:
- A triple term whose own object is itself a triple term (valid RDF 1.2 - nesting is only disallowed in subject position) surfaced two bugs when built via `StarLayerGraph`'s own tuple-shorthand convention: (1) `_intern_tt` cached the *original*, un-normalized `TripleTerm` in `_tt_nodes` (with a raw un-coerced tuple as `.object`) instead of the normalized form actually written to the store, and (2) `_restore()` only followed one level of `tt:HASH` URIRef, so even with (1) fixed, a nested encoded URI in `.object` would come back unresolved rather than as a nested `TripleTerm`. Together these meant nested triple terms round-tripped incorrectly (or crashed a caller trying to encode a raw-tuple nested value further, since duck-typing checks like `hasattr(x, "subject")` fail on a plain tuple).

starshacl impact:
- `TripleTermAdapter.encode_graph()` crashed (`AssertionError: ... must be an rdflib term`) on any StarLayerGraph containing a nested triple term built via the tuple-shorthand convention (not just the fully-pre-constructed-`TripleTerm` form). Also required a companion fix in starshacl itself (`starshacl/adapters.py::_encode_node`, normalizing a raw 3-tuple into `term_factory(*value)` before the `is_triple_term_like` check) since the adapter has the same duck-typing gap for values it receives directly.

Proposed StarLayerGraph API/behavior change:
- `_intern_tt`: cache `TripleTerm(s_n, tt.predicate, o_n)` (the normalized/interned form) in `_tt_nodes`, not the original `tt`.
- `_restore`: recurse into `tt.subject`/`tt.object` so a nested `tt:HASH` URIRef resolves into a real nested `TripleTerm`, not just the outer level.

Validation/tests needed:
- `tests/unit/test_starlayer_graph.py::TestTripleTermAdd::test_nested_tt_object_fully_resolves`

Upstream status:
- implemented (this repo, `starlayergraph/graph/starlayer_graph.py`)

## 2026-07-15 - Fixed: CONSTRUCT BIND for a minted triple term was placed before the WHERE patterns that bind its inputs

Motivation:
- The earlier fix (minting a new triple-term value via a computed BIND when a CONSTRUCT template references one that's never matched in WHERE) placed that BIND right after the WHERE clause's opening brace - before the WHERE clause's own patterns. This works when the minted triple term's components are all constants, but silently fails (SPARQL drops an unbound-input BIND's result rather than erroring) whenever a component is a variable bound only by those WHERE patterns - exactly the common SHACL-AF rule shape of "reify a fact derived via ordinary path matching" (e.g. transitive/cyclic reach rules).

starshacl impact:
- `sh:construct` SHACL-AF rules that mint a triple term from a WHERE-derived (not constant) value silently produced no output; this specifically blocked verifying fixed-point/triple-term-identity behavior for cyclic and transitive rules (Rules Hardening in `docs/shacl12-gap-matrix.md`).

Proposed StarLayerGraph API/behavior change:
- `_rewrite_construct_query`: append collected `pending_binds` after the rewritten WHERE clause's own content, not before it.

Validation/tests needed:
- `tests/unit/test_sparql12_to_11.py::test_construct_bind_for_new_triple_term_placed_after_where_patterns`, `tests/unit/test_sparql12_query.py::TestQ17`

Upstream status:
- implemented (this repo, `starlayergraph/query/sparql12_to_11.py`)

## 2026-07-18 - Fixed: `StarLayerGraph.query()`/`StarLayerDataset.query()` re-rewrote and re-parsed the same query text on every call

Motivation:
- Both rewrote SPARQL 1.2 triple-term syntax to SPARQL 1.1 (`rewrite_sparql12_to_11`) and handed the result to rdflib as a plain string on every single `.query()` call, even when the same query text is evaluated repeatedly with only `initBindings` differing - exactly how pySHACL evaluates a SHACL-AF `sh:construct` rule or `sh:sparql` constraint (once per focus node, per iteration). rdflib's own SPARQL parser has no caching of its own, so this redid the full rewrite+parse work on every call even though the result never changes between them.

starshacl impact:
- Real, measured cost for rule-heavy validations: profiled at ~4.5x slower per repeated call in a microbenchmark simulating pySHACL's actual usage shape (same query, different focus node each call); the win scales with graph size, since larger graphs mean more repeated calls per unmutated shapes graph.

Temporary workaround in starshacl:
- none needed; fixed directly in `starlayergraph`.

Proposed StarLayerGraph API/behavior change:
- New `starlayergraph/query/query_cache.py::prepare_query_cached` - a per-instance cache (`self._prepared_query_cache`) keyed on `(query text, effective namespaces, base IRI)` - all three of which rdflib's own `prepareQuery` bakes into the parsed query at parse time - returning a reused, already-rewritten-and-parsed `rdflib.plugins.sparql.sparql.Query` object instead of a plain string. Passing a pre-parsed `Query` object instead of a string to `Graph.query()` is a documented rdflib capability for the default code path (see the next entry for where it isn't).

Validation/tests needed:
- `tests/unit/test_query_prepare_cache.py` (parse-count verification via monkeypatched `prepareQuery`, correctness across repeated calls with differing bindings/namespaces, cache-doesn't-serve-stale-data-after-mutation, `StarLayerDataset` analogues)

Upstream status:
- implemented (this repo, `starlayergraph/query/query_cache.py`, wired into `starlayer_graph.py`/`starlayer_dataset.py`)

## 2026-07-18 - Fixed: prepared-query caching broke `StarLayerGraph.query()` against remote-endpoint stores (Fuseki, and any `SPARQLStore`/`SPARQLUpdateStore`-backed store)

Motivation:
- The fix above assumed passing a pre-parsed `Query` object to `Graph.query()` was safe for any rdflib store - true for the default in-memory `Memory` store (whose own `query()` just raises `NotImplementedError` and falls through to the generic `SPARQLProcessor` path, which does accept a `Query` object), but confirmed false via real Apache Jena Fuseki testing: `rdflib.plugins.stores.sparqlstore.SPARQLStore`/`SPARQLUpdateStore` (used for *any* remote HTTP SPARQL endpoint, not just Fuseki) hard-require a plain string in their own `query()` method (`assert isinstance(query, str)`), raising `AssertionError` instead of falling back gracefully. 4 test failures in `test_fuseki_backend.py` on first real-Fuseki run.

starshacl impact:
- None directly (starshacl never constructs a `StarLayerGraph` over a `SPARQLUpdateStore` itself), but this would have broken any consumer combining the rdf-1.1 encoding backend with a remote-endpoint-backed store - a real, legitimate rdflib configuration, not an edge case.

Temporary workaround in starshacl:
- none needed; fixed directly in `starlayergraph`.

Proposed StarLayerGraph API/behavior change:
- New `starlayergraph/query/query_cache.py::store_accepts_prepared_query(store)` - `isinstance` check against the two known string-only store classes. `StarLayerGraph.query()` checks this before deciding whether to use the cached prepared object or fall back to a plain rewritten string; no lost benefit for the affected stores either, since they forward the query text to a remote server, so local rdflib-side re-parsing was never the bottleneck there. `StarLayerDataset.query()` was confirmed unaffected - it always executes against its own always-in-memory `_build_raw_execution_graph()`, regardless of the dataset's own backing store.

Validation/tests needed:
- `tests/unit/test_query_prepare_cache.py::test_store_accepts_prepared_query_false_for_sparql_update_store`, `test_store_accepts_prepared_query_true_for_default_memory_store`, `test_starlayer_graph_over_sparql_update_store_falls_back_to_string` (no server needed - mocked store); real-Fuseki `tests/integration/test_fuseki_backend.py`/`test_cross_backend_parity.py` (previously 4 failures, now fully passing)

Upstream status:
- implemented (this repo, `starlayergraph/query/query_cache.py`, `starlayer_graph.py`)

## 2026-07-18 - Fixed: `StarLayerGraph.parse(format='turtle12'/'longturtle12'/'trig12')` wrote the rdf-1.1 encoding directly into the store for *any* backend, including native `rdf-1.2`

Motivation:
- These three parse branches built an intermediate skolemized graph (`_skolemize_encoding`) using the rdf-1.1 backend's own tt:HASH encoding scheme, then wrote it directly into the store via `super().add(triple)` (rdflib's base `Graph.add()`) - correct for the rdf-1.1 backend (that tt:HASH encoding *is* its own on-disk representation), but this call bypassed the backend-aware `StarLayerGraph.add()` override entirely, so it happened unconditionally regardless of backend. For a native (`backend='rdf-1.2'`) graph, a triple term parsed from text (as opposed to added via the `.add()` Python API, which was never affected) never decoded correctly afterward: `.triples()` returned the raw `rdf:subject`/`rdf:predicate`/`rdf:object` encoding fragments instead of a `TripleTerm` object, and `rdf:reifies` lookups against such data never matched anything real. Confirmed to affect both simple and nested triple terms.

starshacl impact:
- Broke `sh:reifierShape`/`sh:reificationRequired` end to end against a native-backend (Oxigraph) data graph - the discovery path, found while investigating whether native-backend `StarLayerGraph` usage was tested at all in starshacl (it wasn't, prior to this).

Temporary workaround in starshacl:
- none needed; fixed directly in `starlayergraph`.

Proposed StarLayerGraph API/behavior change:
- New `starlayergraph/parsers/turtle_parser.py::decode_tt_encoded_triples` - reverses the skolemized tt:HASH encoding back into real `(s, p, o)` triples with any encoded triple-term value restored to a proper `TripleTerm` object (nested triple terms restored recursively). `StarLayerGraph.parse()`'s `turtle12`/`longturtle12`/`trig12` branches now call this and route the result through `self.add()` (-> `_native_add()`) when `self._is_native`, leaving the rdf-1.1 path's `super().add(triple)` loop completely untouched.

Validation/tests needed:
- `tests/integration/test_oxigraph_backend.py::TestOxigraphTurtle12Parse` (5 tests: simple/nested triple-term decoding, no leaked encoding triples, `rdf:reifies` lookup matches parsed data, `trig12` parsing) - all confirmed to fail against the pre-fix code, pass against the fix

Upstream status:
- implemented (this repo, `starlayergraph/parsers/turtle_parser.py`, `starlayer_graph.py`)

## 2026-07-18 - Fixed: same bug, separate code path - `StarLayerDataset.parse(format='trig12')` on a native-backend dataset had the identical problem

Motivation:
- The fix above covers `StarLayerGraph.parse()`, but `StarLayerDataset.parse(format='trig12')` is a genuinely separate implementation (the dataset builds one context per named graph via `parse_trig12_named()`, rather than merging all graphs into one via `parse_trig12()`) with its own per-context write loop, which called the module-level `_raw_graph_add` (rdflib's base `Graph.add()`, aliased at import time) unconditionally regardless of backend - never routing through the per-context `StarLayerGraph.add()` override. Fixing the graph-level path did not fix this one.

starshacl impact:
- Same class of impact as the graph-level bug, for dataset-shaped native-backend input: a triple term parsed into a named graph never came back as a `TripleTerm` from `ds.get_context(...).triples()`. Confirmed via real Oxigraph *and* Fuseki testing.

Temporary workaround in starshacl:
- none needed; fixed directly in `starlayergraph`.

Proposed StarLayerGraph API/behavior change:
- Same technique as the graph-level fix: decode the tt:HASH encoding back into real `TripleTerm` objects before writing, per named-graph context, only on the native-backend path. The rdf-1.1 backend path (`_raw_graph_add` + `_build_registry_from_store()`) is untouched.

Validation/tests needed:
- real Oxigraph and Fuseki integration coverage (see `packages/graph/tests/integration/` in this repo)

Upstream status:
- implemented (this repo)

## 2026-07-18 - Fixed: `StarLayerDataset.query()` crashed on a native-backend dataset whenever a query result contained a triple-term-valued binding

Motivation:
- Found while verifying the fix above. Unlike `StarLayerGraph.query()`, which dispatches to `_native_query()` (using the endpoint's own triple-term SPARQL syntax and result parsing) when `self._is_native`, `StarLayerDataset.query()` has no such dispatch - it always queries a plain in-memory copy built by `_build_raw_execution_graph()`, which for a native-backend context reads through rdflib's base `Graph.triples()` (a plain SPARQL 1.1 `SELECT ?s ?p ?o` against the remote store) rather than the native-aware triple-term read path. A query like `SELECT ?tt WHERE { GRAPH ?g { ?s rdf:reifies ?tt } }` crashes with `TypeError: unknown binding type`.

starshacl impact:
- Cross-graph SPARQL over triple-term data on a native-backed `StarLayerDataset` should be considered unsupported until this is addressed. Plain-triple queries (no triple-term-valued binding in the result) against a native-backend dataset work correctly; only triple-term-valued results are affected. starshacl itself doesn't currently construct native-backend `StarLayerDataset` instances, so no direct impact yet, but this is a real gap for any consumer that does.

Temporary workaround in starshacl:
- none - avoid triple-term-valued SELECT bindings when querying a native-backend `StarLayerDataset` until this lands.

Proposed StarLayerGraph API/behavior change:
- `StarLayerDataset.query()` needs the same kind of native-aware dispatch `StarLayerGraph.query()` already has, extended to the cross-graph/dataset case.

Validation/tests needed:
- confirmed via real Oxigraph and Fuseki testing for SELECT, ASK, and CONSTRUCT (`packages/graph/tests/integration/`).

Upstream status:
- implemented (this repo) - `StarLayerDataset` now has the same native-backend query dispatch `StarLayerGraph` already had (a native-backed dataset's per-context graphs all share one store, so cross-graph queries are the same underlying HTTP operation).

## 2026-07-30 - Fixed: `StarLayerGraph.parse(format='turtle12', ..., publicID=...)` never resolved relative IRIs against `publicID` when parsing from `location=`

Motivation:
- Found while building the W3C SHACL 1.2 test-suite harness (`docs/w3c-shacl12-test-suite-plan.md`) - the vendored suite's own manifest files rely pervasively on `<>` self-reference and relative `mf:include <core/manifest.ttl>`-style targets, the same convention plain rdflib's Turtle parser (and every other RDF 1.1 parser) supports out of the box. `StarLayerTurtleParser.parse(text)` (invoked internally by `StarLayerGraph.parse()`'s `turtle12`/`longturtle12` branch) only resolved a relative IRI against `current_base`, which its own tokenizer set *exclusively* from an in-document `@base` directive - the `publicID` argument passed to `StarLayerGraph.parse(location=..., format='turtle12', publicID=...)` was never threaded through to the parser at all. Confirmed empirically: `<>` parsed to the literal empty-string `URIRef('')`, and `<core/manifest.ttl>` parsed to the literal relative `URIRef('core/manifest.ttl')`, regardless of what `publicID` was passed.

starshacl impact:
- None directly (starshacl itself doesn't rely on `location=`+`publicID`-based relative resolution for `turtle12` parsing in its own runtime code), but this blocked the W3C-suite harness outright until fixed - every self-referencing fixture and every `mf:include` in the vendored suite depends on this resolving correctly.

Temporary workaround in starshacl:
- none needed anymore; fixed directly in `starlayergraph`. (A local post-parse workaround, `tests/w3c_suite/manifest.py::_resolve_relative_uris`, was used until this landed and has since been removed.)

StarLayerGraph API/behavior change (implemented in `starlayergraph`):
- `StarLayerTurtleParser.parse()` gained a `base` parameter that seeds `current_base` before parsing begins (an in-document `@base`/`BASE` directive still overrides it from that point on, `urljoin`'d against it exactly as a second `@base` would be - unchanged behavior for that case). `StarLayerGraph.parse()`'s `turtle12`/`longturtle12` branch now computes an effective base (`publicID` if given, else `location`'s own resolved `file://` IRI) and passes it through - matching the convention rdflib's own parsers follow.

Validation/tests needed:
- `starlayergraph`'s `tests/unit/test_turtle_parser.py::TestBaseURI` gained `test_base_seeded_via_parse_argument`, `test_in_document_base_overrides_seeded_base`, `test_no_base_seeded_behaves_as_before` - all three confirmed to fail against the pre-fix code. This repo's own W3C-suite harness (`tests/w3c_suite/`) re-verified live against the real vendored fixtures after the fix landed - `<>`/`mf:include` resolution confirmed correct.

Upstream status:
- implemented (`starlayergraph`, `starlayergraph/parsers/turtle_parser.py`, `starlayergraph/graph/starlayer_graph.py`)

## 2026-07-30 - Fixed: `StarLayerTurtleParser` rejected three ordinary (non-RDF-1.2) Turtle constructs

Motivation:
- Found by running the real-world W3C SHACL 1.2 test-suite fixtures (`docs/w3c-shacl12-test-suite-plan.md`) through `format='turtle12'` - the visible symptoms weren't RDF-1.2-specific syntax at all; every one was plain Turtle grammar. Empirical debugging (minimal repros bisected against the actual failing fixtures, not just reading the code) found three distinct root causes, two of which were initially mischaracterized as different bugs than they actually were:
  1. **`next_token()`'s plain-token fallback only stopped at whitespace or `<`.** A token immediately followed by `(`, `[`, `{`, `"`, `'`, `,`, or `;` with *no separating space* (e.g. `sh:resultPath( [ sh:inversePath ex:p ] [ sh:inversePath ex:p ] )`, valid Turtle - none of these characters can appear inside a PrefixedName/IRI token, so no space is needed to disambiguate) glued the delimiter onto the preceding token instead of starting a new one, corrupting everything parsed after it. Originally misdiagnosed as "blank-node object descriptions can't be RDF-list members" (the visible symptom in `core/path/path-complex-002.ttl`'s `sh:resultPath(...)` - no space before `(`) - the real cause was this general tokenization gap, confirmed by reproducing the identical failure with a predicate immediately followed by `[`, and separately by a quoted literal, with no list involved at all.
  2. **RDF collection (`( ... )`) members never received the same bare-literal string→Python-value coercion (`coerce_object()`) an ordinary (non-list) object already gets in `extract_fields()`.** A collection containing a bare numeric/boolean literal (e.g. `( 42 )`, `mf:result ( 42 )`) reached final term conversion as a raw string and was rejected as an "unrecognized term" - even though `_to_node()` already handled Python `bool`/`int`/`float` correctly, it just never received them for list members specifically. Originally misdiagnosed as "bare numeric/boolean literals aren't recognized at all" - confirmed narrower: an *ordinary* (non-list) bare literal like `sh:uniqueMembers true` or `ex:age 30` already worked correctly before this fix; only collection members were affected.
  3. **A `#` comment starting after other content on the same line was never stripped** (e.g. `sh:targetNode ex:Invalid ;  # note`) - only a comment occupying a *whole* line was recognized (a pre-filter in `StarLayerTurtleParser.parse()`). The trailing comment text was fed into the grammar as if it were real content, producing a spurious "unexpected trailing content" error. This diagnosis was correct from the start.

starshacl impact:
- Blocked 12 of 172 vendored `core/`+`sparql/` files from loading at all (Phase 1 of `docs/w3c-shacl12-test-suite-plan.md`), plus `core/complex/shacl-shacl-data-shapes.ttl` (found via `sht:dataGraph`/`shapesGraph` resolution, not the `mf:include` manifest walk) - 13 total. Would have blocked a much larger fraction of `node-expr/`'s `shnex-sparql/` subdirectory once Phase 2 starts (bare literals inside collections are pervasive there). No impact on starshacl's own runtime code (it doesn't parse arbitrary third-party Turtle text via `format='turtle12'` in its own pipeline).

Temporary workaround in starshacl:
- none needed anymore; fixed directly in `starlayergraph`. (The 13 affected files were registered in `tests/w3c_suite/known_failures.py` under `pytest.xfail(strict=True)` until this landed; those entries have since been removed - 2 of the 13 turned out to have their own, independent, still-open findings once they could actually run, tracked separately as `reifierShape-001`/`property-sparqlExpr-001` in that same file.)

StarLayerGraph API/behavior change (implemented in `starlayergraph`):
1. Widened `next_token()`'s fallback-scan stop-character set from `{whitespace, '<'}` to also include `( ) [ ] { } " ' , ;` (`starlayergraph/parsers/lexer.py`).
2. `expand_triple_set()` now calls `coerce_object()` on each collection element before using it as an `rdf:first` value, matching what ordinary objects already got (`starlayergraph/parsers/syntax.py`) - safe unconditionally, since a bracket/quote-wrapped member never matches `coerce_object`'s literal patterns.
3. `#`-to-end-of-line stripping added directly to the statement-splitting/directive-scanning character loops (`_split_statements_impl`/`_scan_directive_end` in `starlayergraph/parsers/syntax.py`), gated on not being inside a string or an `<IRI>` (which may legitimately contain a literal `#` fragment) - not just the existing whole-comment-line pre-filter.

Validation/tests needed:
- `starlayergraph`'s `tests/unit/test_turtle_parser.py` gained `TestNoSpaceBeforeDelimiter` (3 cases), `TestCollectionElementLiteralCoercion` (4 cases), `TestMidLineComments` (4 cases, including two negative guards confirming a `#` inside a string/IRI is still never stripped) - all confirmed to fail against the pre-fix code via a temporary revert, not just pass against the fix. This repo's own W3C-suite harness re-ran all 13 previously-blocked fixtures live after the fix landed; all 13 now parse correctly (2 then surfaced independent, still-open findings once they could run - see `tests/w3c_suite/known_failures.py`).

Upstream status:
- implemented (`starlayergraph`, `starlayergraph/parsers/lexer.py`, `starlayergraph/parsers/syntax.py`)

## 2026-07-31 - Fixed: typed-literal construction silently discarded a non-canonical lexical form

Motivation:
- Found while building Phase 2 of the W3C SHACL 1.2 test-suite harness (`docs/w3c-shacl12-test-suite-plan.md`) - `shnex:distinct`/`shnex:remove` fixtures deliberately construct a value-equal-but-lexically-different literal (`"04"^^xsd:integer` alongside `4`) to verify RDF 1.2's own literal term-equality definition (https://www.w3.org/TR/rdf12-concepts/#dfn-literal-term-equality: two literals are term-equal only if their lexical forms match, not just their value). `StarLayerTurtleParser`'s `_to_node()` constructed typed literals via `Literal(text, datatype=...)` with no `normalize=` argument, so rdflib's default (`normalize=True`) silently rewrote `"04"^^xsd:integer` to the canonical `"4"^^xsd:integer` on construction - confirmed empirically (`Literal('04', datatype=XSD.integer)` reprs as `Literal('4', ...)`) - making the parser unable to represent the exact lexical form a document actually wrote for any numeric/boolean-typed literal with a non-canonical spelling.

starshacl impact:
- Blocked 2 W3C SHACL 1.2 Node Expressions fixtures (`distinct-termEquality`, `remove-list-from-list`) from passing - both specifically constructed to test this. No impact on starshacl's own runtime code otherwise (it doesn't rely on non-canonical lexical-form preservation itself).

Temporary workaround in starshacl:
- none needed; fixed directly in `starlayergraph`.

StarLayerGraph API/behavior change (implemented in `starlayergraph`):
- `_to_node()`'s typed-literal (`^^`) branch now passes `normalize=False` to `Literal(...)`, preserving whatever lexical form the source document wrote instead of rdflib silently recanonicalizing it.

Validation/tests needed:
- `starlayergraph`'s `tests/unit/test_turtle_parser.py::TestPlainTurtle::test_typed_literal_preserves_non_canonical_lexical_form` - confirmed to fail against the pre-fix code.

Upstream status:
- implemented (`starlayergraph`, `starlayergraph/parsers/turtle_parser.py`)

## 2026-07-31 - Known gap, not yet fixed: `"04"^^<full IRI>` (non-prefixed datatype IRI) fails to parse

Motivation:
- Found incidentally while writing the regression test for the fix above - `"04"^^<http://www.w3.org/2001/XMLSchema#integer>` (a full bracketed IRI as the datatype, rather than a prefixed name like `xsd:integer`) raises `TurtleSyntaxError: unexpected trailing content '<http://www.w3.org/2001/XMLSchema#integer>' after object`. Not investigated further - low real-world impact (prefixed names are near-universal for datatype IRIs in practice, including throughout the W3C SHACL 1.2 test suite itself), and out of scope for the Node Expressions harness work that surfaced it.

starshacl impact:
- None observed - no fixture in starshacl's own test suite or the vendored W3C suite uses this form.

Temporary workaround in starshacl:
- none needed - not encountered in practice.

Proposed StarLayerGraph API/behavior change:
- Not investigated. Likely a lexer/grammar gap in how a literal's `^^` suffix is tokenized when followed by `<...>` instead of a prefixed name - worth a focused look if a real document using this form ever surfaces.

Validation/tests needed:
- not yet written.

Upstream status:
- draft (known, logged, not yet implemented)

## 2026-07-31 - Fixed (partially - see the "Known gap" entry below): `initBindings`-only triple-term values were never usable by real `validate()`/`apply_rules()` node expressions

Motivation:
- Found by directly checking real end-to-end reachability (per a user question) rather than trusting the W3C-suite harness's own `eval_expr()`-direct test coverage: `sh:expression [ sparql:isTriple ( [ shnex:pathValues ex:says ] ) ] ` against real triple-term data returned the wrong answer (`false`) through the actual `validate()` pipeline, despite the equivalent `tests/w3c_suite/` test (calling `eval_expr()` directly with a hand-built `StarLayerGraph`) passing. Root-caused to two compounding issues, both in `starshacl`, not `starlayergraph` itself: (1) `data_graph` as handed to node-expression evaluation in real usage is pySHACL's plain, unwrapped `RdfLibDataGraph`, so a triple-term value read from it (e.g. via `shnex:pathValues`) was still in `starshacl`'s own flat-encoded `urn:starshacl:tt:HASH` form, not a decoded value; (2) even after decoding, `starlayergraph`'s own `_encode_init_bindings` deliberately treats a triple-term value passed via `initBindings` as "not found" (a fresh, unmatchable `BNode`) unless that *exact* value is already registered in *the specific graph instance being queried*'s own registry - by design (its own docstring: "giving correct 'zero rows' semantics rather than silently comparing a raw Python object against store terms it can never equal") - so a triple-term value belonging to the *data* graph was never recognized when queried against the *shapes* graph (the only triple-term-aware graph reliably available at that call site) either.

starshacl impact:
- Every RDF-1.2-specific `sparql:` function (`isTriple`/`triple`/`subject`/`predicate`/`object`) silently gave wrong answers against real triple-term data in actual `validate()`/`apply_rules()` usage - confirmed only worked at all in `tests/w3c_suite/`'s own direct `eval_expr()` tests, which don't go through pySHACL's real graph-wrapping layers.

Temporary workaround in starshacl:
- `starshacl/sparql_node_expressions.py::_run_sparql_call` now builds a small, disposable `StarLayerGraph` for each call and registers every triple-term-like argument into it (one throwaway triple) before querying, rather than querying the shapes graph or the raw `data_graph` - registering the exact value being asked about sidesteps `_encode_init_bindings`'s registry requirement entirely, correctly, without needing any `starlayergraph`-side change. `_decode_triple_term` (same module) decodes a raw `urn:starshacl:tt:HASH` value first, via the shared `TripleTermAdapter` instance (confirmed the same adapter encodes both the data and shapes graphs for one `validate()`/`apply_rules()` call, so its registry already has what's needed).

Proposed StarLayerGraph API/behavior change:
- None needed for this part - `_encode_init_bindings`'s existing behavior is correct and deliberate; the fix belongs entirely on the caller's side (done, see above).

Validation/tests needed:
- `starshacl`'s `tests/integration/test_shnex_node_expressions.py::test_sparql_only_shapes_graph_reaches_sparql_node_expressions`/`test_sparql_function_call` cover reachability; a direct live repro (`sh:expression [ sparql:isTriple ( [ shnex:pathValues ex:says ] ) ]` against real triple-term data through `validate()`) confirmed the fix, contrasted against the pre-fix behavior.

Upstream status:
- implemented (`starshacl`, not `starlayergraph` - no change needed in this repo for this part). See the next entry for a related, still-open `starlayergraph` gap found during this same investigation.

## 2026-07-31 - Fixed: `TRIPLE(?a, ?b, ?c)` returned zero rows when all three arguments were bound only via `initBindings` (no matching `WHERE`-clause graph pattern)

Motivation:
- Found while verifying the fix above - `sparql:triple`'s W3C-suite test (`node-expr/shnex-sparql/triple.ttl`) appeared to already pass, but only by accident: that fixture's own `mf:result` happens to contain the literal Turtle constant `<<( ex:s ex:p ex:o )>>`, which registers that exact triple term in the document's graph as an ordinary side effect of parsing the file - coincidentally matching what `sparql:triple ( ex:s ex:p ex:o )` was trying to *construct*, masking the real gap. Confirmed independently of starshacl: `StarLayerGraph().query('SELECT (TRIPLE(?a0, ?a1, ?a2) AS ?r) WHERE {}', initBindings={'a0': ex.s, 'a1': ex.p, 'a2': ex.o})` returned zero rows regardless of how much unrelated content the graph already had, while the identical query with `ex:s`/`ex:p`/`ex:o` written directly in the query text (no `initBindings` at all) returned the correct triple term. Unlike the fix above (which is about *recognizing* an existing triple-term value), this is about *constructing* a brand-new one from initBindings-only arguments - a different, narrower case.
- Root cause, in `starlayergraph/query/sparql12_to_11.py`: `TRIPLE(s, p, o)` desugars to `<<( s p o )>>` before the rest of the rewriter runs, and the rewriter decided "match an existing graph pattern" vs. "construct a value via the internal content-addressed hash function" purely by whether `s`/`p`/`o` were syntactically ground (no variables) - never by *where* the triple term occurred (a graph-pattern term slot in an ordinary `subject predicate object .` statement vs. a plain expression position such as a `BIND(...)`/`FILTER(...)`/SELECT-projection argument, which already accepts an arbitrary expression). A non-ground occurrence in an *expression* position (e.g. `SELECT (TRIPLE(?a0, ?a1, ?a2) AS ?r) WHERE {}`, with `?a0`/`?a1`/`?a2` bound only via `initBindings`) was always routed to the "match" branch - injecting `?tt <rdf:subject> ?a0 . ?tt <rdf:predicate> ?a1 . ?tt <rdf:object> ?a2 .` into the (here, empty) `WHERE` clause - which can only ever succeed if a triple term with those exact components already happens to be registered in the store, which an `initBindings`-only value never is.

starshacl impact:
- `sparql:triple` (the `TRIPLE()` constructor function as a node expression) didn't work when its arguments came from evaluated sub-expressions rather than literal constants already present in the shapes graph - confirmed via `tests/w3c_suite/known_failures.py`'s now-removed `triple-example` entry.

Temporary workaround in starshacl:
- none needed; fixed directly in `starlayergraph`.

StarLayerGraph API/behavior change (implemented in `starlayergraph`):
- `_rewrite_group_content` now tracks paren-nesting depth (an unclosed `(` at the point a `<<( )>>`/desugared-`TRIPLE()` occurrence is scanned means it's inside an expression context - `BIND(...)`, a SELECT projection's `(expr AS ?var)`, `FILTER(...)`, or a nested function argument - since SPARQL has no other bare-parenthesized construct at the graph-pattern level). A non-ground triple term in that position is now substituted in place with a direct call to the internal hash function (`<...ns/tt#fn/hash>(s, p, o)`) rather than a "match an existing pattern" injection - a plain expression position already accepts an arbitrary SPARQL expression syntactically, so no fresh variable or hoisted `BIND` is needed; the substituted call's arguments resolve against whatever bindings are already in scope at evaluation time. A non-ground triple term used as a genuine graph-pattern term (e.g. `?stmt rdf:reifies <<( ?s :p ?o )>> .`, no enclosing parens) is unaffected and still uses matching-pattern semantics, which is correct there (RDF-star/1.2's own reification-matching semantics).

Validation/tests needed:
- `starlayergraph`'s `tests/unit/test_sparql12_to_11.py::test_triple_constructor_with_all_initbindings_args_constructs_a_value` and `::test_triple_constructor_in_bind_with_where_bound_vars_still_matches_literal_form` - both confirmed to fail against the pre-fix code via `git stash push -- starlayergraph/query/sparql12_to_11.py`. Full existing `test_sparql12_to_11.py` suite (27 tests) re-run afterward with no regressions, confirming the pre-existing `TRIPLE()`/`<<( )>>`-equivalence and ground-value-construction tests still hold.

Upstream status:
- implemented (`starlayergraph`, `starlayergraph/query/sparql12_to_11.py`)

## 2026-08-01 - Fixed: ECHAR escapes `\b`/`\f` (backspace/form-feed) never decoded in string literals

Motivation:
- Found while chasing a `sh:singleLine` xfail (`known_failures.py`) that claimed the *component's* regex missed form-feed as a line-break character - false on inspection (its regex already covers `\f`); the real bug was one layer down: `turtle_parser.py::_unescape()` and `ntriples12.py::_unescape_nt()` both handle the full RDF 1.1/1.2 ECHAR table (`\t \n \r \" \' \\`) *except* `\b` and `\f`, silently leaving those two escape sequences as the literal two-character text `\b`/`\f` in the decoded string instead of the actual backspace (U+0008) / form-feed (U+000C) control characters the grammar defines them as. Confirmed via direct isolated parser testing (`_unescape('a\\fb')` returned `'a\\fb'` unchanged, not `'a\x0cb'`), independent of any SHACL-side code.

starshacl impact:
- Any literal containing a `\b`/`\f` ECHAR escape round-tripped incorrectly through `StarLayerGraph` parsing - specifically blocked `sh:singleLine`'s "form feed makes this a violation" fixture from ever seeing a real `\x0c`, and would silently corrupt any other data relying on these two escapes.

Temporary workaround in starshacl:
- none needed; fixed directly in `starlayergraph`.

StarLayerGraph API/behavior change (implemented in `starlayergraph`):
- Both `_unescape()` (`starlayergraph/parsers/turtle_parser.py`) and `_unescape_nt()` (`starlayergraph/parsers/ntriples12.py`) now map `\b` → U+0008 and `\f` → U+000C alongside the pre-existing escapes.

Validation/tests needed:
- `starlayergraph`'s `tests/unit/test_turtle_parser.py::TestPlainTurtle::test_form_feed_and_backspace_escapes_decode` (new), and a new `tests/unit/test_ntriples12.py` (previously zero coverage for this parser) - both confirmed to fail against the pre-fix code.

Upstream status:
- implemented (`starlayergraph`, `starlayergraph/parsers/turtle_parser.py`, `starlayergraph/parsers/ntriples12.py`)

## 2026-08-01 - Fixed (via monkeypatch, not a `starlayergraph`-authored bug): two confirmed plain-`rdflib` SPARQL arithmetic bugs

Motivation:
- Found while triaging the W3C SHACL 1.2 test suite's remaining xfails (`tests/w3c_suite/known_failures.py` in `starShacl`) - 9 fixtures (`multiply-example`, `divide-example`, `ceil-example`, `floor-example`, `round-example`, and 4 `rectangle-*` `sh:SPARQLRule` fixtures) all traced to two distinct, confirmed bugs in plain `rdflib` 7.6.0's own `rdflib/plugins/sparql/operators.py` - reproduced with zero `starlayergraph`/`starshacl` involvement via a bare `rdflib.Graph().query()`:
  1. **`MultiplicativeExpression` (the `*`/`/` operators) never applies SPARQL 1.1's numeric type-promotion rules**, unlike `AdditiveExpression` (`+`/`-`), which correctly calls `type_promotion(dt, term.datatype)` and passes the result as `Literal(res, datatype=dt)`. `MultiplicativeExpression` always computes via `Decimal(...)` and returns bare `Literal(res)`, so rdflib infers the datatype from the Python `Decimal` type alone - always `xsd:decimal`, even for `xsd:integer * xsd:integer` (which SPARQL 1.1's op:numeric-multiply requires to stay `xsd:integer`). Confirmed: `Graph().query('SELECT (?a*?b AS ?r) WHERE {}', initBindings={two xsd:integer Literals})` returns `xsd:decimal`.
  2. **`Builtin_CEIL`/`Builtin_FLOOR`/`Builtin_ROUND` correctly preserve the argument's `xsd:decimal` datatype but lose the canonical lexical form** - they construct `Literal(int(...), datatype=l_.datatype)`, and a raw Python `int` lexicalizes as e.g. `"4"`, not XSD decimal's canonical `"4.0"` (a decimal point with a digit on each side is required). Division (in `MultiplicativeExpression`) has the same lexical-form defect for whole-number results (`84 / 2` → `"42"^^xsd:decimal`, not `"42.0"`), even though its datatype was already correct. Confirmed directly: `Literal(Decimal(42))` (rdflib's own default) already lexicalizes as `"42"`, not `"42.0"` - the fix isn't about `datatype=` at all, it's about the lexical string.
- A closely related third finding, `seconds-example` (`Builtin_SECONDS()` returning `"0"` where the fixture expects zero-padded `"00"`), was investigated and deliberately **not** patched. Correction to an earlier version of this entry: `"0"` is *not* actually XSD decimal's true canonical form either (that's `"0.0"` - same decimal-point-required rule as the CEIL/FLOOR/ROUND fix above; `Builtin_SECONDS()` just hasn't been patched for it). But zero-padding to two digits (`"00"`) isn't XSD canonicalization at all - it's ISO-8601-style time formatting that `SECONDS()`'s own specification (a numeric `xsd:decimal` *value*, not a substring of the input's lexical form) doesn't require. Confirmed independently against both native backends below - neither produces `"00"` either - reinforcing that this looks like a fixture-authoring artifact, not a genuine interoperability requirement. Left as a genuine, permanent xfail.

starshacl impact:
- Blocked the 9 fixtures above end-to-end (`sparql:multiply`/`sparql:divide`/`sparql:ceil`/`sparql:floor`/`sparql:round` node expressions, and any `sh:SPARQLRule` CONSTRUCT template computing an integer product) from ever producing the spec-correct result, regardless of anything in `starshacl`'s own code - both bugs live entirely in rdflib's SPARQL evaluator.

Temporary workaround in starshacl:
- none needed; patched directly in `starlayergraph`, applied globally to every consumer.

StarLayerGraph API/behavior change (implemented in `starlayergraph`):
- New `starlayergraph/query/operator_patches.py`, applied eagerly from `starlayergraph/__init__.py` (`apply_all_operator_patches()`) so every consumer gets spec-correct arithmetic without needing to opt in. Both patches mutate the specific `Comp` grammar-node objects inside rdflib's own already-built pyparsing SPARQL grammar tree (found by name via a small recursive tree-walk, `_find_comp`, since `Builtin_CEIL`/`Builtin_FLOOR`/`Builtin_ROUND` aren't separately-named top-level grammar variables in `rdflib.plugins.sparql.parser`) - `Comp.postParse` reads `self.evalfn` fresh on every single query parse (it's a plain mutable instance attribute, not a closure baked in once at grammar-definition/import time), so overwriting it via `.setEvalFn()` after the fact is confirmed safe and takes effect for every future `.query()` call, on any graph, without needing to touch `rdflib`'s own installed files. `patch_multiplicative_expression_type_promotion()` reimplements `MultiplicativeExpression` with `type_promotion()` tracking (mirroring `AdditiveExpression`), special-casing `/` to force `xsd:decimal` rather than `xsd:integer` when both operands are integers (matching op:numeric-divide's actual semantics, which the original bug's ad-hoc "let Python infer it" approach happened to also get right for that one case). `patch_decimal_result_lexical_form()` wraps `Builtin_CEIL`/`Builtin_FLOOR`/`Builtin_ROUND` to run their output through a shared `_canonicalize_decimal_lexical_form()` helper (appends `.0` when the datatype is `xsd:decimal` and the lexical form has no `.`); the division fix reuses the same helper. Both follow the idempotent apply-once pattern (`_xxx_patch_status` flag + marker attribute on the patched callable) already established in `starshacl/validator.py`.

Validation/tests needed:
- `starlayergraph`'s new `tests/unit/test_operator_patches.py` (10 tests: integer\*integer stays integer, integer\*decimal/double promotion, addition unaffected, division/CEIL/FLOOR/ROUND canonical lexical form, ABS unaffected) - all confirmed to fail against the pre-patch code via `git stash push -u -- starlayergraph/__init__.py starlayergraph/query/operator_patches.py`. `starShacl`'s W3C-suite harness re-verified live: all 9 previously-xfailed fixtures now genuinely pass (not just no-longer-gated) - confirmed via the same stash-based adversarial revert against the real fixtures (`tests/w3c_suite/`), which reproduced all 9 original failures with the patch removed.

Upstream status:
- implemented as a monkeypatch in `starlayergraph` (`starlayergraph/query/operator_patches.py`, `starlayergraph/__init__.py`) - the actual bug lives in plain `rdflib`, not this repo; not yet reported upstream to `RDFLib/rdflib`. Full issue write-ups ready to file: `starlayergraph`'s own `docs/rdflib-upstream-issues.md` (Issues 1-2).

## 2026-08-01 - Known gap, not yet fixed: Oxigraph's native SPARQL engine doesn't canonicalize whole-number decimal results, diverging from the in-memory backend and Fuseki

Motivation:
- Follow-up to the operator-patches entry above, prompted by a direct question: does the same canonicalization (CEIL/FLOOR/ROUND/division whole-number results getting a `.0` suffix) hold across every backend this repo supports, or only the one just patched? Checked empirically, live, against all three: the in-memory backend (patched rdflib), a real Fuseki 5.5+ instance (Apache Jena's ARQ engine), and a real Oxigraph instance, running the identical queries (`SELECT (CEIL(3.2) AS ?r) WHERE {}`, `SELECT (84 / 2 AS ?r) WHERE {}`) against each.
- Result: internal (patched rdflib) and Fuseki/Jena-ARQ **agree exactly** - both produce `"4.0"^^xsd:decimal`, `"42.0"^^xsd:decimal` - matching the actual downstream W3C SHACL 1.2 test suite fixtures' own `mf:result` expectations (`starShacl`'s vendored `tests/node-expr/shnex-sparql/{ceil,divide}.ttl`, which literally write `4.0`/`42.0` in Turtle). Oxigraph alone produces `"4"^^xsd:decimal`, `"42"^^xsd:decimal` - a valid but non-canonical decimal lexical form, value-equal but not lexically identical (matters under RDF 1.2's own literal term-equality, which requires exact lexical form match, not just value equality). Two independent, mature engines and the actual conformance-test ground truth all agree; only Oxigraph's own native arithmetic diverges.
- Also checked `SECONDS()` on the same 3-way basis: all three backends (internal, Fuseki, Oxigraph) agree with each other (`"0"`, not the W3C fixture's requested `"00"`) - independent corroboration that fixture's zero-padding expectation is a fixture artifact, not something any real engine naturally produces (see the correction added to the entry above).

Impact:
- A native-backend (`backend='rdf-1.2'`, e.g. Oxigraph) `StarLayerGraph` query computing a whole-number decimal via `CEIL`/`FLOOR`/`ROUND`/division will give a different (though value-equal) lexical form than the same query against the default in-memory backend or a Fuseki-backed native graph. Not currently a live bug - nothing in the W3C SHACL 1.2 test suite or `starshacl`'s own runtime code drives numeric SPARQL arithmetic through a native-backend `StarLayerGraph` today - but it is a real, confirmed gap in this repo's own "identical behavior regardless of backend" contract (`docs/future_enhancements.md`'s "Cross-backend behavior parity" section) for this specific operator family.

Temporary workaround in starshacl:
- none needed; not currently reachable through any code path this consumer exercises.

Proposed StarLayerGraph API/behavior change:
- Not yet implemented. Two options considered: (1) apply the same `_canonicalize_decimal_lexical_form`-style post-processing to Oxigraph's own query results (would need to intercept native-backend result decoding, e.g. `starlayergraph/backends/native.py::native_query`, checked against every value in every result row - broader surface than the operator_patches.py approach, which only touches specific named SPARQL functions); (2) leave it as a documented, tracked divergence given today's zero real-world reachability. Deferred to whichever a concrete future caller actually needs.

Validation/tests needed:
- `tests/integration/test_cross_backend_parity.py`'s new `NUMERIC_LEXICAL_FORM_SCENARIOS` (`CEIL whole-number decimal lexical form`, `division whole-number decimal lexical form`) - `test_fuseki_matches_internal_for_numeric_lexical_form` passes (confirms Fuseki genuinely matches, not just "also untested"); `test_oxigraph_matches_internal_for_numeric_lexical_form` is `xfail(strict=True)`, so it will break loudly (XPASS) if Oxigraph's own arithmetic behavior ever changes to match.

Upstream status:
- draft (known, logged, deliberately not implemented - tracked via a `strict=True` xfail rather than silently passing or hard-failing, per this project's "track deferred scope explicitly" discipline).
