# SHACL engine efficiency plan (2026-11-26)

Status: plan only, no code changed. Decision of 2026-11-26: keep the Python engine; a Rust port is reconsidered when the SHACL 1.2 specs are final and no longer changing (option B, a Rust extension for the inner loop, and option C, a full port, are parked). This plan is option A: find the efficiency gains inside the Python engine, above all where a shapes graph runs many SPARQL queries.

All figures were measured on a snapshot of `main` (769bdf06) on the author's current machine, with synthetic data and shapes (scripts in the session scratchpad, `perf/`). The October benchmarks (`shacl-engine-benchmarks.md`) ran on a 2014 laptop, so the two are not comparable. Every gain below is an estimate from a profile until a stage says it was verified.

## What was measured

| Workload | Result |
|---|---|
| Core validation (datatype, pattern, class, node shapes; 28k triples) | 0.008 ms per triple, 0.23 s in all |
| Cheap `sh:sparql` queries (3,600 calls) | 0.05 ms per call; `inject_everywhere`, the Python character scan that inserts the `VALUES` row for every call, is about 40% of it under the profiler but about 11 microseconds (20 to 25%) measured without it (Stage 0) |
| `sh:sparql` queries the pre-binding does not narrow, at 4 times the data | per-call cost grows: `?this` only in a `FILTER` 2.5x, aggregate sub-select 3.4x, property path 3.4x (total time quadratic) |
| Queries narrowed by the pre-binding (bound triple, two-hop join, `NOT EXISTS`, `OPTIONAL`) | flat per-call cost |
| Meta check (`shacl_shacl`) | 0.17 to 0.25 ms per triple, 20 to 30 times the core path; 8.4k shape triples take 1.45 s; SPARQL is only about 5% of it |
| Meta check profile | `shacl_list` re-reads and re-validates an RDF list on every visit: 16,405 calls for 8,801 focus visits, about 23% of the profile; 13.5 shape visits per focus node; `stringify_node` about 10% (22,840 calls); shapes-graph reads through `StarLayerGraph._quads` / `_terms` about a third |
| Rules, recursive reachability on chains of 20, 40, 80 | inferred triples 210, 820, 3,240 (4x each step); time 0.06, 0.17, 0.84 s (2.8x, then 4.9x): a naive fixpoint re-runs every rule on every focus node each iteration |
| Plan building, focus selection, report building | under 3% (October profile, not re-measured): not worth touching |

Oxigraph takes the query as text only (`Store.query(query: str, ...)`, no prepared-query or algebra object in pyoxigraph 0.5.13), so every run parses and plans the text again (about 0.03 ms). Only batching reduces the number of runs.

## How SHACL builds its queries today

Authored as text: `sh:select`, `sh:ask`, `sh:construct` and `sh:sparqlExpr` are string literals in the shapes graph (SHACL 1.2). The engine then edits the text: a `PREFIX` header is prepended, `$PATH` is replaced by regex, a `sh:sparqlExpr` body is wrapped in an f-string, an `ASK` becomes a `SELECT` by a regex over masked text when a blank node is pre-bound, `inject_everywhere` scans the text per call to insert the `VALUES` row, and `expressions.py` builds its `VALUES` queries with f-strings. The parsed `Node` AST (`parse_sparql`) is used once per text, cached (`_analyse`), only to reject forbidden constructs and find the projected variables.

Precedent for the tree-first pattern already exists: `sparql/sqe/rewrite.py` (correlated `EXISTS` to a join), `sparql/sqe/entailment.py` (RDFS entailment as a rewrite) and `sparql/relevant.py` all parse to the AST, edit it, render to text, check that the text parses again and fall back to the original text on any doubt. SHACL is the one place that still edits text. `rewrite.py` is documented as applying only when no `initBindings` are in use, and the SHACL path always has a pre-bound `?this`, so it never gets that speedup.

## Design: prepared queries

- **Stored form stays text.** The literals in the shapes graph are what SHACL 1.2 defines and what other processors read. The SQE tree may be an authoring and editing view in the workbench, which writes text to the literal.
- **The engine prepares each query once and keeps the result.** Parse the literal, apply the edits as tree operations (prefix header, `$PATH`, `sh:sparqlExpr` wrapping, pre-binding, later batching and rule rewrites), render once into a template with a slot for the pre-bound row. Per call only the slot is filled.
- **Which tree.** The `Node` AST from `parse_sparql`, with `ast_to_triples` and the SQE renderer for the text, as `rewrite.py` does. The RDF tree stays the form for storing, validating and editing queries.
- **Where the edits are made: on the RDF tree, with graph functions (proposed, to be tried in Stage 1).** Stage 0 edited the `Node` AST, as `sqe/rewrite.py` does, and encoded to RDF only to render, because the renderer reads only the RDF tree. The alternative is parse, encode to RDF once, then edit the RDF: `graph/ordinals.py` already has `append`, `insert_at`, `remove_at`, `replace_at` and `renumber_dense` for the `tree:ord` children, so "a `VALUES` node first in every group" is an `insert_at` on each `sqe:where`. This makes the RDF tree the one representation (the AST is only the parser's output), lets the tree's own validator (`validate_sparql_tree`) check an edited query before it is rendered (instead of re-parsing the text), and makes an edit data that can be logged, diffed and RDFC-1.0 hashed. Costs to check: graph edits are slower than list edits (paid once per query, so it should not matter), and the edit code has to use the tree vocabulary, not the AST kinds. Try both on the same Stage 0 corpus before choosing. Names: the tree functions were renamed after the Stage 0 snapshot (`sparql_to_tree`, `tree_to_sparql`, `validate_sparql_tree`, replacing `sqe_parse_to_tree` / `sqe_tree_to_text` / `sqe_validate`; commit 1c5aa822 and earlier); Stage 0's plugin used the old names.
- **Cache key and lifetime.** The key is the query text (before `$PATH` substitution) plus the set of pre-bound variables, never "the graph that was loaded", so an edited shapes graph re-prepares only the texts that changed and nothing goes stale. The cache is process-wide, bounded (LRU), and filled lazily at the first run, so a shape that never fires costs nothing.
- **`shacl_shacl`.** Its text stays in the shipped file; the tree is built on first use in a process and kept until the process ends or the module is reloaded. Measured on the 24 of its 28 distinct query texts that round-tripped: about 1.3 ms per query for encode, render and re-parse (31 ms in all), once per process. If the 31 ms ever shows up in a short CLI run, `scripts/build.py` can store the prepared queries beside `shacl12-shacl.ttl`, with a test that fails if they drift from a fresh build, as the existing stored-file test does.
- **`$PATH`.** A constraint reused on many property shapes has one text but a different path per shape. The prepared form is built from the text before substitution, with `$PATH` as a placeholder node, and each shape fills in its own path when it first uses the query. Otherwise a constraint on 200 property shapes would be prepared 200 times.
- **Break-even.** The scanner costs about 0.03 ms per call, so the tree path pays back after about 45 runs of one query. A shape with fewer focus nodes loses a millisecond or two, which does not matter. A "scanner for the first N runs" fallback is not planned; add it only if measurement shows it matters, because it is a second path to keep correct.
- **The per-call step is a literal marker replace, not a graph edit plus a render (measured 2026-11-26, 258 corpus queries).** Rendering the edited tree on every call costs a median 41 microseconds (90th percentile 84, maximum 941), more than the current scanner (8 microseconds) and more than Oxigraph's own run of a small query (about 30). Rendering once into a template and replacing a marker per call costs a median 0.2 microseconds (maximum 4.8). The marker is a term the tree puts in the `VALUES` row (for example `<urn:starlayer:slot:this>`, one per pre-bound variable, chosen so it cannot occur in the query), and the replacement is the SPARQL text of the actual term (`_sparql_term`, which does the escaping). It is not a regex over the query: only the marker is replaced, and it is whole-token. The graph edit happens once, at preparation; the per-call step is only the replace.
- **Goal: no text path in the end (user, 2026-11-26).** The scanner is a safety net while the tree path is brought to full coverage, not a permanent fallback. Rule for Stage 1: a query the tree path cannot prepare is a bug in the encoder, the vocabulary or the renderer, to be fixed there (the one known case is the `CONSTRUCT WHERE` short form). Each fallback is counted and logged; the exit criterion is zero fallbacks over the Stage 0 corpus, the W3C suite and the shipped shapes, after which the scanner and the regex and f-string edits are deleted. A query that is not valid SPARQL stays a `ShapeCompileError`, as today.

## Stages

Each stage is committed on its own, tested with targeted tests, and gives the same results as before (not necessarily the same text). The full suite runs only when you ask.

**Stage 0. Read-only coverage test (no library change).**
- Run the current scanner path and the prepared-tree path over: every `sh:sparql`, `sh:ask`, `sh:construct`, `sh:select` and `sh:sparqlExpr` query in the repo, the vendored W3C SHACL 1.2 suite, the shipped meta shapes (28 distinct texts; 4 failed to parse in my first harness for a reason not yet found: find it), and the SRL and node-expression fixtures.
- Require equal results (solutions as sets, with multiplicity), not equal text. Record which queries do not round trip and why: the renderer normalises (`$this` to `?this`, extra dots, `NOT EXISTS` wrapped in `FILTER(...)`), and each normalisation is a possible bug.
- Also time it on the workbench's fixture shapes graphs, for a realistic number of queries per user shapes graph.
- Output: a table in this document. Decide the next stages from it.

**Stage 1. Prepared queries.**
- A prepare step as designed above, replacing `inject_everywhere` and the regex and f-string edits (`with_prefixes`, `substitute_path`, the `sparqlExpr` wrapper, the `ASK`-to-`SELECT` regex, the `VALUES` f-strings in `expressions.py`) for every query the tree path covers; the scanner stays as the fallback.
- Expected: about 20 to 25% off `sh:sparql` time for cheap queries (corrected after Stage 0; see its result). The reasons for doing it are correctness and what it enables.
- Check: W3C suite and engine tests; the prepared and scanner paths compared on random shapes and data, as the scoped meta check was.
- Decide here whether `sqe/rewrite.py`'s `EXISTS`-to-join rewrite can now apply to pre-bound SHACL queries (its precondition is "no `initBindings`", which the prepared form removes). This changes performance only, never results; measure first.

**Stage 2. Cache what the shapes graph says once per plan.**
- `shacl_list` and the list members for `sh:and`, `sh:or`, `sh:xone` (and `sh:in`, `sh:languageIn` if measurement agrees), plus the other per-visit parameter reads (counts, shape references) that depend only on the shapes graph, which is fixed for a run.
- Expected: about 20 to 25% off the meta check and off any shapes graph with `sh:or` / `sh:xone` / `sh:and`. Output unchanged by construction.
- Check: the error behaviour is unchanged (a malformed list is still a `ShapeCompileError`, raised at the same point), the W3C suite, and the meta tests.

**Stage 3. Rules: skip a rule when nothing it reads changed.**
- Re-run a rule in the fixpoint loop only if a predicate it reads was added to since its last run (the engine already tracks `expected_predicates`). Not full semi-naive evaluation, which is harder because rules can have conditions and `NOT EXISTS`.
- Needs a fixpoint-equivalence test: the skipping and the plain loop give the same inferred set on random rule sets, and on the W3C rule tests.
- Also look at `InferredView.materialised()`, which copies the whole base graph once per `apply_rules`.
- Expected: removes the growth beyond the size of the output seen in the chain test.

**Stage 4. The meta check, after 1 and 2.**
- Re-profile the meta check. Then trace who calls `stringify_node` (10% of the profile) and whether message text is built for checks that only ask "does it conform" (`sh:or`, `sh:xone`, `sh:not`, `sh:node` through `conforms`); trace whether reads of the shapes graph can use the faster engine view instead of `StarLayerGraph._quads` / `_terms`.
- These two are unverified guesses until traced.

**Stage 5 (decision, not yet planned). Batch SPARQL per shape.**
- Send many focus nodes through one query (a chunked `VALUES` block) and group the rows by `?this`. It is the only change that removes the quadratic growth for queries the pre-binding does not narrow (aggregate sub-select, `?this` only in a `FILTER`, property paths), and the only one that avoids Oxigraph re-parsing the text per focus node.
- It is exact only for a class of queries; the tree tells us which (no aggregate sub-select, no `LIMIT` or `OFFSET`, no `MINUS`; to be settled in Stage 0). Others stay per node. Row order within a focus node may differ, which does not matter for a report graph but must be checked for `sh:sparql` results that depend on it.
- **Measured 2026-11-26 (pyoxigraph directly, 3,000 focus nodes, two queries, same rows in every variant):**

  | Way of running it | Cheap query (`NOT EXISTS`), µs per node | Aggregate sub-select, µs per node |
  |---|---|---|
  | Loop, `VALUES` row in the text, text changes each time (what the engine does) | 27 | 1,402 |
  | Loop, same text, Oxigraph `substitutions` | 24 | 29 |
  | Batch, 10 nodes per query | 6.9 | 142 |
  | Batch, 100 nodes per query | 4.5 | 16 |
  | Batch, 1,000 nodes per query | 4.2 | 3.6 |
  | One unbound query for all nodes | 3.6 | 2.3 |

  So batching is the largest lever in this plan: about 6 times faster for the cheap query at 100 per chunk, and 90 to 400 times faster for the aggregate. Returns diminish beyond about 100 per chunk for cheap queries; an aggregate keeps gaining up to a few thousand. Re-parsing a changed text is not the main per-call cost (same text with `substitutions`: 24 against 27 microseconds), the per-query overhead is.
- **A second finding to follow up: `substitutions` was 48 times faster than the `VALUES` row for the aggregate query (29 against 1,402 µs per node)**, because Oxigraph pushes the binding into the sub-select's projection and the `VALUES` row, placed outside it, is not pushed in. The engine used `substitutions` once and moved to injecting `VALUES` at every group because `substitutions` does not reach a group that holds only a `FILTER` (the comment in `oxigraph_view._run`). So a query-shape-dependent choice (or both: `substitutions` plus the `VALUES` rows) may give the spec's pre-binding semantics and the speed. Needs its own differential run before anything is changed.
- Synthetic data, one machine, two queries chosen to show the two cases; not a survey of real queries.
- Before building it, find out whether any real shapes graph (the workbench's, the guides', the meta shapes) contains such queries; the meta shapes do not benefit (SPARQL is about 5% of their cost).

## Stage 0 result (run 2026-11-26)

Method: a pytest plugin (session scratchpad `perf/sparql_diff.py`, not in the repo) wraps `OxigraphGraph._run` on a snapshot of `main` (769bdf06). For every query the engine sends with pre-bound variables it also builds the query by editing the `Node` AST (a `VALUES` node at the start of every group, as the scanner does, rendered with `ast_to_triples` and `sqe_tree_to_text`), runs both, and compares the results (rows as sorted multisets, blank nodes normalised, ASK as a boolean). The engine always gets the scanner's result, so no test is affected. Run over `tests/shacl`: 5,944 passed, 1 failed (`test_error_classes.py`, a list of error kinds; it has nothing to do with SPARQL and was not investigated), 4 collection errors (modules that need the repo's `scripts/` folder, which the snapshot lacks: `test_meta_shapes_extensions`, `test_shacl_ui_form_kinds`, `test_shacl_ui_forms`, `test_wg_overrides`), 21 xfailed.

| | |
|---|---|
| Distinct (query text, pre-bound variables) pairs that were sent | 259 (181 SELECT, 77 CONSTRUCT, 1 ASK) |
| Same result from the tree path | **258** |
| Different result | **0** |
| Tree path failed | **1**: `CONSTRUCT WHERE { ?this ex:p ?o }`, the short form (`KeyError: 's'` in the encoder; the scanner has a special case for it, the AST has no template). The fallback covers it; fixing the encoder case is a separate small job |
| Features present | `UNION` 11, `EXISTS` 23, `MINUS` 3, `OPTIONAL` 23, `GROUP BY` 2, sub-select 11, `$PATH` text 2 |
| Pre-bound variable sets | `this` alone 209; the rest add `property`, `covers`, `arg0`, `arg1` |
| First-time cost of the tree path (parse, edit, encode, render; text the parser had not seen) | median 0.16 ms, 90th percentile 0.29 ms, maximum 10.4 ms, 70 ms for all 258 queries |
| Scanner, per call | median 11 microseconds, 90th percentile 31, maximum 337 |
| Break-even | the tree path pays back after about 14 runs of a query (median) |

What this changes in the plan:

1. **The tree path is exact on everything the suite sends.** Nothing needs redesigning. The injection by tree edit is a safe replacement, with the scanner kept as the fallback for the one known gap.
2. **Correction: Stage 1's speed claim was too high.** The 35 to 40% I gave came from a profile, which inflates Python-heavy code. Measured without the profiler, the scanner costs about 11 microseconds a call on a typical short query, against about 47 microseconds for the whole `sh:sparql` call (3,600 calls in 0.17 s), so about 20 to 25%. Stage 1 is mainly about correctness (no hand-written scanner), one place to make query edits, and what it makes possible (Stage 3 and Stage 5), not about speed. Do not sell it as a speedup.
3. **The first-time cost is small.** About 0.16 ms a query for typical queries; the earlier 1.3 ms figure was for the longer meta-shape queries and included a re-parse and validation. Both are well below one meta check. No build-time storage of prepared queries is needed on this evidence; leave it as an option.
4. **What was not tested, so not yet shown:**
   - The `$PATH` placeholder design. The text reaching Oxigraph is already substituted, so the plugin edited the final text. Only two queries contained `PATH`. Stage 1 must test the placeholder form itself.
   - `sh:sparqlExpr` wrapping, the `ASK`-to-`SELECT` form for a blank-node binding, and `expressions.py`'s `VALUES` queries were not prepared by the tree; they stay as they are until Stage 1.
   - The four skipped modules, which hold meta-shape tests. The meta shapes' own queries were reached only through the modules that did run (10 queries from `test_meta_starlayer_layer`, 7 from `test_meta_scope_engine`).
   - Data size. The tests use tiny graphs, so "same result" means same on small data; it does not test the cost at scale, nor ordering of rows, which a report graph does not depend on but which was not compared.
   - Queries other than those the shipped tests send. A user's query using a construct the AST encoder or renderer does not cover would hit the fallback; the one short-form `CONSTRUCT` shows the fallback is needed.
5. **Stage 5 (batching) is not yet tested.** The batched form (many focus nodes in one `VALUES` block, rows grouped by `?this`) is a different edit and needs its own differential run, over the same suite, before it is judged.

## Stage 5 differential result (run 2026-11-26)

Method: pytest plugin `batch_diff.py` (session scratchpad `perf/`), over `tests/shacl` on the same `main` snapshot. For each query the engine sent with `?this` pre-bound, it picks the real focus node plus up to 40 other IRIs from that test's data graph, runs the query once per node (the engine's own path, the reference), then once as a single query with a `VALUES` row per node (the tree edit of Stage 0, many rows), groups the batch rows by `?this`, and compares each node's rows with the reference as a multiset. For CONSTRUCT it compares the union of the per-node triples with the batch triples. A first run of the harness had a bug (it looked up the `?this` column by sorted name while the rows are in declaration order) and reported 23 differences; 21 of them were that bug. The figures below are from the corrected run.

| | |
|---|---|
| Distinct queries sent with `?this` pre-bound | 242 |
| SELECT that projects `?this`, checked | 128: **127 same, 1 different** |
| CONSTRUCT | 72: 70 same, 1 different, 1 harness error (the known short-form `CONSTRUCT WHERE`) |
| Not batchable: SELECT that does not project `?this` (node expressions, `sparqlExpr`) | 29 |
| Not tested: ASK (10), views over overlapping graphs (3) | 13 |

The two differences are the two cases the design predicted:
- `SELECT $this WHERE { { SELECT ?local WHERE { $this ex:p ?local } } }`: the sub-select does not project `?this`, so in the batch its rows from every node join with every node (16 of 17 candidates differed).
- `CONSTRUCT { $this ex:youngestOffspring ?o } WHERE { { SELECT $this ?o WHERE { ... } ORDER BY ?age LIMIT 1 } }`: the `LIMIT 1` is applied over all nodes in the batch, not per node.

**Which queries are safe, read out of the tree.** One SPARQL SELECT over each query's `sqe:` tree graph returns the features as booleans (`sqe:limit`, `sqe:offset`, `sqe:groupBy`, `sqe:having`, `sqe:orderBy`, `sqe:distinct`, a `sqe:SubSelect`, a `sqe:Minus`, an aggregate class from `spexpr:`). Cross-tabulated with the result:

| Features in the tree | Queries | Same | Different |
|---|---|---|---|
| none of them (plain patterns, `OPTIONAL`, `UNION`, `FILTER`, `EXISTS`, `BIND`) | 104 | 104 | 0 |
| `DISTINCT` only | 19 | 19 | 0 |
| a sub-select (alone: 2; with limit: 1; with group by and aggregate: 1; with group by, having, order by, limit and aggregate: 1) | 5 | 4 | 1 |

(`MINUS` does not occur among the pre-bound queries.) The proposed rule for the first version of batching is conservative: batch a SELECT only if it projects `?this` and its tree has no `sqe:limit`, `sqe:offset`, `sqe:groupBy`, `sqe:having`, aggregate, `sqe:SubSelect` or `sqe:Minus`; for CONSTRUCT the same without the projection test. That covers 123 of the 128 checked SELECT queries (96%) and 70 of the 72 CONSTRUCT queries (the other difference is excluded by the sub-select test, the short form by the encoder gap). `sqe:orderBy` and `DISTINCT` are harmless without a limit, as the data shows, and are allowed. This rule is the exact condition under which a pre-bound row's solutions cannot depend on another row, so agreement on the corpus is supporting evidence, not the whole argument; Stage 5 still needs the argument written down and a randomised test on larger data.

Not shown by this run: row order within a node (compared as multisets); data larger than the test fixtures; ASK validators (they could be batched as a SELECT, not tested); the cost of splitting the batch rows by `?this` in Python (a dict of lists; to be measured with the engine).

## Test plan

One corpus, one oracle, one harness per kind of change, so every stage is judged the same way.

1. **Corpus.** Every query the engine sends to Oxigraph with a pre-bound variable while `tests/shacl` runs (259 distinct pairs from the W3C SHACL 1.2 suites, the engine tests, the meta-shape tests), plus the query texts in the shipped meta shapes and the guides' and workbench's shapes graphs. Extend it with the four modules that need `scripts/` and with the SRL fixtures. The plugins record it (`sparql_diff.jsonl`, `batch_diff.jsonl`); put the recorded corpus, not the plugin run, under version control so a stage can be re-run without the suite.
2. **Oracle.** The current engine path (scanner injection, one query per node, naive rule fixpoint). A stage passes when it gives equal results on the corpus, compared as multisets of solutions or sets of triples, blank nodes normalised, not as text.
3. **Per stage.**
   - Stage 1 (prepared query): the tree path against the scanner on the corpus (Stage 0 harness); exit when the number of fallbacks is zero; plus the `$PATH` placeholder, `sparqlExpr` wrapping and `ASK` forms, which Stage 0 did not reach.
   - Stage 2 (cached lists): same reports and same errors; a malformed list must still raise `ShapeCompileError` at the same point.
   - Stage 3 (rules): the skipping loop against the plain loop on random rule sets and the W3C rule tests, same inferred set.
   - Stage 5 (batching): the Stage 5 harness; then a randomised version on larger generated data (chunk sizes 1, 10, 100, 1000; focus nodes with no rows, one row, many rows), and the engine-level check that `validate()` with batching on and off gives the same report on the W3C suite.
4. **Features read from the graph.** Classify queries by one SPARQL SELECT over the query's `sqe:` tree (existence of properties and types; no ordered walk is needed). The batchable test of the engine is the same kind of query, stored as data beside the vocabulary (a SPARQL `ASK` over the tree, or a SHACL shape on it, so a "why not" is a report), not Python code walking the tree.
5. **Speed.** After equality passes, time each stage on the synthetic workloads in `perf/` (core, SPARQL-heavy, shape kinds, meta check, rules chain) and on the workbench's own shapes graphs; record before and after in this document. A stage that does not pay is not merged.
6. **Never from the profiler alone.** Wall-clock figures without the profiler decide whether a stage is worth it (the Stage 1 estimate was corrected for this reason).

## Not in scope

- A Rust port of any part of the engine (see the status line).
- Changing the stored form of `sh:select` and the other query properties away from text.
- Plan building, focus-node selection and report building.
- Changes to the SHACL 1.2 behaviour or to results: every stage is an efficiency change that must leave results as they are.

## Open points

- Why 4 of the 28 meta-shape query texts did not parse in the first harness (possibly the harness, not the queries). Not re-examined in Stage 0.
- The encoder's `CONSTRUCT WHERE { ... }` short form (`KeyError: 's'`): fix it or leave it to the fallback.
- `tests/shacl/unit/test_error_classes.py::test_execution_error_is_one_class_with_a_kind_and_the_message_as_its_text` failed on the `main` snapshot (a list of error kinds differs); unrelated to this plan, but worth a look by whoever owns the error scheme.
- Whether the prepared form should also be stored in the built `shacl12-shacl.ttl` (only if the 31 ms per process matters).
- Whether to add an engine benchmark guard once the stages land; `benchmarks/shacl/README.md` says there is none today.
- The measurements are from synthetic data on one machine. Re-measure on the real workloads (the workbench, the guides) before judging a gain.

## Real-workload check: "every dog has an owner" (2026-11-26)

Synthetic data: N dogs, every tenth without an owner; core `sh:minCount 1` against `sh:sparql` with `FILTER NOT EXISTS`, against one bulk query. Scratch scripts only (`dogs_bench.py`, `dogs_bulk.py`, `dogs_prof.py`).

| Approach | Per dog | 1M dogs |
|---|---|---|
| Engine, core `sh:minCount` | 11-13 µs | ~12 s (extrapolated from 100k) |
| Engine, `sh:sparql` | 46 µs | ~46 s (extrapolated) |
| One bulk SPARQL query (list only, no report) | 0.6 µs | 0.64 s (measured at 1M) |

Both engine paths scale linearly (10k and 100k). Core constraints are not SPARQL: they are triple-pattern lookups from Python.

Core path profile (50k dogs, profiler-inflated, so shares are approximate): `executor.run` 65% (path evaluation and value nodes 30%, of which the raw store lookup is about 13% of the total); `build_report` 35% (5000 violations, about half of it message text); copying the data into the engine's store at the start about 18%. The store lookups are cheap. The time is in Python around them: term conversion, dedupe, per-node dispatch, report building.

Consequence: set-based evaluation of core constraints would remove the per-node Python work, but the report (results, messages, order) must stay identical, and the report share (35%) does not shrink unless messages are built lazily. Not yet designed.

### Correction: where core-path time goes (unprofiled, 100k dogs, best of 3)

| Data | Time per dog |
|---|---|
| all dogs conform | 5.7 µs |
| 10% violate | 10.6 µs |
| every dog violates | 54.9 µs |

So a conforming dog costs about 6 µs and each violation about 49 µs (the report: result object, message text, report graph). The earlier profile overstated path evaluation: the graph layer adds only about 0.8 µs to a 2.2 µs raw store lookup (`layer_bench.py`: raw 2.19, with `detached` 2.30, `g.objects` 2.95 µs). The conforming path is therefore already within about 2x of the floor set by the store call, and set-based core evaluation could gain at most about 2x on valid data. The large cost is reporting violations. Revised priorities: (1) report building for violations (lazy messages, cheaper result objects), (2) batching `sh:sparql`, (3) set-based core evaluation only if (1) and (2) leave valid-data time the bottleneck.

### Where a violation's ~49 µs goes (profile, 30k violations of one minCount; profiler-inflated, shares approximate)

| Part | Share | What it is |
|---|---|---|
| Writing the report graph | 41% | 8 quads per result, each converted by `graph/core.py:_quad` (`terms.term` called about 33 times per result) and passed through `lexical.watch`, then `Store.extend` |
| Message text | 32% | `text.py` `generic_message`: parameters, path text, `_n3`, `compute_qname` per result |
| Reading shape-side facts back during `add_result` | 19% | about 5 graph lookups per result (`_terms`, 150k calls), the same answers for every result of one shape |
| The validation itself | 17% | |

Candidate changes, all inside one shape or one report: (a) read the per-shape facts once per (shape, component) and reuse; (b) cache message parts and qnames per shape and component; (c) write the report quads to the store in one batch without the per-term conversion, keeping `lexical.watch` semantics (to check: what it rewrites). Each is checked by comparing the report graph to the current one (isomorphic, same messages).

## Stage R1 result: messages worded once per distinct result (2026-11-27, branch `perf/shacl-engine-efficiency`)

Change: `text.MessageMemo` (new) words a result's messages, and the lines of a text block that are fixed per shape, once per distinct (shape, component, path node, value if any, source constraint, own messages, and the focus node only for a SPARQL constraint) instead of once per result. `api.validate` uses one for the report graph's `sh:resultMessage` values, `report_text` one for the text. No change to what is produced.

Per result, every dog violates, 30,000 results (`viol_bench.py`, best of 3):

| Constraint | Graph, before | Graph, after | Text, before | Text, after |
|---|---|---|---|---|
| `sh:minCount` (no value) | 56.4 µs | 46.2 µs | 41.8 µs | 1.9 µs |
| `sh:datatype` (a value, 5 distinct) | 70.2 µs | 55.8 µs | 46.5 µs | 3.4 µs |
| `sh:in` (a list) | 120.0 µs | 77.8 µs | 103.0 µs | 4.7 µs |

Checks: the text of 30,000 results is byte-identical with and without the memo (7.8 MB); a scratch plugin compared every memoised answer with the direct one over 50 related test files (3,265 message and 1,831 fixed-line comparisons, no difference); `tests/shacl/engine/test_message_memo.py` tests each key field alone (removing any one of focus, value, path, shape or component from the key fails a test; `has_value` is redundant with `value` in the key). The remaining graph cost is the quad write (about 35 of the 46 µs), which pyoxigraph's `Quad` constructor sets (see the report design note); a violation now costs about 40 µs more than a conforming node, down from about 49.

Not yet run: the whole `packages/starlayer/tests/shacl` tree (6,455 tests, includes the W3C suite).

## Stage R2 result: the report graph is written when it is read (2026-11-27)

Change (user's design: results still go through the graph; a caller that knows it needs the graph asks for it; otherwise it is written on first read):
- `report.build_report` is split into `collect_report` (the triples, with the closures of the nodes they name and the messages, and the prefixes of the two graphs, all taken in the call) and `write_report` (the graph). `build_report` is both.
- `engine.api.Outcome.report_graph` and the public `ValidationReport.report_graph` / `.diagnostics` are properties that write the graph on first read and keep it; `ValidationReport(report_graph=<graph or function>, diagnostics=<value or function>)`. The adapter's `sh:conformanceDisallows` edit runs when the graph is written (`Outcome.after_report_graph`).
- New parameter `build=None | "graph" | "text"` on `validate()` (public, `StarShaclProcessor.validate`, `_adapter.validate`, `engine.api.validate`); `apply_rules` refuses it. `"graph"` writes the graph in the call, `"text"` the graph and the text.
- Callers that always read the graph ask for it: `validate_bounded` (the SQE, SRL and Manchester checks), the two reading calls in `derive.py`, and the engine's meta check (real engine).

Per result, every node fails, 30,000 results (`viol_bench.py`, best of 3):

| Constraint | Before (graph in the call) | `validate()` only | + read `report_graph` | `build="graph"` | + read `report_text` |
|---|---|---|---|---|---|
| `sh:minCount` | 56.4 µs | 10.0 | 43.7 | 44.5 | 47.5 |
| `sh:datatype` | 70.2 µs | 14.0 | 54.5 | 56.4 | 58.7 |
| `sh:in` (a list) | 120.0 µs | 36.1 | 77.2 | 76.9 | 80.9 |

Checks: `tests/shacl/engine/test_lazy_report_graph.py` (13 tests: written once and on first read; the same graph, isomorphic, as `build="graph"`; the graph written after the data and shapes graphs are emptied is the graph written in the call; prefixes are those of the call; the conformance floor is in a lazily written graph; the options on the public function, the processor, and `apply_rules`'s refusal; `ValidationReport` takes values or functions). Two mutations are caught: collecting when the graph is written, and dropping the floor edit. The SHACL, SPARQL and ontology test trees pass (12,057 tests, run from `packages/starlayer`; one test that starts a subprocess needs that working directory).

Not changed: how anyone reads results; the text still reads the graph for its provenance lines, so reading `report_text` writes the graph.
Known differences: a graph written later emits its fidelity warning (a literal Oxigraph stores in another form) when it is first read, not in `validate()`; an error while writing would appear at first read.

Stage R2 addendum, the meta check: `MetaResult` and so `meta_validate()` also take the report graph and diagnostics on first read. A shapes graph that conforms has a tiny report, so the saving is small: 1 to 2% of a check (200 shapes: 266 ms with the graph unread, 271 ms with it read). The cost of the check is the meta-shapes themselves, about 1.3 ms per shape; that is stage 4 (trace the meta check), not this stage. Cleanup: `Outcome.write_graph()` / `write_text()` name what `build=` does (no bare property reads); ruff reports nothing new (three function-level import blocks in `api.py` were already flagged at HEAD); the SHACL, SPARQL and ontology trees pass (12,060 tests, from `packages/starlayer`).


## Stage 5 result: `sh:sparql` batching (2026-11-27)

What was built: the engine gives each shape's focus nodes to its components before checking them one by one (`ComponentSpec.prefetch`, called from `executor._prefetch`; a node shape's property shapes get the same nodes). `sh:sparql` runs its query once through `OxigraphGraph.sparql_query_batch` (a `VALUES` block of all the nodes in every group but the `EXISTS` ones), chunks of 5,000, and `run_select` answers each node from the rows. Only a query that `sparql_support.batch_blocker` clears (a SELECT projecting `?this` with no LIMIT, OFFSET, GROUP BY, HAVING, aggregate, sub-select, MINUS or SERVICE); everything else, a blank-node focus node, a single node, `abort_on_first`, `extract_subgraph` and any failure run node by node, as before.

The finding that mattered: with the `VALUES` clause in every group, `FILTER NOT EXISTS` made it SLOWER (46 to 105 µs a node), because Oxigraph evaluates an `EXISTS` group once per outer row, so a block of N rows there costs N times N (97 µs a node at 5,000 rows, 0.9 µs with the block in the outer group only). Inside `EXISTS` the outer solution already binds `?this`, so `inject_everywhere(skip_exists=True)` leaves those groups out of a batch.

Per focus node, `sh:sparql` "has an owner" rule against the core `sh:minCount 1` (10% of nodes fail; `dogs_bench.py`):

| Nodes | `sh:minCount` | `sh:sparql` before | `sh:sparql` now |
|---|---|---|---|
| 10,000 | 7.7 µs | 45.8 µs | 7.2 µs |
| 100,000 | 6.8 µs | 46.1 µs | 6.5 µs |
| 1,000,000 | 7.1 µs (7.1 s) | about 46 µs (about 46 s) | 7.5 µs (7.5 s) |

Checks:
- `tests/shacl/engine/test_sparql_batching.py` (36 tests): the rule (9 batchable, 12 not, each with its reason), the scanner, one run for all nodes, property shapes, identical results and row order against the node-by-node run, chunks, a failing or refusing batch, blank-node nodes, one node, `abort_on_first`, `focus_filter`.
- A scratch plugin (`batch_check.py`) wrapped `prefetch_select` so that every batched query was also run node by node, over the whole `tests/shacl` tree and with each batch widened by up to 40 other nodes of the data: 1,182 batched queries, 80,537 nodes, 28,628 rows compared, no difference in content; 40 queries not batchable (3.3%), none fell back. Two nodes got their two rows in the other order (a meta-shape query with no ORDER BY).
- The SHACL, SPARQL, ontology and graph test trees pass (16,123 tests, from `packages/starlayer`).
- The meta check improves by about 5% (200 shapes: 266 ms to 252 ms): its cost is not mostly SPARQL.

Not done: SPARQL-based components (`sh:select` validators run per focus node and value), SPARQL node expressions, ASK validators, a property shape reached through `sh:node` and other nested shapes, and a query the rule refuses (a `LIMIT` can be batched only with a per-node `LIMIT`, which SPARQL cannot say). The harness test plan of this document applies to each.
