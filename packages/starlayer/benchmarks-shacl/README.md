# Benchmarks

*Last reviewed: 2026-11-10*

Performance benchmarks for the native SHACL 1.2 engine (`starlayer.shacl_engine`). Both scripts run standalone and print timings; neither is part of a CI regression guard.

## Scripts

| Script | Scope | Requires |
| --- | --- | --- |
| `bench_engine_vs_old.py` | The engine against the pySHACL-backed validator, on a generated people/org/address graph and shapes graph; `--profile N` profiles one run | No server |
| `bench_overlay.py` | The engine on a data graph with an RDFS subclass overlay, Python overlay against Oxigraph overlay (`--overlay python\|oxigraph`) | No server |

```bash
PYTHONPATH=packages/starlayer python3 benchmarks-shacl/bench_engine_vs_old.py --sizes 1000,1000
PYTHONPATH=packages/starlayer python3 benchmarks-shacl/bench_overlay.py --sizes 5000,20000 --overlay oxigraph
```

Results and background: [`docs/working/shacl-engine-benchmarks.md`](../../../docs/working/shacl-engine-benchmarks.md) and [`docs/working/shacl-engine-overlay-oxigraph.md`](../../../docs/working/shacl-engine-overlay-oxigraph.md).

## No scheduled regression guard

The nightly `benchmark.yml` workflow guards `benchmarks-graph` only. The earlier guard here timed `TripleTermAdapter`'s encode/decode, which no longer exists (the Oxigraph migration removed it), so the test, its script and its `baseline.json` were deleted. A new guard needs a pytest-benchmark module (`test_bench_shacl.py`, with the calibration benchmark that `scripts/check_benchmark_regression.py` requires) and a baseline recorded on the CI runners with `scripts/record_benchmark_baseline.py`.
