# AGENTS.md

starlayer is a platform for building Python semantic apps on the RDF 1.2 / SPARQL 1.2 / SHACL 1.2 drafts. Read this file first; it is short on purpose.

## Layout
- `packages/starlayer/starlayer/` is the one installed package (the `pyproject.toml` is at the repo root):
  `graph/` (RDF 1.2 graphs, datasets, parsers, backends), `sparql/` (SPARQL 1.2, `sqe:` query trees, SRL rules), `shacl/` (SHACL 1.2 validation, rules, UI widget selection),
  `starontology/` (bundled ontologies and shapes, as `.ttl` files), `conformance.py`, and `codekg/` (the code knowledge graph tooling; repo-only, not shipped).
- Tests: `packages/starlayer/tests/{graph,sparql,shacl,starontology,codekg}/`. Guides: `docs/guides/*.ipynb` (index: `docs/guides/README.md`). Build scripts: `scripts/`.
- Each of `graph/`, `sparql/`, `shacl/` has a `CLAUDE.md` starting with "Rules that bite". Read that block, not the design history below it.

## Set up, test, lint
- `pip install -e ".[test]"` from the repo root (extras: `sqlalchemy`, `reasoning`, `oxigraph`, `hermit`, `rustdl`, `benchmark`; see `pyproject.toml`).
- `cd packages/starlayer && pytest tests -m "not integration"` is the fast tier. Integration tests need local Oxigraph/Fuseki servers and skip without them.
- Test one area alone: `pytest packages/starlayer/tests -m shacl` (areas: graph, shacl, sparql, starontology, codekg). Checks of committed data that CI runs anyway are in `--deferred`; run it before a push.
- Opt-in groups (deselected by default): `--store-matrix`, `--srl-stratification`, `--sqe-coverage`, `--manchester-conformance`, `--codekg-queries`, `STARLAYER_RUN_ENGINE_ABORT_TESTS=1` (see `packages/starlayer/tests/conftest.py`).
- `ruff check packages/` must pass (CI runs it). Formatting is not enforced; do not reformat files you are not changing.

## Generated files: never edit by hand
`docs/generated/*.generated.md`, and in `packages/starlayer/starlayer/`: `starontology/starontology.trig`, `starontology/shacl12-shacl.ttl`, `starontology/skos-ontology.ttl`, `codekg/codekg.trig`.
Edit the source (another `.ttl` in `starontology/`, `scripts/assets/shacl12-validation-shapes.ttl`, `codekg/curated/functionality.ttl`) and run `python scripts/build.py`. `codekg/curated/query-library.ttl` is itself a source (hand-edited, nothing generates it).
CI runs `python scripts/build.py --check --skip codekg`. The code KG is rebuilt on demand (`--only codekg apidocs kg`, about 1 min) and can lag the source.

## Use the knowledge graph first
Do not read large files into context: `codekg/codekg.trig` (6 MB), `docs/generated/api-reference.generated.md` (about 5,000 lines), `starontology/starontology.trig`, or any `CLAUDE.md` below its "Rules that bite" block. Ask the graph a narrow question instead.
- Three layers: the vocabulary `packages/starlayer/starlayer/codekg/ontology.ttl` (`slkg:`), the generated dataset `codekg/codekg.trig` (one named graph per module: classes, functions, calls, overrides, tests), and the hand-written capability graph `codekg/curated/functionality.ttl`.
- Capability map in plain text: `docs/generated/functionality-overview.generated.md`. One line per public symbol: `docs/generated/api-overview.generated.md`.
- **Start with a named query**, not raw SPARQL: `python -m starlayer.codekg.queries list` (or `list --topic call-graph`), then `run find-symbol text=tt_hash` or `run callers-of symbol=<dotted path>`, or `run capabilities-by-role role=ui-generate` to find what StarLayer offers for a job (storage, interchange, query, validate, infer, ui-generate, reference). From Python: `from starlayer.codekg import queries`, then `queries.run_query("callers-of", symbol=...)`. Results are tables limited to 25 rows (`--limit`, `--offset` to page), with file and line. The catalogue is `docs/generated/query-library.generated.md`; queries live in `codekg/curated/query-library.ttl` (edit it directly), and `python scripts/build.py --only queries` validates it and rewrites the catalogue.
- **Without a StarLayer checkout** (the query tool is not in the installed package): download the one-file copy of the whole KG, `packages/starlayer/starlayer/codekg/starlayer-kg.trig` (raw GitHub URL), then `from starlayer import StarLayerDataset; kg = StarLayerDataset(default_union=True); kg.parse(path, format="trig12")`. The 24 named queries are in it as text: `SELECT ?q ?t WHERE { ?q a slkg:NamedQuery ; slkg:queryText ?t }`; bind a parameter with `kg.query(text, initBindings={"symbol": Literal("...")})`. It holds the code graph, curated layer, vocabulary and build stamp. Rebuild: `python scripts/build.py --only codekg apidocs kg`.
- No named query fits: `queries.run_sparql("SELECT ... LIMIT 20")` (SELECT and ASK only; `slkg:`, `dcterms:`, `rdfs:` are predeclared). Raw access: `get_codekg_dataset()` returns a `StarLayerDataset`; always put a `LIMIT` on queries and select a few columns.
- Recipe: find the topic in the functionality overview, take its `implementedByIdentifier` (a dotted path), run `symbol-info` for its file and lines, then open only that range. To see which guide cell demonstrates a symbol, use `demonstratedBy` (derived from `codekg/curated/notebook-links.ttl`, checked by `scripts/build.py`; stale links are reviewed with the `review-notebook-links` skill).
- Every query result ends with how old the KG is ("KG built <date> from commit <sha>; since then N commit(s) ... changed the source", from a build stamp), and `python -m starlayer.codekg.queries status` prints it alone. If code you are about to rely on has changed since, rebuild first: `python scripts/build.py --only codekg apidocs kg` (about 1 min).
- Code that exists because of a bug in rdflib, pySHACL, Fuseki or Oxigraph: `run upstream-workarounds` (optionally `project=rdflib` or `symbol=<dotted path>`); the list is `codekg/curated/upstream-issues.ttl`, the write-ups are in `docs/upstream-issues/`.
- A zero-row call-graph answer means no caller this extractor could resolve, not proof of none. Imports between starlayer modules are not in the graph (only external imports are); use the call graph for dependencies.
- (2026-10-26, GitHub issues #102 and #84) Extractor call-graph scoping now follows Python: a bare `name()` in a method never resolves to a sibling method (class scope is skipped), a parameter or local variable of the caller or an enclosing function hides a same-named module function, a nested function's calls belong to it alone (its decorators and defaults count for the enclosing function), a property's setter/deleter and `@overload` stubs add no facts of their own (the getter, or the implementation, describes the one IRI; a setter's calls are added to it). Still open: a comprehension or lambda variable is not tracked as a local, a `match`/`import`-bound name is only partly handled, and `build.py --check` for the codekg step ignores the build stamp but still takes minutes to compare the ~100k-triple graphs (CI keeps `--skip codekg`). `build.py --check` restores `codekg/CHANGELOG.md`; `record_benchmark_baseline.py` and `check_benchmark_regression.py` now stop or fail on a benchmark missing from a run.
- Questions the KG can answer, and which it cannot yet: the `slkg:CompetencyQuestion` nodes in `codekg/curated/query-library.ttl` (`python -m starlayer.codekg.queries questions --unanswered`).
- Planned, not built yet: a public read-only KG endpoint that logs questions. See `docs/app-development-plans/repo-prep-plan.md`.

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
