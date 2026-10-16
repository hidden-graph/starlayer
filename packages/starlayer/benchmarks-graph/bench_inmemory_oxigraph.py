"""
benchmarks-graph/bench_inmemory_oxigraph.py

In-memory comparison: StarLayerGraph's default store (rdflib Memory, rdf-1.1
representation with the tt:HASH encoding) vs. in-memory Oxigraph
(oxrdflib's OxigraphStore wrapping a path-less pyoxigraph.Store, run in
rdf-1.2 native mode - see starlayer/graph/backends/native_oxigraph.py).

The hypothesis under test: large in-memory graphs with many reifications do
better on Oxigraph than on the default store. So the sweep varies reification
rate (not just size) and measures load time, peak process memory, TT-pattern
queries, and plain triple lookups.

Each (backend, size, reification-rate) cell runs in its own subprocess so peak
RSS is attributable to that one cell, not to earlier cells in the same process.
No server needed. Requires: pip install oxrdflib pyoxigraph

Run:
    .venv/bin/python packages/starlayer/benchmarks-graph/bench_inmemory_oxigraph.py
    .venv/bin/python packages/starlayer/benchmarks-graph/bench_inmemory_oxigraph.py --quick
"""

from __future__ import annotations

import argparse
import gc
import json
import resource
import statistics
import subprocess
import sys
import time

EX = 'http://example.org/'
REPEATS = 3
LOOKUPS = 200
ADDN_CHUNK = 50_000

# Guard for the default store, which holds every triple in Python objects (~4 KB each
# at high reification rates); raise it on a machine with plenty of RAM.
MAX_PHYSICAL_TRIPLES = 1_000_000
SIZES = [50_000, 250_000, 500_000]
REIF_RATES = [0.10, 0.50, 1.00]   # fraction of triples that are reified + annotated
BACKENDS = ['default', 'oxigraph']


# ---------------------------------------------------------------------------
# Worker: one backend x size x rate, prints one JSON line
# ---------------------------------------------------------------------------

def _peak_rss_mb() -> float:
    ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return ru / (1024 * 1024) if sys.platform == 'darwin' else ru / 1024   # bytes on macOS, KB on Linux


def _timeit(fn, repeats=REPEATS) -> float:
    times = []
    for _ in range(repeats):
        gc.collect()
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return statistics.median(times)


def worker(backend: str, n: int, rate: float) -> dict:
    from rdflib import Literal, URIRef
    from rdflib.namespace import XSD
    from starlayer.graph.graph import StarLayerGraph
    from starlayer.graph.model.triple import TripleTerm

    rdf_reifies = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')
    ex_conf = URIRef(EX + 'confidence')

    def uri(k):
        return URIRef(f'{EX}n{k}')

    triples = []
    n_reif = int(n * rate)
    for i in range(n):
        s, p, o = uri(i), uri(i % 200 + 50_000), uri(i % 100 + 60_000)
        triples.append((s, p, o))
        if i < n_reif:
            stmt = uri(f'stmt{i}')
            conf = round(0.5 + (i % 10) / 20, 2)
            triples.append((stmt, rdf_reifies, TripleTerm(s, p, o)))
            triples.append((stmt, ex_conf, Literal(str(conf), datatype=XSD.decimal)))
    bound_pred = uri(50_000)
    base_rss = _peak_rss_mb()

    if backend == 'default':
        g = StarLayerGraph()
    else:
        import pyoxigraph
        from oxrdflib import OxigraphStore
        g = StarLayerGraph(store=OxigraphStore(store=pyoxigraph.Store()), backend='rdf-1.2')

    t0 = time.perf_counter()
    if backend == 'default':
        g.addN((s, p, o, g) for s, p, o in triples)
    else:
        for k in range(0, len(triples), ADDN_CHUNK):
            g.addN((s, p, o, g) for s, p, o in triples[k:k + ADDN_CHUNK])
    load_t = time.perf_counter() - t0
    after_load_rss = _peak_rss_mb()

    queries = {
        'all_reified': (
            'PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> '
            'SELECT ?stmt ?s ?p ?o WHERE { ?stmt rdf:reifies <<( ?s ?p ?o )>> . }'
        ),
        'reified_conf_join': (
            'PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> '
            f'PREFIX ex: <{EX}> PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> '
            'SELECT ?stmt ?s ?p ?o WHERE { ?stmt rdf:reifies <<( ?s ?p ?o )>> . '
            '?stmt ex:confidence ?c . FILTER(xsd:decimal(?c) > 0.7) }'
        ),
        'partial_tt_bound_pred': (
            'PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> '
            f'SELECT ?stmt ?s ?o WHERE {{ ?stmt rdf:reifies <<( ?s <{bound_pred}> ?o )>> . }}'
        ),
    }
    results = {}
    for name, q in queries.items():
        rows = len(list(g.query(q)))
        results[name] = {'ms': _timeit(lambda q=q: list(g.query(q))) * 1000, 'rows': rows}

    # Plain triple lookups (single subject), the case the docs flag as remote Oxigraph's weak point.
    step = max(1, n // LOOKUPS)
    subjects = [uri(i) for i in range(0, n, step)][:LOOKUPS]
    t_lookup = _timeit(lambda: [list(g.triples((s, None, None))) for s in subjects])
    results['subject_lookup_each'] = {'ms': t_lookup * 1000 / len(subjects), 'rows': len(subjects)}

    # Reifications for one specific statement (annotation lookup by TT).
    if n_reif:
        probe = TripleTerm(uri(0), uri(50_000), uri(60_000))
        results['reifiers_of_one_tt'] = {
            'ms': _timeit(lambda: list(g.subjects(rdf_reifies, probe))) * 1000,
            'rows': len(list(g.subjects(rdf_reifies, probe))),
        }

    return {
        'backend': backend, 'n': n, 'rate': rate, 'physical_triples': len(triples),
        'load_s': load_t, 'peak_rss_mb': _peak_rss_mb(),
        'rss_growth_load_mb': after_load_rss - base_rss, 'results': results,
    }


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _fmt_ms(ms: float) -> str:
    if ms >= 1000:
        return f'{ms / 1000:.2f} s'
    if ms >= 1:
        return f'{ms:.1f} ms'
    return f'{ms * 1000:.0f} us'


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--worker', nargs=3, metavar=('BACKEND', 'N', 'RATE'))
    ap.add_argument('--quick', action='store_true', help='50K only, two rates')
    ap.add_argument('--json', metavar='PATH', help='also write all raw results here')
    args = ap.parse_args()

    if args.worker:
        b, n, r = args.worker
        print(json.dumps(worker(b, int(n), float(r))))
        return

    sizes = [50_000] if args.quick else SIZES
    rates = [0.10, 1.00] if args.quick else REIF_RATES
    print(f'In-memory benchmark: default store vs in-memory Oxigraph (rdf-1.2)  |  Python {sys.version.split()[0]}')
    all_rows = []
    for n in sizes:
        for rate in rates:
            if n * (1 + 2 * rate) > MAX_PHYSICAL_TRIPLES:
                print(f'\n  (skipping N={n:,} @ {rate:.0%}: {int(n * (1 + 2 * rate)):,} physical triples exceeds MAX_PHYSICAL_TRIPLES)')
                continue
            print(f'\n{"=" * 78}\n  N = {n:,} base triples  |  {int(n * rate):,} reified+annotated ({rate:.0%})\n{"=" * 78}')
            cell = {}
            for backend in BACKENDS:
                out = subprocess.run(
                    [sys.executable, __file__, '--worker', backend, str(n), str(rate)],
                    capture_output=True, text=True,
                )
                if out.returncode != 0:
                    print(f'  {backend}: FAILED\n{out.stderr[-600:]}')
                    continue
                cell[backend] = json.loads(out.stdout.strip().splitlines()[-1])
                all_rows.append(cell[backend])
            if len(cell) < 2:
                continue
            d, o = cell['default'], cell['oxigraph']
            print(f'  {"":<28}{"default":>14}{"oxigraph":>14}{"oxigraph vs default":>22}')
            def row(label, dv, ov, fmt):
                ratio = (dv / ov) if ov else float('inf')
                print(f'  {label:<28}{fmt(dv):>14}{fmt(ov):>14}{(f"{ratio:.1f}x faster" if ratio >= 1 else f"{1/ratio:.1f}x slower"):>22}')
            row('physical triples loaded', d['physical_triples'], o['physical_triples'], lambda v: f'{v:,}')
            row('load', d['load_s'] * 1000, o['load_s'] * 1000, _fmt_ms)
            row('RSS growth over load (MB)', d['rss_growth_load_mb'], o['rss_growth_load_mb'], lambda v: f'{v:,.0f}')
            row('peak RSS, whole process (MB)', d['peak_rss_mb'], o['peak_rss_mb'], lambda v: f'{v:,.0f}')
            for name in d['results']:
                if name not in o['results']:
                    continue
                dr, orr = d['results'][name], o['results'][name]
                row(name, dr['ms'], orr['ms'], _fmt_ms)
                if dr['rows'] != orr['rows']:
                    print(f'    !! row count differs for {name}: default={dr["rows"]} oxigraph={orr["rows"]}')

    if args.json:
        with open(args.json, 'w') as fh:
            json.dump(all_rows, fh, indent=2)
    print('\nDone.')


if __name__ == '__main__':
    main()
