# Handoff: where the migration stands and what comes next

Branch `shacl-engine` on GitHub (`hidden-graph/starlayer`), written 2026-11-05 at commit 9d3a655 plus this file. Nothing here is on `main`.

## State

- `StarLayerGraph` / `StarLayerDataset` are the Oxigraph-backed classes. The old rdflib classes and the modules only they used are deleted (D1, about 19,300 library lines).
- Phases D1 to D4 and E1 to E4 are merged into `shacl-engine` (branches `mig-d1`, `mig-d2-fixes`, `mig-d3`, `mig-d4`, `mig-e1-sqe`, `mig-e2-small`, `mig-e3-manchester`, `mig-e4-srl-salg`). Their write-ups: `d1-notes.md`, `d2-gaps.md`, `d2-delete-list.md`, `d3-notes.md`, `d4-notes.md`, `e1-notes.md` to `e4-notes.md`.
- The core runs with rdflib blocked (`tests/test_core_without_rdflib.py`). rdflib is an optional extra (`pip install starlayer[rdflib]`). The library imports rdflib at module level only in `graph/graph/owl_dl.py` and `owl_dl_rustdl.py` (owlrl / HermiT export); the bridge `graph/oxgraph/_rdflib_bridge.py` and a few modules import it lazily.
- Gate at 9d3a655: 10,932 passed, 45 skipped, 31 xfailed, 0 failed (`--deferred --codekg-queries`); `build.py --check` and `ruff check packages/` clean.

## Next steps, in order

1. **Bring in three commits from `origin/main`** (SHACL UI form kinds, Nov 2: `86a9bfa`, `98d8c1b`, `040868f`). A trial merge showed the only conflict is the generated `starontology/starontology.trig`: resolve by taking ours and running `python scripts/build.py --only starontology`. The five earlier `origin/main` commits (widget selection per SHACL UI 4.3, rule messages, prefix sets) are already in. Re-run the SHACL UI, starontology and widget tests after.
2. **Notebooks.** `05b`, `appendix-b1`, `05` (cell links), `05d` and `appendix-a` still name `sqe_tree_to_query` or the salg ontology and shapes (both removed in E4). Fix source cells only, restamp links (`scripts/check_notebook_links.py`, skill `review-notebook-links`), then re-execute all guides with nbclient (outputs written back; `pytest --notebooks` discards them). `05d` and `04e` also print `get_resource_iri()` with old output.
3. **Cosmetic salg text:** `salg:` mentions remain in `spexpr_shapes.ttl`, `spexpr-ontology.ttl` and four `@prefix` lines in starontology files.
4. **Packaging:** remove the `sqlalchemy` and `oxigraph` extras (they serve only deleted rdflib store paths) and regenerate `uv.lock`; needs a machine with `uv`. `pyproject.toml` already moved rdflib and owlrl out of core dependencies.
5. **Phase F:** go through `non-spec-behaviour.md` (32 rows) and choose address or document for each; link the result from the user-facing limits page. Check the REPLACE/REGEX, boolean ordering and negated-property-set claims (rows 6 to 8) against the specs before anyone relies on them; look up Oxigraph PR #2010 / issue #190 and the current release.
6. **Phase E:** full suite and notebooks once more, CI, and redo the workbench integration on the final public API (apps use public API only).
7. Reconcile the old pass-count gap if it still matters: 12,683 at 970a97e, now 10,932; the drop is deleted old-class, salg and encoder tests (D1 about 1,400, E4 about 350). Skips fell from 217 to 45 in E4; check which skipped tests went.

## Decisions still open

- Oxigraph #190: stored literals are normalised on insert (`"04"^^xsd:integer` becomes `"4"`); accepted for now.
- `isomorphic()` guard is a heuristic: a very long blank-node path is not caught; Oxigraph is slow on it but does not hang (500 nodes 4.0 s, 1000 nodes 35 s; row 27).
- Update sub-select check for an unbound projected variable (a salg check) was not ported; sqe has no Update shape for it.
- `manchester_validate` stays on owlrl through the bridge; a native RDFS regime or a Rust reasoner is later work. `reasonable` is not supported.
- The Oxigraph-backed sqe tree is store-backed, so a text round trip can normalise numeric forms; an in-memory tree type is the alternative.
- Whether to ship both versions (the old `main` line and this one) is the owner's call.

## Running things

- Python: a venv with the package's dependencies; run `python -m pytest` (not bare `pytest`) from `packages/starlayer`, because an editable install can point at another worktree.
- `PYTHONHASHSEED=0 python -m pytest tests --deferred --codekg-queries -n 4 -q -p no:cacheprovider`. The opt-in suites (`--sqe-coverage`, `--srl-conformance`, `--manchester-conformance`) run serially, with `STARLAYER_SQE_FUZZ_EXAMPLES=20` for the fuzz tests. `-n 4` fails collection for the hypothesis-driven opt-in files.
- `test_timeout.py::test_grandchild_process_does_not_survive_the_timeout_kill` can fail when other pytest processes run at the same time; rerun alone.
- Generated files: `python scripts/build.py --check` (add `--skip codekg` for a quicker check); regenerate with `--only apidocs overview queries` (and `codekg kg`, `starontology` as needed). These go stale after every merge.
- Known failing at the E4 baseline too: `--srl-conformance` `test_infer_matches_the_independent_evaluator`, `--sqe-coverage` `test_matches_plain_rdflib`, `--manchester-conformance` two `test_lenient_where_owlapi_is_lenient` cases (stale leniency list).
- Agents that ran in parallel each used their own git worktree under `.claude/worktrees/`; those worktrees and the `mig-*` branches are local and can be pruned once this branch is merged.
