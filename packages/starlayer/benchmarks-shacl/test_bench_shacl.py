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
