# Benchmarks

*Last reviewed: 2026-07-17*

Performance benchmarks for starlayer.shacl's triple-term encode/decode adapter (`starlayer/shacl/adapters.py::TripleTermAdapter`) - the boundary layer that translates between RDF 1.2 triple terms and the RDF-1.1-only term model pySHACL understands.

## Scripts

| Script | Scope | Requires |
| --- | --- | --- |
| `bench_adapter.py` | In-memory only: `encode_graph`/`decode_graph` wall-clock time and generated support-triple count, for a configurable triple count and triple-term nesting depth | No server - runs standalone |

## Running

```bash
python benchmarks-shacl/bench_adapter.py --triples 1000 --nested-depth 1
```

Flags:
- `--triples` (default 1000): number of triples in the generated test graph.
- `--nested-depth` (default 1): how deeply nested the generated triple terms are (`1` = flat triple-term objects; higher values nest a triple term inside another's object position).

Deeper nesting stresses the recursive parts of `_encode_node`/`_decode_node` specifically:

```bash
python benchmarks-shacl/bench_adapter.py --triples 2000 --nested-depth 3
```

Output:
- total encode time (ms)
- total decode time (ms)
- generated support-triple count (the `rdf:subject`/`rdf:predicate`/`rdf:object` triples the adapter emits per encoded triple term, so pySHACL's own report/rule machinery can still see the decomposed structure)

## What this doesn't cover

This measures the adapter's own encode/decode cost in isolation, not full `StarShaclSchema.validate()`/`apply_rules()` performance - `sh:construct` rule-iteration performance (dominated by `_SparqlAwareEncodedGraph.query()`'s decode cost, not the adapter's `encode_graph`/`decode_graph`) is a related but separate cost, currently only measured ad hoc via manual profiling (see `../docs/shacl/implementation-plan.md`'s "Next Steps" for the known remaining bottlenecks there). Worth a dedicated script here if that becomes a recurring need.

## Results

See [`docs/shacl/benchmark-baselines.md`](../docs/shacl/benchmark-baselines.md) for recorded baselines over time.

## Regression guard: `test_bench_shacl.py`

A separate, CI-fast pytest-benchmark suite (fixed 2000 triples, depth 1) that catches real regressions in `encode_graph`/`decode_graph` - not a replacement for `bench_adapter.py` above, which remains the tool for exploring different triple counts/nesting depths and updating `benchmark-baselines.md`.

Lives outside `testpaths` (`packages/starlayer/tests`), so a bare `pytest` run never collects it:

```bash
pip install -e ".[benchmark]"
pytest benchmarks-shacl/test_bench_shacl.py --benchmark-only
```

Run on a schedule (not every push/PR - timings are too noisy on shared CI runners to gate every commit on) by [`.github/workflows/benchmark.yml`](../../../.github/workflows/benchmark.yml), which compares a fresh run against the committed `baseline.json` via [`scripts/check_benchmark_regression.py`](../../../scripts/check_benchmark_regression.py) and fails the workflow (GitHub's own failed-scheduled-run notification is the alert) if `encode_graph`/`decode_graph`'s minimum time, relative to a calibration benchmark timed in the same run, regresses more than 30%. The calibration (`test_calibration_reference`, a fixed pure-Python workload) cancels the differences between the CPUs GitHub assigns, which are about 2x apart.

To update `baseline.json` after an intentional, accepted performance change, record it from several runs on the CI runners (not from a laptop, and not from one run): trigger `benchmark.yml` four or more times with `gh workflow run`, download each run's `benchmark-results` artifact, and run `scripts/record_benchmark_baseline.py packages/starlayer/benchmarks-shacl/baseline.json <the runs' bench-shacl-result.json>`. Details are in that script's docstring.
