# scripts

Maintainer scripts. Nothing here is part of the installed packages. Run them from the repository root with `python scripts/<name>.py`; each has `--help`. The names say what kind of script it is.

## The one you will use: `build.py`

`python scripts/build.py` regenerates every generated file in dependency order; `--check` changes nothing and exits 1 if any committed generated file is stale (CI runs it); `--only <step> ...` runs some steps. The steps, in order:

| Step | Script | Writes |
| --- | --- | --- |
| `starontology` | `build_starontology.py` (uses `build_meta_shapes.py` and `build_shacl_ui.py`) | the four generated `.ttl` files in `packages/starlayer/starlayer/starontology/` |
| `codekg` | `build_codekg.py` | `tools/kg/codekg/codekg.trig` and `testskg.trig` (not committed) |
| `apidocs` | `generate_api_docs.py` | `docs/generated/api-*.generated.md` |
| `overview` | `generate_functionality_overview.py` | `docs/generated/functionality-overview.generated.md` |
| `queries` | `build_query_catalogue.py` | `docs/generated/query-library.generated.md` |
| `docs` | `check_docs.py` | nothing: checks links, anchors and the guide index |
| `notebooks` | `check_notebook_links.py` | nothing: checks the notebook-to-code links |
| `kg` | `build_kg.py` | `tools/kg/codekg/starlayer-kg.trig` (not committed) |

## Checks (change nothing)

| Script | What it answers |
| --- | --- |
| `check_docs.py` | Do the links, anchors and guide index in the hand-written docs still resolve? |
| `check_notebook_links.py` | Is each hand-made link from a guide cell to the code it demonstrates still current? (`--show`, `--restamp`) |
| `check_docstrings.py` | Is an edit only docstrings, and do they parse? (`inventory` lists the undocumented public symbols) |
| `check_spec_drift.py` | What has moved upstream (specs, the pinned W3C suites, the vendored vocabularies) since the last review? (`--record` after a review) |
| `check_wg_shacl_shacl.py` | Is our pinned copy of the W3C Working Group's SHACL-for-SHACL still the latest? |
| `check_benchmark_regression.py` | Did a benchmark regress against the committed baseline? (used by the benchmark workflow) |

## Tools

| Script | Purpose |
| --- | --- |
| `kg.py` | Query the code knowledge graph (`python scripts/kg.py list`, `run <query> ...`). |
| `publish_kg.py` | Build the `starlayer-kg` data package for a release. |
| `record_benchmark_baseline.py` | Write a benchmark baseline from several CI runs. |
| `sync_w3c_shacl12_suite.py` | Vendor a pinned snapshot of the W3C SHACL 1.2 test suite into the tests. |
| `_docs_ref.py` | The branch the generated docs link to (imported by the generators). |
