"""
benchmarks/bench_http.py

Phase 2 performance benchmarks: StarLayerGraph against HTTP backends.

Compares rdf-1.1 and rdf-1.2 (Fuseki 5.5+ and Oxigraph) modes at
the same scale points used in bench_inmemory.py.

Requirements:
  Fuseki:   docker run -d --name fuseki-bench -p 3030:3030 atomgraph/fuseki:latest --update --mem --ping /bench

  Oxigraph: docker run -d --name oxigraph-bench -p 7878:7878 \\
              ghcr.io/oxigraph/oxigraph serve --location /data --bind 0.0.0.0:7878

Run:
    .venv/bin/python benchmarks/bench_http.py

Skips unavailable backends automatically.
"""

import gc
import statistics
import sys
import time

import requests
from rdflib import URIRef
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore

sys.path.insert(0, '.')
from starlayergraph.graph import StarLayerGraph
from starlayergraph.model.triple import TripleTerm

EX          = 'http://example.org/'
RDF_REIFIES = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')
GRAPH_URI   = URIRef('http://example.org/bench-graph')

SCALES  = [100, 1_000, 5_000, 10_000]
REPEATS = 3


# ---------------------------------------------------------------------------
# Backend descriptors
# ---------------------------------------------------------------------------

BACKENDS = [
    {
        'label':       'rdf-1.1 / Fuseki',
        'backend':     'rdf-1.1',
        'query_url':   'http://localhost:3030/bench/query',
        'update_url':  'http://localhost:3030/bench/update',
        'clear_url':   'http://localhost:3030/bench/update',
        'auth':        ('admin', 'admin'),
        'ping':        'http://localhost:3030/$/ping',
    },
    {
        'label':       'rdf-1.2 / Fuseki',
        'backend':     'rdf-1.2',
        'query_url':   'http://localhost:3030/bench/query',
        'update_url':  'http://localhost:3030/bench/update',
        'clear_url':   'http://localhost:3030/bench/update',
        'auth':        ('admin', 'admin'),
        'ping':        'http://localhost:3030/$/ping',
    },
    {
        'label':       'rdf-1.2 / Oxigraph',
        'backend':     'rdf-1.2',
        'query_url':   'http://localhost:7878/query',
        'update_url':  'http://localhost:7878/update',
        'clear_url':   'http://localhost:7878/update',
        'auth':        None,
        'ping':        'http://localhost:7878',
    },
]


# ---------------------------------------------------------------------------
# Data generators (same as bench_inmemory)
# ---------------------------------------------------------------------------

def _uri(n):
    return URIRef(f'{EX}n{n}')


def plain_triples(n):
    return [(_uri(i), _uri(i % 100 + 10_000), _uri(i % 50 + 20_000))
            for i in range(n)]


def tt_triples(n):
    return [
        (_uri(f's{i}'), RDF_REIFIES,
         TripleTerm(_uri(i), _uri(i % 20 + 10_000), _uri(i % 10 + 20_000)))
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _available(ping_url):
    try:
        return requests.get(ping_url, timeout=2).status_code == 200
    except Exception:
        return False


def _clear(cfg):
    kwargs = {}
    if cfg['auth']:
        kwargs['auth'] = cfg['auth']
    requests.post(
        cfg['clear_url'],
        data=f'CLEAR SILENT GRAPH <{GRAPH_URI}>',
        headers={'Content-Type': 'application/sparql-update'},
        timeout=10,
        **kwargs,
    ).raise_for_status()


def _make_graph(cfg):
    store = SPARQLUpdateStore(
        query_endpoint=cfg['query_url'],
        update_endpoint=cfg['update_url'],
        auth=cfg['auth'],
    )
    return StarLayerGraph(store=store, identifier=GRAPH_URI, backend=cfg['backend'])


def timeit(fn, repeats=REPEATS):
    times = []
    for _ in range(repeats):
        gc.collect()
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return statistics.median(times)


def fmt_ms(s):
    return f'{s * 1000:.1f} ms'

def fmt_tps(n, s):
    return f'{n / s:,.0f} t/s'


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

def bench_insert(cfg, triples):
    """Time to insert all triples from a clean graph."""
    g = [None]

    def run():
        _clear(cfg)
        g[0] = _make_graph(cfg)
        for t in triples:
            g[0].add(t)

    t = timeit(run)
    run()
    return t, g[0]


def bench_contains(g, triples):
    probe = triples[len(triples) // 2]

    def run():
        _ = probe in g

    return timeit(run, repeats=10)


def bench_wildcard_full(g):
    def run():
        _ = list(g.triples((None, None, None)))
    return timeit(run)


def bench_sparql_plain(g):
    q = f'SELECT ?s ?o WHERE {{ GRAPH <{GRAPH_URI}> {{ ?s <{EX}n10000> ?o . }} }}'

    def run():
        _ = list(g.query(q))

    return timeit(run)


def bench_sparql_tt(g):
    q = f"""
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    SELECT ?stmt ?s ?p ?o WHERE {{
        GRAPH <{GRAPH_URI}> {{
            ?stmt rdf:reifies <<( ?s ?p ?o )>> .
        }}
    }}
    """

    def run():
        _ = list(g.query(q))

    return timeit(run)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_backend(cfg, triple_fn, label_suffix):
    print(f'\n  [{cfg["label"]}] — {label_suffix}')

    header = f'{"N":>8}  {"insert":>12}  {"t/s":>10}  {"contains":>12}  {"full scan":>12}  {"sparql":>12}'
    print('  ' + header)
    print('  ' + '-' * len(header))

    for n in SCALES:
        triples = triple_fn(n)
        insert_t, g = bench_insert(cfg, triples)
        contains_t  = bench_contains(g, triples)
        full_t      = bench_wildcard_full(g)
        sparql_t    = bench_sparql_plain(g) if triple_fn is plain_triples else bench_sparql_tt(g)

        row = (
            f'{n:>8}  '
            f'{fmt_ms(insert_t):>12}  '
            f'{fmt_tps(n, insert_t):>10}  '
            f'{fmt_ms(contains_t):>12}  '
            f'{fmt_ms(full_t):>12}  '
            f'{fmt_ms(sparql_t):>12}'
        )
        print('  ' + row)
        sys.stdout.flush()


if __name__ == '__main__':
    print('StarLayerGraph HTTP backend performance benchmarks')
    print(f'Python {sys.version}')
    print(f'Repeats per measurement: {REPEATS} (median reported)')

    for cfg in BACKENDS:
        if not _available(cfg['ping']):
            print(f'\n[SKIP] {cfg["label"]} — endpoint not reachable ({cfg["ping"]})')
            continue

        print(f'\n{"=" * 70}')
        print(f'  Backend: {cfg["label"]}')
        print(f'{"=" * 70}')

        run_backend(cfg, plain_triples,  'plain triples')
        run_backend(cfg, tt_triples,     'triple-term (reification) workload')

    print('\nDone.')
