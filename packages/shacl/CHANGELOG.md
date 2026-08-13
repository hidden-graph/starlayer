# Changelog

## Unreleased

### pySHACL upgraded to v0.40.1: Issue 1 (`sh:intersection`) fixed upstream

- `pyproject.toml` now requires `pyshacl>=0.40.1`. That release fixes the `sh:intersection` node-expression bug reported in `docs/pyshacl-upstream-issues.md` (Issue 1) - confirmed by re-running that entry's reproduction script against 0.40.0 (bug present, `conforms: False`) and 0.40.1 (fixed, `conforms: True`), and by diffing the upstream fix commit against the exact one-line change suggested in the report.
- `starshacl`'s own workaround for this bug (`_inject_intersection_list_triples` in `validator.py`) has been removed, since it's dead weight now that the new minimum pySHACL version has the fix. `sh:intersection` coverage (`tests/integration/test_node_expressions_integration.py`) still passes end to end without it.
- Issues 2-4 in that same doc remain unfixed upstream (as expected - none were reported).

### SHACL 1.2 Core: complete native migration

- Every SHACL 1.2 predicate that was ever handled by the old "merge-after" native-pass architecture is now a real `pyshacl.constraints.constraint_component.ConstraintComponent` registered directly into pySHACL's own dispatch map, so composition (`sh:not`/`sh:and`/`sh:or`/`sh:xone`), `sh:deactivated`, and `sh:severity` are handled correctly by construction rather than reimplemented per predicate. The entire old merge-after/strip-and-replace machinery in `starshacl/validator.py` was removed. See `docs/shacl12-gap-matrix.md` pattern 10 and `docs/implementation-plan.md`.

### `sh:uniqueValuesFor` composition: fixed across every pySHACL mechanism that can reach it

- Composition through `sh:not`/`sh:and`/`sh:or`/`sh:xone`, `sh:node`, and `sh:qualifiedValueShape` (including its `sh:qualifiedValueShapesDisjoint` sibling check) is now correct at any nesting depth and through any mixture of these mechanisms, not just the shallow/single-level case.
- Detection of which shapes need full-batch (rather than per-value) evaluation is transitive, computed once per shapes graph and cached, not a live shallow walk.
- Two real bugs found and fixed during a dedicated review pass, not just the initial fix: a hash-seed-dependent correctness bug in the transitive-reachability computation (a DFS-with-memoization approach was unsound under cycles; replaced with monotonic fixed-point propagation), and a branch-condition gap where `sh:qualifiedValueShapesDisjoint`'s sibling-shape check wasn't itself checked for needing full-batch treatment.
- See `docs/shacl12-gap-matrix.md` pattern 11 for the full mechanism and regression coverage (`tests/integration/test_native_component_composition.py`).

### Meta-SHACL: extended to SHACL 1.2

- starshacl now runs its own meta-shacl preflight (`starshacl/meta_shapes.py`) instead of delegating to pySHACL's own `meta_shacl` kwarg, which has no SHACL 1.2 awareness at all - it both silently under-validated new SHACL 1.2 predicates and actively rejected valid shapes using several predicates SHACL 1.2 widened (list-valued `sh:class`/`sh:datatype`/`sh:nodeKind`, path-valued `sh:equals`/`sh:disjoint`/`sh:lessThan`/`sh:lessThanOrEquals`, `sh:closed sh:ByTypes`).
- New supplementary meta-shapes, shipped as standalone, hand-editable `.ttl` files (`starshacl/assets/shacl12-validation-shapes.ttl`, `shacl12-presentation-shapes.ttl`) - reusable by downstream SHACL 1.2 tooling (e.g. a shapes-graph editor), not vendoring pySHACL's own SHACL 1.0/1.1 base.
- New `validate(..., meta_shapes_extra=[...])` parameter so callers can layer their own additional shape rules on top.
- See `docs/shacl12-gap-matrix.md`'s Meta-SHACL Policy section and `README.md`'s "SHACL 1.2 Meta-Shapes" section.

### Native (RDF 1.2) backend: tested for the first time, two real bugs found upstream

- Native (`backend='rdf-1.2'`) `StarLayerGraph`/`StarLayerDataset` usage was previously completely untested in starshacl. Investigated against real Oxigraph and Fuseki instances (`tests/integration/test_native_backend_oxigraph.py`).
- Found and fixed two real bugs in `starlayergraph` (not starshacl): `StarLayerGraph.parse(format='turtle12'/'longturtle12'/'trig12')` wrote the rdf-1.1 backend's own tt:HASH encoding directly into the store for *any* backend, breaking triple terms parsed from text (not added via `.add()`) on the native backend - this broke `sh:reifierShape`/`sh:reificationRequired` end to end. And the SPARQL query-prepare-cache performance work (below) initially broke `StarLayerGraph.query()` against Fuseki/any remote-SPARQL-endpoint-backed store.
- See `docs/starlayergraph-upstream-change-log.md` for full detail on both fixes (and a related `StarLayerDataset` gap found along the way, tracked but not yet fixed).

### SHACL 1.2, full six-document family: adopted and investigated to completion

- "SHACL 1.2" turned out to be six separate W3C documents (Core, SPARQL Extensions, Node Expressions, Rules, User Interfaces, Profiling), not one - all now covered, each to the depth its content warrants.
- **Node Expressions**: added full support for the current draft's `shnex:` namespace (~20 operators - `pathValues`, `filterShape`, `var`, `if`/`then`/`else`, `exists`, `distinct`, `remove`, `intersection`, `concat`, `orderBy`/`desc`, `limit`, `offset`, `flatMap`, `findFirst`, `matchAll`, `count`/`min`/`max`/`sum`, `instancesOf`, `nodesMatching`), coexisting with pySHACL's own old `sh:union`/`sh:intersection`/`sh:filterShape`/`sh:path` forms (`starshacl/node_expressions.py`).
- **Rules / SPARQL Extensions**: `sh:condition` (rule-applicability filtering) and user-defined `sh:ConstraintComponent` (ASK- and SELECT-based) confirmed working, including with RDF-1.2 triple-term data. Surfaced a 5th real pySHACL bug: `pyshacl.validate()` returns a `ValidationFailure` exception *as* `report_graph` instead of raising it - fixed with a defensive re-raise.
- **User Interfaces (`shui:`)**: confirmed the vocabulary passes through `validate()`/`apply_rules()`/meta-shacl as inert, well-formed annotations, including with RDF-1.2 data. The spec's own widget-selection algorithm is scoped out as a separate, optional capability.
- **Profiling**: investigated with the same rigor as the other five (multiple targeted verbatim-quote fetches) - confirmed it defines no new validator runtime behavior. Its packaging conventions are SHOULD-level organizational metadata; its one runtime-relevant item (the `sh:conformsTo` inference rule) is mechanically an ordinary SPARQL CONSTRUCT rule already within reach of the existing rule engine, but requires caller-supplied graph identity to ever fire and was deliberately not built as a generic helper.
- See `docs/shacl12-gap-matrix.md` for full per-document detail and `docs/implementation-plan.md`'s Current Status.

### Meta-SHACL: extended past Core to Rules/SPARQL Extensions/`shui:`/`sh:declare`/node expressions

- `starshacl/assets/shacl12-validation-shapes.ttl` gained real `sh:property`/`sh:node`/`sh:or` well-formedness rules (not just descriptive content) for `sh:sparql`/`sh:rule`/`sh:condition`/custom `sh:ConstraintComponent`, `shui:editor`/`shui:viewer`/`shui:propertyRole`, `sh:prefixes`/`sh:declare`, and node expressions themselves.
- New `stsh:NodeExpressionShape`: deliberately "shallow but broad" - recognizes any of the ~25 known `sh:`/`shnex:` node-expression forms, or a value structurally shaped like a SHACL Function call, without recursing into the internal correctness of whichever form matched. `sh:path` gets full recursive path-grammar checking for free via pySHACL's own `shsh:PathNodeShape`. Wired into `sh:subject`/`sh:predicate`/`sh:object` on `sh:TripleRule`.
- This additional nesting exceeded pySHACL's default `max_validation_depth` (15) with a "Validation path too deep!" error even for simple, valid shapes - `starshacl/meta_shapes.py::meta_validate` now defaults it to 30.
- `sh:condition`'s shape-reference value is now auto-typed via the same mechanism as `sh:someValue`/`sh:memberShape`/`sh:reifierShape` (`SHAPE_EXPECTING_PREDICATES`), replacing an earlier, inconsistent one-off stricter check.
- The `stsh:` namespace was unified to a single canonical IRI (`https://github.com/hidden-graph/starshacl/ns#`) everywhere, including a production-code constant that had drifted to an unrelated IRI.
- `docs/shacl-presentation-content.md`'s full reviewed draft (16 field groups, 108 predicates) is now converted into both meta-shapes `.ttl` files.
- 419 tests passing, 6 skipped (up from 348 at the start of this changelog's "Unreleased" section).

### Documentation

- Removed two outdated architecture-planning documents (`docs/pyshacl-extension-plan.md`, `docs/pyshacl-triple-term-object-extension-map.md`) that sketched an "extend pySHACL's core term model natively" approach never actually taken - already marked historical, no remaining operational value.
- Rewrote `docs/compatibility.md`'s "How starshacl Uses pySHACL" section, which had drifted badly out of date (still described the removed merge-after pipeline).
- Added a "Benchmarks" section to the top-level `README.md` (previously undiscoverable from the project's main entry point) and re-ran the benchmark suite against the current build.
- Cleaned up dangling references to `docs/failure-register.md` (deleted in an earlier cleanup) left in code comments.

No tagged release yet (`pyproject.toml` version `0.1.0` is still unreleased) - see `git log` for full history predating this changelog.
