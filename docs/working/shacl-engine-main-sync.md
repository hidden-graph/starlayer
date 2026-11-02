# Tracking `main` and porting its changes to `shacl-engine`

Rule (project owner, 2026-10-30): the engine branch is built on its own and reaches `main` once, when it works. Meanwhile
`main` keeps moving; its changes are tracked and ported to this branch periodically.

## What "port" means here
`main` still runs the old pySHACL-backed validator, which the engine replaces, so a git merge of `shacl/` is not the
goal. For each change on `main` since the last sync:
1. **Outside `starlayer/shacl/` and its tests** (graph, sparql, query layer, docs tooling, KG, build scripts, CI): merge it
   into this branch as is (`git merge main`, resolving conflicts in favour of `main` unless the branch changed the same
   lines on purpose). The engine uses `starlayer.graph` and `starlayer.sparql`, so these matter to it directly.
2. **A SHACL behaviour fix or feature** in `starlayer/shacl/`: decide whether the engine already behaves that way (check the
   draft, not only the old code); if not, implement it in `shacl_engine/` with a test; if the change is a project extension
   the draft lacks, record it in the deviations section of `shacl-engine-feasibility.md` instead.
3. **New or changed tests** under `tests/shacl/`: they are oracle cases. Run the differential plugin over them; every new
   `differ` gets a disposition in `shacl-engine-differential.md`.
4. **Old-code-only changes** (patches to pySHACL, `_patch_*`, glue): note and skip; they disappear at cut-over.
Never push this branch's changes to `main` as part of a sync.

## How to list what changed
    git fetch origin
    git log --oneline shacl-engine-baseline..origin/main                       # everything since the baseline tag
    git diff <last-synced-commit>..origin/main -- packages/starlayer/starlayer/shacl packages/starlayer/tests/shacl
    git diff <last-synced-commit>..origin/main --stat -- . ':!packages/starlayer/starlayer/shacl' ':!packages/starlayer/tests/shacl'
After a sync, update `Last synced` below and add a row per change.

## Log
Last synced: `68349c8` (2026-11-02, merged with `git merge origin/main`). Earlier: `7583cb9`, the baseline tag `shacl-engine-baseline`. The three branches off `main` listed first are all reflected here.

| main change | kind | engine action | status |
|---|---|---|---|
| branch `fix-unique-values-for-peers` (383c417, not merged): `sh:uniqueValuesFor` peers are the shape's own targets (Core 7.9.5) | SHACL behaviour | engine already follows the draft | done; the 15 old tests it rewrites stop showing as differences once it lands |
| branch `remove-sparql-targets` (bcfe221, not merged): `sh:target` SPARQL targets removed, ignored with a warning | SHACL behaviour | engine implements none; `extract_subgraph` mirrors the warning | done |
| branch `fix-filter-false` (99adca9, not merged): `FILTER(false)` in a group is dropped (issue #186, query layer) | query-layer bug | cherry-picked here as bc33993; clears W3C `pre-binding-002` | done |
| issue #185: legacy SHACL-AF candidates to remove from `main` | cleanup | engine never had them; nothing to port | open (needs Node Expressions 5-8 read) |
| `main` 7583cb9..68349c8 (workbench work): widget selection follows SHACL UI 4.3 (`shui:defaultWidgetScore`), prefix sets are inferred and `sh:entailment` values checked, clearer rule-validation messages, starontology data regenerated | UI / old-code SHACL / data | merged as is: the changes sit in `shacl/` (UI and meta shapes, which the engine does not replace) and `starontology/`; conflicts were `ui_widget_selection.py` (kept both sides: this branch's `_via_rdflib`, main's `default_widget_score`) and generated blank-node labels in `starontology.trig` (main's) | done; 231 tests in the changed areas pass |

## Next sync
Check when any of these happens: a PR merges to `main`; before a differential run used as a gate; before any cut-over step.
