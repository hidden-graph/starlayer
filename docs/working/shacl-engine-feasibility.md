# Native SHACL engine: feasibility notes

Branch `shacl-engine`, from tag `shacl-engine-baseline` (main at 7583cb9). Compare later with
`git diff shacl-engine-baseline..main -- packages/starlayer/starlayer/shacl packages/starlayer/tests/shacl`.

## Plan under evaluation
Replace pyshacl with an engine written against a narrow graph interface and a compiled plan (shapes parsed once into
plain data), validated against the W3C SHACL 1.2 suite and our tests with pyshacl kept beside it as a differential
reference. Port to Rust once the SHACL 1.2 text settles. Order: measure SHACL on Oxigraph, swap the store for non-SHACL
work, build the engine, add Oxigraph as a second implementation of the interface, retire pyshacl.

## Findings so far

### How deep pyshacl goes (shacl/, sparql/, graph/)
- References by file: validator.py 72, native_components.py 68, rule_engine.py, node_expressions.py, meta_shapes.py 13
  each; about a dozen more files with 2-10.
- Imports: 28 `ConstraintComponent`, 26 `pyshacl.errors`, 6 `ShapesGraph`, about 20 small helpers (rdfutil, pytypes,
  rules, helper). Errors and the base class are mechanical to replace.
- validator.py monkeypatches pyshacl at runtime, process-global: `Shape.validate`, `Shape.value_nodes`,
  `Shape.focus_nodes` and `RdfLibDataGraph.clone` (about lines 5087-5611). Our behaviour today is pyshacl's core loop
  plus these patches. Each patch is a requirement the new engine has to meet and a checklist item.
- `shacl/engine/` already exists (contracts.py, core.py, normalization.py; 375 lines): `target_nodes`,
  `evaluate_component(ComponentRequest)`, `build_report`. validator.py imports from it, so a seam exists. How much of
  the validation loop goes through it is not yet measured.

### SHACL on the Oxigraph store (tests, not benchmarks)
- The W3C SHACL 1.2 suite already has a store axis. Default fast tier: 324 passed, 1 skipped, 1 xfailed. In-process
  Oxigraph store (`test_w3c_validate_oxigraph_store`) runs inside that tier.
- `-m store_matrix` with the persisted Oxigraph store: 318 passed, 7 xfailed.
- All the Oxigraph xfails are one cause: Oxigraph normalizes literals on storage ("04"^^xsd:integer -> "4",
  "1"^^xsd:boolean -> "true", "300"^^xsd:byte re-typed, ill-formed values rewritten or dropped), tracked upstream as
  oxigraph/oxigraph#526. SHACL needs the original lexical form and ill-formed literals (datatype, pattern, uniqueLang,
  sh:in). So Oxigraph cannot be the system of record for the lexical form that the engine reads, unless that option
  lands. The graph interface must say whether lexical forms are preserved.
- validator.py reads graphs back through the store and re-encodes them for pyshacl: the store is storage only and SHACL
  still runs in memory. A store swap alone therefore buys little for SHACL.

### Not yet done
- Benchmarks (benchmarks-shacl) on default vs Oxigraph: not run.
- Which patches `shacl/engine/` already routes around.
- Line-by-line split of validator.py and native_components.py into pyshacl glue and our logic.
- rudof SHACL Core spike (needs a Rust toolchain).

## Parked
The literal-normalization issue (Oxigraph rewrites lexical forms on storage) is parked by decision; revisit when the graph interface is designed.

## Implication for the interface
Two requirements from the findings: the interface must expose original lexical forms and ill-formed literals, and it
must not assume a store can supply them. A store that normalizes literals can only be a source for data whose lexical
form does not matter, or must be paired with a side table of original forms.

## validator.py is a pipeline around pyshacl, not an engine (6,110 lines)
Flow: normalize graphs, entailment, new target types, node expressions, native component registration, encode triple
terms to RDF 1.1, call `pyshacl.validate` through `_default_validate`, decode the report. `StarShaclSchema.validate` and
module-level `validate` are two parallel copies of the same body (the "two-step flip" note), and likewise `evaluate`,
`apply_rules` and target augmentation, so the unique logic is well under the line count.
Rough split by function name (heuristic, 5,730 of 6,110 lines): rules/evaluate 1,228; validate pipeline 1,068;
other 769; patches to pyshacl 679; native fast paths 642; report text/provenance 521; target augmentation 432;
UI/extraction 198; conformance helpers 193.
The Core evaluation loop (shape, focus and value nodes, 28 core components, paths, SPARQL constraints) lives in
pyshacl and is what a fresh engine writes. native_components.py (3,416 lines) holds our 1.2 components, which
survive with a different base class.

## Scope decision: all of SHACL 1.2, no backward compatibility with SHACL-AF
The engine implements everything the SHACL 1.2 drafts define (Core, SPARQL, node expressions, rules, `sh:targetWhere`,
values and defaults, and so on) and nothing that exists only in the 2017 SHACL-AF note. Rules are therefore in scope for
the new engine, not left on the old path.

Correction (earlier version of this section was wrong). I inferred "AF-only" from absence in the W3C test suite and
listed `sh:TripleRule`, `sh:SPARQLFunction`, `sh:SPARQLTarget` and `sh:TargetType` as drop candidates. They are in the
1.2 vocabulary (`scripts/assets/vendor/w3c-shacl.ttl`, "under development by the Data-Shapes (SHACL 1.2) WG"), alongside
`sh:SPARQLRule`, `sh:SPARQLTargetType`, `sh:SPARQLRuleTemplate`, `sh:rule`, `sh:condition`, `sh:order`, `sh:values`,
`sh:defaultValue`, `sh:expression` and the `sh:NodeExpression` family. `docs/shacl/shacl12-gap-matrix.md` records that
`sh:TripleRule` is defined in the SHACL 1.2 Inference Rules draft ("Triple Rules"; the matrix's "SPARQL Extensions
section 8.10" is stale: the 22 Oct 2026 SPARQL draft has no section 8). The rules vocabulary lives in the SHACL 1.2 Inference Rules editor's draft (the former "SHACL 1.2 Rules" document became
SPARQL 1.2 Rules, SRL). Test-suite coverage is not a scope test; the vocabulary and the spec text are.

### Audit method: code against the 1.2 vocabulary
Every `sh:` term the code uses (`SH.x`, `SH["x"]`, `"sh:x"`) was compared with the vendored vocabulary (246 terms).
190 distinct terms are used; 186 are in the vocabulary. The four that are not: `conformsTo` and `validationReport`
(shacl/profiling.py; check against the Profiling draft), `usedConfiguration` (ours, validator.py) and `or_` (a Python
name, not a term). So at the term level the code is already 1.2-shaped; the legacy lives in forms and fallbacks.

### Candidates for removal as legacy / earlier-draft (to confirm against the spec text, then remove from main too)
1. **pySHACL's own old `sh:`-namespaced node-expression forms** (`sh:union`, `sh:intersection`, `sh:filterShape`,
   `sh:path` as expressions), kept alongside the current `shnex:` namespace (21 operators). node_expressions.py line 16
   says "old and new coexist". The vocabulary still lists some of these names, so confirm each against the Node
   Expressions draft before removal.
2. **The `sh:filterShape` compatibility shim** (validator.py about lines 652-683 and 3588) and **pySHACL's legacy
   node-expression fallback** (about line 1094), which exist only to handle form 1.
3. **A legacy `sh:path`-bearing-blank-node fallback** (validator.py about line 2270).
4. **Citations of the 2017 SHACL-AF note** in rule_conditions.py (`shacl-af/#rules-order`, `#condition`): re-point to
   the Inference Rules draft or confirm the rule still matches it.
5. Code that exists to bridge pyshacl's rule classes (`adapters.py`, `_patch_rules_for_native_engine`,
   `_global_engine_rules`): not legacy 1.2, but replaced wholesale by the new engine.
Not legacy: `sh:TripleRule`, `sh:SPARQLRule`, `sh:SPARQLFunction`, `sh:SPARQLTarget`, `sh:TargetType`, rule ordering,
conditions, `sh:resultAnnotation`: all in the 1.2 vocabulary, so the new engine implements them.

## Spec reading (partial), 2026-10-30
Node Expressions WD 28 Oct 2026, read verbatim to part of 4.2.5: no `sh:union`/`sh:intersection`/`sh:minus`/
`sh:filterShape`/`sh:path` as expressions; the `shnex:` keys are used. The 2017 SHACL-AF note section 6 defines the old
`sh:` forms (6.3, 6.6, 6.7). Supports candidate 1. Unread: Node Expressions sections 5-8, SPARQL Features section 6 and
Appendix F, Inference Rules section numbers. The Inference Rules draft adds `sh:layer`, `sh:runOnce`,
`sh:expectedPredicate`, rule sets, `sh:ruleProcessor`, `sh:tempTriple`, `sh:sourceRule` and rule templates; the engine
must cover them.

## Spike result (shacl_engine, 2026-10-30)
New package `starlayer/shacl_engine/` (plan, builder, executor, report, paths, targets, four component modules; about
1,560 lines) with no pyshacl and no rdflib object model in the core. Vendored W3C SHACL 1.2 `tests/core`: 137 of 138
Validate entries pass; the one failure is `nodeByExpression-001` (node expressions, design step 5). 118 new unit tests
pass. Built in about an hour with four parallel agents on separate files over a skeleton.

Open points the build surfaced (decide before cut-over):
- `ctx.conforms` treats a recursive re-entry as conforming; that is wrong under `sh:not`. Recursion semantics need a
  decision (the draft's rules, or stratification).
- `sh:class`, `sh:datatype`, `sh:nodeKind` accept an rdf:list as a union because two fixtures need it; confirm in the
  Core text.
- `shape_targets` adds a pseudo-target for `ex:x sh:shape ex:S` (fixture shape-001); consider moving it to the executor.
- `sh:targetWhere` candidates are all subjects and objects of the data graph; triple-term components are not enumerated.
- `sh:nodeKind` and triple terms: only `sh:TripleTerm` matches one; unverified against the text.
- Subclass triples for class targets and `sh:rootClass` come from the data graph only.
- `sh:detail` results for the list components are not emitted (the comparison ignores them).
- `uniqueValuesFor`: a focus node with no value for any listed property is not compared (fixture 004).

## Round 2 (2026-10-30): SHACL-SPARQL through starlayer query, and a native Oxigraph view
- `sparql_support.py`, `components/sparql_constraints.py`, `components/sparql_components.py`: `sh:sparql`, SPARQL-based
  constraint components (ASK and SELECT validators, optional parameters), pre-binding, prefixes, message templates,
  `sh:select` / `sh:sparqlExpr` expressions. All queries run through starlayer's own query layer
  (`prepareQuery` + `graph.query(..., initBindings=...)`). W3C `tests/sparql`: 22 of 23 entries pass.
- Not implemented: `sh:SPARQLTarget`, `sh:SPARQLTargetType`, `$currentShape`, `$shapesGraph`. The agent reports that
  Appendix F of the current SPARQL draft says they were removed in 1.2 in favour of node-expression targets; verify
  against Appendix F, then add to the #185 list if confirmed. `sh:labelTemplate` is unused (no fixture). `VALUES` is
  rejected wholesale because fixture unsupported-sparql-002 expects it, though the spec text forbids only `VALUES`
  that mention a pre-bound variable.
- **Query-layer bug found:** `FILTER(false)` in a group is dropped, so `SELECT * { ?s ?p ?o FILTER(false) }` returns
  rows (plain rdflib does the same). Fails W3C pre-binding-002 and breaks any ASK validator written as
  `ASK { FILTER(false) }`. Fix belongs in `starlayer/graph/query/algebra_translator_patches.py`. Not yet filed.
- `oxigraph_view.py`: `OxigraphGraph` is a native GraphView over a `pyoxigraph.Store`; term conversion both ways
  including triple terms and base-direction literals; native `query()` with pyoxigraph substitutions. Contract tests run
  on StarLayerGraph and OxigraphGraph. W3C core over Oxigraph: 132 of 138, with 5 strict xfails for literal
  normalization (oxigraph#526: `"4.0"^^xsd:decimal` stored as `"4"`, `"300"^^xsd:byte` re-typed, `"none"^^xsd:boolean`
  rewritten, `"1"^^xsd:boolean` -> true, which wrongly activates `sh:uniqueLang`) plus the shared nodeByExpression-001.
  The literal issue is parked by decision. Timing is equal on the core suite (parse dominates); no large-data benchmark yet.
- Oxigraph conversion edge cases: patterns with a literal subject or non-IRI predicate raise `TypeError` in pyoxigraph
  (the view returns empty, as rdflib does); `"x"` and `"x"^^xsd:string` are one term; blank-node ids must be valid
  Oxigraph ids; a substituted variable must be projected.
- Totals: shacl_engine about 2,300 lines; 472 passed, 6 xfailed, 2 failed (nodeByExpression-001: step 5;
  pre-binding-002: the FILTER(false) bug).
