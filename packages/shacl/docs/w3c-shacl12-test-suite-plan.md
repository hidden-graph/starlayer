# W3C SHACL 1.2 Test Suite Integration Plan

*Last reviewed: 2026-07-31*

**Status (2026-08-15, re-synced from the 2026-08-01/2026-07-30 pin): Phases 1, 2, and 3 all done, triaged, and every fixable finding fixed.** `sht:Validate` (`tests/core/`+`tests/sparql/`), `sht:EvalNodeExpr` (`tests/node-expr/`), and `sht:Infer` (`tests/sparql/rules/`) entries are all wired up - **320 passed, 5 xfailed (all reasoned, `strict=True`), 0 unexplained failures combined**, pinned to `gh-pages` commit `59b38cd7061ff3e6e3dc9e216836ef848f7d8baf` (up from `e5311eef94ac9a6bd15fd22ecfe256c658ef1bc1`). The re-sync (24 added / 2 removed net) surfaced 11 new results, resolved the same session: 7 fixed (new SHACL 1.2 SPARQL Extensions §8 rule-execution predicates - `sh:layer`/`sh:runOnce`/`sh:expectedPredicate`/`sh:tempTriple` - plus a genuine pre-existing fixpoint-iteration bug in the global/unattached-rule execution path, exposed by 4 new RDFS-entailment fixtures), 4 newly xfailed with real reasoning (`run-once-example` - a deeper implicit-class-target-recomputation-timing gap; 3 `sh:ListParameterExpressionFunction` fixtures - a genuinely separate, unimplemented user-definable-custom-SPARQL-function feature). See `docs/shacl12-gap-matrix.md`'s "SHACL 1.2 SPARQL Extensions" rows for the full technical writeup. The 1 pre-2026-08-15 xfail is a plain-`rdflib` fixture-formatting quirk deliberately left unpatched (`seconds-example` - patching it would make rdflib's output *less* spec-compliant elsewhere) - it does not represent open work. Two earlier "out of scope"/"deliberate limitation" framings were since revisited and fixed: 9 fixtures depending on 2 rdflib SPARQL-evaluator bugs (now monkeypatched directly in `starlayergraph`, the same technique already used elsewhere in this project for pySHACL internals), and 2 fixtures (`subsetOf-002`, `instancesOf-base-class`) that turned out to be narrow implementation choices rather than structural gaps - see `docs/starlayergraph-upstream-change-log.md`'s 2026-08-01 entry and `docs/shacl12-gap-matrix.md`'s Phase 1/2 writeups. See `docs/shacl12-gap-matrix.md`'s "W3C SHACL 1.2 Test Suite Integration" section for the full results summary and `tests/w3c_shacl12/known_failures.py` for exact per-entry reasons. Only "Not scheduled": SRL (`tests/rules/`) - see "Scope decision" below.

Both phases found and fixed real bugs rather than just cataloguing them, at the user's explicit direction each time:

- **Phase 1** (2026-07-30): 4 `starlayergraph` `StarLayerTurtleParser`/`StarLayerGraph.parse()` bugs, fixed directly in that repo - see `docs/starlayergraph-upstream-change-log.md`'s 2026-07-30 entries. `tests/w3c_shacl12/manifest.py`'s local `_resolve_relative_uris` workaround was removed accordingly. One Phase 1 finding (`sh:expression` "not implemented") was also found to be a false positive on re-check - the harness needed `advanced=True`, not a missing feature - see the gap matrix's "Self-correction" note.
- **Phase 2** (2026-07-31): a core correctness bug affecting most `shnex:` list-argument operators, several smaller `shnex:` bugs, the entire previously-unimplemented `sparql:` node-expression namespace (~74 SPARQL functions/operators), one more `starlayergraph` lexical-form bug, and a real `validate()`/`apply_rules()` wiring gap for shapes graphs using only `sparql:` (not `shnex:`) node expressions - all fixed in `starshacl` (and one in `starlayergraph`); see the gap matrix's Phase 2 section for the full list.

The W3C Data Shapes Working Group publishes an official SHACL 1.2 test suite at
[w3c/data-shapes, `gh-pages` branch, `shacl12-test-suite/`](https://github.com/w3c/data-shapes/tree/gh-pages/shacl12-test-suite).
This did not exist when `docs/implementation-plan.md` and `docs/shacl12-gap-matrix.md` were
last written (both explicitly say "no W3C test suite exists" for any of the six SHACL 1.2
documents) - that statement is now stale and should be corrected as part of this work.

This plan covers (1) a one-time integration of the suite as it exists today, and (2) a
repeatable procedure for absorbing it as the Working Group continues to grow and change it -
confirmed live that it is still actively under construction (see "Suite anatomy" below).

## Suite anatomy (confirmed by direct inspection, 2026-07-30)

The suite reuses the DAWG-style test-manifest format from the original (SHACL 1.0)
`data-shapes-test-suite`, at `tests/manifest.ttl`, recursively including per-directory
manifests via `mf:include`. Top-level manifest currently includes three of four test
directories:

| Directory | Wired into top-level `manifest.ttl`? | Leaf test files | Test-entry vocabulary |
| --- | --- | --- | --- |
| `tests/core/` | Yes | 158 `.ttl` | `sht:Validate` |
| `tests/sparql/` | Yes | 31 `.ttl` | `sht:Validate` (162 with inline `sh:ValidationReport`, 7 `sht:Failure`), `sht:Infer` (6) |
| `tests/node-expr/` | Yes | 102 `.ttl` | `sht:EvalNodeExpr` (145 entries) |
| `tests/rules/` | **No** - not `mf:include`d from the top-level manifest | 36 `.ttl` + 166 `.srl` | `srt:RulesPositiveSyntaxTest`/`RulesNegativeSyntaxTest`/`RulesEvalTest`/`RulesPositiveWellFormednessTest`/`RulesNegativeWellFormednessTest`/`RulesPositiveStratificationTest`/`RulesNegativeStratificationTest` |

Four distinct test-entry shapes exist, each needing its own runner:

1. **`sht:Validate`** (the bulk of the suite, `core/` + `sparql/`). `mf:action` gives
   `sht:dataGraph`/`sht:shapesGraph` (IRIs, usually both `<>` - i.e. the test file parses
   into one graph serving as both data and shapes graph - but sometimes distinct sibling
   files, e.g. `core/complex/personexample.ttl` + `core/complex/shacl-shacl.ttl`). `mf:result`
   is either an inline `sh:ValidationReport` (a `sh:conforms` boolean plus a set of
   `sh:result` blank nodes - present for 162 of the `sht:Validate` entries) or the atom
   `sht:Failure` (7 entries - the test is expected to make validation itself fail/raise,
   not merely non-conform; sampled example: an `sh:sparql` constraint using an unsupported
   SPARQL `SERVICE` clause).
2. **`sht:EvalNodeExpr`** (`node-expr/`, per `tests/node-expr/README.md`, quoted in full since
   it's the authoritative format description): evaluate the node expression given by
   `sht:nodeExpr` (optionally seeded with `sht:focusNode`, and `sht:scope-XY` for named
   variables), compare the output node list against the `rdf:List` in `mf:result`.
   `sht:ignoreOrder` relaxes ordering (cardinality must still match) when present.
3. **`sht:Infer`** (6 entries, `sparql/rules/`): run rule inferencing over `sht:dataGraph`/
   `sht:shapesGraph`, compare the resulting *added* triples against the `rdf:List` of
   `( subject predicate object )` triples in `mf:result` (empty list for a
   deliberately-inert case like a `sh:deactivated` rule).
4. **SRL-based `srt:*` types** (`rules/`): these test the Shape Rules Language's own
   concrete *text* syntax (parse `.srl` files directly, not RDF `sht:Validate` fixtures) -
   syntax positive/negative, well-formedness positive/negative, stratification
   positive/negative, and eval tests. This is a fundamentally different mechanism (a text
   parser, not a `sh:rule`/`sh:TripleRule` RDF structure).

## Scope decision: what this plan covers now vs. defers

**In scope**: `sht:Validate`, `sht:EvalNodeExpr`, `sht:Infer` - all three map directly onto
`StarShaclValidator.validate()` / `apply_rules()` / `starshacl.node_expressions.eval_expr()`,
the library's actual public surface. This is 291 of the 391 leaf-level RDF test files (158 + 31 + 102).

**Deferred, not built**: the `rules/` SRL text-syntax tests. `docs/shacl12-gap-matrix.md`'s
"Not Covered / Deferred" table already excludes "Shape Rules Language (SRL) concrete text
syntax" for starshacl itself (SRL compiles to the same `sh:rule` RDF vocabulary the
library already executes; parsing the human-authoring text syntax is a separate, currently
unneeded capability). Building an SRL parser purely to consume these 166 `.srl` fixtures would
be scope creep beyond what this test-suite-integration task calls for - consistent with that
existing decision, not a new one. Revisit together if/when SRL parsing itself becomes a real
feature (same trigger condition already recorded in the gap matrix).

## Vendoring mechanism

A pinned, vendored snapshot lives at `tests/vendor/shacl12-test-suite/`, refreshed by a
small, re-runnable script rather than a git submodule - this matches the project's existing
style of manual-but-documented, repeatable upstream-tracking procedures (see the gap
matrix's "Tracking Upstream Spec Changes" section) rather than introducing new git tooling.

- `scripts/sync_w3c_shacl12_suite.py`: downloads the `shacl12-test-suite/` subtree from a
  **pinned commit SHA** on `w3c/data-shapes`'s `gh-pages` branch (via the GitHub REST API's
  recursive tree + raw-content endpoints, no `git submodule`/no full-repo clone needed since
  the target is one subtree of a much larger repo that also bundles the unrelated SHACL 1.0
  suite), and writes it verbatim into `tests/vendor/shacl12-test-suite/`, replacing whatever
  was there. Records the pinned SHA and sync date in a `tests/vendor/shacl12-test-suite/VENDORED_FROM.md`
  stamp file (source URL, commit SHA, ISO date, file/entry counts at sync time) so a diff of
  that one file tells a reviewer exactly what changed and when, without needing `git log`
  archaeology on the vendored `.ttl` files themselves.
- The pinned SHA is a constant at the top of the sync script - bumping it is a deliberate,
  reviewable one-line change, not an automatic moving target. This is the same "manual,
  explicit, one commit to update" posture as the six-document spec-baseline tracking already
  in `docs/shacl12-gap-matrix.md`.
- Vendored files are committed to the repo (not `.gitignore`d) so `tests/` remains fully
  self-contained and offline-runnable, matching every other fixture already under `tests/`.

## Harness architecture

New package: `tests/w3c_shacl12/` (parallel to `tests/integration/`, `tests/unit/`).

- **`tests/w3c_shacl12/manifest.py`** - a generic DAWG-manifest walker, independent of test
  type: given a manifest IRI/path, resolve `mf:include` recursively and `mf:entries`
  (`rdf:List`) at each level, yielding `(entry_iri, entry_type, source_file)` tuples. Each
  leaf `.ttl` file is parsed exactly once into an `rdflib.Graph` (cached per absolute path,
  since a single file commonly defines both its own manifest *and* the data/shapes triples
  the entry's `mf:action` references via `<>`).
- **`tests/w3c_shacl12/closure.py`** - a small "RDF closure from a node" helper: given a graph
  and a node (e.g. an `mf:result` blank node holding an inline `sh:ValidationReport`), walk
  outgoing triples recursively (following blank-node objects) to extract just that
  substructure as an independent graph, needed because the expected report lives inline in
  the same file as everything else, not as a separate document.
- **Per-test-type runner + comparator, one module each:**
  - `test_w3c_validate.py` (`sht:Validate`): loads `sht:dataGraph`/`sht:shapesGraph` (usually
    the same parsed file, occasionally distinct sibling files - resolved generically by IRI,
    not hardcoded to `<>`), calls `StarShaclValidator().validate(...)`. For an inline
    `sh:ValidationReport` expectation: compare `conforms` first (cheap, catches the common
    case fast), then compare the **multiset** of `sh:result` entries structurally - by
    `(focusNode, resultPath, sourceConstraintComponent, value, severity)` tuples, not graph
    isomorphism or exact blank-node identity, since `sourceShape` values and blank-node IDs
    are not guaranteed stable across implementations and pySHACL's own reports don't promise
    them either. For `sht:Failure`: assert `validate()` raises (currently expected to be
    `pyshacl.errors.ValidationFailure`/`ReportableRuntimeError` per
    `docs/pyshacl-upstream-issues.md`'s existing conventions - confirm exact exception type
    empirically per-case during Phase 1, don't assume).
  - `test_w3c_node_expr.py` (`sht:EvalNodeExpr`): calls
    `starshacl.node_expressions.eval_expr(expr, focus_node, data_graph, shapes_graph, scope)`
    directly (the library's actual internal entry point - already used this way in
    `tests/unit/test_validator.py` and `tests/integration/test_shnex_node_expressions.py`, so no
    new public API is needed), building `scope` from any `sht:scope-XY` triples on the
    action. Compares the returned node list against `mf:result`'s `rdf:List`, order-sensitive
    unless `sht:ignoreOrder` is present (in which case compare as multisets).
  - `test_w3c_infer.py` (`sht:Infer`): snapshot the data graph, call
    `StarShaclValidator().apply_rules(...)`, diff added triples against the snapshot, compare
    against `mf:result`'s `rdf:List` of `(s p o)` triples as a set.
- **Pytest wiring**: each runner module uses `pytest_generate_tests` (or an equivalent
  fixture-parametrization) to walk the relevant vendored manifest at collection time and
  produce one parametrized test per manifest entry, with a readable test ID derived from the
  entry's local name (e.g. `core/node/and-001`) - so a single failing W3C test shows up as one
  specific, greppable pytest node ID, not a monolithic "suite failed" result.
- **`meta_shacl` defaults to `False`** for every W3C-suite call: these fixtures are the
  Working Group's own established-correct shapes, not shapes whose well-formedness this repo
  is trying to test - running starshacl's meta-shacl preflight against them would be
  testing the wrong thing (and risks spurious failures if a fixture uses an SHACL 1.2 form
  starshacl's own meta-shapes haven't been told about yet, which would then read as a
  suite failure rather than what it actually is).

## Known-failures registry (not blanket skips)

Given `docs/shacl12-gap-matrix.md` already documents specific, deliberate gaps (`sh:PropertyRule`/
`sh:values` unimplemented; SPARQL `SERVICE` unsupported; etc.), expect some suite entries to
legitimately fail on first run. Per this repo's `CLAUDE.md` testing discipline, the response
to a failing conformance test is never a silent skip - it's one of:

1. **A real, fixable gap** - fix it, the test starts passing.
2. **A already-known, deliberate scope boundary** (matches an existing gap-matrix "Not
   Covered / Deferred" row) - mark `xfail(strict=True, reason="...")` with a reason that
   names the specific gap-matrix row, so the xfail breaks loudly (as a new *pass*, i.e.
   `XPASS`) the moment the gap is closed, rather than silently rotting.
3. **A confirmed upstream pySHACL bug** - same treatment, reason pointing at the specific
   `docs/pyshacl-upstream-issues.md` entry.
4. **Working-Draft churn** - the test itself encodes a reading of the spec that has since
   changed, or conflicts with a documented starshacl interpretation - reason explains
   the discrepancy explicitly; this is the rare case and should be treated with suspicion
   first (assume starshacl is wrong until checked, not the test).

The registry (`tests/w3c_shacl12/known_failures.py`, a plain dict keyed by entry IRI ->
reason string) is reviewed the same way `docs/shacl12-gap-matrix.md`'s tables are: every entry
is a claim that should still be true, not a historical record to leave stale.

## Phased implementation

1. **Phase 1 - `sht:Validate` (`core/` + `sparql/`'s 189 `.ttl` files, ~193 entries). Done
   (2026-07-30), 165 passed / 0 xfailed as of 2026-08-01.** The largest and highest-value
   slice - this is direct `validate()` conformance, the library's core promise. All 19
   originally-found genuine findings have since been fixed, including `subsetOf-002`
   (compound sequence-path comparison, fixed 2026-08-01 by converting `sh:subsetOf`'s
   comparison path via pySHACL's own `shacl_path_to_sparql_path` rather than requiring a
   simple IRI).
2. **Phase 2 - `sht:EvalNodeExpr` (`node-expr/`'s 102 files, 145 entries). Done (2026-07-31),
   142 passed / 1 xfailed as of 2026-08-01.** Directly exercises `starshacl/node_expressions.py`
   (and, as of this phase, the new `starshacl/sparql_node_expressions.py`) - confirmed
   live to be the newest and most spec-volatile area per `docs/shacl12-gap-matrix.md`: surfaced
   a core correctness bug and several smaller ones in existing `shnex:` operators, plus a
   wholly unimplemented `sparql:` node-expression namespace. All fixed, including 5 of the 6
   fixtures originally xfailed as "out-of-scope plain-`rdflib` quirks" - `starlayergraph` now
   monkeypatches the 2 underlying rdflib SPARQL-evaluator bugs (see
   `docs/starlayergraph-upstream-change-log.md`'s 2026-08-01 entry) - and `instancesOf-base-class`,
   fixed by making `shnex:instancesOf` walk `rdfs:subClassOf` directly (via the same
   `_transitive_subclasses` helper `sh:ShapeClass` uses) rather than relying on the caller's
   `inference=` setting. The 1 remaining xfail is a plain-`rdflib` fixture-formatting quirk
   deliberately left unpatched (`seconds-example` - patching it would make rdflib's output
   less spec-compliant elsewhere).
3. **Phase 3 - `sht:Infer` (`sparql/rules/`'s 6 entries). Done (2026-07-31), 6 passed / 0
   xfailed as of 2026-08-01.** Small, as expected; the manifest walker/harness pieces it
   needed already existed from Phases 1-2. Surfaced one genuine new SHACL 1.2 feature - a
   "global" (shape-independent) `sh:SPARQLRule` node, which pySHACL's rule discovery never
   finds at all - since implemented, scoped to `sh:SPARQLRule` (see
   `docs/shacl12-gap-matrix.md`'s "Not Covered / Deferred" table for why `sh:TripleRule`
   wasn't extended the same way). The 4 fixtures originally xfailed on the Phase 2
   rdflib integer-multiplication-yields-decimal quirk now pass, fixed by the same
   `starlayergraph` monkeypatch.
4. **Not scheduled**: SRL (`rules/`) - see "Scope decision" above.

Each phase ends with the full triage pass described in "Known-failures registry" - a phase
isn't "done" until every failing entry has a specific, reasoned disposition, not just a
green checkmark on the entries that already passed.

## Ongoing maintenance: absorbing suite growth over time

The suite is confirmed still actively growing (`rules/` exists with real content but isn't
even wired into the top-level manifest yet - the Working Group is still assembling it). This
needs a repeatable procedure, not a one-time import:

1. **Re-run `scripts/sync_w3c_shacl12_suite.py`** with an updated pinned SHA (bump it, don't
   auto-follow `gh-pages`'s tip) whenever `docs/shacl12-gap-matrix.md`'s existing "Tracking
   Upstream Spec Changes" review cadence flags it worth checking, or whenever a specific
   SHACL 1.2 behavior change is being investigated anyway.
2. **Diff manifest entries before/after the sync**, not just file contents - a small helper
   (`scripts/diff_w3c_shacl12_manifest.py`, or a documented manual `git diff` procedure over
   `tests/vendor/shacl12-test-suite/`) listing entries added, removed, or changed since the
   last recorded sync. New entries need the Phase-1-style triage pass (pass, or reasoned
   xfail); removed entries need their `known_failures.py` rows cleaned up so the registry
   doesn't accumulate stale references to tests that no longer exist; changed entries
   (same IRI, different expected result) need a fresh look since that's a signal the Working
   Group's own understanding of correct behavior shifted.
3. **If `rules/` ever gets wired into the top-level `manifest.ttl`** (i.e. the Working Group
   finishes assembling it) or a fifth top-level test directory appears, that's a prompt to
   revisit the "Scope decision" section above, not to silently ignore new content the sync
   script would otherwise pull in unnoticed. The sync script should log (not silently drop)
   any top-level manifest directory it doesn't yet have a runner for.
4. **Record results in `docs/shacl12-gap-matrix.md`**: replace the stale "no W3C test suite
   exists" line in `docs/implementation-plan.md` (line 16) and add a short "W3C Test Suite
   Conformance" summary (pass/xfail counts per phase, last-synced SHA and date) alongside the
   existing per-document coverage table, so suite conformance becomes part of the same
   single source of truth the rest of SHACL 1.2 status already lives in, rather than a
   separate, easily-forgotten tracker.

## Open questions to resolve empirically during Phase 1 (not assumed up front)

- Exact exception type/shape pySHACL raises for each of the 7 `sht:Failure` cases - may
  differ per case (unsupported `SERVICE`, other unsupported-feature cases) rather than one
  uniform exception.
- Whether `sh:sourceShape` should be included in the `sht:Validate` result-comparison tuple
  for any subset of tests where the suite's own fixtures pin it to a *named* (non-blank)
  shape IRI - if so, comparing it for named-IRI cases while excluding it for blank-node cases
  gives strictly more coverage than dropping it universally.
- Whether any `core/complex/` entries that reference `shacl-shacl.ttl` are meta-shacl
  self-tests in disguise (validating SHACL shapes against SHACL-SHACL) rather than ordinary
  data validation - these may need `meta_shacl`-style handling rather than the Phase 1
  default of `False`, and should be identified individually rather than assumed away.
