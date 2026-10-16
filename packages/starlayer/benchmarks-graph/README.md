# Benchmarks

*Last reviewed: 2026-07-17*

Performance benchmarks for starlayergraph across all supported backends.

## Scripts

| Script | Scope | Requires |
|---|---|---|
| `bench_inmemory.py` | In-memory only: insert/query/memory characterization at 100–100K facts | No server — runs standalone |
| `bench_http.py` | Small-scale (100–10K) generic op comparison (insert/contains/full-scan/SPARQL) across backends | Fuseki and/or Oxigraph — skips whichever isn't reachable |
| `bench_scaling.py` | Large-scale (50K/250K/500K) TT-pattern query performance: in-memory vs rdf-1.1/Fuseki vs rdf-1.2/Fuseki vs rdf-1.2/Oxigraph | Fuseki and/or Oxigraph — skips whichever isn't reachable |
| `bench_inmemory_oxigraph.py` | In-memory default store vs in-memory Oxigraph (`OxigraphStore`, `rdf-1.2`), sweeping size (50K-500K) *and* reification rate (10/50/100%): load, memory, TT-pattern queries, lookups. Each cell in its own subprocess (clean peak RSS). `--quick` for a 50K smoke run | `pip install oxrdflib pyoxigraph`; no server |

`bench_http.py` and `bench_scaling.py` look like they'd overlap (both compare backends) but ask different questions: `bench_http.py` measures general per-operation overhead at small scale across both plain-triple and TT workloads, while `bench_scaling.py` is specifically about how TT-pattern query latency scales with dataset size. `bench_scaling.py` replaced three former scripts (`bench_fuseki.py`, `bench_fuseki_rdf11.py`, `bench_oxigraph.py`) that duplicated the same dataset generator, query set, and timing harness three times over with only the backend-loading logic differing.

## Running

```bash
# In-memory — no server needed
python benchmarks-graph/bench_inmemory.py

# Start Fuseki and/or Oxigraph (see below), then:
python benchmarks-graph/bench_http.py
python benchmarks-graph/bench_scaling.py
```

## Starting Fuseki

```bash
docker run -d --name fuseki-bench -p 3030:3030 atomgraph/fuseki:latest --update --mem --ping /bench
```

## Starting Oxigraph

```bash
docker run -d --name oxigraph-bench -p 7878:7878 \
    ghcr.io/oxigraph/oxigraph serve --bind 0.0.0.0:7878
```

## Results summary

See [performance.md](../docs/graph/performance.md) for benchmark results and backend recommendations.

## Regression guard: `test_bench_graph.py`

A separate, CI-fast pytest-benchmark suite (fixed N=2000, not the full scaling sweep above) that catches real regressions in a handful of hot paths - not a replacement for the scripts above, which remain the tool for characterizing scaling and updating `performance.md`.

Lives outside `testpaths` (`packages/starlayer/tests`), so a bare `pytest` run never collects it:

```bash
pip install -e ".[benchmark]"
pytest benchmarks-graph/test_bench_graph.py --benchmark-only
```

Run on a schedule (not every push/PR - timings are too noisy on shared CI runners to gate every commit on) by [`.github/workflows/benchmark.yml`](../../../.github/workflows/benchmark.yml), which compares a fresh run against the committed `baseline.json` via [`scripts/check_benchmark_regression.py`](../../../scripts/check_benchmark_regression.py) and fails the workflow (GitHub's own failed-scheduled-run notification is the alert) if any benchmark's mean time regresses more than 20%.

To update `baseline.json` after an intentional, accepted performance change:

```bash
pytest benchmarks-graph/test_bench_graph.py --benchmark-only --benchmark-json=benchmarks-graph/baseline.json
```
