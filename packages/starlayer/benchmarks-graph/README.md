# Benchmarks

*Last reviewed: 2026-07-17*

Performance benchmarks for starlayergraph across all supported backends.

## Scripts

| Script | Scope | Requires |
|---|---|---|
| `bench_inmemory.py` | In-memory only: insert/query/memory characterization at 100–100K facts | No server — runs standalone |
| `bench_http.py` | Small-scale (100–10K) generic op comparison (insert/contains/full-scan/SPARQL) across backends | Fuseki and/or Oxigraph — skips whichever isn't reachable |
| `bench_scaling.py` | Large-scale (50K/250K/500K) TT-pattern query performance: in-memory vs rdf-1.1/Fuseki vs rdf-1.2/Fuseki vs rdf-1.2/Oxigraph | Fuseki and/or Oxigraph — skips whichever isn't reachable |

`bench_http.py` and `bench_scaling.py` look like they'd overlap (both compare backends) but ask different questions: `bench_http.py` measures general per-operation overhead at small scale across both plain-triple and TT workloads, while `bench_scaling.py` is specifically about how TT-pattern query latency scales with dataset size. `bench_scaling.py` replaced three former scripts (`bench_fuseki.py`, `bench_fuseki_rdf11.py`, `bench_oxigraph.py`) that duplicated the same dataset generator, query set, and timing harness three times over with only the backend-loading logic differing.

## Running

```bash
# In-memory — no server needed
python benchmarks/bench_inmemory.py

# Start Fuseki and/or Oxigraph (see below), then:
python benchmarks/bench_http.py
python benchmarks/bench_scaling.py
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

See [performance.md](../docs/performance.md) for benchmark results and backend recommendations.
