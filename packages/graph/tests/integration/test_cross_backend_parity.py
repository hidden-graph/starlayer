"""
tests/integration/test_cross_backend_parity.py

Systematic behavioral parity checks: the same operation, run against the
default in-memory (rdf-1.1) backend and against each live native (rdf-1.2)
backend in turn, must produce the same observable result.

This project's core value proposition is "identical behavior regardless of
backend" (see docs/future_enhancements.md's "Cross-backend behavior parity"
section), but until now that was only verified by a one-off script
(three_way_compare.py) run manually in a scratch directory. It found 3 real
bugs the first time it was run. This module checks in that methodology as a
standing, reusable test rather than something that only runs when someone
remembers to.

Requires a running Fuseki and/or Oxigraph instance - see the docstrings in
test_fuseki_backend.py / test_oxigraph_backend.py for the docker run
commands. Each backend's scenarios skip independently if that backend isn't
reachable, so this still provides value with only one of the two running.

Run:
    .venv/bin/pytest tests/integration/test_cross_backend_parity.py -v
"""

import pytest
import requests

from rdflib import URIRef, Literal
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore

from starlayergraph.graph import StarLayerGraph
from starlayergraph.model.triple import TripleTerm
from starlayergraph.model.dirlangstring import DirLangString

# See test_fuseki_backend.py's identical pytestmark for why this is here.
pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Endpoint config
# ---------------------------------------------------------------------------

FUSEKI_BASE = 'http://localhost:3030/starlayergraph'
FUSEKI_Q    = f'{FUSEKI_BASE}/query'
FUSEKI_U    = f'{FUSEKI_BASE}/update'

OXIGRAPH_BASE = 'http://localhost:7878'
OXIGRAPH_Q    = f'{OXIGRAPH_BASE}/query'
OXIGRAPH_U    = f'{OXIGRAPH_BASE}/update'

GRAPH_URI = URIRef('http://example.org/test-graph')
EX        = 'http://example.org/'
RDF_REIF  = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')


def ex(local: str) -> URIRef:
    return URIRef(EX + local)


# ---------------------------------------------------------------------------
# Availability / skip markers — duplicated from test_fuseki_backend.py /
# test_oxigraph_backend.py rather than cross-imported, matching this
# directory's existing convention of each integration test file being
# self-contained.
# ---------------------------------------------------------------------------

def _fuseki_available() -> bool:
    try:
        return requests.get('http://localhost:3030/$/ping', timeout=2).status_code == 200
    except Exception:
        return False


def _oxigraph_available() -> bool:
    try:
        return requests.get(OXIGRAPH_BASE, timeout=2).status_code == 200
    except Exception:
        return False


fuseki = pytest.mark.skipif(
    not _fuseki_available(),
    reason='Fuseki not running — start with: docker run -d --name fuseki-test -p 3030:3030 '
           'atomgraph/fuseki:latest --update --mem --ping /starlayergraph '
           '(see test_fuseki_backend.py); needs Fuseki 5.5+ for native RDF 1.2 <<( )>> syntax - '
           'not stain/jena-fuseki (only reaches 5.1.0), and not secoresearch/fuseki (tops out at '
           '5.5.0, no longer updated).',
)
oxigraph = pytest.mark.skipif(
    not _oxigraph_available(),
    reason='Oxigraph not running — start with: '
           'docker run -d --name oxigraph-test -p 7878:7878 '
           'ghcr.io/oxigraph/oxigraph serve --location /data --bind 0.0.0.0:7878',
)


def _clear_http(update_url: str, auth=None) -> None:
    requests.post(
        update_url,
        data=f'CLEAR SILENT GRAPH <{GRAPH_URI}>',
        headers={'Content-Type': 'application/sparql-update'},
        auth=auth,
        timeout=10,
    ).raise_for_status()


def _internal_graph() -> StarLayerGraph:
    return StarLayerGraph()


def _fuseki_graph() -> StarLayerGraph:
    _clear_http(FUSEKI_U, auth=('admin', 'admin'))
    store = SPARQLUpdateStore(query_endpoint=FUSEKI_Q, update_endpoint=FUSEKI_U, auth=('admin', 'admin'))
    return StarLayerGraph(store=store, identifier=GRAPH_URI, backend='rdf-1.2')


def _oxigraph_graph() -> StarLayerGraph:
    _clear_http(OXIGRAPH_U)
    store = SPARQLUpdateStore(query_endpoint=OXIGRAPH_Q, update_endpoint=OXIGRAPH_U)
    return StarLayerGraph(store=store, identifier=GRAPH_URI, backend='rdf-1.2')


# ---------------------------------------------------------------------------
# Scenarios — ported directly from the scratchpad three_way_compare.py run
# 2026-07-16. Each takes a StarLayerGraph and returns a plain, comparable
# Python value. Scenarios that need to know whether they're talking to a
# native backend (to scope a query to GRAPH <...> the way the native HTTP
# store requires) check g._is_native.
# ---------------------------------------------------------------------------

def _scenario_plain_triple(g):
    g.add((ex('alice'), ex('knows'), ex('bob')))
    return list(g.triples((ex('alice'), ex('knows'), None)))


def _scenario_triple_term_write_read(g):
    tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
    g.add((ex('stmt1'), RDF_REIF, tt))
    rows = list(g.triples((ex('stmt1'), RDF_REIF, None)))
    return [(s, p, str(o)) for s, p, o in rows]


def _scenario_nested_triple_term(g):
    inner = TripleTerm(ex('bob'), ex('knows'), ex('dave'))
    outer = TripleTerm(ex('alice'), ex('believes'), inner)
    g.add((ex('r'), ex('about'), outer))
    result = list(g.triples((ex('r'), ex('about'), None)))[0][2]
    return str(result)


def _scenario_triple_term_subject_rejected(g):
    tt = TripleTerm(ex('a'), ex('b'), ex('c'))
    try:
        g.add((tt, ex('prop'), ex('val')))
        return 'NO ERROR RAISED'
    except ValueError:
        return 'ValueError raised'


def _scenario_sparql_tt_pattern_match(g):
    tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
    g.add((ex('stmt1'), RDF_REIF, tt))
    where = (f'GRAPH <{GRAPH_URI}> {{ ?stmt rdf:reifies <<( ex:alice ex:knows ex:bob )>> . }}'
              if g._is_native else '?stmt rdf:reifies <<( ex:alice ex:knows ex:bob )>> .')
    q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?stmt WHERE {{ {where} }}
    """
    return sorted(str(r[0]) for r in g.query(q))


def _scenario_triple_constructor_fn(g):
    r = g.query(f'SELECT (TRIPLE(<{EX}a>, <{EX}b>, <{EX}c>) AS ?t) WHERE {{}}')
    row = r.bindings[0]
    return str(row[r.vars[0]])


def _scenario_is_triple_fn(g):
    r = g.query(f'SELECT (isTRIPLE(TRIPLE(<{EX}a>, <{EX}b>, <{EX}c>)) AS ?v) WHERE {{}}')
    return bool(r.bindings[0][r.vars[0]])


def _scenario_dirlangstring_write_read(g):
    d = DirLangString('hello', 'en', 'rtl')
    g.add((ex('s'), ex('p'), d))
    result = list(g.triples((ex('s'), ex('p'), None)))[0][2]
    if isinstance(result, DirLangString):
        return (result.value, result.language, result.direction)
    return repr(result)


def _scenario_dirlang_functions(g):
    r = g.query("""
        SELECT (LANGDIR("hi"@en--rtl) AS ?dir)
               (hasLANGDIR("hi"@en--rtl) AS ?hd)
               (STRLANGDIR("hi", "en", "ltr") AS ?sld)
               (LANG("hi"@en--rtl) AS ?l)
               (hasLANG("hi"@en--rtl) AS ?hl)
        WHERE {}
    """)
    row = r.bindings[0]
    sld = row[r.vars[2]]
    sld_repr = (sld.value, sld.language, sld.direction) if isinstance(sld, DirLangString) else repr(sld)
    return (str(row[r.vars[0]]), bool(row[r.vars[1]]), sld_repr, str(row[r.vars[3]]), bool(row[r.vars[4]]))


def _scenario_strlangdir_invalid_direction(g):
    try:
        g.query('SELECT (STRLANGDIR("x", "en", "sideways") AS ?v) WHERE {}')
        return 'NO ERROR RAISED'
    except Exception as e:
        return f'{type(e).__name__} raised'


def _scenario_construct_round_trip(g):
    tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
    g.add((ex('stmt1'), RDF_REIF, tt))
    g.add((ex('s'), ex('p'), DirLangString('hola', 'es', 'ltr')))
    where = f'GRAPH <{GRAPH_URI}> {{ ?s ?p ?o }}' if g._is_native else '?s ?p ?o'
    r = g.query(f'CONSTRUCT {{ ?s ?p ?o }} WHERE {{ {where} }}')
    return sorted((str(s), str(p), str(o)) for s, p, o in r.graph.triples((None, None, None)))


def _scenario_reifier_annotation_formal_pattern(g):
    tt = TripleTerm(ex('bob'), ex('knows'), ex('carol'))
    g.add((ex('stmt1'), RDF_REIF, tt))
    g.add((ex('stmt1'), ex('confidence'), Literal('0.9')))
    where = (f'GRAPH <{GRAPH_URI}> {{ ?r rdf:reifies <<( ex:bob ex:knows ex:carol )>> . ?r ?p ?o . }}'
              if g._is_native else '?r rdf:reifies <<( ex:bob ex:knows ex:carol )>> . ?r ?p ?o .')
    q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?p ?o WHERE {{ {where} }}
    """
    return sorted((str(r[0]), str(r[1])) for r in g.query(q))


# isTripleTerm() (starlayergraph's own pre-spec-stabilization alias for isTRIPLE())
# is deliberately excluded here: it's not SPARQL syntax at all, only a name
# _IS_TT_RE rewrites away before rdflib's real parser ever sees it (rdf-1.1
# in-memory backend only). The native rdf-1.2 backend sends queries straight
# through with zero rewriting by design (starlayergraph/backends/native.py), so a
# real SPARQL 1.2 engine correctly 400s on it as a parse error - confirmed
# live against both Fuseki 5.5.0 and Oxigraph 0.5.9 while building this test.
# That's not a parity bug to fix; isTRIPLE() (the real spec name, tested
# below) already covers the same functionality and does match everywhere.
SCENARIOS = [
    ('plain triple write/read', _scenario_plain_triple),
    ('triple term write/read', _scenario_triple_term_write_read),
    ('nested triple term', _scenario_nested_triple_term),
    ('triple term as subject rejected', _scenario_triple_term_subject_rejected),
    ('<<( )>> pattern match', _scenario_sparql_tt_pattern_match),
    ('TRIPLE() constructor', _scenario_triple_constructor_fn),
    ('isTRIPLE()', _scenario_is_triple_fn),
    ('DirLangString write/read', _scenario_dirlangstring_write_read),
    ('LANGDIR/hasLANGDIR/STRLANGDIR/LANG/hasLANG', _scenario_dirlang_functions),
    ('STRLANGDIR invalid direction', _scenario_strlangdir_invalid_direction),
    ('CONSTRUCT round trip', _scenario_construct_round_trip),
    ('reifier annotation formal pattern', _scenario_reifier_annotation_formal_pattern),
]


# ---------------------------------------------------------------------------
# Parametrized parity tests — each scenario compared against the in-memory
# backend independently per native backend, so a partial environment (only
# one of Fuseki/Oxigraph running) still exercises everything it can.
# ---------------------------------------------------------------------------

@fuseki
@pytest.mark.parametrize('name,fn', SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_fuseki_matches_internal(name, fn):
    internal_result = fn(_internal_graph())
    fuseki_result = fn(_fuseki_graph())
    assert fuseki_result == internal_result, (
        f'{name}: fuseki={fuseki_result!r} != internal={internal_result!r}'
    )


@oxigraph
@pytest.mark.parametrize('name,fn', SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_oxigraph_matches_internal(name, fn):
    internal_result = fn(_internal_graph())
    oxigraph_result = fn(_oxigraph_graph())
    assert oxigraph_result == internal_result, (
        f'{name}: oxigraph={oxigraph_result!r} != internal={internal_result!r}'
    )


# ---------------------------------------------------------------------------
# Numeric SPARQL-builtin lexical-form parity — found 2026-08-01 while
# investigating a downstream consumer's confirmed rdflib bugs (see
# starlayergraph/query/operator_patches.py: CEIL/FLOOR/ROUND/division whole-number
# decimal results lost the canonical XSD decimal lexical form, e.g.
# CEIL(3.2) -> "4" instead of "4.0"; that module now patches rdflib's own
# Python SPARQL evaluator to fix it). Deliberately NOT folded into the
# shared SCENARIOS table above: parity does *not* hold uniformly across both
# native backends for this family without the fix below, so adding it there
# would either mask a real divergence or force a misleading blanket xfail on
# a backend that's actually fine.
#
# Ground truth checked against the actual downstream consumer's W3C SHACL
# 1.2 test suite fixtures (they expect e.g. `84 / 2` -> "42.0"^^xsd:decimal
# - XSD decimal's canonical form requires a decimal point with at least one
# digit each side), confirmed empirically against three independent
# engines:
#   - Internal (patched rdflib):     "42.0" / "4.0" - matches the fixtures
#   - Fuseki (Apache Jena ARQ 5.5+): "42.0" / "4.0" - matches fixtures AND internal
#   - Oxigraph (native, 0.5.x):      "42"   / "4"   - matched neither, on its own
# Two independent, mature engines (patched rdflib, Jena/ARQ) agree with each
# other and with the actual downstream test suite; only Oxigraph's own
# SPARQL engine computes a non-canonical lexical form. Fixed 2026-08-05, not
# on the Oxigraph side (out of this project's control) but client-side:
# starlayergraph/backends/native.py::_parse_json_term now re-canonicalizes any
# xsd:decimal literal coming back from a native backend's query results
# (reusing operator_patches.py's own _canonicalize_decimal_lexical_form
# helper - a no-op for any lexical form that already has a "."), so this now
# passes for real rather than needing an xfail.

def _scenario_ceil_whole_number_decimal(g):
    r = g.query('SELECT (CEIL(3.2) AS ?r) WHERE {}')
    row = r.bindings[0]
    val = row[r.vars[0]]
    return (str(val), str(val.datatype))


def _scenario_division_whole_number_decimal(g):
    r = g.query('SELECT (84 / 2 AS ?r) WHERE {}')
    row = r.bindings[0]
    val = row[r.vars[0]]
    return (str(val), str(val.datatype))


NUMERIC_LEXICAL_FORM_SCENARIOS = [
    ('CEIL whole-number decimal lexical form', _scenario_ceil_whole_number_decimal),
    ('division whole-number decimal lexical form', _scenario_division_whole_number_decimal),
]


@fuseki
@pytest.mark.parametrize(
    'name,fn', NUMERIC_LEXICAL_FORM_SCENARIOS, ids=[s[0] for s in NUMERIC_LEXICAL_FORM_SCENARIOS]
)
def test_fuseki_matches_internal_for_numeric_lexical_form(name, fn):
    internal_result = fn(_internal_graph())
    fuseki_result = fn(_fuseki_graph())
    assert fuseki_result == internal_result, (
        f'{name}: fuseki={fuseki_result!r} != internal={internal_result!r}'
    )


@oxigraph
@pytest.mark.parametrize(
    'name,fn', NUMERIC_LEXICAL_FORM_SCENARIOS, ids=[s[0] for s in NUMERIC_LEXICAL_FORM_SCENARIOS]
)
def test_oxigraph_matches_internal_for_numeric_lexical_form(name, fn):
    internal_result = fn(_internal_graph())
    oxigraph_result = fn(_oxigraph_graph())
    assert oxigraph_result == internal_result, (
        f'{name}: oxigraph={oxigraph_result!r} != internal={internal_result!r}'
    )
