# starshacl Implementation Plan

*Last reviewed: 2026-08-01*

starshacl is a `pyshacl` wrapper that adds native RDF 1.2 triple-term support and full SHACL 1.2 Core coverage. The architecture is "pySHACL wrapper with a growing set of native carve-outs" - not a from-scratch rebuild of pySHACL. See `docs/shacl12-gap-matrix.md`'s "Note on Architecture Direction" for why, and what that means for adding new features.

## Current Status

- **SHACL 1.2 Core**: fully implemented. See `docs/shacl12-gap-matrix.md`'s Full Changelog Coverage table.
- **The other five SHACL 1.2 documents** (SPARQL Extensions, Node Expressions, Rules, User Interfaces, Profiling): covered to the depth documented in `docs/compatibility.md`'s RDF / SHACL Version Support section and `docs/shacl12-gap-matrix.md`'s per-document table.
- **RDF 1.1 and RDF 1.2** (triple terms, `rdf:dirLangString`) share one validation/rules path - no separate runtime modes.
- **Known pySHACL bugs and starshacl's workarounds**: `docs/pyshacl-upstream-issues.md` and `docs/compatibility.md`'s "starshacl and pySHACL" section.
- **Test suite**: 789 passed, 7 skipped (6 Oxigraph/Fuseki-gated, clean without a running instance; 1 W3C-suite parse-health placeholder, expected now that no fixtures fail to parse), 1 xfailed (W3C SHACL 1.2 test suite finding - reasoned and `strict=True`; a plain-`rdflib` fixture-formatting quirk deliberately left unpatched, `seconds-example`, see `docs/shacl12-gap-matrix.md`'s "W3C SHACL 1.2 Test Suite Integration" section). Two earlier rounds of "permanently out of scope"/"already-documented deliberate limitation" xfails (11 fixtures total) were revisited 2026-08-01 and fixed: `starlayergraph` now monkeypatches 2 confirmed plain-rdflib SPARQL-evaluator bugs directly (integer-multiplication type promotion, decimal-result canonical lexical form), `sh:subsetOf` now supports any SHACL property path (not just a simple IRI) via pySHACL's own `shacl_path_to_sparql_path`, and `shnex:instancesOf` now walks `rdfs:subClassOf` directly instead of relying on the caller's `inference=` setting - see `docs/starlayergraph-upstream-change-log.md`'s 2026-08-01 entry and `docs/shacl12-gap-matrix.md`'s Phase 1/2 writeups.
- What changed and why, in detail: `CHANGELOG.md` and `git log`.

**Spec baseline caveat**: all six SHACL 1.2 documents are tracked against Working Draft (First Public Working Draft for User Interfaces) TR-track snapshots - none are Candidate Recommendation yet. Re-verify wording against the live TR pages before relying on it. RDF 1.2 itself (tracked by `starlayergraph`) reached Candidate Recommendation 2026-04-07 - one stage ahead of any SHACL 1.2 document.

**W3C test suite**: the Working Group has since published an official SHACL 1.2 test suite (`w3c/data-shapes`'s `shacl12-test-suite/`, still actively growing). Phases 1 (`sht:Validate`), 2 (`sht:EvalNodeExpr`), and 3 (`sht:Infer`) are all integrated and **every fixable finding has been fixed** - see `docs/w3c-shacl12-test-suite-plan.md` for the plan and `docs/shacl12-gap-matrix.md`'s "W3C SHACL 1.2 Test Suite Integration" section for the full list (a core `shnex:` correctness bug, the entire previously-missing `sparql:` node-expression namespace, 5 `starlayergraph` parser/lexical bugs, a `starlayergraph` monkeypatch for 2 confirmed plain-`rdflib` SPARQL arithmetic bugs, generalized `sh:subsetOf` to any SHACL property path, generalized `shnex:instancesOf` to walk `rdfs:subClassOf`, 2 confirmed pySHACL bugs (`docs/pyshacl-upstream-issues.md` Issues 5-6), and roughly 20 starshacl findings ranging from single-line fixes to new SHACL 1.2 features - `sh:nodeByExpression`, SELECT-based `sh:targetNode`, per-constraint `sh:severity`/`sh:deactivated` annotations, `sh:values` on property shapes, ambient prefix discovery, and global (shape-independent) `sh:SPARQLRule`). The 1 remaining xfail is a plain-`rdflib` fixture-formatting quirk deliberately left unpatched (`seconds-example` - patching it would violate XSD decimal's canonical form elsewhere) - it does not represent open work.

## Next Steps

1. Report the logged pySHACL bugs upstream (`docs/pyshacl-upstream-issues.md`).
2. Periodically re-check all six SHACL 1.2 documents against the live TR-track for spec deltas - see `docs/shacl12-gap-matrix.md`'s "Tracking Upstream Spec Changes" section for the procedure.
3. `sh:conformsTo` convenience helper (SHACL 1.2 Profiling) - deliberately not built, since it needs a caller-supplied IRI-naming convention for data/shapes graphs that doesn't exist generically yet. See `docs/shacl12-gap-matrix.md`'s Follow-up list.
4. **Done**: W3C SHACL 1.2 test suite integration, all three in-scope phases (Phases 1-3), per `docs/w3c-shacl12-test-suite-plan.md` - including fixing every genuine gap/bug the three phases found (20 items: 8 starshacl bugs, 6 new SHACL 1.2 features, 1 test-harness fix, 5 `starlayergraph` bugs handled as part of the same effort). See `docs/shacl12-gap-matrix.md`'s "W3C SHACL 1.2 Test Suite Integration" section and `tests/w3c_shacl12/known_failures.py` for the final, itemized disposition of every entry (all 12 remaining xfails are permanently out of scope or confirm already-documented limitations).

**Correction**: the previous "no known feature gaps remain" claim here no longer held once the W3C test suite (item 4) surfaced several genuine ones the hand-written test suite hadn't caught - all have since been fixed (see item 4 above). Everything still open is tracked in one of: `docs/shacl12-gap-matrix.md`'s "Not Covered / Deferred" table (deliberate, documented scope boundaries), `tests/w3c_shacl12/known_failures.py` (confirmed permanently out-of-scope or deliberate-limitation entries only, as of 2026-08-01), or upstream reporting/tracking work (items 1-2 above) - not silently missing.

## Working Principles

- One integrated validation/rules engine behavior for RDF 1.1 and RDF 1.2 inputs - no separate runtime modes.
- Semantics that are genuinely unimplemented (e.g. a case the spec itself disallows) hard-fail with a clear error; a shape the native fast path doesn't recognize but pySHACL can still process falls back to the generic pySHACL-encoded path rather than hard-failing.
- New native-pass additions should fit one of the established architectural patterns (see `docs/shacl12-gap-matrix.md`'s "Note on Architecture Direction") rather than inventing a new one without reason.
