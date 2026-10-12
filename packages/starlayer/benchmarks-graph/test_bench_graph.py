"""
benchmarks-graph/test_bench_graph.py

pytest-benchmark regression guards for StarLayerGraph's hot paths. These
live outside `testpaths` (packages/starlayer/tests), so a bare `pytest`
run never collects them - invoke explicitly:

    pytest benchmarks-graph/test_bench_graph.py --benchmark-only

One fixed, CI-fast scale (N=2000) - these catch regressions, they don't
characterize scaling. For the full scaling sweep used to update
docs/graph/performance.md, see bench_inmemory.py/bench_scaling.py in this
same directory (unaffected by this file - they stay the deep-dive tool).

Requires the `benchmark` extra: pip install -e ".[benchmark]"
"""

from bench_inmemory import plain_triples, tt_triples
from starlayer.graph.graph import StarLayerGraph

N = 2000


def _insert(triples):
    g = StarLayerGraph()
    for t in triples:
        g.add(t)
    return g


def test_insert_plain_triples(benchmark):
    triples = plain_triples(N)
    benchmark(_insert, triples)


def test_insert_tt_triples(benchmark):
    triples = tt_triples(N)
    benchmark(_insert, triples)


def test_contains_lookup(benchmark):
    triples = plain_triples(N)
    g = _insert(triples)
    probe = triples[len(triples) // 2]
    benchmark(lambda: probe in g)


def test_sparql_select_plain(benchmark):
    triples = plain_triples(N)
    g = _insert(triples)
    query = "SELECT ?s ?o WHERE { ?s <http://example.org/n10000> ?o . }"
    benchmark(lambda: list(g.query(query)))


def test_sparql_tt_pattern(benchmark):
    triples = tt_triples(N)
    g = _insert(triples)
    query = """
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    SELECT ?stmt ?s ?p ?o WHERE {
        ?stmt rdf:reifies <<( ?s ?p ?o )>> .
    }
    """
    benchmark(lambda: list(g.query(query)))
