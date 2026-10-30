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

Evidence from the vendored W3C SHACL 1.2 test suite (`tests/shacl/vendor/shacl12-test-suite`), file counts: present are
`sh:SPARQLRule` 12, `sh:rule` 9, `shnex:` 105, `sh:values` 3, `sh:condition` 2, `sh:defaultValue` 2, `sh:expression` 1,
`sh:targetWhere` 1. Absent (0): `sh:TripleRule`, `sh:SPARQLFunction`, `sh:SPARQLTarget`, `sh:JSFunction`, `sh:TargetType`.
Absence from the suite is not proof the drafts omit them; confirm each against the spec text before dropping.

Candidate AF-only features to drop, with where the current code uses them: `sh:TripleRule` (10 source files, 27 test
files), `sh:SPARQLFunction` (4 source, 2 tests), `sh:SPARQLTarget`/custom target types (6 source, 5 tests), JS
(`sh:JSFunction` etc., 1 source file), pyshacl's own rule classes and `pyshacl.rules` imports.
