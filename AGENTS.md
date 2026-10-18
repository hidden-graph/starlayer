# AGENTS.md

starlayer is a platform for building Python semantic apps on the RDF 1.2 / SPARQL 1.2 / SHACL 1.2 drafts. Read this file first; it is short on purpose.

## Layout
- `packages/starlayer/starlayer/` is the one installed package (the `pyproject.toml` is at the repo root):
  `graph/` (RDF 1.2 graphs, datasets, parsers, backends), `sparql/` (SPARQL 1.2, `sqe:` query trees, SRL rules), `shacl/` (SHACL 1.2 validation, rules, UI widget selection),
  `starontology/` (bundled ontologies and shapes, as `.ttl` files), `conformance.py`, and `codekg/` (the code knowledge graph tooling; repo-only, not shipped).
- Tests: `packages/starlayer/tests/{graph,sparql,shacl,starontology,codekg}/`. Guides: `docs/guides/*.ipynb` (index: `docs/guides/README.md`). Build scripts: `scripts/`.
- Each of `graph/`, `sparql/`, `shacl/` has a `CLAUDE.md` starting with "Rules that bite". Read that block, not the design history below it.

## Set up, test, lint
- `pip install -e ".[test]"` from the repo root (extras: `sqlalchemy`, `reasoning`, `oxigraph`, `owl-dl`; see `pyproject.toml`).
- `cd packages/starlayer && pytest tests -m "not integration"` is the fast tier. Integration tests need local Oxigraph/Fuseki servers and skip without them.
- Opt-in groups (deselected by default): `--store-matrix`, `--srl-stratification`, `STARLAYER_RUN_ENGINE_ABORT_TESTS=1` (see `packages/starlayer/tests/conftest.py`).
- `ruff check packages/` must pass (CI runs it). Formatting is not enforced; do not reformat files you are not changing.

## Generated files: never edit by hand
`docs/generated/*.generated.md`, and in `packages/starlayer/starlayer/`: `starontology/starontology.trig`, `starontology/shacl12-shacl.ttl`, `starontology/skos-ontology.ttl`, `codekg/codekg.trig`.
Edit the source (another `.ttl` in `starontology/`, `scripts/assets/shacl12-validation-shapes.ttl`, `codekg/curated/functionality.ttl`) and run `python scripts/build.py`.
CI runs `python scripts/build.py --check --skip codekg`. The code KG is rebuilt on demand (`--only codekg apidocs`, about 30 s) and can lag the source.

## Use the knowledge graph first
Do not read large files into context: `codekg/codekg.trig` (6 MB), `docs/generated/api-reference.generated.md` (about 5,000 lines), `starontology/starontology.trig`, or any `CLAUDE.md` below its "Rules that bite" block. Ask the graph a narrow question instead.
- Three layers: the vocabulary `packages/starlayer/starlayer/codekg/ontology.ttl` (`slkg:`), the generated dataset `codekg/codekg.trig` (one named graph per module: classes, functions, calls, overrides, tests), and the hand-written capability graph `codekg/curated/functionality.ttl`.
- Capability map in plain text: `docs/generated/functionality-overview.generated.md`. One line per public symbol: `docs/generated/api-overview.generated.md`.
- Load: `from starlayer.codekg import get_codekg_dataset`; the result is a `StarLayerDataset`. Always put a `LIMIT` on queries and select a few columns, never `SELECT *` or `CONSTRUCT` over the whole graph.
- Recipe: find the topic in the functionality overview, take its `implementedByIdentifier` (a dotted path), query the KG for that symbol's file and line range, then open only that range.
- Questions the KG can answer, and which it cannot yet: `packages/starlayer/starlayer/codekg/competency-questions.md`.
- Planned, not built yet: named queries (`list_queries`, `run_query`) and a public read-only KG endpoint that logs questions. See `docs/app-development-plans/repo-prep-plan.md`. Until then, queries are plain SPARQL against the local file.

## Working agreements
- Do not push, merge, publish or delete branches without being asked. Confirm before any outward-facing action.
- Do not edit a guide notebook unless asked; describe the change and wait. If a file may be open with unsaved changes, ask the user to save first.
- Docs say what a reader needs (inputs, outputs, errors), not interesting side facts. No notes to the reader about how the doc was produced.
- Docstrings give the "why". Do not restate what the signature, calls or overrides already show; the code KG records those.
- Test discipline: before calling a fix done, check the new test fails without it. For SHACL and SPARQL behaviour, compare against plain pySHACL or rdflib as the oracle.
- Commit messages end with the Co-Authored-By line given to you. Keep generated-file changes in their own commit.

## App-building defaults (provisional)
FastAPI + Jinja2 + HTMX, one vendored JS library for graph drawing, no Node build chain, UI behind an optional extra so the core stays UI-free. Reasoning and the revision process: `docs/app-development-plans/repo-prep-plan.md`. The first app is planned in `docs/app-development-plans/graph-workbench-app.md`.

## Plans and open work
`docs/app-development-plans/` (planning only), `packages/starlayer/docs/future_enhancements.md` (open items; some entries are stale, check before relying on one), `docs/upstream-issues/` (rdflib, pySHACL and Oxigraph bugs with minimal repros).
