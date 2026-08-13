"""
tests/integration/test_sqlalchemy_backend.py

Integration tests for StarLayerGraph backed by a real on-disk SQLite
database via rdflib-sqlalchemy (backend='rdf-1.1' - rdflib-sqlalchemy has
no RDF 1.2 native mode, so only the encoding-based backend applies here).

Ports examples/sqlalchemy_store_demo.py's scenario into permanent pytest
coverage, plus regression coverage for the custom SPARQL functions
(TRIPLE()/isTRIPLE()/SUBJECT()/PREDICATE()/OBJECT()/STRLANGDIR()) confirmed
this session to already work correctly against this store: unlike a genuinely
remote SPARQLStore/SPARQLUpdateStore endpoint (Fuseki-as-1.1), the SQLAlchemy
store accepts a pre-parsed rdflib Query object
(starlayergraph.query.query_cache.store_accepts_prepared_query returns True for
it), so queries are evaluated locally, in-process, where starlayergraph's custom
function registrations are visible - no decomposition needed. These tests
exist to keep that fact pinned down, not to fix a bug.

Requires the `sqlalchemy` extra: pip install -e ".[sqlalchemy]"

Run:
    .venv/bin/pytest tests/integration/test_sqlalchemy_backend.py -v
"""

import os
import tempfile

import pytest

from rdflib import URIRef, Literal
from rdflib.namespace import XSD

from starlayergraph.graph import StarLayerGraph
from starlayergraph.model.triple import TripleTerm
from starlayergraph.model.dirlangstring import DirLangString

# Applies the "integration" marker (declared in pyproject.toml) to every test
# in this module, so `pytest -m "not integration"` (used by CI) excludes them.
pytestmark = pytest.mark.integration

try:
    import rdflib_sqlalchemy
    rdflib_sqlalchemy.registerplugins()
    _SQLALCHEMY_AVAILABLE = True
except ImportError:
    _SQLALCHEMY_AVAILABLE = False

sqlalchemy_extra = pytest.mark.skipif(
    not _SQLALCHEMY_AVAILABLE,
    reason='rdflib-sqlalchemy not installed — install with: pip install -e ".[sqlalchemy]"',
)

EX       = 'http://example.org/'
RDF_NS   = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
RDF_REIF = URIRef(RDF_NS + 'reifies')
EX_CONF  = URIRef(EX + 'confidence')
GRAPH_URI = URIRef(EX + 'main')


@pytest.fixture
def db_path():
    path = tempfile.mktemp(suffix='.db')
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def sg(db_path):
    """Fresh StarLayerGraph backed by a new SQLite database (rdf-1.1 mode)."""
    g = StarLayerGraph(store='SQLAlchemy', identifier=GRAPH_URI)
    g.open(f'sqlite:///{db_path}', create=True)
    g.bind('ex', EX)
    yield g
    g.close()


def _reopen(db_path) -> StarLayerGraph:
    """A fresh StarLayerGraph instance opened against an existing database -
    exercises _build_registry_from_store() the way a real second process
    reconnecting to persisted data would, rather than reusing the same
    in-process graph/registry that wrote the data."""
    g = StarLayerGraph(store='SQLAlchemy', identifier=GRAPH_URI)
    g.open(f'sqlite:///{db_path}', create=False)
    g.bind('ex', EX)
    return g


# ---------------------------------------------------------------------------
# Round-trip through a real SQLite file
# ---------------------------------------------------------------------------

@sqlalchemy_extra
class TestSQLAlchemyRoundTrip:

    def test_plain_triple_write_read(self, sg):
        s, p, o = URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob')
        sg.add((s, p, o))
        assert (s, p, o) in sg

    def test_triple_term_survives_reconnect(self, sg, db_path):
        tt = TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
        stmt = URIRef(EX+'stmt1')
        sg.add((stmt, RDF_REIF, tt))
        sg.close()

        reloaded = _reopen(db_path)
        try:
            results = list(reloaded.triples((stmt, RDF_REIF, None)))
            assert len(results) == 1
            _, _, restored = results[0]
            assert isinstance(restored, TripleTerm)
            assert restored == tt
        finally:
            reloaded.close()

    def test_triple_term_encoding_hidden(self, sg):
        tt = TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))
        sg.add((URIRef(EX+'stmt'), RDF_REIF, tt))
        visible = list(sg.triples((None, None, None)))
        predicates = {p for _, p, _ in visible}
        assert URIRef(RDF_NS + 'subject')   not in predicates
        assert URIRef(RDF_NS + 'predicate') not in predicates
        assert URIRef(RDF_NS + 'object')    not in predicates

    def test_multiple_triple_terms_survive_reconnect(self, sg, db_path):
        tts = [
            TripleTerm(URIRef(EX+f'a{i}'), URIRef(EX+'rel'), URIRef(EX+f'b{i}'))
            for i in range(5)
        ]
        for i, tt in enumerate(tts):
            sg.add((URIRef(EX+f'stmt{i}'), RDF_REIF, tt))
        sg.close()

        reloaded = _reopen(db_path)
        try:
            assert len(list(reloaded.triple_terms())) == 5
        finally:
            reloaded.close()


# ---------------------------------------------------------------------------
# SPARQL 1.2 queries against SQLite (examples/sqlalchemy_store_demo.py's
# original scenario)
# ---------------------------------------------------------------------------

@sqlalchemy_extra
class TestSQLAlchemySPARQL:

    def _load(self, sg):
        sg.add((URIRef(EX+'stmt1'), RDF_REIF,
                TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))))
        sg.add((URIRef(EX+'stmt1'), EX_CONF, Literal('0.9', datatype=XSD.decimal)))
        sg.add((URIRef(EX+'stmt2'), RDF_REIF,
                TripleTerm(URIRef(EX+'bob'), URIRef(EX+'likes'), URIRef(EX+'carol'))))
        sg.add((URIRef(EX+'stmt2'), EX_CONF, Literal('0.4', datatype=XSD.decimal)))

    def test_triple_term_pattern_query_survives_reconnect(self, sg, db_path):
        self._load(sg)
        sg.close()

        reloaded = _reopen(db_path)
        try:
            q = f"""
            PREFIX ex: <{EX}>
            PREFIX rdf: <{RDF_NS}>
            SELECT ?stmt ?tt ?conf WHERE {{
                ?stmt rdf:reifies ?tt .
                OPTIONAL {{ ?stmt ex:confidence ?conf }}
            }}
            ORDER BY ?stmt
            """
            rows = list(reloaded.query(q))
            assert len(rows) == 2

            stmt1_row = next(r for r in rows if r.stmt == URIRef(EX+'stmt1'))
            assert isinstance(stmt1_row.tt, TripleTerm)
            assert stmt1_row.tt == TripleTerm(
                URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
            assert str(stmt1_row.conf) == '0.9'
        finally:
            reloaded.close()


# ---------------------------------------------------------------------------
# Custom SPARQL 1.2 functions - TRIPLE()/isTRIPLE()/accessors/STRLANGDIR()
# against SQLite. Confirmed (2026-08-11) to already work: SQLAlchemy is not
# a string-only store (store_accepts_prepared_query() is True for it), so
# these run through the ordinary local-evaluation path, not the remote
# decomposition mechanism starlayergraph.query.remote_decompose implements for a
# genuinely remote SPARQLStore/SPARQLUpdateStore.
# ---------------------------------------------------------------------------

@sqlalchemy_extra
class TestSQLAlchemySparqlFunctions:

    def test_triple_constructor_function(self, sg):
        r = sg.query(f"""
            SELECT (TRIPLE(<{EX}a>, <{EX}b>, <{EX}c>) AS ?t) WHERE {{}}
        """)
        assert r.bindings[0][r.vars[0]] == TripleTerm(
            URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))

    def test_is_triple_spec_name(self, sg):
        r = sg.query(f"""
            SELECT (isTRIPLE(TRIPLE(<{EX}a>, <{EX}b>, <{EX}c>)) AS ?v) WHERE {{}}
        """)
        assert r.bindings[0][r.vars[0]] == Literal(True)

    def test_subject_predicate_object_accessors(self, sg):
        sg.add((URIRef(EX+'stmt'), RDF_REIF,
                TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))))
        r = sg.query(f"""
            PREFIX rdf: <{RDF_NS}>
            SELECT (SUBJECT(?tt) AS ?s) (PREDICATE(?tt) AS ?p) (OBJECT(?tt) AS ?o)
            WHERE {{ ?stmt rdf:reifies ?tt }}
        """)
        row = r.bindings[0]
        assert row[r.vars[0]] == URIRef(EX+'a')
        assert row[r.vars[1]] == URIRef(EX+'b')
        assert row[r.vars[2]] == URIRef(EX+'c')

    def test_dirlangstring_write_read(self, sg):
        d = DirLangString('hello', 'en', 'rtl')
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), d))
        results = list(sg.triples((URIRef(EX+'s'), URIRef(EX+'p'), None)))
        assert results == [(URIRef(EX+'s'), URIRef(EX+'p'), d)]

    def test_strlangdir(self, sg):
        r = sg.query("""
            SELECT (STRLANGDIR("hi", "en", "ltr") AS ?sld) WHERE {}
        """)
        assert r.bindings[0][r.vars[0]] == DirLangString('hi', 'en', 'ltr')
