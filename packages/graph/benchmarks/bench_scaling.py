"""
benchmarks/bench_scaling.py

TT-pattern query performance across all backends at increasing scale:
in-memory, rdf-1.1/Fuseki, rdf-1.2/Fuseki, rdf-1.2/Oxigraph.

Consolidates three previous near-duplicate scripts (bench_fuseki.py,
bench_fuseki_rdf11.py, bench_oxigraph.py) into one. All three shared the
same dataset generator, the same three TT-pattern queries, and the same
timing harness, differing only in how each backend loads/clears/queries
data (named-graph wrapping for Fuseki, rdf-1.1 encoding-triple expansion,
Oxigraph's unnamed default graph). Backends are skipped automatically if
not reachable, so this can run standalone (in-memory only) or against
whichever of Fuseki/Oxigraph happen to be up.

Queries tested:
  1. All reified TTs — single TT pattern          : <<( ?s ?p ?o )>>
  2. Reified TTs with confidence > 0.7 — TT + join
  3. Partial TT match — TT with bound predicate   : <<( ?s <pred> ?o )>>

Scales: 50K, 250K, 500K TTs (10% reification rate throughout).

Fuseki requirements:
  docker run -d --name fuseki-bench -p 3030:3030 atomgraph/fuseki:latest --update --mem --ping /bench

Oxigraph requirements:
  docker run -d --name oxigraph-bench -p 7878:7878 \\
      ghcr.io/oxigraph/oxigraph serve --bind 0.0.0.0:7878

Run:
    .venv/bin/python benchmarks/bench_scaling.py
"""

import gc
import statistics
import sys
import time

import requests
from rdflib import Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore

sys.path.insert(0, '.')
from starlayergraph.backends.native import sparql_term
from starlayergraph.graph import StarLayerGraph
from starlayergraph.model.encoding import TT_NS, tt_hash
from starlayergraph.model.triple import TripleTerm

EX          = 'http://example.org/'
RDF_REIFIES = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')
RDF_SUBJECT = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#subject')
RDF_PRED    = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#predicate')
RDF_OBJECT  = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#object')
EX_CONF     = URIRef(EX + 'confidence')
GRAPH_URI   = URIRef(EX + 'bench')

FUSEKI_QUERY_URL   = 'http://localhost:3030/bench/query'
FUSEKI_UPDATE_URL  = 'http://localhost:3030/bench/update'
FUSEKI_PING_URL    = 'http://localhost:3030/$/ping'
FUSEKI_AUTH        = ('admin', 'admin')

OXIGRAPH_BASE_URL   = 'http://localhost:7878'
OXIGRAPH_QUERY_URL  = f'{OXIGRAPH_BASE_URL}/query'
OXIGRAPH_UPDATE_URL = f'{OXIGRAPH_BASE_URL}/update'

SCALES      = [50_000, 250_000, 500_000]
REPEATS     = 3
BATCH_SIZE  = 500


# ---------------------------------------------------------------------------
# Dataset (shared by every backend)
# ---------------------------------------------------------------------------

def _uri(n):
    return URIRef(f'{EX}n{n}')


def build_dataset(n_tt):
    """N TTs, 10% reified, 10% annotated. Same shape for every backend."""
    triples = []
    pred_bound = URIRef(f'{EX}n{50_000}')
    for i in range(n_tt):
        tt = TripleTerm(_uri(i), _uri(i % 200 + 50_000), _uri(i % 100 + 60_000))
        triples.append((_uri(i), _uri(i % 200 + 50_000), _uri(i % 100 + 60_000)))
        if i < n_tt // 10:
            stmt = _uri(f'stmt{i}')
            conf = round(0.5 + (i % 10) / 20, 2)
            triples.append((stmt, RDF_REIFIES, tt))
            triples.append((stmt, EX_CONF, Literal(str(conf), datatype=XSD.decimal)))
    return triples, pred_bound


def expand_rdf11(triples):
    """Expand TripleTerms to tt:HASH URIRefs + encoding triples for rdf-1.1 storage."""
    plain, encoding = [], []
    seen = set()

    def encode(tt):
        s = encode(tt.subject) if isinstance(tt.subject, TripleTerm) else tt.subject
        o = encode(tt.object)  if isinstance(tt.object,  TripleTerm) else tt.object
        uri = URIRef(TT_NS + tt_hash(str(s), str(tt.predicate), str(o)))
        if uri not in seen:
            seen.add(uri)
            encoding.append((uri, RDF_SUBJECT, s))
            encoding.append((uri, RDF_PRED,    tt.predicate))
            encoding.append((uri, RDF_OBJECT,  o))
        return uri

    for s, p, o in triples:
        plain.append((s, p, encode(o) if isinstance(o, TripleTerm) else o))

    return plain + encoding


def _queries(pred_bound, named_graph):
    """The three benchmark queries. named_graph wraps patterns in GRAPH <uri>
    for Fuseki; Oxigraph and in-memory use the unwrapped default graph."""
    def wrap(body):
        if named_graph:
            return f'GRAPH <{GRAPH_URI}> {{\n        {body}\n    }}'
        return body

    # Pulled out of the f-strings below rather than inlined: a pre-3.12 f-string
    # can't contain a backslash escape (e.g. '\n') inside its {...} expression
    # part (PEP 701 lifted that restriction only in 3.12+), and this repo
    # supports 3.10+.
    confidence_pattern = (
        '?stmt rdf:reifies <<( ?s ?p ?o )>> .\n'
        '        ?stmt ex:confidence ?c .\n'
        '        FILTER(xsd:decimal(?c) > 0.7)'
    )

    return [
        ('All reified TTs  (single TT pattern)',  f"""
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?stmt ?s ?p ?o WHERE {{
    {wrap('?stmt rdf:reifies <<( ?s ?p ?o )>> .')}
}}"""),
        ('Reified + confidence>0.7  (TT + join)', f"""
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ex:  <{EX}>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?stmt ?s ?p ?o WHERE {{
    {wrap(confidence_pattern)}
}}"""),
        ('Partial TT match  (bound predicate)',   f"""
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?stmt ?s ?o WHERE {{
    {wrap(f'?stmt rdf:reifies <<( ?s <{pred_bound}> ?o )>> .')}
}}"""),
    ]


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------

def timeit(fn, repeats=REPEATS):
    times = []
    for _ in range(repeats):
        gc.collect()
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return statistics.median(times)


def fmt_ms(s):
    ms = s * 1000
    return f'{ms/1000:.2f} s' if ms >= 1000 else f'{ms:.1f} ms'


def fmt_tps(n, s):
    return f'{n / s:,.0f} t/s'


def _run_queries(g, pred_bound, named_graph):
    queries = _queries(pred_bound, named_graph)
    col = max(len(q[0]) for q in queries)
    print(f'  Queries (median of {REPEATS}):')
    for label, q in queries:
        t = timeit(lambda q=q: list(g.query(q)))
        result_count = len(list(g.query(q)))
        print(f'    {label:<{col}}  {fmt_ms(t):>10}  ({result_count} rows)')


# ---------------------------------------------------------------------------
# In-memory runner
# ---------------------------------------------------------------------------

def run_inmemory(triples, pred_bound):
    print('\n  --- In-memory ---')
    g = StarLayerGraph()
    t0 = time.perf_counter()
    g.addN((s, p, o, g) for s, p, o in triples)
    load_t = time.perf_counter() - t0
    print(f'  Load : {fmt_ms(load_t)}  ({fmt_tps(len(triples), load_t)})')
    _run_queries(g, pred_bound, named_graph=False)


# ---------------------------------------------------------------------------
# Fuseki runner (rdf-1.1 and rdf-1.2 share the same endpoint/named-graph setup)
# ---------------------------------------------------------------------------

def _fuseki_clear():
    requests.post(
        FUSEKI_UPDATE_URL,
        data=f'CLEAR SILENT GRAPH <{GRAPH_URI}>'.encode(),
        headers={'Content-Type': 'application/sparql-update'},
        auth=FUSEKI_AUTH, timeout=30,
    ).raise_for_status()


def _fuseki_batch_insert(triples):
    buf = []

    def flush():
        body = (
            f'INSERT DATA {{\n  GRAPH <{GRAPH_URI}> {{\n'
            + ''.join(buf)
            + '  }\n}\n'
        )
        requests.post(
            FUSEKI_UPDATE_URL,
            data=body.encode('utf-8'),
            headers={'Content-Type': 'application/sparql-update'},
            auth=FUSEKI_AUTH, timeout=60,
        ).raise_for_status()
        buf.clear()

    for s, p, o in triples:
        buf.append(f'    {sparql_term(s)} {sparql_term(p)} {sparql_term(o)} .\n')
        if len(buf) >= BATCH_SIZE:
            flush()
    if buf:
        flush()


def _fuseki_triple_count():
    resp = requests.post(
        FUSEKI_QUERY_URL,
        data=f'SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{GRAPH_URI}> {{ ?s ?p ?o }} }}'.encode(),
        headers={'Content-Type': 'application/sparql-query',
                 'Accept': 'application/sparql-results+json'},
        auth=FUSEKI_AUTH, timeout=30,
    )
    resp.raise_for_status()
    return int(resp.json()['results']['bindings'][0]['n']['value'])


def run_fuseki(backend, triples, pred_bound):
    print(f'\n  --- {backend} / Fuseki ---')
    load_triples = expand_rdf11(triples) if backend == 'rdf-1.1' else triples
    print(f'  Physical triples to load: {len(load_triples):,}  (batch size: {BATCH_SIZE})', flush=True)

    _fuseki_clear()
    t0 = time.perf_counter()
    _fuseki_batch_insert(load_triples)
    load_t = time.perf_counter() - t0
    stored = _fuseki_triple_count()
    print(f'  Load : {fmt_ms(load_t)}  ({fmt_tps(len(load_triples), load_t)})  [{stored:,} in Fuseki]')

    store = SPARQLUpdateStore(
        query_endpoint=FUSEKI_QUERY_URL,
        update_endpoint=FUSEKI_UPDATE_URL,
        auth=FUSEKI_AUTH,
    )
    g = StarLayerGraph(store=store, identifier=GRAPH_URI, backend=backend)
    # rdf-1.2 passes the query text straight to Fuseki's own engine, which
    # understands GRAPH against its real quad store. rdf-1.1 runs through
    # rdflib's local SPARQL engine, which already scopes to this Graph's
    # identifier — a GRAPH clause in the query text would look for a *nested*
    # named graph inside that single-graph view and always find none.
    _run_queries(g, pred_bound, named_graph=(backend == 'rdf-1.2'))

    _fuseki_clear()


# ---------------------------------------------------------------------------
# Oxigraph runner (native RDF 1.2 storage, unnamed default graph)
# ---------------------------------------------------------------------------

def _oxigraph_clear():
    requests.post(
        OXIGRAPH_UPDATE_URL,
        data=b'DELETE WHERE { ?s ?p ?o }',
        headers={'Content-Type': 'application/sparql-update'},
        timeout=30,
    ).raise_for_status()


def _oxigraph_batch_insert(triples):
    buf = []

    def flush():
        body = 'INSERT DATA {\n' + ''.join(buf) + '}\n'
        requests.post(
            OXIGRAPH_UPDATE_URL,
            data=body.encode('utf-8'),
            headers={'Content-Type': 'application/sparql-update'},
            timeout=60,
        ).raise_for_status()
        buf.clear()

    for s, p, o in triples:
        buf.append(f'  {sparql_term(s)} {sparql_term(p)} {sparql_term(o)} .\n')
        if len(buf) >= BATCH_SIZE:
            flush()
    if buf:
        flush()


def _oxigraph_triple_count():
    resp = requests.post(
        OXIGRAPH_QUERY_URL,
        data=b'SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }',
        headers={'Content-Type': 'application/sparql-query',
                 'Accept': 'application/sparql-results+json'},
        timeout=30,
    )
    resp.raise_for_status()
    return int(resp.json()['results']['bindings'][0]['n']['value'])


def run_oxigraph(triples, pred_bound):
    print('\n  --- rdf-1.2 / Oxigraph ---')
    print(f'  Physical triples to load: {len(triples):,}  (native RDF 1.2 storage)', flush=True)

    _oxigraph_clear()
    t0 = time.perf_counter()
    _oxigraph_batch_insert(triples)
    load_t = time.perf_counter() - t0
    stored = _oxigraph_triple_count()
    print(f'  Load : {fmt_ms(load_t)}  ({fmt_tps(len(triples), load_t)})  [{stored:,} in Oxigraph]')

    store = SPARQLUpdateStore(
        query_endpoint=OXIGRAPH_QUERY_URL,
        update_endpoint=OXIGRAPH_UPDATE_URL,
    )
    g = StarLayerGraph(store=store, identifier=GRAPH_URI, backend='rdf-1.2')
    _run_queries(g, pred_bound, named_graph=False)

    _oxigraph_clear()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _reachable(url, **kwargs):
    try:
        requests.get(url, timeout=2, **kwargs).raise_for_status()
        return True
    except Exception:
        return False


if __name__ == '__main__':
    fuseki_up   = _reachable(FUSEKI_PING_URL)
    oxigraph_up = _reachable(OXIGRAPH_BASE_URL)

    print('StarLayerGraph — scaling benchmark: in-memory / rdf-1.1 & rdf-1.2 Fuseki / rdf-1.2 Oxigraph')
    print(f'Python {sys.version.split()[0]}')
    print(f'Fuseki   : {"available (" + FUSEKI_QUERY_URL + ")" if fuseki_up else "not reachable — skipping"}')
    print(f'Oxigraph : {"available (" + OXIGRAPH_QUERY_URL + ")" if oxigraph_up else "not reachable — skipping"}')

    for n in SCALES:
        n_reif = n // 10
        print(f'\n{"=" * 65}')
        print(f'  N = {n:,} TTs  |  {n_reif:,} reifications  |  {n_reif:,} annotations')
        print(f'{"=" * 65}')
        triples, pred_bound = build_dataset(n)

        run_inmemory(triples, pred_bound)
        if fuseki_up:
            run_fuseki('rdf-1.1', triples, pred_bound)
            run_fuseki('rdf-1.2', triples, pred_bound)
        if oxigraph_up:
            run_oxigraph(triples, pred_bound)

    print('\nDone.')
