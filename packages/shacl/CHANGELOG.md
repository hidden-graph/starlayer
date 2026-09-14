# Changelog

## Unreleased

### SHACL 1.2 Profiling: conformance declaration + `sh:conformsTo` helper

- New `starshacl.profiling` module, two pieces:
  - `declared_conformance_profile()` - loads starshacl's own bundled self-declaration (`starshacl/assets/shacl12-conformance-profile.ttl`) of which named SHACL 1.2 feature profiles (§3, `http://www.w3.org/ns/shacl/profile/*`) it implements, using the spec's own `prof:`/`dcterms:` vocabulary.
  - `derive_conforms_to()` - implements §5.5's `sh:conformsTo` inference rule as a caller-usable helper. Reuses this repo's existing `sh:usedDataGraph`/`sh:usedShapesGraph` report-provenance support (`data_graph_iri=`/`shapes_graph_iri=` on `validate()`) when present on the report, so a caller who already supplied that identity at validation time doesn't have to repeat it.
- `docs/guides/04e-shacl-profiling.ipynb` updated with two new sections demonstrating both.
- See `docs/shacl12-gap-matrix.md`'s Profiling row and "Not Covered / Deferred" table for the full reasoning. Regression coverage: `tests/integration/test_profiling.py`.
