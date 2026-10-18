# Plan: Make starlayer self-explaining to humans and agents (KG-first)

## Context

starlayer is a platform for building Python semantic apps on the RDF/SPARQL/SHACL 1.2 drafts. It already has strong raw assets: a generated code KG (`codekg.trig`, ~75K triples, calls/overrides/tests), a curated capability graph (`codekg/curated/functionality.ttl`), generated API docs, 27 guide notebooks, and conformance suites. But a newcomer (human or agent) cannot find or use them:

- No root `CLAUDE.md`/`AGENTS.md`; nothing tells an agent the code KG exists.
- Root `README.md`, `CONTRIBUTING.md`, `packages/starlayer/README.md`, and doc indexes still describe the pre-2026-10-12 three-package layout (dead paths, wrong import names, failing dev commands).
- No way to ask the KG a question without hand-writing rdflib + SPARQL. No query library.
- Curated layer is thin and unwired (`CURATED_GRAPH_IRI` never populated; `demonstratedBy` has 0 triples; no links to specs, gap matrices, docs, upstream bugs).
- CI deliberately does not rebuild `codekg.trig` (decision 2026-10-18: every code change would force a ~90,000-line regeneration); hand-written docs/indexes/manifest are unchecked and have drifted.
- No runnable examples; onboarding requires Jupyter notebooks.

Intended outcome: an agent landing in the repo reads one short file, learns that the KG is the map, can query it via named queries, and finds runnable examples; a human gets a working quick-start. Decisions from the user: query library only (no MCP) but stored **as a graph of SQE graphs**, not text; add `examples/` with runnable apps; do all cleanup including CI guards.

## Design principle: explore the graph, never ingest it
The code KG (`codekg.trig`, ~6.5 MB / 75K triples) must never be read into an agent's context. Agents explore it through narrow, bounded interfaces: named queries (workstream 2) and the workbench app (workstream 5). This shapes every workstream:
- **AGENTS.md** says so explicitly: do not `cat`/Read `codekg.trig`, `api-reference.generated.md` (4.9K lines) or other large generated files; start from `list_queries(topic=...)` or the workbench, then drill down. Give a 5-line "typical exploration" recipe (find topic -> pick query -> follow `implementedByIdentifier` -> open only the source file/lines returned).
- **Query results are bounded by default**: `run_query` applies a row limit (default ~25) with a "N more rows; refine or page" footer, returns compact tables (symbol, file:line, one-line summary), never raw triples, and supports paging/`describe(symbol)` for one-symbol neighbourhoods.
- **Guardrails**: the query library's free-form SPARQL entry point enforces a `LIMIT` and warns on unbounded `CONSTRUCT`/`DESCRIBE`/`SELECT *`; the workbench KG browser pages and collapses by default.
- **Discoverability without bulk**: a tiny generated "KG map" (<60 lines: topics -> counts -> query names) is the only KG summary meant to be read whole; AGENTS.md links to it instead of the data.
- **Make the repo enforce it**: a test that asserts AGENTS.md stays under a size budget and that the KG map is under its budget; the query log (workstream 8) flags queries returning huge results so the FAQ can recommend narrower named queries.
- Also consider a `.claudeignore`-style note / Claude Code permission deny rule suggestion for `codekg.trig` in AGENTS.md so a stray Read is discouraged.

## Starting assumptions: app-building stack (living guidance)
These are the default assumptions we start from, written into AGENTS.md as "Default stack for apps built on starlayer". They are explicitly provisional: as we build different app types we revise them and record why.
- **Backend:** FastAPI/Starlette + Jinja2; all semantic logic stays in Python (`select_widgets`, SHACL validation, SPARQL, store access).
- **Interactivity:** server-rendered HTML + HTMX (inline validation via HTML fragments); no client-side validation logic to mirror SHACL.
- **Graph visualization:** one vendored library (e.g. Cytoscape.js) in a contained pane; more JS only there if a use case demands it.
- **No Node build chain**; UI behind optional extra `starlayer[workbench]`; core stays UI-free.
- **Neutral form model:** `select_widgets` output feeds a framework-neutral structure (property, widget, constraints, value, errors) rendered by templates and also served as JSON, so other frontends (React, native) remain possible.
- **Testing:** `httpx`/`TestClient` for fragments, a few Playwright end-to-end checks.
- **Not defaults:** Streamlit/NiceGUI/Dash (opaque HTML, fights custom SHACL widgets); React/Vue SPA (build chain, duplicated logic) — revisit if an app type needs rich client interaction.
- **Revision process:** a `docs/app-stack-guidance.md` records each assumption, the evidence from apps built so far (`graph_workbench` first), and a changelog; AGENTS.md links to it. Each new example app ends with a short "did the default stack hold?" note that feeds back into this doc, and revisions are also captured as curated KG nodes (`slkg:Guidance` linked to the capabilities/examples that motivated them) so agents can query them.

## Graph workbench decisions (round 2; the full, current version is in [graph-workbench-app.md](graph-workbench-app.md))
- Widget selection follows the SHACL UI scoring algorithm (`select_widgets`); `shui:editor`/`shui:viewer` annotations feed the candidate set, they don't bypass scoring.
- **Division of labour**: the scoring algorithm is built into starlayer. Running a node against a shape plus a scoring graph yields a widget IRI per property; the app never scores. The app's only widget logic is the widget-IRI → HTML template mapping (one Jinja partial per widget class, with a visible fallback for unmapped IRIs). So gaps in the baseline scoring graph are library/data issues; gaps in the mapping are app issues.
- starlayer should ship a generic datatype-keyed baseline scoring graph (library addition, deferred; the app carries a private copy until a separate approved PR).
- Users edit the UI layer (scores, matchers, annotations, order/group, label role) inside the app, with the same two-layer treatment, writing to a user scoring file so baseline upgrades never clobber their intent.
- **Location (supersedes the `apps/` folder idea): a separate repo `hidden-graph/starlayer-apps`** — starlayer is the platform, apps are built on it. Verified: the public `hidden-graph` org currently has only `starlayer`, `rdflib-starlight` and `.github`, so this repo does not exist yet (the user creates it on GitHub). Locally it should be a sibling checkout, `~/Documents/GitHub/starlight/starlayer-apps`, next to `~/Documents/GitHub/starlight/starlayer` (remote `hidden-graph/starlayer`). Layout: `graph_workbench/` as the first app, a root README index, and apps depend on `starlayer` (editable path locally, `git+https://github.com/hidden-graph/starlayer.git` pinned to a commit in CI). This also fully avoids touching the library. Note `gh` is not installed on this machine, so repo creation/issues need the GitHub web UI or installing `gh`. Other local repos (`KnowledgeGraphExplorer`, `RDF_Tree_Claude`) belong to the personal `jclem326` account and are prior art to skim.
- v1 is file-based (Turtle/TriG/N-Triples); store backends are later. Root selection is a first-class option (shape targets, class, IRI list, SPARQL, all subjects, no-incoming). Triple terms: read-only chips first, `TripleTermEditor` in M3.
- **Two-layer editing**: immutable base layer + edit layer (additions as triples; deletions as reifications of the deleted triple term plus metadata; modification = deletion + addition). Effective view = (base − deletions) ∪ additions; display modes merged / highlighted / base / edits; validation on the effective view; undo/redo on the edit layer; combine → Save, Save As, or save edit layer only.
- Milestones: M0 skeleton+baseline scores, M1 lazy tree+roots, M2 panel+edit layer, M3 richer widgets+triple-term editor+combine, M4 UI-config editing, M5 dogfood/perf/polish.
- Resolved: deletions are `wb:Deletion` resources that `rdf:reifies` the deleted triple term (plus timestamp/optional reason); root selection and display-mode preferences persist in a sidecar `.workbench.json`.
- **Sessions are saveable as a TriG file** (supersedes my earlier "session only" answer): "Save session" writes one TriG dataset holding the in-progress work, and "Open session" restores it exactly. Named graphs: the edit layer (additions + `wb:Deletion` reifications), the UI-config edit layers (shapes and scoring), and a `wb:Session` metadata graph (references to the base data/shapes/scoring files by path plus RDFC hash so a changed base is detected on reopen, the chosen roots, display mode, selected node, undo/redo history). The base files themselves stay untouched. Save session is distinct from combine (Save / Save As write the merged graph); the UI warns on exit with unsaved edits and offers to save the session.
- Open for the session file: whether it should also embed a copy of the base data (self-contained, portable but larger) or only reference it (default: reference + hash, with an "embed base" option).
- These decisions have been folded into [graph-workbench-app.md](graph-workbench-app.md).

## Immediate step: put the plans in the repo (done)
- These plans live in `docs/app-development-plans/` (this file as `repo-prep-plan.md`, plus `graph-workbench-app.md` and a `README.md` index). Docs only, no library code. Wording in this file that refers to the "approved plan" or to plan mode is a leftover of how it was drafted.

## Progress (2026-10-18)
- Workstream 1 done: `AGENTS.md`, `CLAUDE.md`, "Rules that bite" in the three subpackage `CLAUDE.md` files, a test guarding `AGENTS.md`.
- Workstream 6, part 1 done: root `README.md` (with a tested example), `CONTRIBUTING.md`, `docs/README.md` (the docs map), `docs/sparql/README.md`, dead links fixed in the graph and shacl docs READMEs.
- Workstream 6 guards done: `scripts/check_docs.py` (links, anchors, guide index, paths in the Rules-that-bite blocks), run by `build.py --check` and so by CI. Open decision: guide `05d-shacl-library-registry.ipynb` calls a removed function; it is listed as a known exception in `check_docs.py` until it is repaired or deleted.
- Still open in workstream 6: the remaining stale-doc repairs (the "Notes on guides" file, Appendix A status, the changelog-style paragraph at the top of `docs/guides/README.md`, `future_enhancements.md` cleanup).

## Workstreams

### 1. Agent entry point (highest leverage, smallest effort)
- New root `AGENTS.md` (+ root `CLAUDE.md` that just says "read AGENTS.md"). Short (<120 lines). Contents: repo layout; how to install/run tests from the right cwd (`pip install -e ".[test]"`, `pytest -m "not integration"`; note deselected opt-in groups); the generated-file rule (never hand-edit `*.generated.md`, `starontology.trig`; run `python scripts/build.py`); **"Use the knowledge graph first"** section with load snippet, the three layers (ontology / generated / curated), the named-query entry point, and the caveat that call resolution is heuristic (zero callers = lead, not proof); links to the three subpackage `CLAUDE.md` files and to `docs/README.md`.
- Slim the three subpackage `CLAUDE.md` files (shacl is 988 lines): add a "Rules that bite" section (~30 lines) at the top; leave history below under a clear "Design history" heading. Fix their stale paths (`docs/testing-strategy.md`, `tests/vendor/...`, "starsparql").
- Add a generated `docs/generated/kg-overview.generated.md` is NOT needed; AGENTS.md links to `functionality-overview.generated.md`.

### 2. Query library as a graph of SQE graphs
- New curated file `packages/starlayer/starlayer/codekg/curated/queries.ttl` (loaded into the curated graph). Each query is an `sqe:` RDF tree (the repo's own RDF encoding of SPARQL, produced by `starlayer.sparql.sqe.to_rdf.sqe_parse_to_tree` and decoded by `from_rdf.sqe_tree_to_query` / `to_text.sqe_tree_to_text`), wrapped in a small `slkg:` resource: `slkg:NamedQuery` with `rdfs:label`, `dcterms:description`, `slkg:answersCompetencyQuestion`, `slkg:aboutTopic` (-> `slkg:CapabilityArea`/`slkg:Capability`/spec section), `slkg:queryRoot` (-> the SQE tree root), and parameter declarations (`slkg:Parameter` with name/type/default).
- Ontology additions in `codekg/ontology.ttl`: `slkg:NamedQuery`, `slkg:CompetencyQuestion` (promote the rows in `competency-questions.md` to RDF with status), `slkg:aboutTopic`, `slkg:answersCompetencyQuestion`, `slkg:queryRoot`, `slkg:queryParameter`. Add SHACL shapes for them (reuse the `sqe_validate` pattern in `sparql/sqe/shapes.py`).
- New `starlayer/codekg/queries.py`: `list_queries(topic=None)`, `get_query(name)`, `run_query(name, **params)` which loads the dataset, decodes the SQE tree to a `Query`, binds params, runs it via `StarQuery`. Also `queries_for_topic(capability_iri)` so topic -> query links are traversable in SPARQL itself.
- Seed ~15 queries from `competency-questions.md` (who calls X, what overrides Y, public API of module, untested functions, capabilities and their implementing symbols, notebooks demonstrating X, ...).
- **Risk:** the SQE encoder may not cover every SPARQL feature (OPTIONAL/FILTER/aggregates/property paths). Step 1 of this workstream is a round-trip coverage probe; queries the SQE form can't express get logged in the library as a documented gap (and become upstream-style TODOs in `docs/`), not silently stored as text.
- Tests in `tests/codekg/unit/`: every stored query SQE-validates, round-trips to text, executes against the committed `codekg.trig` and returns non-empty (or documented-empty) results; every `aboutTopic` resolves.

### 3. Enrich and wire up the curated KG
- Populate and load the curated graph: extend `starlayer/codekg/__init__.py` to load `curated/*.ttl` into `CURATED_GRAPH_IRI` (it already reserves it) and expose `load_codekg_dataset(include_curated=True)`.
- Fill the empty links: `demonstratedBy` (notebooks -> symbols; extend extractor or derive from code cells importing/calling symbols, with `notebookPath`/`cellIndex`), `slkg:examplifiedBy` (examples/ -> capabilities), spec sections (SHACL 1.2/SPARQL 1.2 section IRIs), gap-matrix rows (`docs/shacl/shacl12-gap-matrix.md`), upstream issues (`docs/upstream-issues/*`), docs pages (`seeAlsoPath`).
- Add a test that every `slkg:implementedByIdentifier` in `functionality.ttl` resolves in `codekg.trig` (currently unchecked).
- Add a "how to build with starlayer" capability taxonomy: tag each capability with `slkg:appRole` (storage, query, validate, infer, UI-generate) so an agent can go from "I need to build a form app" to capabilities, queries, symbols, and examples.

### 4. Keep the KG usable while it can lag the source
**Decision (2026-10-18): CI does not check `codekg.trig`.** `build.py --check --skip codekg` stays as is; `build.py --only codekg apidocs` rebuilds on demand. So the KG can be behind the source, and the plan makes that visible instead of preventing it:
- `build_codekg.py` records a small build stamp in the KG (a `slkg:KGBuild` node: git commit, date, source file count). `run_query`/`list_queries` print it in their footer ("KG built from commit abc1234, 3 days old"), and AGENTS.md says to rebuild when it is older than the code being changed.
- AGENTS.md states plainly that the KG may lag, how to rebuild (`python scripts/build.py --only codekg apidocs`, about 30 s), and that line numbers in query results should be checked against the file.
- Auto-append the `codekg/CHANGELOG.md` entry from `build_codekg.py` instead of by hand.
- The tests on stored queries run against the committed `codekg.trig`, so they check the queries, not the KG's freshness.

### 5. Runnable examples (`examples/`)
- `examples/README.md` index + small apps, each with a pytest in `tests/examples/` so they cannot rot:
  1. **`graph_workbench` – flagship: a generic graph viewer/editor driven by SHACL shapes. Both an example and a shipped tool.** Given a data graph + shapes graph (+ optional `shui:` annotations), it: lists node-shape targets/instances, renders a form per node using `select_widgets` (`shacl/ui_widget_selection.py`), edits values, validates live via `StarShaclSchema.validate`, shows violations inline, and saves back to Turtle/TriG/store (rdf-1.2/Oxigraph or Fuseki backend). Also a read-only graph/neighbourhood view (`shacl.extract_subgraph`). Packaged as a runnable module (`python -m starlayer_workbench` or `examples/graph_workbench/`); shipped as a separate optional extra (`starlayer[workbench]`) so the core stays UI-free. Pending UI-tech choice (see open questions): default is a small local web app (Python server + minimal JS, no build step) so agents can drive/test it headlessly. It self-describes via the KG: its own shapes/widgets are curated nodes. Use it to browse the code KG itself (dogfooding: KG shapes -> forms).
  2. `sparql12_service` – load Turtle 1.2 with triple terms into a `StarLayerGraph` (rdf-1.1 encoding by default, Oxigraph if installed), run SPARQL 1.2 queries, entailment option.
  3. `rules_and_entailment` – SRL ruleset (`parse_ruleset`) + OWL RL inference.
- `examples/app-template/`: minimal project skeleton (pyproject, shapes/, app.py, tests/) that an agent can copy to start a new app.
- Each example gets curated-KG nodes linking to the capabilities it demonstrates.
- Promote qualified-only features users need (`select_widget(s)`, `parse_ruleset`) in the guides and AGENTS.md; do not change `__all__` without a separate decision.

### 6. Fix stale docs and add guards
Repairs (all found in survey):
- Rewrite root `README.md`: current single-package layout, real install + dev commands (`pip install -e ".[test]"`), a real usage example, links to AGENTS.md, docs map, examples. Resolve the "must stay in sync" duplication by making `packages/starlayer/README.md` a thin pointer (or generate it from the root one in `build.py`). Fix its dead `../../docs/README.md` link.
- Rewrite `CONTRIBUTING.md` (single package, `scripts/build.py` and the CI generated-files check, test tiers, ruff, where to add tests).
- New `docs/README.md` as the **docs map**: guides, generated reference, design/gap docs (`packages/starlayer/docs/*`), upstream issues, KG. Add missing `packages/starlayer/docs/sparql/README.md`; fix `docs/graph/README.md` and `docs/shacl/README.md` links (`../CLAUDE.md`, `../CHANGELOG.md`, `starshacl/assets/`).
- `docs/guides/`: move the stray "Notes on guides and other comments" to the repo task tracker/`docs/working/`; move the changelog-style history paragraph out of the top of `docs/guides/README.md`; resolve `05d-shacl-library-registry` (delete or index it); fix `docs/user-guide-version.json` (missing notebooks/appendices, nonexistent "superseded" files and "Task List"); finish or label Appendix A (currently 8 markdown-only cells, self-described WIP) and run the 4 unexecuted code cells in `04d-shacl-ui.ipynb`.
- Fix stale test-path mentions (`tests/w3c_turtle12/README.md`, `docs/shacl12-gap-matrix.md` references).
- Housekeeping: strengthen `.gitignore` (`__pycache__`, `.pytest_cache`); decide on archiving `docs/working/archive/`.
Guards (new, in `scripts/check_docs.py`, wired into `build.py --check` and CI):
- Relative-link and anchor checker across `*.md` and notebook markdown cells.
- Manifest/index drift: every notebook in `docs/guides/` appears in `README.md` and `user-guide-version.json` and vice versa.
- Every file path mentioned in AGENTS.md / CLAUDE.md files exists.
- Optional: warn on "Last reviewed" older than N days.

### 7. Feedback channel: bugs and suggestions to GitHub (humans and agents)
- `.github/ISSUE_TEMPLATE/` issue forms: `bug.yml`, `suggestion.yml`, `docs-or-kg-gap.yml` ("the KG/docs couldn't answer my question"), `spec-conformance.yml`; `config.yml` linking to Discussions. Labels created for each (`from-agent`, `kg-gap`, `docs`, `conformance`).
- Agent path: AGENTS.md "Reporting problems" section: use `gh issue create --template ...` with required fields (version/commit, backend, minimal repro, what the KG/docs said), and a `slkg:`-IRI field for the symbol/capability involved so reports link back into the KG.
- Helper `starlayer.feedback` (repo tooling, excluded from the wheel like `codekg`): `build_issue_url(kind, title, body, symbols=[...])` returns a pre-filled `issues/new` URL and an optional `gh` command. It never submits on its own; the human or the agent's user confirms (posting to GitHub is outward-facing).
- Workbench gets a "Report an issue" button that uses the same helper.
- Triage doc: `docs/CONTRIBUTING-feedback.md` (what happens to a report, how reports become curated-KG/gap-matrix updates).

### 8. Query log and auto-generated FAQ
- **Primary feed is the public endpoint's server-side log (see "Public KG endpoint")**; the rest of this workstream describes the local fallback. Log every named-query and free-form query made through `starlayer.codekg.queries` (and the workbench's KG browser) to a local, gitignored JSONL (`.starlayer/query-log.jsonl`): timestamp, query name or SPARQL text, topic IRIs, params, row count, duration, caller kind (human/agent if declared via env var), and an `empty_result` flag. Opt-out via env var; no network, no personal data.
- `scripts/build_faq.py` aggregates logs (from any number of contributors' log files passed in, or a shared log committed as an anonymised summary) into `docs/generated/faq.generated.md`: top named queries per topic, most-asked free-form questions grouped by topic, and **unanswered/empty-result questions** ranked, each rendered with its answering named query (from the query graph) or a "no answer yet" marker.
- Closing the loop: unanswered clusters become candidate `slkg:CompetencyQuestion` entries and a pre-filled `docs-or-kg-gap` issue (workstream 7). FAQ is built into `build.py` but not CI-checked for freshness (it depends on local data); the generator and its output format are tested with fixture logs.
- Privacy/consent note in AGENTS.md: logs stay local unless the user chooses to share a summary.

## Suggested order / phasing
1. Workstream 1 + the README/CONTRIBUTING/docs-map fixes in 6 (fast, unblocks everyone).
2. Workstream 6 guards (so later work can't regress).
3. Workstream 2 (SQE coverage probe first), then 3.
4. Workstream 7 (feedback templates; cheap, early value), then 4, then 5 (examples depend on the curated links; `graph_workbench` first), then 8 (needs the query library to exist).
Each phase is its own commit on `prep-for-app-development`.

## Critical files
- New: `AGENTS.md`, `CLAUDE.md`, `docs/README.md`, `examples/**`, `scripts/check_docs.py`, `starlayer/codekg/queries.py`, `starlayer/codekg/curated/queries.ttl`
- Edit: `README.md`, `CONTRIBUTING.md`, `packages/starlayer/README.md`, `starlayer/{graph,sparql,shacl}/CLAUDE.md`, `docs/guides/README.md`, `docs/user-guide-version.json`, `packages/starlayer/docs/{graph,shacl}/README.md`, `starlayer/codekg/__init__.py`, `codekg/ontology.ttl`, `codekg/competency-questions.md`, `scripts/build.py`, `scripts/build_codekg.py`, `.github/workflows/test.yml`, `.gitignore`

## Reuse (do not rebuild)
- SQE encode/decode: `starlayer/sparql/sqe/{to_rdf,from_rdf,to_text,shapes}.py`; query execution: `StarQuery` in `starlayer/sparql/star_query.py`.
- Loader pattern: `starlayer/codekg/__init__.py` (fresh-copy-per-call, `CURATED_GRAPH_IRI`).
- Check harness: `scripts/build.py --check --skip codekg` (isomorphism/byte compare) – extend rather than add a second runner.
- Existing generators: `scripts/generate_api_docs.py`, `generate_functionality_overview.py`.

## Verification
- `python scripts/build.py --check --skip codekg` passes (now including the docs checks; the code KG stays out of CI).
- `pytest -m "not integration"` green, including new `tests/codekg/unit` (query library) and `tests/examples`.
- Smoke as a fresh agent: in a clean checkout, follow only AGENTS.md to (a) install, (b) run a named query ("who calls X") and get results, (c) run an example, (d) run tests. Record any step that needed outside knowledge and fix the docs.
- `python scripts/check_docs.py` reports zero broken links/drift; CI workflow runs it.
- Validate curated queries/ontology additions with `sqe_validate` and the new shapes.

## Public KG endpoint (proposed 2026-10-18; replaces the earlier "hosting" note)
**Idea (user):** the code and curated KG do not need to live in the repo for outside users, and an outside agent should not have to build its own. Agents query a **public, read-only copy**, so we can log what they ask (see workstream 8) instead of each agent keeping a private copy. Nothing stops an agent building its own (`build_codekg.py` stays), but the documented path is the public one.

**What it needs**
- **A host** running a read-only SPARQL endpoint (Oxigraph server fits: the library already supports it as a store) with a query timeout, a result cap, no update endpoint and rate limiting. A thin HTTP API in front of it (named queries by id + parameters, plus a size-limited free-form route) is easier to log and limit than a raw SPARQL endpoint, and matches the "bounded results, never the whole graph" principle.
- **A publish step**: on merge to `main` (or on demand) a job loads `codekg.trig`, the curated graphs and `queries.ttl` into the endpoint, replacing the old copy. The build stamp from workstream 4 becomes the endpoint's "built from commit X on date Y".
- **A client**: `starlayer.codekg.queries` takes `endpoint=` (default: the public URL when reachable) and falls back to the local file, so offline or sandboxed agents still work. `get_codekg_dataset()` stays.
- **Server-side logging**: query text or named-query id, parameters, timestamp, row count, duration, a caller-kind header. This replaces the contributor-local log as the main feed to the FAQ (workstream 8); the local opt-in log stays for offline use. AGENTS.md must say that queries to the public endpoint are logged, what is kept, and for how long.

**Decisions needed before building:** who hosts it and who pays; the domain; retention period and what counts as personal data; whether free-form SPARQL is allowed or only named queries; abuse handling; whether to keep `codekg.trig` in the repo once the endpoint exists (it must stay until the publish pipeline does, because the scripts, tests and generated API docs read it).

**Limits:** GitHub Pages cannot run an endpoint or log queries, so this needs real hosting. A published KG is only as fresh as its last publish. An agent without network access cannot reach it. A later local stdio MCP server could wrap the same queries; MCP is still deferred.

**Effect on workstream 1:** AGENTS.md describes the local KG now and carries a short "planned: public endpoint" note, with no URL until one exists.

## Open risks
- SQE may not express all needed SPARQL; mitigated by the coverage probe and logging gaps.
- A lagging `codekg.trig` can mislead an agent; mitigated by the build stamp and AGENTS.md guidance, not by CI.
- `README.md` sync approach (pointer vs. generated) is a small design choice made during implementation.

## Open items from `future_enhancements.md` to settle before or with this work (reviewed 2026-10-18)
Checked against the repo, not just read:

**Do first (they feed the workstreams):**
- **Clean `packages/starlayer/docs/future_enhancements.md` itself.** Several entries are already stale: "20+ notebooks import `starlayergraph`" (none do now), the three root-level frozen SHACL guides and the "CLAUDE:" leftover in the Manchester guide (both gone), "only two examples exist in `packages/starlayer/examples/`" (the folder does not exist), and two entries about `docs/api-reference.md` (archived 2026-10-17; replaced by the generated docs). An agent will treat this file as a source of truth, so fix it as part of workstream 6.
- **The "Before publishing" checklist** overlaps workstream 6 (steps 5 and 7: re-execute guides, check for stale claims). Reconcile it with `check_docs.py` so there is one list.
- **Code-KG extractor misses `namedtuple(...)` types** (8 types in `starontology/manchester.py`). Fix before workstream 2/3, since the query library's answers are only as complete as the KG.
- **More examples / a `StarLayerDataset` example:** fold into workstream 5 (include a multi-graph example).

**With the workstreams:**
- **Functionality overview: a guide reference for each item, and stub guides for gaps** (curated graph `demonstratedBy` links, workstream 3). Known gaps: no guide for `derive_shape()`, none for `validate()`/`StarShaclSchema` as a whole.
- **No HTML-rendered user guide:** decide when writing the docs map (workstream 6). The workbench could serve rendered guides, so this may be answered by the app.
- **Remaining guide-review findings** (Getting Started missing the Manchester guide, the `06c` isomorphism wording, the stale `subgraph_extraction` docstring): workstream 6.

**Defer:** the SHACL UI shapes for the validation shapes and the `pyoxigraph` direct API (both app-time), SRL follow-ups (waiting on the spec), the three import mechanisms, rdflib 8, the testing-process question, and the upstream-bug tail.

