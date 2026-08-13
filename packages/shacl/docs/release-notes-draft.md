# starshacl v0.1.0 - Draft

*Last reviewed: 2026-07-18*

> **Stale draft.** This predates most of the project's current functionality (full SHACL 1.2 Core coverage, several native pySHACL bug workarounds, `rdf:dirLangString` support, and more - see `docs/implementation-plan.md`'s "Current Status") and references at least one API (`prepare_query_plan`/`SparqlQueryService`) that has since been removed as dead code. Regenerate from `docs/release-notes-template.md` against the actual state of the codebase before using this for a real release rather than editing this draft incrementally.

## Summary

This release establishes the initial starshacl validation wrapper over pySHACL with first-class triple-term encoding and decode restoration for `StarLayerGraph` inputs.

## Highlights

- Added deterministic triple-term encode/decode adapter with registry persistence support.
- Added validator and rules execution APIs with diagnostics in typed result objects.
- SPARQL 1.2 support (`sh:sparql`/`sh:construct` with triple-term syntax) works transparently through `validate()`/`apply_rules()` - see `docs/shacl12-gap-matrix.md`.
- Added execution profiles (`validation`, `rules`, `debug`) with centralized option resolution.

## Behavior And Contract Changes

- Graph contract: `StarLayerGraph` or plain `rdflib.Graph` (auto-normalized) accepted for validator entrypoints.
- Validation/rules/report behavior: pySHACL executes against encoded RDF 1.1-compatible graphs, with report decode fidelity for triple-term values.

## Compatibility

- Python: 3.10+
- StarLayer runtime: `starlayergraph` (`StarLayerGraph`)
- pySHACL: current project dependency range in `pyproject.toml`

## Performance

- Benchmark command: `python benchmarks/bench_adapter.py --triples 1000 --nested-depth 1`
- Latest baseline: encode 90.000 ms, decode 1021.324 ms (1000 triples, nested depth 1)

## Migration Notes

- Integrators can pass `StarLayerGraph` or plain `rdflib.Graph` for `data_graph`, `shacl_graph`, and `ont_graph` - plain graphs are auto-normalized.
- Consumers relying on pySHACL internals should use starshacl's validator API instead.

## Validation Evidence

- `pytest -q`: pass (test count as of actual release - re-run and fill in; stale figure removed)
- `pytest -q tests/integration`: included in full suite coverage
- Benchmark run: completed and logged in `docs/benchmark-baselines.md`
