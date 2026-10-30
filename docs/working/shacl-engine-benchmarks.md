# SHACL engine benchmarks: native engine vs the pyshacl-backed validator

Script: `packages/starlayer/benchmarks-shacl/bench_engine_vs_old.py` (branch `shacl-engine`). Background: `shacl-engine-feasibility.md`, `shacl-engine-design.md`.

## Environment

- python 3.10.8, rdflib 7.6.0, pyoxigraph 0.5.13
- macOS 12.7.6 (x86_64), Intel Core i7-4578U 3.0 GHz (2 cores, 2014-era laptop), 16 GB. Slow by current standards; read the ratios, not the absolute seconds.
- Each measurement runs in its own subprocess, one at a time (peak RSS from `resource.getrusage`; "RSS growth" is peak minus RSS after building the data graph, so it excludes the generated data). Best of 3 up to 10k triples, one run above. Timing covers `validate()` only; data generation is excluded. For the Oxigraph column "setup" is the one-off `OxigraphGraph.from_graph` copy, not included in "best".
- Columns: old = `starlayer.shacl.validator.validate(data, shapes, meta_shacl=False)` on StarLayerGraph; new-slg = `shacl_engine.api.validate` on StarLayerGraph; new-ox = same on OxigraphGraph.

## Data and shapes

The existing `bench_adapter.py` data is triple-term encode/decode only and has no shapes, so there was nothing to reuse for validation; the generators here are new. Data: people (Employee/Manager under Person), addresses, orgs (Startup under Company under Org), certs; about 14 triples per person, about 3% planted violations. Shapes: `sh:and` of two node shapes, `sh:node` to an address shape, cardinality + `sh:datatype` + `sh:pattern` + numeric ranges on properties, `sh:class` against the subclass hierarchy, `sh:qualifiedValueShape` + `sh:qualifiedMinCount`, a `sh:sparql` SELECT constraint, and `sh:uniqueValuesFor`. Result counts agree between old and new in every row below (no disagreement).

One caveat on the Oxigraph column: as it ships in this worktree, `OxigraphGraph` has `query()` but not the `sparql_query()` hook that `sparql_support.run_query` looks for, so any `sh:sparql` constraint crashes on it (`TypeError: OxigraphGraph.query() got an unexpected keyword argument 'initBindings'`). The script uses a small benchmark-local subclass that adds the hook (wrapping `query()` into `Solutions`). That is a bug in the engine to fix, not something the benchmark hides.

## Results A: shapes set without `sh:uniqueValuesFor` (to 200k)

| triples | old s | new-slg s | new-ox s | slg speedup | ox speedup | results | old RSS MB (growth) | new-slg RSS MB (growth) | new-ox RSS MB (growth) | ox load s |
|---|---|---|---|---|---|---|---|---|---|---|
| 941 | 0.23 | 0.13 | 0.10 | 1.8x | 2.3x | 10 | 56 (13) | 47 (4) | 48 (5) | 0.03 |
| 9,295 | 2.19 | 1.25 | 0.91 | 1.8x | 2.4x | 61 | 102 (50) | 57 (5) | 63 (11) | 0.22 |
| 46,414 | 11.16 | 6.24 | 4.58 | 1.8x | 2.4x | 302 | 245 (145) | 106 (5) | 133 (34) | 1.10 |
| 185,615 | 46.11 | 26.47 | 19.69 | 1.7x | 2.3x | 1193 | 844 (562) | 291 (8) | 389 (107) | 4.66 |

Time scales linearly for all three (about 0.25 ms/triple old, 0.14 ms new-slg, 0.11 ms new-ox). The new engine is a steady 1.7-1.8x faster on StarLayerGraph and 2.3-2.4x faster on Oxigraph, and it uses far less memory because it keeps no copy of the data (old: 562 MB growth at 185k; new-slg: 8 MB; new-ox: 107 MB, which is the Oxigraph store itself).

## Results B: full shapes set including `sh:uniqueValuesFor` (to 18.5k, then stopped)

| triples | old s | new-slg s | new-ox s | slg vs old | ox vs old | results |
|---|---|---|---|---|---|---|
| 941 | 0.23 | 0.21 | 0.19 | 1.1x faster | 1.2x faster | 10 |
| 4,657 | 1.16 | 2.71 | 2.90 | **2.3x slower** | **2.5x slower** | 35 |
| 9,295 | 2.26 | 8.97 | 10.63 | **4.0x slower** | **4.7x slower** | 66 |
| 18,572 | 4.38 | 33.87 | 42.09 | **7.7x slower** | **9.6x slower** | 130 |

Peak RSS stayed at 47-81 MB for the new engine here (old 55-121 MB). Larger sizes were not run: new-slg time quadruples per doubling of data, so 50k would take about 4 minutes and 200k about an hour.

**The new engine is slower than the old validator in this configuration, and it gets worse quadratically.** Cause: `components/core_cross_node.py::unique_values_for` compares each focus node with every other focus node of the shape (`any(other != focus and key(other) == mine for other in ctx.shape_focus(shape))`, recomputing `key(other)` with two graph lookups each time). That is O(n^2) graph reads (about 507,000 `objects()` calls at 9.3k triples, where the data has only about 660 focus nodes). The old validator is linear here. Removing `sh:uniqueValuesFor` from the shapes gives Results A.

## Time split (cProfile, 10k-triple data, shapes without `sh:uniqueValuesFor`, profiler-inflated)

| phase | new-slg | new-ox |
|---|---|---|
| plan building (`Plan.shape` and lazy shape reads) | under 1% | 1% |
| focus nodes (`targets.focus_nodes`, `Context.shape_focus`) | under 1% | 1% |
| report building (`build_report`) | under 1% | 1% |
| constraint components, i.e. `validate_shape_at` and everything under it | 98% | 98% |

So essentially all the time is in evaluating shapes at focus nodes. Within that:

| work | new-slg | new-ox |
|---|---|---|
| `sh:sparql` constraint (`run_select`) | 42-46% | 6-13% |
| `sh:and`/`sh:node`/`sh:class` nested conformance (`Context.conforms`) | 25% | 41% |
| shape-component dispatch overhead in `_validate_shape_at` (self time plus the `present` dict comprehension, 475k iterations for 11k shape visits) | about 16% | about 28% |
| graph reads (`triples`/`objects`) | about 20% | about 18% |
| `from_ox` + `to_ox` term conversion | n/a | 11% |

(Percentages from two separate profiling runs differ a few points; the order is stable.)

## Top 5 hot spots

Case 1, typical shapes (10k triples, no uniqueValuesFor), cumulative share of the profiled run:

1. `sparql_constraints.sparql_constraint` -> `starlayer_graph.query` (714 calls, one per focus node): 46% on StarLayerGraph, of which about 19% is rdflib `Graph.bind` / `NamespaceManager` trie rebuilds (20,707 `bind` calls) and about 10% is `restore_select_bindings` / filter patches. On Oxigraph the same constraint is 13% (`Store.query` itself is 2%).
2. `executor._validate_shape_at`: the loop over all registered components (about 42 specs) for every shape visit, rebuilding `present` each time, 16% (slg) to 28% (ox) of the run. Pure Python dispatch cost, independent of the graph view.
3. `executor.Context.conforms` for `sh:and` / `sh:node` / `sh:class` / qualified shapes: 25% (slg) / 41% (ox) cumulative, which is mostly re-entry into hot spot 2 plus graph reads.
4. Graph reads: `StarLayerGraph.triples` (starlayer_graph.py:1466) + `rdflib Graph.objects`: about 20% on slg. `OxigraphGraph.triples/objects`: about 18% on ox, of which `from_ox` is 9% and rdflib term construction under it (`URIRef.__new__`, `Literal.__new__`, `_is_valid_uri`) most of the rest.
5. `eval_path` -> `_dedupe` -> `dict.fromkeys` on value nodes: about 13%.

Case 2, with `sh:uniqueValuesFor` (9.3k triples; slg total 36.7 s profiled, ox 31.6 s):

1. `core_cross_node.unique_values_for` and its `key()` lambdas: 87% (slg) / 91% (ox) cumulative. An algorithmic problem (O(n^2)), not an interpreter-speed problem.
2. `Graph.objects` -> `StarLayerGraph.triples`: 76% / 27 s (slg); `OxigraphGraph.triples/objects`: 74-78% (ox).
3. `OxigraphGraph.from_ox`: 42% of the Oxigraph run (13.3 s for 1.56M calls); of that, rdflib `Literal.__new__` + `_castPythonToLiteral` is 24% of the whole run, and `URIRef.__new__` + `_is_valid_uri` about 8%. `to_ox` (query-term conversion) is 6%. `store.quads_for_pattern` itself is 2%.
4. rdflib `MemoryStore.triples` + context handling (slg): 26%; StarLayerGraph's own per-triple `_restore`/`_is_encoding_triple`/bnode checks: about 14%.
5. `isinstance` (8.1M calls in slg, 10.5M in ox): about 9%.

## What a Rust port or an Oxigraph-native fast path would remove

- **Would remove (term conversion, ox only):** `from_ox`/`to_ox` plus the rdflib term constructors they trigger are 42% of the Oxigraph run under heavy reads (Case 2) and 9-11% of a typical run (Case 1). A Rust port that works on Oxigraph terms directly (no rdflib `Literal`/`URIRef` objects) removes all of it. A cheaper Python step: cache `from_ox` per term (the same IRIs are converted millions of times) and construct `URIRef` without validation.
- **Would remove (sh:sparql):** an Oxigraph-native `sparql_query` (the hook that is missing) cuts the SPARQL constraint from 46% (slg) to about 13% (ox) of a typical run. A bigger win is running the query once per shape with `$this` bound by `VALUES` over all focus nodes instead of once per focus node.
- **Would remove (graph reads and dispatch):** a Rust loop over components removes the 16-28% dispatch overhead and the per-call Python `isinstance` traffic (about 9%). A Python-only fix removes most of the dispatch cost: precompute the "present" parameter tuples per shape when the plan is built, since the plan is immutable.
- **Would NOT be removed by a Rust port or Oxigraph alone:** the `sh:uniqueValuesFor` O(n^2) (87% of Case 2). Even with a native 100x faster read it stays quadratic. It needs a hash-based rewrite (group focus nodes by key once; any group with more than one member is a violation), which is a ten-line Python change and brings the full-set run back to the Results A numbers. The same applies to any other component that scans `ctx.shape_focus(shape)` per focus node.
- Plan building, focus-node selection and report building are under 3% combined; they are not worth optimising.

## Recommendation

1. Fix `sh:uniqueValuesFor` first (correctness-neutral, removes a 2-10x slowdown versus the old validator and a quadratic blow-up).
2. Add `OxigraphGraph.sparql_query` (currently a crash on `sh:sparql`) and batch SPARQL per shape instead of per focus node.
3. Hoist per-shape component selection out of `_validate_shape_at` into the plan.
4. Only then consider a Rust port of the inner loop and term conversion; after steps 1-3 the remaining cost is graph reads and rdflib term construction, which is exactly what a native path removes. Memory is already a clear win (3x lower peak on StarLayerGraph at 185k triples).

## Addendum: after the fixes (2026-10-30)
Fixes made from the findings above: `sh:uniqueValuesFor` groups focus nodes by key once per shape (was O(n^2));
`OxigraphGraph.sparql_query` exists, so `sh:sparql` runs natively on Oxigraph (it crashed before); component selection per
shape is computed once per run instead of on every visit. Re-run, full shapes set, same machine, best of 5, results
identical to old (35 and 130):

| triples | old | new on StarLayerGraph | new on OxigraphGraph |
|---|---|---|---|
| 4.7k | 1.12 s | 0.52 s | 0.35 s |
| 18.6k | 4.51 s | 2.21 s | 1.52 s |

Before the fix at 18.6k: new 33.9 s and 42.1 s. Still open from the hot-spot list: `sh:sparql` runs one query per focus
node (batch per shape), `Context.conforms` and `eval_path` dedupe, and term conversion on the Oxigraph path.
