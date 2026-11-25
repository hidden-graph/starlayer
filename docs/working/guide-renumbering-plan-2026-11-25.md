# Guide renumbering plan (2026-11-25)

Status: PLAN ONLY. Nothing in `docs/guides/`, `scripts/`, `tests/` or `packages/` was changed to make this document. Every number below comes from a scan of the repository at commit `5b9d39b3` (working tree as of 2026-11-25, with the user's uncommitted edits to `05.02` and `05.03` in place). Where a count is a heuristic, it says so.

The decisions this plan implements (user, 2026-11-25): file names `NN.MM-title.ipynb` for every guide (including `01.01-getting-started.ipynb`); the chapter lead becomes `NN.01`; `05a..05h` become `05.04..05.11`; `07a..07c` become `07.01..07.03`; the appendices keep their names; headings fully qualified (`# 02.03 Title`, `## 02.03.1 ...`, `### 02.03.1.1 ...`); unnumbered headings stay unnumbered; old names removed with no alias, stub or redirect; every reference updated; text edits go through `scripts/guide_staging.py`; changes are approved one notebook (or one group of cells) at a time, with the notebook saved and closed first, and nothing else pushed with it.

## 1. The mapping table

New file names keep the title part of the old name. No new name clashes with another file. Chapter 07 has no lead guide, so `07a` becomes `07.01`. Chapter 01 has one guide, `01.01`.

Columns: H1 = the `#` title; H2 / H3 / H4 = the number of numbered `##`, `###`, `####` headings whose text changes (a heading counts only if it carries a number today: `1.`, `1.1`, `.3.1`). "Cells (max)" is an upper bound on the cells that change for any reason (heading, link target, link text, bare id, "section N" reference, code comment); it includes the "How to run this notebook" cell, whose link to `01-getting-started.ipynb` changes in all but four guides.

| # | Old file | New file | Old H1 | New H1 | H1 | H2 | H3 | H4 | Cells (max) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `01-getting-started.ipynb` | `01.01-getting-started.ipynb` | 01 Getting Started | 01.01 Getting Started | 1 | 4 | 0 | 0 | 6 |
| 2 | `02-graphs.ipynb` | `02.01-graphs.ipynb` | 02 Graphs | 02.01 Graphs | 1 | 2 | 11 | 0 | 15 |
| 3 | `02a-graphs-datasets.ipynb` | `02.02-graphs-datasets.ipynb` | 02a Working with Datasets | 02.02 Working with Datasets | 1 | 3 | 4 | 0 | 9 |
| 4 | `02b-oxigraph-wrapper.ipynb` | `02.03-oxigraph-wrapper.ipynb` | 02b The Oxigraph-backed graph (`StarLayerGraph` / `StarLayerDataset`) | 02.03 The Oxigraph-backed graph (`StarLayerGraph` / `StarLayerDataset`) | 1 | 3 | 0 | 0 | 5 |
| 5 | `02c-graph-content.ipynb` | `02.04-graph-content.ipynb` | 02c Reading and Building Graph Content | 02.04 Reading and Building Graph Content | 1 | 6 | 0 | 0 | 8 |
| 6 | `02d-combining-comparing-graphs.ipynb` | `02.05-combining-comparing-graphs.ipynb` | 02d Combining and Comparing Graphs | 02.05 Combining and Comparing Graphs | 1 | 5 | 0 | 0 | 7 |
| 7 | `02e-graphs-inferencing.ipynb` | `02.06-graphs-inferencing.ipynb` | 02e Inferencing using RDF, RDFS and OWL 2 RL | 02.06 Inferencing using RDF, RDFS and OWL 2 RL | 1 | 5 | 9 | 0 | 16 |
| 8 | `02f-owl-dl-reasoning.ipynb` | `02.07-owl-dl-reasoning.ipynb` | 02f OWL 2 DL Reasoning | 02.07 OWL 2 DL Reasoning | 1 | 5 | 0 | 0 | 7 |
| 9 | `03-sparql.ipynb` | `03.01-sparql.ipynb` | 03 SPARQL | 03.01 SPARQL | 1 | 5 | 1 | 0 | 10 |
| 10 | `03a-sparql-12-queries.ipynb` | `03.02-sparql-12-queries.ipynb` | 03a SPARQL 1.2 in queries | 03.02 SPARQL 1.2 in queries | 1 | 5 | 0 | 0 | 8 |
| 11 | `03b-preparing-extending-checking-queries.ipynb` | `03.03-preparing-extending-checking-queries.ipynb` | 03b Preparing, extending and checking queries | 03.03 Preparing, extending and checking queries | 1 | 4 | 0 | 0 | 6 |
| 12 | `03c-sparql-entailment.ipynb` | `03.04-sparql-entailment.ipynb` | 03c SPARQL Entailment | 03.04 SPARQL Entailment | 1 | 4 | 0 | 0 | 6 |
| 13 | `04-srl-sparql-rules.ipynb` | `04.01-srl-sparql-rules.ipynb` | 04 SRL (SPARQL Rules) | 04.01 SRL (SPARQL Rules) | 1 | 9 | 0 | 0 | 11 |
| 14 | `04a-srl-running-rule-sets.ipynb` | `04.02-srl-running-rule-sets.ipynb` | 04a SRL: how a rule set runs | 04.02 SRL: how a rule set runs | 1 | 11 | 0 | 0 | 18 |
| 15 | `04b-srl-more-features.ipynb` | `04.03-srl-more-features.ipynb` | 04b SRL: more features | 04.03 SRL: more features | 1 | 6 | 0 | 0 | 12 |
| 16 | `04c-srl-vs-sparql.ipynb` | `04.04-srl-vs-sparql.ipynb` | 04c SRL vs. SPARQL | 04.04 SRL vs. SPARQL | 1 | 14 | 7 | 0 | 22 |
| 17 | `05.01-validating-with-shacl-1.2.ipynb` | `05.01-validating-with-shacl-1.2.ipynb` | 05.01 Validating with SHACL 1.2 | 05.01 Validating with SHACL 1.2 (unchanged) | 0 | 0 | 13 | 16 | 34 |
| 18 | `05.02-starlayer-shacl-engine.ipynb` | `05.02-starlayer-shacl-engine.ipynb` | 05.02 The StarLayer SHACL engine | 05.02 The StarLayer SHACL engine (unchanged) | 0 | 0 | 5 | 0 | 10 |
| 19 | `05.03-shapes-as-classes.ipynb` | `05.03-shapes-as-classes.ipynb` | 05.03 SHACL shapes as classes | 05.03 SHACL shapes as classes (unchanged) | 0 | 0 | 0 | 0 | 1 |
| 20 | `05a-shacl-node-expressions.ipynb` | `05.04-shacl-node-expressions.ipynb` | 05a SHACL 1.2 Node Expressions | 05.04 SHACL 1.2 Node Expressions | 1 | 9 | 19 | 0 | 32 |
| 21 | `05b-shacl-and-sparql.ipynb` | `05.05-shacl-and-sparql.ipynb` | 05b SHACL and SPARQL | 05.05 SHACL and SPARQL | 1 | 2 | 3 | 0 | 8 |
| 22 | `05c-shacl-inference-rules.ipynb` | `05.06-shacl-inference-rules.ipynb` | 05c SHACL Inference Rules | 05.06 SHACL Inference Rules | 1 | 13 | 0 | 0 | 16 |
| 23 | `05d-shacl-ui.ipynb` | `05.07-shacl-ui.ipynb` | 05d SHACL UI | 05.07 SHACL UI | 1 | 4 | 4 | 0 | 13 |
| 24 | `05e-shacl-profiling.ipynb` | `05.08-shacl-profiling.ipynb` | 05e SHACL Profiling | 05.08 SHACL Profiling | 1 | 5 | 6 | 0 | 14 |
| 25 | `05f-shacl-subgraph-extraction.ipynb` | `05.09-shacl-subgraph-extraction.ipynb` | 05f SHACL Shape-Scoped Subgraph Extraction | 05.09 SHACL Shape-Scoped Subgraph Extraction | 1 | 12 | 0 | 0 | 15 |
| 26 | `05g-building-on-shacl.ipynb` | `05.10-building-on-shacl.ipynb` | 05g Building on SHACL | 05.10 Building on SHACL | 1 | 7 | 5 | 0 | 13 |
| 27 | `05h-shacl-evaluate.ipynb` | `05.11-shacl-evaluate.ipynb` | 05h SHACL `evaluate()`: shaping data for another process | 05.11 SHACL `evaluate()`: shaping data for another process | 1 | 2 | 0 | 0 | 6 |
| 28 | `06-starlayer-schemas-and-ontologies.ipynb` | `06.01-starlayer-schemas-and-ontologies.ipynb` | 06 StarLayer Schemas and Ontologies | 06.01 StarLayer Schemas and Ontologies | 1 | 5 | 0 | 0 | 7 |
| 29 | `06a-manchester-syntax.ipynb` | `06.02-manchester-syntax.ipynb` | 06a OWL 2 Manchester Syntax | 06.02 OWL 2 Manchester Syntax | 1 | 17 | 1 | 0 | 21 |
| 30 | `06b-sparql-query-as-rdf.ipynb` | `06.03-sparql-query-as-rdf.ipynb` | 06b SPARQL Queries as RDF | 06.03 SPARQL Queries as RDF | 1 | 5 | 2 | 0 | 10 |
| 31 | `06c-srl-sparql-rules-as-rdf.ipynb` | `06.04-srl-sparql-rules-as-rdf.ipynb` | 06c SRL (SPARQL Rules) as RDF | 06.04 SRL (SPARQL Rules) as RDF | 1 | 6 | 1 | 0 | 10 |
| 32 | `06d-shacl-library-registry.ipynb` | `06.05-shacl-library-registry.ipynb` | 06d The SHACL Library Registry | 06.05 The SHACL Library Registry | 1 | 6 | 0 | 0 | 9 |
| 33 | `07a-serialization-formats.ipynb` | `07.01-serialization-formats.ipynb` | 07a Serialization Formats | 07.01 Serialization Formats | 1 | 2 | 7 | 0 | 11 |
| 34 | `07b-backend-graph-databases.ipynb` | `07.02-backend-graph-databases.ipynb` | 07b Where Your Data Lives: On-Disk Stores and Remote Endpoints | 07.02 Where Your Data Lives: On-Disk Stores and Remote Endpoints | 1 | 2 | 0 | 0 | 4 |
| 35 | `07c-canonical-hashing.ipynb` | `07.03-canonical-hashing.ipynb` | 07c Graph Comparison and Canonical Hashing | 07.03 Graph Comparison and Canonical Hashing | 1 | 2 | 0 | 0 | 4 |
| 36 | `appendix-a-public-resources.ipynb` | `appendix-a-public-resources.ipynb` | Appendix A: Public Resources | Appendix A: Public Resources (unchanged) | 0 | 0 | 0 | 0 | 2 |
| 37 | `appendix-b.ipynb` | `appendix-b.ipynb` | Appendix B | Appendix B (unchanged) | 0 | 0 | 0 | 0 | 1 |
| 38 | `appendix-b1-sqe-shared-parts.ipynb` | `appendix-b1-sqe-shared-parts.ipynb` | Appendix B1: Named, Shared Parts in `sqe:` Syntax Trees | Appendix B1: Named, Shared Parts in `sqe:` Syntax Trees (unchanged) | 0 | 0 | 0 | 0 | 2 |
| 39 | `appendix-b2-dl-reasoning-examples.ipynb` | `appendix-b2-dl-reasoning-examples.ipynb` | Appendix B2: A Complex DL Reasoning Example - Constraint Satisfaction at Scale | Appendix B2: A Complex DL Reasoning Example - Constraint Satisfaction at Scale (unchanged) | 0 | 0 | 0 | 0 | 4 |
| | **Total** | | | | **32** | **190** | **98** | **16** | |

Totals: 32 H1 titles, 190 `##`, 98 `###` and 16 `####` headings change: 336 headings in 34 guides (the 32 renamed guides, plus subsection headings only in `05.01` (13 `###` + 16 `####`) and `05.02` (5 `###`)). `05.03` and the four appendices need no heading change (`05.03` still has one link cell to change). In `05.01` and `05.02` the sections are already `## 05.01.4`; only the relative subsection headings (`### .3.1`, `#### .3.1.1`, `### .4.2`) become `### 05.01.3.1`, `#### 05.01.3.1.1`, `### 05.02.4.2`.

Other files that carry the mapping (not guides): `docs/guides/README.md`, `docs/guides/STYLE_GUIDE.md`, `docs/guides/parked-02b-oxigraph-wrapper.md`, `parked-02d-combining-comparing-graphs.md`, `parked-02f-owl-dl-reasoning.md`, `docs/user-guide-version.json`, `tools/kg/codekg/curated/notebook-links.ttl`. Decisions for these are in section 7.

Parked files (proposal, see question 2): `parked-02b-oxigraph-wrapper.md` -> `parked-02.03-oxigraph-wrapper.md`, `parked-02d-combining-comparing-graphs.md` -> `parked-02.05-combining-comparing-graphs.md`, `parked-02f-owl-dl-reasoning.md` -> `parked-02.07-owl-dl-reasoning.md`. They are referenced only by themselves (no file in the repo links to them), so the rename costs nothing outside them, but `check_docs.py` checks their relative links, so their links to `02f-owl-dl-reasoning.ipynb` etc. must follow.

## 2. Reference inventory

Method: `grep -rIn` over the repository excluding `.git`, `.venv`, `node_modules`, `.pytest_cache`, `__pycache__`, `.ruff_cache` and `docs/guides-staging` (which is git-excluded, see 2.9), plus a JSON-level scan of every cell of every notebook (so counts are per cell, not per JSON line). The search keys were the 35 old stems (`01-getting-started` ... `07c-canonical-hashing`) and the letter forms (`05c`, `4.a`). The three `05.0x` guides and the appendices keep their names, so links to them are not counted as changes.

### 2.1 File names, by kind

| Kind | Where | Count | Examples |
|---|---|---|---|
| Links between guides, `](old.ipynb)` | markdown cells of 39 notebooks | 172 links | `05.02-starlayer-shacl-engine.ipynb` cell `e9020001` (the index table, ~20 links); `04c-srl-vs-sparql.ipynb` cell `04c00002`; every "How to run" cell (`](01-getting-started.ipynb)`, 36 notebooks: all guides except `01` itself, `appendix-a` and `appendix-b`) |
| Links to old names in guide-folder Markdown | `docs/guides/README.md` (~32), `STYLE_GUIDE.md` (~12), `parked-*.md` (~8) | 42 links (README 32, parked 8, STYLE_GUIDE 2), plus 11 un-linked file names in `STYLE_GUIDE.md` (e.g. line 11 `` `01-getting-started.ipynb` ``, line 33 `` `05f-shacl-subgraph-extraction.ipynb` ``) | `README.md` lines 11-60 |
| Links with an anchor | `03c-sparql-entailment.ipynb` cell `a1c2e304` (`02e-graphs-inferencing.ipynb#3.5-Detecting-inconsistencies`), `05b-shacl-and-sparql.ipynb` cell `419ec2e1` (2 anchors), `appendix-b2-dl-reasoning-examples.ipynb` cells `6ea6f15b`, `259216b9`, `parked-02f-owl-dl-reasoning.md` | 6 links | `check_docs.py` does not verify `#anchor` on a `.ipynb` target, only on `.md`. 3 of the 6 are already broken today: `02f...#1.2-A-small-logic-puzzle`, `02f...#1.-OWL-2-DL-entailment` (02f has no such heading) and `05.01...#Known-limitations` (05.01 has no such heading). One self-anchor, `05d-shacl-ui.ipynb` cell `n10-fixed-intro` -> `#appendix-the-built-in-widgets`, is unnumbered and stays valid |
| Links between guides to a name that does not change | 05.01-05.03, appendices | 53 links | no change needed |
| `README.md` tables and links | `docs/guides/README.md` | 33 `.ipynb` links, 31 letter labels (`**2.a`, `5.c`, `**5.2`, `**5.3`) | whole file is rewritten (section 7, question 4) |
| `docs/user-guide-version.json` | `artifacts.notebook` | 32 old names (note: three lines, 05h/05.02/05.03, are mis-indented today) | one list, rewritten sorted |
| `tools/kg/codekg/curated/notebook-links.ttl` | `slkg:notebookPath` | 57 of 64 links name a renamed notebook (01: 3, 02: 16, 03: 8, 04: 5, 05: 16, 06: 6, 07: 3); 7 keep their path (05.01 x5, 05.02 x1, appendix-b1 x1). The link ids (`nl:05f-...`) are labels, see section 5 | line 15 `slkg:notebookPath "docs/guides/01-getting-started.ipynb"` |
| Scripts | `scripts/check_docs.py`, `scripts/check_notebook_links.py`, `tools/kg/codekg/notebook_links.py`, `scripts/build*.py` | 0 names | They glob `docs/guides/*.ipynb` and read README with `\(([\w.-]+\.ipynb)\)`, which accepts `02.03-...ipynb`. `notebook-links-shapes.ttl` pattern `^docs/guides/[A-Za-z0-9_.-]+\.ipynb$` accepts the new names. Nothing to change for names |
| Tests that name guides | `packages/starlayer/tests/repo/test_hunt_docs_notebooks.py` | 7 lines name 8 old guides (lines 44, 53, 69, 89 (two), 111, 115, 131) plus `test_guide_04f_section_references_point_at_the_right_sections` whose regex `^## (\d+)\. (.*)$` stops matching once the headings are `## 05.09.1 ...`; test function names carry old ids (`test_guide_05a_...`, `..._04f_...`) | must change in the same stage as `05f`/`06a`/etc. |
| Tests that glob or copy the guides (no change needed) | `tests/notebooks/test_guide_notebooks.py` (`GUIDES.glob("*.ipynb")`, opt-in `--notebooks`; test ids are the stems, so any `-k` selection by old stem changes), `tests/kg/unit/test_notebook_links.py` (copies `GUIDES`), `tests/repo/test_guide_staging.py` (synthetic `a.ipynb`, `b.ipynb`) | 3 files | none |
| Tests in `starlayer-reasoning` | `packages/starlayer-reasoning/tests/test_infer.py:5` (`02e-graphs-inferencing.ipynb`), `test_infer_owl_dl_rustdl.py:21` (`05e-owl-dl-reasoning.ipynb`, a name that has not existed for some time) | 2 docstrings | |
| Package source | `packages/starlayer-reasoning/starlayer_reasoning/owl_dl_rustdl.py:28`, `packages/starlayer/starlayer/graph/CLAUDE.md:3`, `packages/starlayer/starlayer/shacl/ui/widget_selection.py:14` | 3 comments | other agents are editing under `packages/`, see stage 8 |
| Ontology comment text | `starontology/_sources/shacl12-validation-shapes.ttl` (28 `rdfs:comment` lines "see docs/guides/05d-shacl-ui.ipynb") and its generated copy `starontology/shacl/shacl12-shacl.ttl` (28) | 56 lines | the `.ttl` under `shacl/` is generated: edit the source and run `python scripts/build.py --only starontology`; generated-file changes get their own commit (AGENTS.md) |
| `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `README.md` (repo root), `.github/`, `pyproject.toml` | | 0 names | `AGENTS.md` and `pyproject.toml` say `docs/guides/*.ipynb` generically; `docs/README.md:6` names `guides/01-getting-started.ipynb` (1) |
| `docs/README.md` | line 6 | 1 | `[getting started](guides/01-getting-started.ipynb)` |
| `docs/design/` | `future_enhancements.md` 10 (lines 30, 37, 220, 306, 371-374, 380), `graph/manchester_syntax_gap_analysis.md:170`, `shacl/shacl12-gap-matrix.md:223`, `shacl/starlayer-profile-direction.md:3` | 13 | some already name guides that do not exist (`03a-sparql-inferencing.ipynb` at `future_enhancements.md:220`) |
| `docs/app-development-plans/` | `graph-workbench-app.md:50`, `repo-prep-plan.md` lines 56, 62, 63, 107 | 5 | |
| `docs/working/` | `guide-coverage-2026-11-13.md:38`, `step-a-error-scheme-plan-2026-11-25.md` (13, lines 153-193, written today by another agent), `archive/shacl-engine-cutover.md:269` (names guides that do not exist) | 15 | dated notes; see question 10 |
| `docs/generated/` | `api-overview`, `api-reference`, `functionality-overview`, `query-library` | 0 names | none of them names a guide file, so none goes stale from the rename (the grep for `ipynb`, `docs/guides` is empty). The agent cannot and need not rebuild them |
| Built KG files (not committed, git-ignored) | `tools/kg/codekg/codekg.trig` (1), `starlayer-kg.trig` (56) | 57 | stale until `python scripts/build.py --only codekg kg`; the agent may not rebuild, list as stale |
| Skill text | `.claude/skills/review-notebook-links/SKILL.md:41` documents the link-id convention `nl:<notebook-number>-<cell-id>` | 1 | changes only if the ids are renamed (question 6) |
| Outside this repository | `../graph-workbench/docs/deferred.md:17` (`04d-shacl-ui.ipynb`, already stale); the `starlayer-main` worktree is on the archived branch | 1 | cannot be changed by this task; external URLs, see question 12 |

### 2.2 In-text references that are not file names

A scan of all markdown cells, all code-cell source, and the Markdown files in `docs/guides/` (guides folder only). A line can match several patterns.

| Pattern | Hits | Where | Mechanical? |
|---|---|---|---|
| A. Link target `](old-name.ipynb)` (also with `#anchor`) | 214 | 172 in markdown cells, 42 in README/STYLE/parked; 0 in code cells | Yes: a lookup in the mapping table |
| B. Bare letter id `05c`, `04b`, `02e` in prose, titles or link text | 73 | 31 own H1 (`# 05d SHACL UI`), 25 as link text (`[05c](05c-...)`), 11 in prose (`04-srl-sparql-rules.ipynb` cell `d1000007`: "04a"), 6 in md files | Yes for H1 and link text (id -> new id, `04` -> `04.01`); prose ids: yes by lookup, but read each |
| C. Dotted letter ids `2.e`, `3.a`, `4.d`, `5.f` | 36 | 28 in README (labels), 3 in STYLE_GUIDE (`3.b`, `5.f`, `5.e`), 5 in notebooks | README: rewritten whole. The 5 notebook hits are already wrong today and need a human: `02b` cells `e936afab` ("2.e") and `894e7dce` ("3.a"), `05g` cells `c0a19dc0` ("4.e"), `f504cab4` ("4.a"), `212cf303` ("4.d") |
| D. "section N", "Section N.M", "§N" | 195 | 148 markdown cells, 17 code-cell comments, 30 in md files | Partly. By heuristic: 128 name a heading of the same notebook and no other guide or spec on the line (mechanical, after a read); 23 share a line with another guide or spec (human); 12 resolve to no heading of the notebook, mostly spec section numbers (`§4.2`, "SRL section 4.2" linking to w3.org, `§3 "Profiles of SHACL"`) and must NOT be rewritten (human, mostly "leave"); 30 are in `STYLE_GUIDE.md` (its own section numbers `§2`, `§9`, `§10`, which are not guide numbers) or the `parked-*.md` files ("Section 4 of 02b") |
| E. "guide N" / "Guide 04b" | 0 | | n/a |
| F. Already fully qualified `05.01.4.2`, `section 05.02.4.2` | 58 | `05.02` 33, `05.03` 11, `05.01` 8, `05e` 2, README 2, `05a` 1, `05b` 1 | No change: they already use the target scheme. The script must leave them alone and verify each still names an existing heading afterwards |
| G. Relative heading text `.3.1`, `.4.2` | 50 | `05.01` 44, `05.02` 5, `05e` 1 | Yes: 34 are the headings themselves (29 in `05.01`, 5 in `05.02`); 16 are bullets/prose: 13 in the two overview lists of `05.01` (cells `1ce6a456` and `a5040001`: `- **.3.1 Working with RDF 1.2 terms**`), and 3 in prose (`05.01` `ed000009`, `ed000016`, `05e` `4ef4c393`) which need a read |
| H. Anchor in a link | 6 + 1 | see 2.1 | The anchor is recomputed from the new heading text; the 3 already broken ones need a human |
| Bare dotted numbers with no word "section" (e.g. "see 3.5") | ~190 raw hits, almost all spec versions (`1.2`, `1.1`) | | The script lists candidates that equal a heading number of the same guide, excluding `1.0/1.1/1.2/1.3`; none was found that needs a rewrite, so I would only report them |

Ten examples of each pattern:

A. `04c-srl-vs-sparql.ipynb` `04c00002` ("[04](04-srl-sparql-rules.ipynb) shows how to write rules, [04a](04a-srl-running-rule-sets.ipynb) ..."); `05.02` `e9020001` (`[05f](05f-shacl-subgraph-extraction.ipynb)`, `[05g](05g-building-on-shacl.ipynb)`, `[05e](05e-shacl-profiling.ipynb)`, `[05d](05d-shacl-ui.ipynb)`); `02b-oxigraph-wrapper.ipynb` `e936afab` and 35 other "How to run" cells (`](01-getting-started.ipynb)`); `03c-sparql-entailment.ipynb` `a1c2e304`; `appendix-b2-dl-reasoning-examples.ipynb` `6ea6f15b`; `06c-srl-sparql-rules-as-rdf.ipynb` (8 links); `README.md` line 11 `(01-getting-started.ipynb)`.

B. `02a-graphs-datasets.ipynb` `7a46c5fd` (`# 02a Working with Datasets`); `05d-shacl-ui.ipynb` `n01-title` (`# 05d SHACL UI`); `06c...` `71241a76` (`# 06c SRL (SPARQL Rules) as RDF`); `03-sparql.ipynb` `12ad2aba` ("03a", "03b" in prose); `04-srl-sparql-rules.ipynb` `d1000005` ("[04c](...)"); `04b-srl-more-features.ipynb` `n12-group-md2` ("04a"); `04c...` `e2000007` ("04b"); `05.02` `c0f90001` ("[05c](05c-shacl-inference-rules.ipynb)"); `STYLE_GUIDE.md` ("04f" in section 12, a guide that does not exist); `parked-02b-oxigraph-wrapper.md` line 1 ("# Section 4 of 02b").

C. `README.md` lines 13-60 (`**2.a [Working with datasets]`, `**4.c [SRL vs. SPARQL]`, `**5.d [SHACL UI]`, `**5.g [Building on SHACL]`, `**6.b ...`, `**7.c ...`); `02b` `e936afab` ("2.e"); `02b` `894e7dce` ("3.a"); `05g` `f504cab4` ("4.a"); `05g` `c0a19dc0` ("4.e"); `05g` `212cf303` ("4.d"); `STYLE_GUIDE.md` line 85 ("`3.b` and `5.f`").

D. Mechanical candidates: `01-getting-started.ipynb` `bd5253b9` ("Section 1 installs ... section 2"); `02d-combining-comparing-graphs.ipynb` `c1a2e004` ("section 3"); `02e-graphs-inferencing.ipynb` `84a1536e` ("Section 4"); `04c-srl-vs-sparql.ipynb` `e2000070` ("section 11.6"); `05f-shacl-subgraph-extraction.ipynb` `89087497` ("Section 12"); `05d-shacl-ui.ipynb` `n28-launch` ("section 1"); `06d-shacl-library-registry.ipynb` `e15a0b33` ("section 6"). Code comments: `03-sparql.ipynb` `b2d4f6a8` ("see section 2"), `04b-srl-more-features.ipynb` `b8fa7710` ("stays safe in section 4"). Human decisions: `05.02` `c0f90001` ("section 12" next to a link to `05c`: that is section 12 of the 05c guide, so it becomes `section 05.06.12`); `05a-shacl-node-expressions.ipynb` `2f33594a` ("[05c](...), section 2"); `04a` `e1000007` ("SRL section 4.2" with a w3.org link: spec, leave); `06c` `a8f39e1c` ("§4.2" of the SRL draft: leave); `05e-shacl-profiling.ipynb` `32d1eb05` ("§4.4, Profile Hierarchies" of the Profiling draft: leave) and its H2 "## 5. Declaring ... (§3, "Profiles of SHACL")" (number prefix only); `05h-shacl-evaluate.ipynb` `f5a00004` (code comment "see section 2.1": which guide? it says `(StarLayerGraphs, see section 2.1)` while the same comment in 05.01 and 05.03 says `section 05.01.2`: a wrong reference today, rewrite to `05.01.2`, human).

F. `05.02` `e9020001` ("section 05.02.2", "section 05.02.3", "section 05.02.4", "section 05.02.5", "section 05.02.6"); `05.02` `c0f90001` ("05.01.4.3", "05.03.2", "05.01.3.7"); `05.03` `f5c00002` ("section 05.03.1", "05.03.2", "05.03.3"); `05.01` `5a28c71d` ("section 05.01.1"); `05e` `e0b10001` ("Section 05.01.4.3"); `05e` `ed000011` ("section 05.01.4.4"); `README.md` line 27 ("05.01.1").

G. `05.01` `1ce6a456` (`- **.3.1 Working with RDF 1.2 terms**`, `.3.2` ... `.3.8`: 8 bullets); `05.01` `a5040001` (`- **.4.1 Each graph of a dataset**` ... `.4.5`); `05.01` `ea000001` (`#### .3.1.2 Reifiers of a value: ...`); `05.01` `eb000003` (`#### .3.2.2 At least one value matches: ...`); `05.01` `a3040001` (`### .3.4 Property path comparisons`); `05.01` `a3070001` (`### .3.7 Severity, messages and conformance`); `05.01` `a3080005` (`#### .3.8.1 A value when none is stored`); `05.01` `ed000009` (`### .4.4 Naming the graphs in a report`); `05.02` `e9020010` (`### .2.2 Imports of the shapes graph`); `05e` `4ef4c393` (prose).

H. See 2.1 "Links with an anchor".

What needs a human decision (summary): the 5 stale dotted ids (C); the 23 + 12 "section" hits that share a line with another guide or a spec (D); the 3 broken anchors (H); the 3 relative-number prose references (G); the one wrong `section 2.1` in `05h`; bare chapter numbers (`04`, `05`, `06` used as a guide id) in prose, if any (the script flags a bare two-digit id that is not followed by a letter). Everything else (172 link targets and their link text, 31 H1 ids, the 11 prose letter ids, ~128 own-guide section references, the 34 heading numbers of `05.01`/`05.02`, 13 bullets) can be rewritten by the script, and each rewrite is shown in the diff for the user's approval.

### 2.3 What is also in the staging copy

`docs/guides-staging/base` and `docs/guides-staging/stage` each hold a copy of every guide, README, STYLE_GUIDE, parked files, the manifest and the `.ttl` (each copy has the same 400-odd old-name hits). They are git-excluded (`.git/info/exclude`), never committed, and are rebuilt by `push`; they must be excluded from the final leftover scan.

## 3. Heading rewrite rules and the dry-run script

### 3.1 How a heading is recognised

Only markdown cells are scanned, line by line. A heading is a line that starts at column 0 with one to four `#`, a space, then the text; the line must be outside a fenced block (a line starting with three backticks or `~~~` toggles the fence). Headings can sit in the middle of a cell (6 cases today: `02c` cell 6, `04a` cell 25, `04c` cell 33, `05d` cell 39, `05g` cell 4, `07a` cell 6); the rule is per line, not per cell. Code cells are never scanned for headings (a `# comment` line is not a heading). Numbered lists (`1. text`, `2) text`) never start with `#`, so they are not headings and are not touched. Setext headings (underlined) do not occur; the script asserts that every line it classifies as a heading matches the ATX form and reports any markdown cell whose first line looks like a title but is not an ATX heading.

### 3.2 The rewrite table

NN.MM is the new id of the notebook the cell belongs to (taken from the file's own mapping row, not from the old text; the script asserts that the old id in the H1 equals the old id of the file).

| Old form | Example | New form |
|---|---|---|
| H1 `# 02b Title` / `# 02 Title` / `# 01 Title` | `# 02a Working with Datasets` | `# 02.02 Working with Datasets` (the old id token is replaced, the title text is untouched) |
| H1 already `# 05.01 Title`; appendix H1s (`# Appendix B1: ...`) | | unchanged |
| H2 `## N. Title` | `## 3. Matching blank nodes` | `## 02.05.3 Matching blank nodes` (no trailing dot, as `05.01` does it today) |
| H2 already `## 05.01.4 Title` | | unchanged; checked that the prefix equals the guide's id |
| H3 `### N.M Title` | `### 2.1 Canonical form: ...` | `### 02.01.2.1 Canonical form: ...` |
| H3/H4 relative `### .3.1 T`, `#### .3.1.2 T`, `### .4.2 T` | `### .4.2 When the shapes are wrong` | `### 05.01.4.2 When the shapes are wrong`; `#### .3.1.2 ...` -> `#### 05.01.3.1.2 ...` (the guide prefix comes from the notebook) |
| Overview bullets `- **.3.1 Title**:` | `05.01` `1ce6a456` | `- **05.01.3.1 Title**:` |
| Unnumbered headings: `How to run this notebook`, `Related guides`, `Known limitations`, `Further reading`, `Appendix`, `Appendix: the built-in widgets` and its H3 children, `What sqe: covers` | | unchanged (60 such headings in all, 37 of them "How to run this notebook"; 10 are H3 under numbered sections, next row) |
| Unnumbered H3 under a numbered H2 | `02c` ("How an RDF list is stored", "Reading and maintaining lists", "Using prefixes"), `04a` (6), `04b` (1) | unchanged (10 headings; question 8) |
| Appendix guides' own numbered sections (`## 1.` in `appendix-a`, `appendix-b1`, `appendix-b2`) | | unchanged (question 9) |

Sanity checks the script runs before writing: the H2 numbers of a notebook run 1, 2, 3 ... without a gap (no gaps or duplicates exist today: I checked all 39 notebooks); every H3/H4 number has the number of the nearest preceding H2/H3 as its prefix; the new numbered heading is unique inside the notebook. Duplicate numbers or a gap stop the script for that notebook and print the heading.

Headings that contain a spec citation keep it: `## 5. Declaring starlayer.shacl's own conformance (§3, "Profiles of SHACL")` becomes `## 05.08.5 Declaring ... (§3, "Profiles of SHACL")`; only the leading number token is rewritten.

### 3.3 `scripts/renumber_guides.py` (to be written by the later agent)

It works on the staging tree only (`docs/guides-staging/stage`), never on `docs/guides`, so the IDE never sees a half-made change, and the output is pushed with `guide_staging.py`.

- Data: the mapping table of section 1 as a dict in the script (`old stem -> new stem`, id `05c` -> `05.06`, `05` is not an id), a test pins it to the files on disk (every notebook in the mapping, every new name unique, the pattern `^\d\d\.\d\d-`).
- `python scripts/renumber_guides.py plan --only 05c-shacl-inference-rules.ipynb [--chapter 05]`: a dry run. For each selected notebook it computes the result and prints, per notebook: the new file name; the heading table (old -> new, with cell id); link rewrites (cell id, old target -> new target, text change); in-text rewrites split in "will rewrite" and "needs a decision" (each with its cell id and the sentence); and counts. It writes nothing.
- `... apply --only ...`: writes the same result into the staging copy (new content under the new file name, old file removed in the staging copy), after which `guide_staging.py diff` shows it cell by cell.
- Rewrite order inside a cell, so one rule cannot disturb another: (1) links `](...)` with file names and anchors, (2) link text equal to an old id, (3) heading lines, (4) overview bullets, (5) `section N` / `Section N.M` / `sections N and M` / `§N` references, with the default referent rule: the referent is the cell's own guide unless the same sentence contains another guide marker (`.ipynb`, an old id, `guide`, `spec`, `draft`, `SRL`/`SHACL`/`SPARQL` followed by `section`, a w3.org URL, a `§` inside quotation marks), in which case the item goes to "needs a decision"; (6) bare ids `\b0[1-7][a-h]\b` and dotted ids `[1-7]\.[a-h]` (decision list). An old number is only rewritten when it resolves to an existing heading of the referent notebook; otherwise it is reported.
- Verification built in (exit 1 when any fails): every notebook still loads as JSON and passes `nbformat.validate` when `nbformat` is installed (it is in the `notebooks` extra; otherwise a structural check: `cells` list, each cell has `id`, `cell_type`, `source`); cell ids unchanged, unique and in the same order; only `source` of markdown cells (and of code cells in the comment-only list, question 7) differs from the input; no `outputs`/`execution_count` change; JSON dumped as `json.dumps(nb, indent=1, ensure_ascii=False) + "\n"`, the same bytes `guide_staging._dump` writes, so an untouched notebook is byte-identical; after writing, rescan: every link target exists (old or new tree), every `.ipynb#anchor` equals the anchor of a heading of the target, every numbered heading is fully qualified, no old stem remains in the notebook.
- `python scripts/renumber_guides.py leftovers`: the final repository-wide check. It greps all tracked files (`git ls-files`, so the staging copy and the built KG are excluded) for the 35 old stems and the 35 old ids in the filename and `section`/`§` forms, and prints each hit with its class (allowed-historical list from question 10 versus must-fix). Exit 1 on any must-fix hit.
- A `check_docs.py` extension (small, in stage 0): verify `#anchor` on `.ipynb` targets (the checker today only does it for `.md`), using the same anchor rule as the six existing links (`heading text with spaces as hyphens`). I could not confirm how GitHub's notebook renderer forms anchors for dotted headings such as `02.06.3.5-Detecting-inconsistencies`; the six existing anchors suggest `number-Words-with-hyphens`, case kept. The check should encode that same rule and be treated as best effort.

## 4. The staging tool and the user's concurrent IDE edits

### 4.1 What `scripts/guide_staging.py` does today, read in full

- Tracked set (`tracked()`): every file under `docs/guides/` (not hidden), plus the two `COMPANIONS`: `docs/user-guide-version.json` and `tools/kg/codekg/curated/notebook-links.ttl`. The path is the key in `base/`, `stage/` and the working tree.
- `merge_file` for a notebook merges by cell id and cell source when the notebook exists in stage and work; any other file (and a notebook missing on one side) is compared whole.
- A rename in the staging copy works today as delete plus create: `stage/OLD` removed, `stage/NEW` created. The merge then sees OLD with `stage=None`, and if `work == base` it deletes OLD in the working tree; if the user changed OLD since the last sync it reports "deleted on one side, changed on the other" and skips OLD. NEW has `base=None` and `work=None`, so the whole file is taken from the staging copy. There is a test for this (`test_a_guide_renamed_in_staging_is_moved_in_the_working_guides`).
- `push --yes` writes EVERYTHING pending in the whole tree (all notebooks, README, manifest, `.ttl`) in one go; there is no way to limit it. `pull` and `status` also cover everything. `init --force` deletes both copies and re-copies: it would discard pending staging edits and must not be used during the migration.
- Cell ids are never changed by the renumbering, so the merge keeps working cell by cell for the same notebook as long as the file keeps its path key.

### 4.2 What goes wrong, and what the tool needs

1. The rename changes the path key, so the cell-level safety is lost for the one push that renames: NEW is taken whole from staging. If the user edited OLD in the IDE after the last `pull`, OLD is skipped with a conflict, but NEW is still written, giving two copies and the user's edit only in OLD. Needed: **rename pairing**. When a path is deleted in staging and a new path appears with at least 80% of the same cell ids, treat them as one rename: refuse to push NEW when OLD has a conflict, and print `renamed OLD -> NEW`. (Small change in `plan()`/`push()`.)
2. **`--only PATH...` on `status`, `diff`, `pull` and `push`** (needed, the user's requirement that one push applies one notebook): accepts a path relative to `docs/guides` or the repository root; `--only OLD NEW` names a rename pair. `plan()` filters the names; `push` writes, backs up, and updates `stage` and `base` only for the selected paths, leaving every other pending edit untouched in the staging copy. A path that does not exist in any tree is an error. This is the change the coordinator asked for ("a per-notebook option"); a staging copy that holds only one notebook would work without a tool change, but it needs a second tree and breaks the `base`, so I recommend the option.
3. **`--cells ID[,ID...]` (optional)** for the cell-only link retargeting of a notebook in another chapter (stage section 6, B). It restricts a notebook's merge to those cell ids: cells not listed take the working copy's version, and after the push `stage` keeps its other pending cells and `base` advances only for the pushed cells. Without it the same effect is reached by discipline (stage only the unit being approved, so nothing else is pending), but the option makes "nothing else is pushed in the same push" a property of the tool rather than a habit. The later agent decides after the first two stages; the tests in `tests/repo/test_guide_staging.py` get one case per new option.
4. `push` prints a final line "reload any notebook that is open in the IDE". The tool cannot see unsaved IDE buffers (the working file on disk is all it reads), so the protocol below has the user close the notebook; I do not propose a tool-side check.

### 4.3 Protocol for each approval (one notebook, or one group of cells)

1. The agent runs `guide_staging.py pull --only <files>` and `status --only <files>`: the staging copy of this unit must equal the working file (no "yours" lines). If it does not, stop and ask: the user has unsaved or unsynced edits.
2. The agent stages the unit only (`renumber_guides.py apply --only <file>`), runs `guide_staging.py diff --only <files>`, runs the verification of section 3.3 and prints the summary: new file name, headings old -> new, links, in-text rewrites, "needs a decision" items.
3. The user reads the diff, resolves the decision items, SAVES AND CLOSES the notebook (and every other notebook in the same push, for a cell-only group), then says "push". (Closing matters: VS Code keeps the buffer of an open file, and the old tab of a renamed file stays open on a deleted path and can write the old name back.)
4. The agent runs `guide_staging.py push --only <files> --yes`, then (for a rename) `git add -A docs/guides` so Git records `OLD -> NEW`, and reports "pushed". The user reopens the new file.
5. Nothing else is pushed with it: the tool pushes only the named paths; README, manifest, `.ttl` and tests for this unit are pushed in their own approval or in the stage's closing approval (each is a separate named path).
6. Commits: one commit per stage after all its approvals and checks (section 6), not per notebook, because inside a chapter the notebooks link to each other and the tree is red between the first and last push of the chapter (6.1). `git add` only the stage's paths; never `git stash` (memory note); the user's uncommitted edits to other files stay uncommitted.

Before stage 1 starts, the user's uncommitted edits to `05.02` and `05.03` (shown today as `M`; `status` reports "yours: changed ed000013" in 05.02) must be pulled into staging and committed or at least saved and pulled, otherwise the first push of stage 1 hits them.

## 5. The notebook-links (KG) consequences

- `tools/kg/codekg/curated/notebook-links.ttl` holds 64 links, all to CODE cells. A link has `slkg:notebookPath`, `slkg:cellId`, `slkg:cellHash` (the first 16 hex digits of the SHA-256 of the normalized cell source), a review date, a comment and the symbols. The link id (for example `nl:05f-<cell id>`) is only a label: `notebook_links.load_links()` reads `notebookPath` and `cellId` from triples and uses the IRI fragment as the display name for `--show` and `--restamp`; no code derives a path from the id. Three ids are already out of step with their files (`nl:04d-n13-editors`, `nl:04d-n45-schema-select` for `05d`, `nl:05i-30c67e26` for `05.02`), which shows nothing depends on them.
- Cell ids do not change in the renumbering, and a code cell's text changes only where a comment mentions a section. Headings live in markdown cells, which no link uses, so a heading edit changes no link hash. I checked the 14 code cells whose comments say "section N" (the mechanical class): none of them is one of the 64 linked cells (I compared the cell ids to the `.ttl`), so the expected restamp cost is zero. The check is nevertheless part of every stage: `python scripts/check_notebook_links.py` must report `unchanged` for all 64. If a linked code cell ever changes, `--show` then `--restamp NAME` after the `review-notebook-links` skill review.
- What does need an edit: 57 `slkg:notebookPath` lines (one chapter at a time, in the same push as the chapter's renames; the file is a `COMPANION` of the staging tool). Until a chapter's path lines are changed, `check_notebook_links.py` reports those links `broken` ("cell ... is not in ...") or `moved` (it finds the same hash elsewhere), so the `.ttl` push belongs to the same stage as the renames.
- Link ids: propose renaming the prefix to the new number (`nl:05f-xxxxxxxx` -> `nl:05.09-xxxxxxxx`; a `.` inside a Turtle local name is legal when not first or last) and fixing the three mismatches, so the convention in `.claude/skills/review-notebook-links/SKILL.md:41` stays true. Cost: 64 ids, one edit per link block, mechanical. The generated `demonstratedBy` triples change their subject IRIs on the next rebuild. This is optional (question 6).
- `docs/generated/*.generated.md`: none names a guide file, so none changes. `tools/kg/codekg/codekg.trig`, `testskg.trig`, `starlayer-kg.trig` are git-ignored build products that carry the old paths (57 hits in the two I searched): they are stale until a maintainer runs `python scripts/build.py --only codekg kg`; the agent does not rebuild them and lists them as stale in each stage report. The KG test `tests/kg/unit/test_curated.py::test_every_notebook_link_names_symbols...` builds the KG on first use (about 30 s); the agent may run it, it does not touch committed files.
- `scripts/build.py --check` steps relevant to guides: `docs` (`check_docs.py`) and `notebooks` (`check_notebook_links.py`). The `starontology` step regenerates the SHACL ttl whose comments name `05d-shacl-ui.ipynb` (28 lines); see stage 8.

## 6. The stages

### 6.0 How a stage is built, and why it is not green after every push

A guide link needs a target that exists. Renaming one notebook changes inbound links in other notebooks (all notebooks link to `01-getting-started.ipynb`; `05.02` alone has 36 guide links). With one push per notebook, the tree cannot be green after every single push without an alias, and aliases are excluded. So:

- Each stage is one chapter. It has two kinds of approval: (P) a primary notebook of the chapter: file rename, H1, headings, own in-text references, and every link in it that points into this chapter or into an earlier-stage chapter, all in one push; (R) a referrer: a notebook of ANOTHER chapter that links into this chapter, pushed with only its link cells (and only those cells). A notebook is a primary once and a referrer in each stage it links into (cell-only each time).
- Between the first and last push of a stage the tree is red for `check_docs.py` (a link to a not-yet-pushed neighbour). The stage is committed only when all its approvals are done and every check below passes: the committed states are green. If the user prefers a notebook to be touched once (all links retargeted in its own push), the alternative is that links to later stages' names are written early and the tree stays red until stage 7 (Option A in question 1); I recommend the stage version above, at the cost of more small approvals.
- Every stage ends with a STOP: the agent prints the stage report (what was pushed, the check results, what is stale) and waits for the user's approval before the next stage starts. Nothing is pushed or committed across a STOP without a go.
- Checks run at the end of each stage (A = the common set): `python scripts/check_docs.py` (links, README and manifest vs disk, cell ids); `python scripts/check_notebook_links.py` (all 64 `unchanged`); `python scripts/renumber_guides.py verify --chapter NN` (all headings of the chapter fully qualified, every `.ipynb` link and `#anchor` resolves, no old stem of the chapter remains anywhere tracked); `pytest packages/starlayer/tests/repo packages/starlayer/tests/kg/unit/test_notebook_links.py packages/starlayer/tests/kg/unit/test_curated.py -q` (the tests that read or glob the guides; targeted, not the 4-minute full suite, which is only run if the user asks); `ruff check` for any `.py` touched. Running the guides' code cells is NOT part of the stages (only comments in code cells change; the opt-in `--notebooks` run is for the user).
- Per stage, besides the notebooks: README rows of the chapter, `docs/user-guide-version.json` entries of the chapter, the chapter's `slkg:notebookPath` lines in the `.ttl`, and the tests that name the chapter's guides. Each of these is its own named path in its own approval (they are Markdown/JSON/TTL, so they are pushed whole).
- Order is the user's: 0, then 05, 07, 06, 04, 03, 02, 01 (with README, STYLE_GUIDE, manifest), cleanup.

### Stage 0. Tooling and mapping (no guide is touched)

Files: new `scripts/renumber_guides.py` and its test `packages/starlayer/tests/repo/test_renumber_guides.py`; changes to `scripts/guide_staging.py` (`--only`, rename pairing, optional `--cells`) and `packages/starlayer/tests/repo/test_guide_staging.py`; `scripts/check_docs.py` (anchor check for `.ipynb` targets, one test). No notebook is touched.
Checks: the new tests; `python scripts/check_docs.py` still passes on the unchanged guides (it will report the three already-broken anchors of 2.1 once the anchor check exists: either fix them in stage 5/6 where their notebooks are, or list them as known until then; question 11); `ruff check scripts packages`; a dry-run of `renumber_guides.py plan` over all notebooks that writes nothing and prints the counts of this document (a regression check that the script and this plan agree).
Risks: the anchor check shows the three broken anchors; the tool change touches the tool the user depends on, so each option gets a test and the first real push uses `status --only` first.
STOP: user approves the tool and the mapping table (section 1) before any guide is staged.

### Stage 1. Chapter 05 (letters to numbers; the largest)

Primary notebooks (P), 11, one approval each:
`05.01-validating-with-shacl-1.2.ipynb` (29 heading numbers: 13 `###`, 16 `####`; 2 overview lists with 13 bullets; links to 05a-05h), `05.02-starlayer-shacl-engine.ipynb` (5 `###`; index table cell `e9020001`, settings table cell `c0f90001`, 36 links), `05.03-shapes-as-classes.ipynb` (links only), and the eight renames `05a-shacl-node-expressions` -> `05.04-...` (H1, 9 `##`, 19 `###`), `05b-shacl-and-sparql` -> `05.05-...`, `05c-shacl-inference-rules` -> `05.06-...` (13 `##`), `05d-shacl-ui` -> `05.07-...`, `05e-shacl-profiling` -> `05.08-...`, `05f-shacl-subgraph-extraction` -> `05.09-...` (12 `##`), `05g-building-on-shacl` -> `05.10-...`, `05h-shacl-evaluate` -> `05.11-...`.
Referrers (R), 5, cell-only: `02e-graphs-inferencing.ipynb`, `06-starlayer-schemas-and-ontologies.ipynb`, `06d-shacl-library-registry.ipynb`, `07c-canonical-hashing.ipynb`, `appendix-a-public-resources.ipynb` (and `05b`'s anchor to `05a#7.-Extending-...`, which is in a primary).
Other paths: `docs/guides/README.md` (chapter 5 rows), `docs/user-guide-version.json`, `notebook-links.ttl` (16 paths), `packages/starlayer/tests/repo/test_hunt_docs_notebooks.py` (names `05e`, `05f`, `05.01`; the `05f` section-regex test: new regex `^## 05\.09\.(\d+) (.*)$`; test names).
Risks: heaviest chapter (11 approvals, about 160 cells at most); `05.01` and `05.02` carry the user's uncommitted edits (resolve first); the relative `.3.1` bullets and `section 12` reference in `05.02` (cell `c0f90001`, means 05c section 12) need a human; the user is working on the 05 guides, so this is where a conflict is most likely: the pull/status step must be clean for each unit.
STOP.

### Stage 2. Chapter 07

P (3): `07a-serialization-formats` -> `07.01-serialization-formats`, `07b-backend-graph-databases` -> `07.02-...`, `07c-canonical-hashing` -> `07.03-...`.
R (4 notebooks, referrers of chapter 07): `02-graphs`, `02a-graphs-datasets`, `02d-combining-comparing-graphs`, `03a-sparql-12-queries` (links to `07a/07b/07c`).
Other paths: README rows, manifest, `.ttl` (3 paths), tests (`07b` at `test_hunt_docs_notebooks.py:111`).
Risks: small. `07a` has 7 `###` headings and 2 `##`.
STOP.

### Stage 3. Chapter 06

P (5): `06-starlayer-schemas-and-ontologies` -> `06.01-...`, `06a-manchester-syntax` -> `06.02-...` (17 `##`, long), `06b-sparql-query-as-rdf` -> `06.03-...`, `06c-srl-sparql-rules-as-rdf` -> `06.04-...`, `06d-shacl-library-registry` -> `06.05-...`.
R (5): `05e-shacl-profiling` (now `05.08`), `07a-serialization-formats` (now `07.01`), `appendix-a-public-resources`, `appendix-b`, `appendix-b1-sqe-shared-parts`.
Other paths: README, manifest, `.ttl` (6), tests (`06a`, `06b` names).
Risks: `06c` cell `a8f39e1c` ("§4.2" is the SRL draft's section, leave); the `06b` heading "## What `sqe:` covers" is unnumbered and sits before "How to run" (leave).
STOP.

### Stage 4. Chapter 04

P (4): `04-srl-sparql-rules` -> `04.01-...`, `04a-srl-running-rule-sets` -> `04.02-...`, `04b-srl-more-features` -> `04.03-...`, `04c-srl-vs-sparql` -> `04.04-...` (14 `##`, 7 `###`, 22 cells at most).
R (2): `02e-graphs-inferencing`, `06c-srl-sparql-rules-as-rdf` (now `06.04`).
Other paths: README, manifest, `.ttl` (5), tests (none name chapter 04).
Risks: `04a` has 6 unnumbered H3 (leave). `04a` cell `e1000007` "SRL section 4.2" is a spec reference (leave).
STOP.

### Stage 5. Chapter 03

P (4): `03-sparql` -> `03.01-...`, `03a-sparql-12-queries` -> `03.02-...`, `03b-preparing-extending-checking-queries` -> `03.03-...`, `03c-sparql-entailment` -> `03.04-...`.
R (7): `01-getting-started`, `02b-oxigraph-wrapper`, `02e-graphs-inferencing`, `04b-srl-more-features` (now `04.03`), `05.01-validating-with-shacl-1.2`, `05b-shacl-and-sparql` (now `05.05`), `06b-sparql-query-as-rdf` (now `06.03`). `01-getting-started` is touched again in stage 7 as a primary.
Other paths: README, manifest, `.ttl` (8), tests.
Risks: the stale "3.a" in `02b` cell `894e7dce` and the anchor in `03c` cell `a1c2e304` (`02e...#3.5-...`, whose target heading changes in stage 6; so this link cell is edited in stage 6, when `02e` is renamed, as an R of that stage).
STOP.

### Stage 6. Chapter 02

P (7): `02-graphs` -> `02.01-...`, `02a-graphs-datasets` -> `02.02-...`, `02b-oxigraph-wrapper` -> `02.03-...`, `02c-graph-content` -> `02.04-...`, `02d-combining-comparing-graphs` -> `02.05-...`, `02e-graphs-inferencing` -> `02.06-...` (5 `##`, 9 `###`), `02f-owl-dl-reasoning` -> `02.07-...`.
R (12): `01-getting-started`, `03b-preparing-extending-checking-queries` (now `03.03`), `03c-sparql-entailment` (now `03.04`, anchor to `02e`), `05.01-validating-with-shacl-1.2`, `05d-shacl-ui` (now `05.07`), `05g-building-on-shacl` (now `05.10`), `06d-shacl-library-registry` (now `06.05`), `07a`, `07b`, `07c` (now `07.01` to `07.03`), `appendix-b`, `appendix-b2-dl-reasoning-examples` (two anchors to `02f`).
Other paths: README, manifest, `.ttl` (16), the three `parked-*.md` renames (each its own approval; they link to `02f` and `02e#3.5-...`), tests (`02e`, `02f`, `test_hunt_docs_notebooks.py:89`).
Risks: the three already-broken anchors into `02f` (`appendix-b2` cells `6ea6f15b`, `259216b9`) need a human choice of target heading; `02c` has 3 unnumbered H3 (leave); `02e` carries the most "Section N" references of the chapter (cells `84a1536e`, `4cab0119`, `9fefc998`, `914fe93d`), several next to a link to another guide, so a human reads them.
STOP.

### Stage 7. Chapter 01, then README, STYLE_GUIDE and the manifest

P (1): `01-getting-started` -> `01.01-getting-started` (4 `##`, H1).
R (36 notebooks, one cell each, the "How to run this notebook" link): every other guide: `02.01` to `02.07`, `03.01` to `03.04`, `04.01` to `04.04`, `05.01` to `05.11`, `06.01` to `06.05`, `07.01` to `07.03`, `appendix-b1`, `appendix-b2` (`appendix-a` and `appendix-b` do not link to it). One approval for the whole group is acceptable if the user closes all of them; the cell-only option (`--cells`) keeps anything else of theirs out of the push.
Other paths (each its own approval): `docs/guides/README.md` rewritten (question 4), `docs/guides/STYLE_GUIDE.md` rewritten for the new scheme (question 3), `docs/user-guide-version.json` (all names; question 5), `docs/README.md:6`, `notebook-links.ttl` (3 paths and, if approved, the link ids), `tests` (`01-getting-started` in `test_hunt_docs_notebooks.py:44`).
Risks: the biggest fan-in (36 referrers), but each is one cell. STYLE_GUIDE section 3 (the standard "How to run" text) and 13 (the template) quote `01-getting-started.ipynb`, and the guide template has to be changed or the next new guide is written in the old scheme.
STOP.

### Stage 8. Clean-up of the scan

Not guides. Files: the 13 active design/plan docs (2.1), `packages/starlayer-reasoning/{starlayer_reasoning/owl_dl_rustdl.py,tests/test_infer.py,tests/test_infer_owl_dl_rustdl.py}`, `packages/starlayer/starlayer/graph/CLAUDE.md`, `packages/starlayer/starlayer/shacl/ui/widget_selection.py`, `starontology/_sources/shacl12-validation-shapes.ttl` and, in a separate commit, the regenerated `starontology/shacl/shacl12-shacl.ttl` (`python scripts/build.py --only starontology`), `.claude/skills/review-notebook-links/SKILL.md`. Possibly the dated notes in `docs/working/` (question 10).
Checks: `python scripts/renumber_guides.py leftovers` exits 0 (no old stem or old id in a tracked file outside the allowed list); `python scripts/build.py --only docs notebooks --check` and `python scripts/build.py --only starontology --check`; `ruff check packages/`; the targeted tests above; `git grep` of every old stem returns nothing outside the allowed list.
Risks: other agents change files under `packages/` at the same time, so this stage reads `git status` first and edits only comment lines in those files; comment-only changes, but a file that another agent has modified must wait for them (not `git stash`). `step-a-error-scheme-plan-2026-11-25.md` (13 names) is a live plan of another agent: ask before editing it.
Stale after the stage, for the maintainer to rebuild: `tools/kg/codekg/codekg.trig`, `starlayer-kg.trig`, `testskg.trig` (`python scripts/build.py --only codekg kg`), and, at release time, `python scripts/publish_kg.py`.
STOP and final report.

### Final repository-wide check (end of stage 8, and a shortened form at every stage)

1. `git grep -nE` for each of the 35 old stems and `\b0[1-7][a-h]\b` and `\b[1-7]\.[a-h]\b` over tracked files: zero hits outside the allowed list (dated working notes if question 10 says leave them; `docs/working/archive/`; third-party test data such as `w3c_sparql11/data/index.tsv`, which matches `02a`, `03a` etc. by accident, and `vendor/shacl12-test-suite`: these two groups must be on the allowed list, they are false positives).
2. `python scripts/check_docs.py`, `python scripts/check_notebook_links.py`, `renumber_guides.py verify` over all 39 notebooks: all headings fully qualified; all `.ipynb` links and anchors resolve.
3. `ls docs/guides` shows no file whose name starts `0Na-`, no `02-graphs.ipynb`, and the new names exactly as in section 1.
4. The targeted tests, then (only if the user asks) the full suite.

## 7. Questions for the user, with proposed answers

1. Green after every push is not possible without an alias. Which do you prefer? (A) each notebook pushed once, with every link retargeted at once, and the tree red until the last push, then green at the end; (B) stages as in 6.0: primary notebooks plus cell-only referrer pushes, green at each stage commit. Proposed: B (about 40 extra cell-only approvals, 36 of them in stage 7 for the one "How to run" link; they can be one group approval if you close those notebooks).
2. The `parked-02b/02d/02f-*.md` files: nothing links to them and README lists none. Proposed: rename with the guide (`parked-02.03-oxigraph-wrapper.md`, `parked-02.05-combining-comparing-graphs.md`, `parked-02.07-owl-dl-reasoning.md`), update their own links and "Section 4 of 02b"-style titles; no other change.
3. `STYLE_GUIDE.md` documents the old scheme. Lines to rewrite, with today's text: line 28 and line 106 (`# <Topic> — User Guide`: the guides read `# 02.03 Title`, not this form); line 47 ("`## N. Title` for top-level sections, `### N.M Subtitle` for subsections" -> `## NN.MM.N Title`, `### NN.MM.N.K Subtitle`); line 48 ("unnumbered headings ... never": your decision keeps "How to run this notebook", "Related guides", "Known limitations" unnumbered); line 50 (`### 2.2a`); line 53 ("`####` is never used"; `05.01` has 16 `####` headings); lines 11, 35, 41, 79, 113 (names of the `01` and `02` guides) and 33, 43, 57 (`05f-`, `02f-`, `02e-`); line 89 (`[Topic](NNx-filename.ipynb)` -> `[Topic](NN.MM-filename.ipynb)`, and the anchor example `02e-graphs-inferencing.ipynb#2.4-Detecting-inconsistencies` -> `02.06-graphs-inferencing.ipynb#02.06.3.5-Detecting-inconsistencies`, whose heading is `3.5` today); line 98 (`04a`-`04f`, a stale reference to files that do not exist); line 117 (`## 1. <First topic>` in the template). Proposed: rewrite in stage 7 as one approval. Decide whether the `####` ban stays (proposed: keep it; `05.01`'s 16 are renumbered as they are).
4. `README.md` layout. Proposed: one heading per chapter (`### 02 Graphs`), then one bullet per guide in the form `**02.03** [The Oxigraph-backed graph](02.03-oxigraph-wrapper.ipynb) - ...`, the chapter's lead guide first as `**02.01**`; chapter 07 gets a heading "07 Other" with no lead guide; update "Last reviewed"; drop the "Its headings are numbered 05.01.1" sentence (now true everywhere).
5. `docs/user-guide-version.json`: the file names are the public names of the guides, so a rename is a breaking change for anyone who linked them. Proposed: version `2.0.0`, `lastUpdated` 2026-11-25, notebook list rewritten sorted and re-indented (three lines are mis-indented today).
6. Link ids in `notebook-links.ttl` (`nl:05f-...`): rename the prefix to the new number (`nl:05.09-...`), fix the three that already disagree with their file, and update `.claude/skills/review-notebook-links/SKILL.md:41`? Proposed: yes, as a script step in the chapter's stage; costs nothing in hashes.
7. Code-cell comments that cite sections ("see section 2", 17 in 12 notebooks, none a linked cell): rewrite to the fully qualified number? Proposed: yes, comment text only, since the later reader sees the heading `## 03.01.2`.
8. The 10 unnumbered H3 headings under numbered sections (`02c` 3, `04a` 6, `04b` 1): number them (`### 04.02.3.1`) or leave? Proposed: leave; it is a content decision outside renumbering and adds new numbers to every reference.
9. The appendices keep their names; their headings (`# Appendix B1: ...`, `## 1. Two queries ...` in `appendix-b1`, `## 1.` ... in `appendix-a`, `appendix-b2`) stay as they are? Proposed: leave, since "Appendix B1" is the id in their title and README labels them `B1`, `B2`.
10. Historical working notes and design docs name guides by old letters, many already stale (`04d`, `04e`, `04f`, `05e-owl-dl-reasoning`): about 270 letter tokens in `docs/working` (96 in `archive/`), 30 in `docs/design`, 9 in `docs/app-development-plans`. Proposed: update the file names in live docs (`docs/README.md`, `docs/design/*`, `docs/app-development-plans/*`, `docs/working/guide-coverage-2026-11-13.md`) and leave dated notes and `docs/working/archive/` unchanged, because they record what the guides were called then; `leftovers` has an allowed list for them.
11. Fix the already-broken or stale references while renaming (3 broken anchors in `appendix-b2` and `05b`; "2.e", "3.a" in `02b`; "4.a", "4.e", "4.d" in `05g`; "section 2.1" in `05h`; "04f" in STYLE_GUIDE)? Proposed: yes, each as a "needs a decision" item in the unit where it sits, shown in the diff.
12. External links to old guide URLs (GitHub `blob/.../docs/guides/05d-shacl-ui.ipynb`, issues, PR descriptions, other repos: `graph-workbench/docs/deferred.md:17` names `04d-shacl-ui.ipynb`) break with no redirect, as decided. I could not scan GitHub issues, PRs, PyPI pages or other people's pages. Proposed: no action; mention in the release note.
13. Commit policy: one local commit per stage after its STOP is approved, never in the middle of a stage, no push, `git add` of the stage's paths only (the user's other uncommitted files stay). Proposed: yes; the generated `shacl12-shacl.ttl` in its own commit.

## 8. What I could not determine

- Whether GitHub's notebook renderer produces the anchor form used by the six existing links for headings that begin with a dotted number; the plan keeps the existing rule and treats it as best effort.
- Whether the user has other notebooks open with unsaved edits: the tool sees only files on disk; the protocol relies on the user closing the notebook.
- References outside this checkout (GitHub issues and pull requests, PyPI, blogs, the sibling repositories other than `graph-workbench`, which has one hit).
- The exact number of cells that change: section 1 gives upper bounds; the script's dry run (stage 0) gives the exact figure per notebook.
- Whether any code cell outside the comment cases mentions a guide by name in a string: the scan found no old stem in any code cell (0 hits in 172+ code cells scanned for patterns A, B, C), only "section N" comments (17 cells).
