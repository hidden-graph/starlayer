"""
benchmarks-shacl/test_bench_shacl.py

pytest-benchmark regression guards for TripleTermAdapter's encode/decode
hot path. Lives outside `testpaths` (packages/starlayer/tests), so a bare
`pytest` run never collects this - invoke explicitly:

    pytest benchmarks-shacl/test_bench_shacl.py --benchmark-only

Requires the `benchmark` extra: pip install -e ".[benchmark]"
"""

from bench_adapter import _build_graph
from starlayer.shacl import TripleTermAdapter

TRIPLES = 2000
NESTED_DEPTH = 1


def test_encode_graph(benchmark):
    graph = _build_graph(TRIPLES, NESTED_DEPTH)
    adapter = TripleTermAdapter()
    benchmark(adapter.encode_graph, graph)


def test_decode_graph(benchmark):
    graph = _build_graph(TRIPLES, NESTED_DEPTH)
    adapter = TripleTermAdapter()
    encoded = adapter.encode_graph(graph)
    benchmark(adapter.decode_graph, encoded)


# --- calibration -------------------------------------------------------------------------------------------------------
# A fixed, pure-Python workload (no rdflib, no starlayer) timed in the same run. GitHub's runners draw a different CPU
# from day to day (about 2x apart), so scripts/check_benchmark_regression.py compares each benchmark as a ratio to this
# one, not as absolute milliseconds. Keep it identical in benchmarks-graph and benchmarks-shacl, and do not change it
# without re-recording both baselines (GitHub issue #33).
CALIBRATION_NAME = "test_calibration_reference"


def _reference_workload():
    rows = {f"http://example.org/node/{i}": (i, str(i * 7), i % 13) for i in range(20000)}
    keys = sorted(rows, key=lambda k: (rows[k][2], k))
    evens = {k for k in keys if rows[k][0] % 2 == 0}
    threes = {k for k in keys if rows[k][0] % 3 == 0}
    return len(evens & threes) + len(" ".join(keys[:2000]))


def test_calibration_reference(benchmark):
    benchmark(_reference_workload)
