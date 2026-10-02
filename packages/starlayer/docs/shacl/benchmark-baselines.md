# Benchmark Baselines

*Last reviewed: 2026-07-18*

Use this document to track adapter encode/decode benchmark output before each release.

## Command

```bash
python benchmarks/bench_adapter.py --triples 1000 --nested-depth 1
```

## Baseline Log

| Date (UTC) | Version | Python | Host | Triples | Nested Depth | Encode (ms) | Decode (ms) | Notes |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 2026-06-30 | unreleased | 3.10+ | local | 1000 | 1 | 90.000 | 1021.324 | Captured from benchmarks/bench_adapter.py |
| 2026-07-17 | unreleased (commit `824ea2f`) | 3.14.2 | local (Darwin arm64) | 1000 | 1 | 11.8 | 23.0 | 3 runs, range encode 11.68-12.04ms / decode 22.55-23.45ms. Substantially faster than the 2026-06-30 baseline (~8x encode, ~44x decode) - not attributed to a specific optimization; this session's changes to `adapters.py` (a shared `_starlayer_graph_class()` helper, the `_SparqlAwareEncodedGraph` mutation-version cache) don't touch `encode_graph`/`decode_graph`'s core loops directly, so the difference is more likely Python version (3.14.2 vs whatever ran the original baseline) and/or host state than a code change - re-baseline on a like-for-like environment if this needs to be trusted precisely |
| 2026-07-17 | unreleased (commit `824ea2f`) | 3.14.2 | local (Darwin arm64) | 2000 | 3 | 68.7 | 112.0 | 2 runs, range encode 67.9-69.5ms / decode 109.3-114.6ms. The deeper-nesting configuration from `benchmarks/README.md`'s example |
| 2026-07-18 | unreleased (uncommitted, on top of commit `046e4b1`) | 3.14.2 | local (Darwin arm64) | 1000 | 1 | 13.0 | 22.7 | 3 runs, range encode 12.65-13.24ms / decode 22.08-23.08ms. Re-run after this session's native-component/meta-shapes/composition work - none of it touches `adapters.py::encode_graph`/`decode_graph`'s core loops, so this is essentially unchanged from the 2026-07-17 baseline (within run-to-run noise), as expected |
| 2026-07-18 | unreleased (uncommitted, on top of commit `046e4b1`) | 3.14.2 | local (Darwin arm64) | 2000 | 3 | 69.9 | 119.0 | 3 runs, range encode 69.2-70.7ms / decode 117.8-120.1ms. Decode is ~5-8ms higher than the 2026-07-17 baseline's range (109.3-114.6ms) - small enough relative to host-level noise already flagged in that entry to not be worth chasing without a controlled re-run; not close to the 20 percent regression threshold below |

## Guidance

- Record at least one baseline before tagging a release.
- If encode/decode time regresses by more than 20 percent, investigate and note the cause in release notes.
- Keep entries append-only for trend visibility.
