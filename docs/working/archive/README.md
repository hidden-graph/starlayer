# Archived hand-written docs

Archived 2026-10-17; no longer maintained.

| File | Replaced by |
|---|---|
| `api-reference.md` | `docs/generated/api-overview.generated.md` and `api-reference.generated.md` (generated from the code knowledge graph) |
| `functionality-overview.md` | `docs/generated/functionality-overview.generated.md` (generated from `codekg/curated/functionality.ttl`) |

| `shacl-claude-md-pyshacl-era.md` | `packages/starlayer/starlayer/shacl/CLAUDE.md` (rewritten for the native engine, 2026-11-02). The dated log of the pySHACL-backed validator (monkeypatches, the triple-term adapter, `native_components`) and of the fixes made to it; the engine's own design notes are `docs/working/shacl-engine-design.md` |

Both of the first two are kept for reference. Their per-entry notes (for example the `Modified` / `Unchanged` status of inherited methods) are not reproduced in the generated docs.

## Finished migration, phase and spike notes (archived 2026-11-12)

The notes written while the library moved from rdflib to Oxigraph and from pySHACL to the native SHACL engine are history now: the phase notes (`b1`, `d1` to `d4`, `e1` to `e4`, `phase-c-*`, `phase-f-triage`), the migration plans and inventories (`graph-*`), the spikes and feasibility studies (`sparql-*`, `shacl-engine-feasibility`, `shacl-engine-term-model-spike`, `shacl-engine-overlay-oxigraph`, `shacl-engine-native-mode-run`), the cutover and branch records (`shacl-engine-cutover`, `shacl-engine-main-sync`, `branch-decision-2026-11`, `main-changes-for-shacl-engine-2026-11-11`) and the dated audits and hunts. What is still true of the code lives in the `CLAUDE.md` files, `docs/working/shacl-engine-design.md`, `shacl-engine-differential.md`, `oxgraph-wrapper.md` (in docs/working) and the other notes left in `docs/working/`. Git history has the rest.

## Design notes of the old rdflib-based class and the pre-engine SHACL plans (archived 2026-11-13)

Files named `design-graph-*` are the notes in `docs/design/graph` that describe the deleted rdflib-based `StarLayerGraph` (their own headers say "Historical"): the architecture, the method-coverage tracker against `rdflib.Graph`, the Fuseki reasoning setup, the performance notes, the SPARQL 1.2 design examples and the Protocol gap analysis. Files named `design-shacl-*` are the starshacl-era implementation plan, the W3C SHACL 1.2 test-suite integration plan and the upstream change log, all written before the native engine (July and August 2026). Git history has the rest.
