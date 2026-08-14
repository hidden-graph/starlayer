# Compatibility And Versioning

*Last reviewed: 2026-07-20*

This is the compatibility contract for starshacl: what inputs are supported, what guarantees hold across releases, and what callers need to know about the pySHACL layer underneath. For implementation rationale or SHACL 1.2 feature-by-feature status, see `docs/implementation-plan.md` and `docs/shacl12-gap-matrix.md`.

## Graph Contract

- `data_graph`, `shacl_graph`, and `ont_graph` each accept a `StarLayerGraph` or a plain `rdflib.Graph`. A plain `rdflib.Graph` is normalized to `StarLayerGraph` at the API boundary. Any other type is rejected at runtime.
- `rdflib.Dataset` / `StarLayerDataset` are also accepted at the type check (rdflib's `Dataset` is a Python subclass of `Graph`), but starshacl validates it as a single graph, not as a collection of named graphs.
  - For `data_graph` and `shacl_graph`: the dataset's default graph is used, unless it was built with `default_union=True` or a specific graph is passed directly (e.g. `ds.get_context(uri)`). Named-graph-only data is otherwise silently invisible - no error, just a partial or empty result.
  - For `ont_graph`: starshacl always treats it as the union of all named graphs, regardless of the dataset's own `default_union` setting - matching pySHACL's own native behavior when given a raw `Dataset` as `ont_graph`. This is intentionally asymmetric with `data_graph`/`shacl_graph` above.
  - See `tests/integration/test_starlayer_dataset_input.py`.

## RDF / SHACL Version Support

- **RDF 1.2** (triple terms, `rdf:dirLangString` direction-tagged literals) is a first-class value type, not an add-on: `StarLayerGraph` carries these natively, and they round-trip through validation and rules unchanged.
- **RDF 1.1 / SHACL 1.0-1.1** inputs are fully supported through the same code path - there are no separate 1.1/1.2 runtime modes.

**"SHACL 1.2" spans six separate W3C documents**, each with its own status and coverage below. All are still Working Drafts, not Candidate Recommendations - see `docs/shacl12-gap-matrix.md` for full per-document detail and how to track upstream spec changes.

### SHACL 1.2 Core

- Status: Working Draft.
- Coverage: fully implemented. Every predicate is registered as a pySHACL constraint component, so `sh:not`/`sh:and`/`sh:or`/`sh:xone` composition, `sh:deactivated`, and `sh:severity` all work correctly.

### SHACL 1.2 SPARQL Extensions

- Status: Working Draft.
- Coverage: functionally supported and meta-shacl-checked - `sh:sparql` and user-defined `sh:ConstraintComponent`.

### SHACL 1.2 Node Expressions

- Status: Working Draft.
- Coverage: supported. The current `shnex:` namespace coexists with pySHACL's older node-expression forms.

### SHACL 1.2 Rules

- Status: Working Draft.
- Coverage: functionally supported and meta-shacl-checked - `sh:rule`/`sh:TripleRule`/`sh:SPARQLRule`/`sh:condition`.

### SHACL 1.2 User Interfaces

- Status: First Public Working Draft.
- Coverage: `shui:` annotations pass through as inert, well-formedness-checked metadata. The spec's own widget-selection algorithm is not implemented.

### SHACL 1.2 Profiling

- Status: Working Draft.
- Coverage: this document isn't a validation-behavior spec - it defines conventions for *describing* shapes/data graphs as identifiable resources (`sh:ShapesGraph`/`sh:DataGraph`, `owl:imports`) and for declaring which subset of SHACL features something uses or requires. None of that changes what a validator does at runtime, so no implementation was needed on that front. The one runtime-relevant piece, an optional `sh:conformsTo` inference rule, is a plain SPARQL CONSTRUCT already expressible via starshacl's existing `sh:rule` support - not a gap, just unused unless a caller wants it.

### Meta-shacl validation

`meta_shacl=True` (the shapes-graph well-formedness preflight, on by default) covers predicates from all six documents above, via starshacl's own preflight (`starshacl/meta_shapes.py`) rather than pySHACL's built-in mechanism. See `docs/shacl12-gap-matrix.md`'s Meta-SHACL Policy section for exact coverage and the `meta_shapes_extra` extension hook.

## starshacl and pySHACL

starshacl wraps `pyshacl` as its validation engine; there is a single validation path for every input (no separate native/fallback modes a caller needs to reason about). SHACL 1.2 predicates are registered directly into pySHACL's own constraint dispatch map, so they participate in pySHACL's generic shape-composition logic rather than being evaluated by a separate mechanism.

Known pySHACL limitations are handled transparently - a caller does not need to work around these:

| Limitation | Effect without starshacl | starshacl's handling |
| --- | --- | --- |
| `sh:filterShape` node expressions crash | `AttributeError` on evaluation | Compatibility shim in `starshacl/validator.py` |
| `sh:intersection` node expressions return no results | Silently evaluates to empty | List-chain triples pre-copied into a data-graph copy before validation, removed after |
| A `ValidationFailure` raised deep in constraint evaluation is returned instead of raised | Crashes with an unrelated `TypeError` at report-decoding time | Detected and re-raised as the real exception |
| `meta_shacl=True`'s bundled meta-shapes predate SHACL 1.2 | New predicates under-validated; some widened SHACL 1.2 forms rejected | Replaced by starshacl's own meta-shapes preflight (`starshacl/meta_shapes.py`) |

Full technical detail and reproduction steps for each are in `docs/pyshacl-upstream-issues.md`.

One additional, deliberate deviation from pySHACL's own defaults: the meta-shacl preflight (not ordinary data validation) raises pySHACL's default `max_validation_depth` from 15 to 30, since meta-shape nesting goes deeper than ordinary data shapes. A caller relying on pySHACL's own default depth limit to reject a very deeply nested *shapes graph* during meta-shacl validation will see a higher threshold under starshacl than under plain `pyshacl.validate(..., meta_shacl=True)`. Overridable via the same `max_validation_depth` kwarg.

## Semantic Versioning Policy

starshacl follows Semantic Versioning.

- MAJOR:
  - breaking API changes
  - graph contract changes
  - behavior changes that alter validation/rule outputs for existing inputs
- MINOR:
  - backward-compatible feature additions
  - new helper APIs and diagnostics fields
- PATCH:
  - backward-compatible fixes and test/doc updates

## Compatibility Statements

- Python: 3.10+
- `rdflib`: >=7.0
- `starlayergraph` (`StarLayerGraph`/`StarLayerDataset`): >=0.1.0
- `pyshacl`: >=0.30.0 declared as installable, but the specific pySHACL bugs and workarounds in the table above are verified against **pySHACL 0.40.0**. The workarounds are defensive (they detect a mismatched internal API shape and fail with a clear error rather than silently misbehaving - see `starshacl/validator.py::_patch_shape_validate_for_filter_shape`), but correctness against pySHACL versions other than 0.40.0 has not been separately confirmed. Pin to 0.40.0 if exact behavior matters.

## Upgrade Guidance

When upgrading between minor versions:

1. Run the integration suite first.
2. Verify diagnostics counters used by downstream tooling.
3. Re-run benchmark harness for encode/decode regressions.

## Release Process

- Follow `docs/releasing.md` before cutting a release.
