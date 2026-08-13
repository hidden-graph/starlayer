"""
benchmarks/bench_inmemory.py

Phase 1 performance benchmarks: StarLayerGraph in-memory mode.

Measures insert throughput, query latency, and memory footprint at
increasing graph sizes to find where in-memory performance degrades.

Run:
    .venv/bin/python benchmarks/bench_inmemory.py

Output is tab-separated tables suitable for pasting into performance.md.
"""

import gc
import statistics
import sys
import time
import tracemalloc

from rdflib import URIRef

sys.path.insert(0, '.')
from starlayergraph.graph import StarLayerGraph
from starlayergraph.model.triple import TripleTerm

EX          = 'http://example.org/'
RDF_REIFIES = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')

SCALES = [100, 1_000, 5_000, 10_000, 50_000, 100_000]

REPEATS = 3   # median of this many runs per measurement


# ---------------------------------------------------------------------------
# Data generators
# ---------------------------------------------------------------------------

def _uri(n):
    return URIRef(f'{EX}n{n}')


def plain_triples(n):
    """n plain triples with ~100 distinct predicates and ~50 distinct objects."""
    return [(_uri(i), _uri(i % 100 + 10_000), _uri(i % 50 + 20_000))
            for i in range(n)]


def tt_triples(n):
    """n reification triples: stmt_i rdf:reifies <<( s_i p_i o_i )>>
    Uses ~20 distinct predicates and ~10 distinct objects so some triple
    terms repeat — realistic for annotation workloads."""
    return [
        (_uri(f's{i}'), RDF_REIFIES,
         TripleTerm(_uri(i), _uri(i % 20 + 10_000), _uri(i % 10 + 20_000)))
        for i in range(n)
    ]


def mixed_triples(n):
    """Half plain, half reification — realistic mixed graph."""
    half = n // 2
    return plain_triples(half) + tt_triples(half)


# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------

def timeit(fn, repeats=REPEATS):
    """Return median wall-clock seconds over `repeats` calls."""
    times = []
    for _ in range(repeats):
        gc.collect()
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return statistics.median(times)


def measure_memory(fn):
    """Return peak memory delta in MiB while fn() runs."""
    gc.collect()
    tracemalloc.start()
    fn()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak / 1024 / 1024


# ---------------------------------------------------------------------------
# Benchmark: insert
# ---------------------------------------------------------------------------

def bench_insert(triples, use_addN=False):
    """Time to insert all triples into a fresh graph. Returns (seconds, graph)."""
    g = [None]

    def run():
        g[0] = StarLayerGraph()
        if use_addN:
            g[0].addN((s, p, o, g[0]) for s, p, o in triples)
        else:
            for t in triples:
                g[0].add(t)

    t = timeit(run)
    run()  # final run to leave g populated for subsequent benchmarks
    return t, g[0]


# ---------------------------------------------------------------------------
# Benchmark: point lookup (__contains__)
# ---------------------------------------------------------------------------

def bench_contains(g, triples):
    """Median time for a single __contains__ check (existing triple)."""
    probe = triples[len(triples) // 2]

    def run():
        _ = probe in g

    return timeit(run, repeats=20)


# ---------------------------------------------------------------------------
# Benchmark: wildcard triples()
# ---------------------------------------------------------------------------

def bench_wildcard_full(g):
    """Time to exhaust triples((None, None, None)) — full scan."""
    def run():
        _ = list(g.triples((None, None, None)))
    return timeit(run)


def bench_wildcard_bound_subject(g, triples):
    """Time to look up all triples with a known subject (typically 1–3 results)."""
    s = triples[0][0]

    def run():
        _ = list(g.triples((s, None, None)))

    return timeit(run, repeats=20)


# ---------------------------------------------------------------------------
# Benchmark: SPARQL query
# ---------------------------------------------------------------------------

def bench_sparql_select_plain(g):
    """Simple SELECT over plain triples — no TT patterns."""
    q = f'SELECT ?s ?o WHERE {{ ?s <{EX}n10000> ?o . }}'

    def run():
        _ = list(g.query(q))

    return timeit(run)


def bench_sparql_tt_pattern(g):
    """SELECT with rdf:reifies <<( )>> TT pattern."""
    q = """
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    SELECT ?stmt ?s ?p ?o WHERE {
        ?stmt rdf:reifies <<( ?s ?p ?o )>> .
    }
    """

    def run():
        _ = list(g.query(q))

    return timeit(run)


# ---------------------------------------------------------------------------
# Benchmark: registry rebuild
# ---------------------------------------------------------------------------

def bench_registry_rebuild(g):
    """Time to call _build_registry_from_store() — full scan + reconstruct."""
    def run():
        g._build_registry_from_store()
    return timeit(run)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def fmt_ms(s):
    return f'{s * 1000:.1f} ms'

def fmt_us(s):
    return f'{s * 1_000_000:.0f} µs'

def fmt_mib(m):
    return f'{m:.1f} MiB'

def fmt_tps(n, s):
    return f'{n / s:,.0f} t/s'


def run_phase(label, triple_fn):
    print(f'\n{"=" * 70}')
    print(f'  {label}')
    print(f'{"=" * 70}')

    header = f'{"N":>8}  {"insert":>12}  {"t/s":>10}  {"addN":>12}  '
    header += f'{"contains":>10}  {"full scan":>12}  {"subj lookup":>12}  {"sparql plain":>14}  {"mem peak":>10}'
    print(header)
    print('-' * len(header))

    for n in SCALES:
        triples = triple_fn(n)

        insert_t, g  = bench_insert(triples, use_addN=False)
        addN_t,   _  = bench_insert(triples, use_addN=True)
        contains_t   = bench_contains(g, triples)
        full_t       = bench_wildcard_full(g)
        subj_t       = bench_wildcard_bound_subject(g, triples)
        sparql_t     = bench_sparql_select_plain(g)
        mem_mib      = measure_memory(lambda: bench_insert(triples)[1])

        row = (
            f'{n:>8}  '
            f'{fmt_ms(insert_t):>12}  '
            f'{fmt_tps(n, insert_t):>10}  '
            f'{fmt_ms(addN_t):>12}  '
            f'{fmt_us(contains_t):>10}  '
            f'{fmt_ms(full_t):>12}  '
            f'{fmt_ms(subj_t):>12}  '
            f'{fmt_ms(sparql_t):>14}  '
            f'{fmt_mib(mem_mib):>10}'
        )
        print(row)
        sys.stdout.flush()


def run_tt_phase():
    print(f'\n{"=" * 70}')
    print('  Triple-term workload — reification + SPARQL TT pattern')
    print(f'{"=" * 70}')

    header = f'{"N":>8}  {"insert":>12}  {"t/s":>10}  {"sparql TT":>12}  {"registry rebuild":>18}  {"mem peak":>10}'
    print(header)
    print('-' * len(header))

    for n in SCALES:
        triples = tt_triples(n)

        insert_t, g  = bench_insert(triples, use_addN=False)
        sparql_tt_t  = bench_sparql_tt_pattern(g)
        rebuild_t    = bench_registry_rebuild(g)
        mem_mib      = measure_memory(lambda: bench_insert(triples)[1])

        row = (
            f'{n:>8}  '
            f'{fmt_ms(insert_t):>12}  '
            f'{fmt_tps(n, insert_t):>10}  '
            f'{fmt_ms(sparql_tt_t):>12}  '
            f'{fmt_ms(rebuild_t):>18}  '
            f'{fmt_mib(mem_mib):>10}'
        )
        print(row)
        sys.stdout.flush()


if __name__ == '__main__':
    print('StarLayerGraph in-memory performance benchmarks')
    print(f'Python {sys.version}')
    print(f'Repeats per measurement: {REPEATS} (median reported)')

    run_phase('Plain triples', plain_triples)
    run_phase('Mixed workload (50% plain, 50% reification)', mixed_triples)
    run_tt_phase()

    print('\nDone.')
