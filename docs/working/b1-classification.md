# B1 classification: what breaks when the old graph defaults to the native backend (2026-11-04)

Branch `mig-b1-classify`, from `shacl-engine` at 18538e8. Nothing was deleted. The measurement was a throwaway change
(`scripts/b1_flip_experiment.py apply`, reverted before this commit) that makes `StarLayerGraph()` / `StarLayerDataset()` default to
`backend='rdf-1.2'` over an in-process `OxigraphStore` (query and update text goes straight to Oxigraph, no lowering, no `tt:`
encoding). The whole `packages/starlayer/tests` tree ran with `--deferred` (`-n 4`, `PYTHONHASHSEED=0`): 13,110 collected, **403 failed,
12,177 passed, 507 skipped, 23 xfailed** (15 min). The earlier measurement (713 failures of about 3,300 in `graph/unit` and
`sparql/unit` only) is outdated: query-time entailment, the union fix and the D1 prerequisites have since landed. `scripts/b1_classify.py`
turns the JUnit file into the counts below (rules in the script; every failing test is in exactly one class).

## 0. The measurement tests the old wrapper, not the new backend

The flip runs the *old rdflib-based class* on a native store. It is not `OxGraph`. Most failures are therefore properties of that
wrapper (blank-node `identifier` scoping that wraps every pattern in `GRAPH <bnode>`, prepared-query objects, rdflib stores) that
disappear when the class is replaced. To decide what is a real bug, each non-obvious cluster was re-run on bare `pyoxigraph` 0.5.13
or on `OxGraph` (probe scripts were throwaway; results are quoted below).

## 1. Headline

| Class | Failures | Meaning |
|---|---:|---|
| D delete | 185 | tests of code the plan deletes |
| M migrate | 186 | behaviour kept, test rewritten (what changes: see the per-file table and section 3) |
| B real bug / missing behaviour | 20 | see section 2 |
| X environmental or flaky | 12 | strict xfails that pass only because the flipped loader hands over rdflib literals |
| **Total** | **403** | 93 test classes in 50 test files |

D by reason: lowering 78 (`test_lower_rdf11`) + 8 (`test_phase3_rdf12`); old-vs-new comparators 22; hand-written writers 22 and parsers 10;
rdflib stores 17; hand-parser warnings 9; prepared-query cache 10; backend parity 6; `tt:` encoding 3.
M by reason: prepared query object passed to `query()` 42; entailment (old native path raises `NotImplementedError`) 28; lexical forms
25; derive_shape 18; old-class API (row access, identifiers, str of triple terms, `isomorphic`) 20; old-wrapper artefacts 23;
error type 17; graph identifier 6; basic-encoding input 7.
No test failed for a flaky or environmental reason (no timing, no hash seed, no network); class X is the strict-xfail artefact only.

No kg test failed (`tests/kg`, the starontology suites, the shacl_engine suites, `test_d1_readiness` and the root tests all pass on the
flipped class). By directory: `graph/unit` 223, `sparql/unit` 132, `graph/oxgraph` 25, `graph/integration` 6, `shacl/integration` 8,
`shacl/w3c_shacl12` 6, `graph/w3c_sparql12` 2, `sparql/w3c_sparql12` 1.

## 2. Class B, grouped by root cause

"Upstream" means reproduced on bare `pyoxigraph` 0.5.13, so a wrapper cannot fix it without client-side work.

| # | Root cause | Tests | Minimal reproduction | Proposed fix |
|---|---|---:|---|---|
| B1 | `OxGraph`/`OxDataset` cannot be pickled or `copy.deepcopy`-ed (`pyoxigraph.Store` is not picklable). `.copy()` works | 4 | `copy.deepcopy(OxGraph())` -> `TypeError: cannot pickle 'pyoxigraph.Store' object` | add `__deepcopy__` (= `copy()`) and `__reduce__` (N-Quads round trip) to `OxGraph`/`OxDataset`; about 30 lines. Owner decision O2 whether pickling is kept |
| B2 | Missing methods the plan keeps: `OxGraph.from_rdflib` (plan section 2: supported public input; today only a function in `_rdflib_bridge`), `reduce_prefixes`, `add_reifier_annotation` | 6 | `OxGraph.from_rdflib(rdflib.Graph())` -> `AttributeError` | classmethod over the existing bridge; `reduce_prefixes` over `used_prefixes()`; about 60 lines. Needed before D1 (public API names) |
| B3 | Oxigraph REPLACE and REGEX do not follow XPath: a zero-length match is an error in XPath, Oxigraph returns `-a-b-c-`; invalid replacement `'$'` is accepted (`a$c`); `\$` kept as `\$`; a regex the XPath dialect rejects (`\p{L}+` in the test) is accepted | 5 | `SELECT (REPLACE('abc','x*','-') AS ?r) {}` on bare Oxigraph gives `"-a-b-c-"`, SPARQL (via fn:replace) says unbound | upstream. The old rdflib evaluator patches implemented these; their deletion drops them. Either file upstream and xfail strictly, or accept (O7) |
| B4 | Oxigraph boolean ordering: `false < true` is unbound | 1 | `SELECT (false < true AS ?r) {}` -> unbound (also `true > false`); SPARQL operator table defines it | upstream; xfail strictly, report |
| B5 | Property paths: a zero-length path to a constant that is not a node (`:zzz :p* ?y`) matches nothing (already `oxigraph-upstream-issues.md` section 1); `!(:p\|^:q)` returns each pair once where the spec translation (`!(:p) UNION ^!(:q)`) is a bag with `(b,a)` twice | 2 | `SELECT ?y { :zzz :p* ?y }` -> no rows | upstream. First is already tracked; add the second to the doc |
| B6 | `COPY` / `ADD` from a graph that does not exist, without `SILENT`, do not raise (`MOVE`, `DROP`, `CLEAR` do) | 2 | `OxDataset().update('COPY <urn:nope> TO <urn:g1>')` -> no error, target emptied | upstream; or the wrapper checks `has_graph` before COPY/ADD (5 lines, but needs the parsed operation; defer to upstream) |

Total B: 4 + 6 + 5 + 1 + 2 + 2 = 20. Only B1 and B2 are wrapper work (10 tests); B3 to B6 are Oxigraph deviations the plan did not know about
and that the old rdflib evaluator (and its patches, `evaluate_patches.py` etc.) had hidden. Nothing in class B is a wrong result from
the native path that the old class got right by luck of the test data: all six reproduce on `pyoxigraph` or `OxGraph` directly.

Things checked on `OxGraph` that are **not** bugs although the old-class test fails: RDFS entailment (`query(entailment=RDFS)` works);
`initNs` and bound-prefix injection into queries work; blank nodes are stable across queries of one store; `INSERT DATA { ?s ... }`
and a blank node shared by two blocks raise `SyntaxError` as the spec requires (the tests expect `ValueError`, class M, O5).

## 3. Per-test-file table

Columns: file (under `packages/starlayer/`), failures, class counts (`class:subreason xN`), one-line reason.

| File | Failures | Classes | Reason |
|---|---:|---|---|
| `tests/graph/integration/test_cross_backend_parity.py` | 4 | D:backend-parity x4 | compares the rdf-1.1 and rdf-1.2 backends; one backend left |
| `tests/graph/integration/test_oxigraph_store_rdf12.py` | 2 | D:backend-parity x2 | old class over an OxigraphStore vs in-memory; the premise is two backends |
| `tests/graph/oxgraph/test_conformance.py` | 5 | D:old-vs-new comparator x5 | runs each scenario on old and new class and compares; goes with the old class (keep scenarios as golden data if wanted) |
| `tests/graph/oxgraph/test_engine_adapter.py` | 6 | X:xpass x6 | strict xfails for the Oxigraph lexical rewrite (#190) pass because the flipped old loader hands over rdflib literals; flip artefact |
| `tests/graph/oxgraph/test_helpers_conformance.py` | 14 | D:old-vs-new comparator x14 | helpers compared against the old class; goes with it |
| `tests/graph/unit/test_conformance.py` | 9 | D:hand-parser warnings (O3) x9 | RDF12ConformanceWarning from the hand-written parsers (VERSION / @version); Oxigraph parsers do not warn (O3) |
| `tests/graph/unit/test_contracts_hunt3.py` | 9 | B:pickle x4, B:xpath-regex x5 | 4 deepcopy/pickle of OxGraph (B-pickle); 5 REPLACE / REGEX XPath semantics Oxigraph does not follow (B-xpath) |
| `tests/graph/unit/test_dataset.py` | 16 | D:rdflib-store x11, M:old-class API: row access, identifiers, isomorphic, str of triple terms, bnode labels x2, M:old-wrapper artefact: identifier scoping, tuple wildcards, prefixes x3 | 11 rdflib store open/close/cache tests (D); 5 old-class API (n3 on a None wildcard, default graph, serialize) (M) |
| `tests/graph/unit/test_dataset_hunt2.py` | 1 | M:old-class API: row access, identifiers, isomorphic, str of triple terms, bnode labels x1 | default-union remove; OxDataset has its own union tests (M) |
| `tests/graph/unit/test_dirlangstring.py` | 3 | M:old-class API: row access, identifiers, isomorphic, str of triple terms, bnode labels x3 | row access of an unbound variable (KeyError), exception type of STRLANGDIR arity (M) |
| `tests/graph/unit/test_entailment.py` | 15 | M:entailment on OxGraph.query x15 | query-time RDF/RDFS entailment raises NotImplementedError on the OLD native path; OxGraph.query implements it (M: point at OxGraph) |
| `tests/graph/unit/test_entailment_hunt2.py` | 10 | M:entailment on OxGraph.query x10 | same: RDFS entailment on the old native path (M) |
| `tests/graph/unit/test_graph_core_round4.py` | 2 | M:old-class API: row access, identifiers, isomorphic, str of triple terms, bnode labels x2 | BNode/URIRef graph names and union counts compared with rdflib Dataset (M) |
| `tests/graph/unit/test_interop.py` | 3 | D:tt: encoding x3 | compares to the tt: encoding (D) |
| `tests/graph/unit/test_io_hunt3.py` | 1 | M:old-class API: row access, identifiers, isomorphic, str of triple terms, bnode labels x1 | used_prefixes on the old class (M) |
| `tests/graph/unit/test_parse_fidelity.py` | 25 | M:lexical forms (O1) x25 | parse keeps "+1.50", "04", "1"^^boolean; Oxigraph canonicalises (M, owner decision O1) |
| `tests/graph/unit/test_parser_fixes.py` | 3 | D:hand parser x3 | hand-written Turtle/TriG parser fixes; the W3C RDF 1.2 suites cover Oxigraph (D) |
| `tests/graph/unit/test_parser_fixes_hunt2.py` | 2 | D:hand parser x2 | hand-written parser fixes (D) |
| `tests/graph/unit/test_parsers_r4.py` | 2 | M:old-class API: row access, identifiers, isomorphic, str of triple terms, bnode labels x1, M:old-wrapper artefact: identifier scoping, tuple wildcards, prefixes x1 | JSON-LD round trip uses Graph.isomorphic; a prefix test on the old class (M) |
| `tests/graph/unit/test_prefixes.py` | 2 | B:api-reduce_prefixes x1, M:old-wrapper artefact: identifier scoping, tuple wildcards, prefixes x1 | reduce_prefixes() missing on OxGraph (B-api); a plain-rdflib used_prefixes test (M) |
| `tests/graph/unit/test_property_paths_hunt2.py` | 2 | B:paths x2 | Oxigraph: zero-length path to an absent constant (upstream issue 1), NPS with an inverse arm gives a set not a bag (B-upstream) |
| `tests/graph/unit/test_proposition_form_encoding.py` | 7 | M:basic-encoding input (O4) x7 | plain `turtle` parse used to adopt the basic encoding as triple terms; OxGraph needs interop.from_basic (M, O4) |
| `tests/graph/unit/test_query_prepare_cache.py` | 10 | D:prepared-query cache x10 | rdflib prepared-query cache (D) |
| `tests/graph/unit/test_rdf12_formats.py` | 5 | D:hand writers (O3) x5 | hand-written writers and the VERSION line (D; VERSION output is O3) |
| `tests/graph/unit/test_rdfc_native.py` | 3 | D:old-vs-new comparator x3 | native vs old rdfc agreement properties (D) |
| `tests/graph/unit/test_shape_derivation.py` | 18 | M:derive_shape on OxGraph x18 | derive_shape tests on the old class; OxGraph.derive_shape exists through the bridge (M) |
| `tests/graph/unit/test_sparql12_grammar_hunt2.py` | 6 | M:error type (O5) x6 | Oxigraph raises SyntaxError where the old parser raised ValueError("not permitted") (M, O5) |
| `tests/graph/unit/test_sparql12_query.py` | 8 | M:old-class API: row access, identifiers, isomorphic, str of triple terms, bnode labels x2, M:old-wrapper artefact: identifier scoping, tuple wildcards, prefixes x6 | prefixed names without PREFIX, str() of triple terms, KeyError on an unbound row value (M) |
| `tests/graph/unit/test_sparql12_update.py` | 1 | M:old-class API: row access, identifiers, isomorphic, str of triple terms, bnode labels x1 | basic-encoding triple left behind by DELETE DATA (M) |
| `tests/graph/unit/test_sparql_builtins_hunt3.py` | 1 | B:boolean-order x1 | false < true is unbound in Oxigraph (B-upstream) |
| `tests/graph/unit/test_sparql_r4_remainders.py` | 1 | M:old-class API: row access, identifiers, isomorphic, str of triple terms, bnode labels x1 | the old wrapper leaks a skolem IRI from STR(bnode); OxGraph already gives unbound as the test wants (M) |
| `tests/graph/unit/test_starlayer_graph.py` | 23 | B:api-from_rdflib x5, D:rdflib-store x6, M:old-class API: row access, identifiers, isomorphic, str of triple terms, bnode labels x3, M:old-wrapper artefact: identifier scoping, tuple wildcards, prefixes x9 | 6 rdflib store lifecycle (D); 5 from_rdflib (B-api: OxGraph.from_rdflib is missing); 12 tuple wildcards, str of triple terms (M) |
| `tests/graph/unit/test_trig_graph_blocks.py` | 2 | D:hand parser x2 | compares the hand TriG parser with rdflib (D) |
| `tests/graph/unit/test_turtle12_serializer.py` | 17 | D:hand writer x17 | hand-written Turtle 1.2 writer (D) |
| `tests/graph/unit/test_turtle_parser.py` | 3 | D:hand parser x3 | hand-written Turtle parser (D) |
| `tests/graph/unit/test_update_hunt3.py` | 13 | B:copy-add x2, M:error type (O5) / prepared query x11 | ValueError to SyntaxError (M, O5); prepared query object (M); COPY/ADD of an absent graph does not raise in Oxigraph (B-upstream) |
| `tests/graph/w3c_sparql12/test_algebra_regenerated_queries.py` | 1 | M:old-class API: row access, identifiers, isomorphic, str of triple terms, bnode labels x1 | compares two runs by raw blank node labels; fresh labels per query (M: compare up to isomorphism) |
| `tests/graph/w3c_sparql12/test_w3c_sparql12_eval.py` | 1 | M:old-class API: row access, identifiers, isomorphic, str of triple terms, bnode labels x1 | op-2: decimal "123.0" comes back "123" (M, O1) |
| `tests/shacl/integration/test_profiling.py` | 1 | M:old-wrapper artefact: identifier scoping, tuple wildcards, prefixes x1 | `.n3()` on a pyoxigraph term in a SHACL profile check (M) |
| `tests/shacl/integration/test_report_text_provenance.py` | 2 | M:graph identifier x2 | the report names the old default graph identifier as used graph (M) |
| `tests/shacl/integration/test_shacl_ui_form_kinds.py` | 1 | M:old-wrapper artefact: identifier scoping, tuple wildcards, prefixes x1 | `StarLayerGraph.from_rdflib(Graph())` then apply_rules goes through a prepared query path (M) |
| `tests/shacl/integration/test_used_graphs_and_configuration.py` | 4 | M:graph identifier x4 | urn:x-rdflib:default identifier appears as the used data graph (M) |
| `tests/shacl/w3c_shacl12/test_w3c_engine_core.py` | 3 | X:xpass x3 | strict xfail XPASS, as in the engine adapter (X) |
| `tests/shacl/w3c_shacl12/test_w3c_engine_core_oxigraph.py` | 3 | X:xpass x3 | strict xfail XPASS (X) |
| `tests/sparql/unit/test_dirlang_string_functions.py` | 40 | M:prepared query object -> text x40 | `graph.query(prepareQuery(...))`; pass text (M) |
| `tests/sparql/unit/test_lower_rdf11.py` | 78 | D:lowering x78 | the lowering layer (D) |
| `tests/sparql/unit/test_phase3_rdf12.py` | 8 | D:lowering/algebra round trip x8 | lowering and algebra round trips through prepareQuery (D) |
| `tests/sparql/unit/test_phase6_serialize12.py` | 1 | M:old-wrapper artefact: identifier scoping, tuple wildcards, prefixes x1 | query text relies on graph-bound prefixes on the old path (M) |
| `tests/sparql/unit/test_star_query.py` | 5 | M:entailment on OxGraph.query x3, M:prepared query object -> text x2 | RDFS entailment on the old native path; prepared query (M) |
| `tests/sparql/w3c_sparql12/test_w3c_sparql12.py` | 1 | M:old-class API: row access, identifiers, isomorphic, str of triple terms, bnode labels x1 | op-2 decimal lexical form (M, O1) |

Notes on the table. Counts include only the failing tests of a file; a file marked D usually has passing tests too, and the module
tests listed in `phase-c-dependency-inventory.md` ("Tests") that did not fail here (for example `test_operator_patches.py`,
`test_direct_query.py`, `test_remote_decompose.py`, `test_lowering_hunt3.py`, `test_native_and_update_hunt2.py`,
`test_skolem_semantics.py`, `test_rdflib_inherited_contract.py`, `test_result_patches.py`, `test_entailment_rdf.py`,
`test_entailment_rdfs.py`) still go with their modules. The D-class files fully or mostly deleted are about 7,000 test lines, plus about 850
for those module tests.

## 4. Answers

### (1) Can B1 be done before D1?

Not as deletions. As the work that decides whether the deletions are safe, yes. The owner's suspicion is right in one way: the native
path already sends text straight to Oxigraph, and flipping the default breaks only 3.2 percent of the run (403 of 12,580 run), 185 of
them tests of code that goes anyway. But B1 as a separate branch has nothing left to delete once the old class is considered:

- Every module B1 names (`backends/native`, `skolem_semantics`, `native_oxigraph`; the seven rdflib patch modules, `custom_functions`,
  `query_cache`, `remote_decompose`, `sparql_api`, `direct`, `version_directive`; `lower_rdf11`, `entailment_rdf`, `entailment_rdfs`) is
  class **a** in `phase-c-dependency-inventory.md` and in the `d1-readiness.md` section 2 deletion list (8,496 lines of its 19,349).
  The importer table (`d1-readiness.md` section 1) shows what holds them: `graph/graph/starlayer_graph.py` / `starlayer_dataset.py` (not in
  the table because D1 deletes them; they import `backends.native`, `query_cache`, `custom_functions`; `backends.native` imports
  `lower_rdf11` and `operator_patches`), and the facade rows `starlayer/graph/__init__.py` (imports and installs all seven patch
  modules, `sparql_api`, `custom_functions`), `graph/graph/__init__.py`, `graph/query/__init__.py` (`sparql_api`), plus
  `starlayer/__init__.py` (re-exports the names). Those five rows unblock only with D1.
- The `rdf-1.1` code inside the old classes is 127 + 23 lines that mention `_tt_registry`, `_tt_nodes`, `tt:HASH`, `_is_native`,
  `TT_NS` or `rdf-1.1`, interleaved with the native branches of a 5,237-line pair. Cutting them out of classes D1 deletes next is work
  with no end state.
- `model/encoding.py` (433 lines) cannot go whole: `encode_dirlang_datatype` / `decode_dirlang_datatype` are used by live
  `compare.py` and `oxgraph/_rdflib_bridge.py`. About 380 lines of the `tt:` machinery go; the dirlang pair (about 50 lines) moves.
- The one importer-table row that is not D1-only is `oxgraph/_rdflib_bridge.py` (`starlayer_graph()`), unblocked by `mig-small-ports`
  (port `shape_derivation`), which is independent of B1.

So B1's deletions are a subset of D1's. What B1 still needs before D1 is behaviour work: the B1/B2 gaps of section 2, the rewrite of the
186 M tests onto `OxGraph`, and the owner decisions of section 6. The facade side effect (`import starlayer.graph` installs patches
into rdflib; `d1-readiness.md` section 6 item 3) goes with D1 and is decision O8.

### (2) Smallest safe sequence to a tree with no rdflib-store backend

| Step | Branch | Does | Deletes |
|---|---|---|---|
| 0 | (owner) | decisions O1 to O8 below | - |
| 1 | `mig-b1-gaps` | `OxGraph.from_rdflib`, `reduce_prefixes`, `add_reifier_annotation`, `__deepcopy__` / `__reduce__` (B1, B2); strict xfails and an entry in `oxigraph-upstream-issues.md` for B3 to B6 | 0 (adds about 100 lines) |
| 2 | `mig-small-ports` (already planned) | port `shape_derivation`; remove `_rdflib_bridge.starlayer_graph()` | about 0 now (the old graph import goes) |
| 3 | `mig-d2-oxgraph-tests` | rewrite the 186 M tests (and, in the same pass, the other D2 files) onto `OxGraph`/`OxDataset` and text queries; assertions change as in section 5; tests only, library untouched, suite green on the old default | 0 library lines |
| 4 | `mig-d1` | delete the D tests; rename `OxGraph` to `StarLayerGraph`, `OxDataset` to `StarLayerDataset`; rewrite the facades; delete the old classes and every module only they import (this is B1) | 19,349 library lines: old classes 5,549, prefixes 136, parsers 3,770, serializers 1,398, **B1: backends 1,012, rdflib query machinery 5,073, lowering and entailment 2,411 (8,496)**; `model/encoding.py` about 380; the D-class tests (about 7,900 lines) |
| 5 | `mig-d3-d4` | regenerate docs, code KG, notebook links; rdflib to an optional extra | generated files |

Steps 3 and 4 can be separate branches because step 3's tests use only the `OxGraph` API (they run before and after the rename). If the owner wants B1 isolated anyway, the only honest intermediate is
`mig-b1-flip`: default the old class to `rdf-1.2` and remove the `backend=` argument; it deletes no module (the old class still imports
them) and only prunes branch code inside the 5,237-line pair (estimate 600 to 900 lines, not measured). Not recommended: all of it
dies in step 4.

### (3) Behaviour differences users would see

| Difference | Old default | Native / `OxGraph` | Needs owner decision |
|---|---|---|---|
| Literal lexical forms (25 tests, 3 W3C) | kept as written (faithful default, `lexical-fidelity-default.md`): `"+1.50"^^xsd:double`, `"04"`, `"1"^^xsd:boolean`, `1.50` | canonical on parse: `1.5`, `4`, `true`; `"4.0"^^xsd:decimal` is `"4"`; derived numeric types rewritten to `xsd:integer` (#190) | **O1**: this reverses the 2026-10-31 decision (turtle is faithful). Accept, or keep spelling by a side table |
| Blank nodes | labels from the source kept inside a graph | relabelled on parse (`_:a` is lost); stable across queries of one store; a label may not be shared by two update blocks (spec; error) | no (documented), but note it in the migration guide |
| Result and triple order | rdflib store order; trees in source order | store order (also property order in a tree; already accepted in `d1-readiness.md` 4.2) | no |
| Graph identifier | `urn:x-rdflib:default` or a BNode; appears as used data graph in SHACL reports | `DefaultGraph`; no used-graph line | O5: report provenance for the default graph |
| Query result objects | rdflib `ResultRow` (unbound is `KeyError` on mapping access), prepared `Query` objects accepted by `query()` | `Row` (unbound is `None`); text only | O6 (42 tests use `prepareQuery`) |
| Exceptions | `ValueError("not permitted")`, rdflib parse exceptions | `SyntaxError` from Oxigraph | O5 (error type, 17 tests) |
| Triple term `str` | prefixed names (`<<( :bob :knows :carol )>>`) | full IRIs | no |
| Conformance warnings | `RDF12ConformanceWarning` for `VERSION` / `@version` mismatches, 9 tests | none | **O3** |
| `VERSION` line on write (nt, nq, trig) | written by the hand serializers | not written | O3 |
| Plain `turtle` parse of a basic-encoding document | adopted as real triple terms | stays plain triples; `interop.from_basic` converts | **O4** (7 tests) |
| Tuple wildcards (`triples((None, None, (None, None, None)))`), `triples_choices`, `Graph.isomorphic`, `open`/`close`/stores | supported | `TypeError` / absent | O6 |
| Pickle, deepcopy | supported | `TypeError` (B1) | O2 |
| SPARQL deviations (B3 to B6) | rdflib evaluator, patched toward the spec | Oxigraph's own | **O7** |

## 5. What each M test changes

- Pass the query as text (and `initNs=` if needed); drop `prepareQuery` (42).
- Query-time RDF/RDFS entailment: call `OxGraph.query(text, entailment=...)` (the old native path raises `NotImplementedError`; `OxGraph`
  has it since `mig-query-entailment`) (28).
- Lexical-form tests assert the canonical form, or are moved to the faithful-parse decision (25 plus 3).
- Row access by `row[var]` or `row.asdict()`; unbound is `None`.
- Exceptions: `pytest.raises(SyntaxError)`.
- derive_shape tests: call `OxGraph.derive_shape` (18).
- Identifier tests: `DefaultGraph`.
- Triple-term wildcards: use `ox.Triple` patterns or SPARQL.
- `test_algebra_regenerated_queries`: compare rows up to blank-node isomorphism.

## 6. Decisions needed

- **O1** Lexical forms: accept Oxigraph's canonical forms for the default class (reverses the faithful-parse decision), or keep the
  spelling (cost: a side table and a custom serializer; Oxigraph cannot).
- **O2** Keep pickle and `deepcopy` of the graph classes (adds about 30 lines), or drop them with the old class.
- **O3** `RDF12ConformanceWarning` and the `VERSION` line on write: drop with the hand-written parsers and writers, or re-implement in the
  wrapper (`ntversion.py` already validates the directive for N-Triples).
- **O4** Should `parse(format='turtle')` keep adopting the RDF 1.2 basic encoding as triple terms, or is `interop.from_basic` the only way?
- **O5** Exception types (`SyntaxError`) and the used-graph line for the default graph in SHACL reports.
- **O6** Old-class API with no `OxGraph` counterpart: prepared query objects, tuple wildcards for triple terms, `triples_choices`,
  `isomorphic`, rdflib store lifecycle. Drop all (the plan's "give-ups"), or port any.
- **O7** The Oxigraph deviations B3 to B6 (REPLACE and REGEX XPath rules, boolean `<`, negated property set bag, COPY/ADD of an absent graph):
  accept with strict xfails and an upstream issue, or patch client-side.
- **O8** `import starlayer.graph` stops installing rdflib patches (`d1-readiness.md` section 6 item 3). Accept (the earlier plan did).
- Sequencing: confirm that B1 is folded into D1 (section 4, answer 2) rather than run as its own branch.

## 7. Reproducing

`python scripts/b1_flip_experiment.py apply` in a clean worktree, then
`python -m pytest tests --deferred -n 4 -q --junitxml=run1.xml` from `packages/starlayer` with `PYTHONHASHSEED=0`, then
`python scripts/b1_classify.py run1.xml`. Restore the two files under `starlayer/graph/graph/` from the index afterwards. The probes of
sections 2 and 4 used `pyoxigraph` 0.5.13 and `OxGraph` directly (zero-length path, boolean ordering, REPLACE, COPY/ADD, NPS, pickle,
lexical forms, `from_basic`).
