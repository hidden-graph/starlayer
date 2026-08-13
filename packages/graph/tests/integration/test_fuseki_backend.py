"""
tests/integration/test_fuseki_backend.py

Integration tests for StarLayerGraph backed by Apache Jena Fuseki via
rdflib's SPARQLUpdateStore.

Requires a running Fuseki instance, with the dataset created at startup
(test against the latest release - secoresearch/fuseki tops out at 5.5.0
and is no longer updated; atomgraph/fuseki tracks current Jena releases):
    docker run -d --name fuseki-test -p 3030:3030 atomgraph/fuseki:latest \\
        --update --mem --ping /starlayergraph

Run:
    .venv/bin/pytest tests/integration/ -v
"""

import pytest
import requests

from rdflib import URIRef, Literal
from rdflib.namespace import XSD
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore

from starlayergraph.graph import StarLayerGraph, StarLayerDataset
from starlayergraph.model.triple import TripleTerm

# Applies the "integration" marker (declared in pyproject.toml) to every test
# in this module, so `pytest -m "not integration"` (used by CI) actually
# excludes them rather than relying solely on the skipif fixtures below.
pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Endpoint config
# ---------------------------------------------------------------------------

FUSEKI_BASE   = 'http://localhost:3030/starlayergraph'
QUERY_URL     = f'{FUSEKI_BASE}/query'
UPDATE_URL    = f'{FUSEKI_BASE}/update'
GRAPH_URI     = URIRef('http://example.org/test-graph')

EX        = 'http://example.org/'
RDF_NS    = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
RDF_REIF  = URIRef(RDF_NS + 'reifies')
EX_CONF   = URIRef(EX + 'confidence')


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _fuseki_available() -> bool:
    try:
        r = requests.get('http://localhost:3030/$/ping', timeout=2)
        return r.status_code == 200
    except Exception:
        return False


fuseki = pytest.mark.skipif(
    not _fuseki_available(),
    reason='Fuseki not running — start with: docker run -d --name fuseki-test -p 3030:3030 '
           'atomgraph/fuseki:latest --update --mem --ping /starlayergraph '
           '(needs Fuseki 5.5+ for the native RDF 1.2 tests below; stain/jena-fuseki only reaches 5.1.0, '
           'secoresearch/fuseki tops out at 5.5.0 and is no longer updated)',
)


def _make_store() -> SPARQLUpdateStore:
    store = SPARQLUpdateStore(
        query_endpoint=QUERY_URL,
        update_endpoint=UPDATE_URL,
        auth=('admin', 'admin'),
    )
    return store


def _clear_graph():
    """Delete all triples from the test graph between tests."""
    requests.post(
        UPDATE_URL,
        data=f'CLEAR SILENT GRAPH <{GRAPH_URI}>',
        headers={'Content-Type': 'application/sparql-update'},
        auth=('admin', 'admin'),
        timeout=10,
    ).raise_for_status()


@pytest.fixture
def sg():
    """Fresh StarLayerGraph backed by Fuseki, cleared before each test (rdf-1.1 mode)."""
    _clear_graph()
    g = StarLayerGraph(store=_make_store(), identifier=GRAPH_URI)
    g.bind('ex', EX)
    yield g


@pytest.fixture
def sg_rdf12():
    """Fresh StarLayerGraph backed by Fuseki in rdf-1.2 native mode.

    Fuseki 5.5.0 (verified 2026-07-16) speaks the final <<( s p o )>> syntax
    and returns "type":"triple" in SPARQL JSON results - the milestone
    docs/future_enhancements.md's "Fuseki RDF 1.2 Native Syntax" note was
    waiting for. No starlayergraph code changes were needed; only the backend flag.
    """
    _clear_graph()
    g = StarLayerGraph(store=_make_store(), identifier=GRAPH_URI, backend='rdf-1.2')
    g.bind('ex', EX)
    yield g


# ---------------------------------------------------------------------------
# Basic round-trip
# ---------------------------------------------------------------------------

@fuseki
class TestFusekiRoundTrip:

    def test_plain_triple_write_read(self, sg):
        s, p, o = URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob')
        sg.add((s, p, o))
        assert (s, p, o) in sg

    def test_triple_term_write_read(self, sg):
        tt  = TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
        stmt = URIRef(EX+'stmt1')
        sg.add((stmt, RDF_REIF, tt))
        sg._build_registry_from_store()   # reload registry as if fresh connection

        results = list(sg.triples((stmt, RDF_REIF, None)))
        assert len(results) == 1
        _, _, restored = results[0]
        assert isinstance(restored, TripleTerm)
        assert restored == tt

    def test_triple_term_encoding_hidden(self, sg):
        """Encoding triples (rdf:subject/predicate/object) are not surfaced."""
        tt = TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))
        sg.add((URIRef(EX+'stmt'), RDF_REIF, tt))
        visible = list(sg.triples((None, None, None)))
        predicates = {p for _, p, _ in visible}
        assert URIRef(RDF_NS + 'subject')   not in predicates
        assert URIRef(RDF_NS + 'predicate') not in predicates
        assert URIRef(RDF_NS + 'object')    not in predicates

    def test_multiple_triple_terms(self, sg):
        tts = [
            TripleTerm(URIRef(EX+f'a{i}'), URIRef(EX+'rel'), URIRef(EX+f'b{i}'))
            for i in range(5)
        ]
        for i, tt in enumerate(tts):
            sg.add((URIRef(EX+f'stmt{i}'), RDF_REIF, tt))
        sg._build_registry_from_store()
        assert len(list(sg.triple_terms())) == 5



# ---------------------------------------------------------------------------
# SPARQL 1.2 queries via Fuseki
# ---------------------------------------------------------------------------

@fuseki
class TestFusekiSPARQL:

    def _load(self, sg):
        sg.add((URIRef(EX+'stmt1'), RDF_REIF,
                TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))))
        sg.add((URIRef(EX+'stmt1'), EX_CONF,
                Literal('0.9', datatype=XSD.decimal)))
        sg.add((URIRef(EX+'stmt2'), RDF_REIF,
                TripleTerm(URIRef(EX+'bob'), URIRef(EX+'likes'), URIRef(EX+'carol'))))
        sg.add((URIRef(EX+'stmt2'), EX_CONF,
                Literal('0.4', datatype=XSD.decimal)))
        sg._build_registry_from_store()

    def test_select_reified_triples(self, sg):
        self._load(sg)
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <{RDF_NS}>
        SELECT ?stmt ?tt WHERE {{
            ?stmt rdf:reifies ?tt .
        }}
        """
        rows = list(sg.query(q))
        assert len(rows) == 2
        stmts = {r[0] for r in rows}
        assert URIRef(EX+'stmt1') in stmts
        assert URIRef(EX+'stmt2') in stmts

    def test_triple_term_restored_in_results(self, sg):
        self._load(sg)
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <{RDF_NS}>
        SELECT ?tt WHERE {{
            <{EX}stmt1> rdf:reifies ?tt .
        }}
        """
        rows = list(sg.query(q))
        assert len(rows) == 1
        assert isinstance(rows[0][0], TripleTerm)
        assert rows[0][0] == TripleTerm(
            URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob')
        )

    def test_sparql12_triple_term_pattern(self, sg):
        """SPARQL 1.2 <<( )>> pattern is rewritten and executed via Fuseki."""
        self._load(sg)
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <{RDF_NS}>
        SELECT ?stmt ?s ?o WHERE {{
            ?stmt rdf:reifies <<( ?s ex:knows ?o )>> .
        }}
        """
        rows = list(sg.query(q))
        assert len(rows) == 1
        assert rows[0][1] == URIRef(EX+'alice')
        assert rows[0][2] == URIRef(EX+'bob')

    def test_filter_by_confidence(self, sg):
        """Combined triple-term pattern + FILTER sent to Fuseki."""
        self._load(sg)
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <{RDF_NS}>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        SELECT ?stmt WHERE {{
            ?stmt rdf:reifies <<( ?s ?p ?o )>> .
            ?stmt ex:confidence ?conf .
            FILTER(xsd:decimal(?conf) > 0.5)
        }}
        """
        rows = list(sg.query(q))
        assert len(rows) == 1
        assert rows[0][0] == URIRef(EX+'stmt1')


# ---------------------------------------------------------------------------
# Bulk write via addN
# ---------------------------------------------------------------------------

@fuseki
class TestFusekiBulkWrite:

    def test_addN_writes_all_triples(self, sg):
        n = 20
        triples = [
            (URIRef(EX+f'stmt{i}'), RDF_REIF,
             TripleTerm(URIRef(EX+f'a{i}'), URIRef(EX+'rel'), URIRef(EX+f'b{i}')))
            for i in range(n)
        ]
        sg.addN((s, p, o, sg) for s, p, o in triples)
        sg._build_registry_from_store()
        assert len(list(sg.triple_terms())) == n

    def test_addN_triple_terms_restorable(self, sg):
        tt = TripleTerm(URIRef(EX+'x'), URIRef(EX+'y'), URIRef(EX+'z'))
        sg.addN([(URIRef(EX+'stmt'), RDF_REIF, tt, sg)])
        sg._build_registry_from_store()
        results = list(sg.triples((URIRef(EX+'stmt'), RDF_REIF, None)))
        assert len(results) == 1
        assert isinstance(results[0][2], TripleTerm)
        assert results[0][2] == tt


# ---------------------------------------------------------------------------
# Native rdf-1.2 backend (final <<( s p o )>> syntax) - Fuseki 5.5.0+
# ---------------------------------------------------------------------------

@fuseki
class TestFusekiNativeRdf12:
    """Confirmed 2026-07-16: Fuseki 5.5.0 speaks the final RDF 1.2 <<( )>>
    syntax and returns "type":"triple" correctly - this is the thing
    docs/future_enhancements.md's "Fuseki RDF 1.2 Native Syntax" note said to
    verify once available. It's available now, and it just works.

    (The older Jena draft << s p o >> bracket syntax, `backend='rdf-star'`,
    was removed after this testing found it broken against current Fuseki -
    see docs/future_enhancements.md.)
    """

    def test_triple_term_write_read(self, sg_rdf12):
        tt   = TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
        stmt = URIRef(EX+'stmt1')
        sg_rdf12.add((stmt, RDF_REIF, tt))
        results = list(sg_rdf12.triples((stmt, RDF_REIF, None)))
        assert len(results) == 1
        _, _, restored = results[0]
        assert isinstance(restored, TripleTerm)
        assert restored == tt

    def test_query_triple_term_pattern(self, sg_rdf12):
        tt = TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
        sg_rdf12.add((URIRef(EX+'stmt1'), RDF_REIF, tt))
        q = f"""
        PREFIX rdf: <{RDF_NS}>
        SELECT ?tt WHERE {{
            GRAPH <{GRAPH_URI}> {{
                <{EX}stmt1> rdf:reifies ?tt .
            }}
        }}
        """
        rows = list(sg_rdf12.query(q))
        assert len(rows) == 1
        assert isinstance(rows[0][0], TripleTerm)
        assert rows[0][0] == tt

    def test_construct_round_trip(self, sg_rdf12):
        tt = TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
        sg_rdf12.add((URIRef(EX+'stmt1'), RDF_REIF, tt))
        r = sg_rdf12.query(f'CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH <{GRAPH_URI}> {{ ?s ?p ?o }} }}')
        assert (URIRef(EX+'stmt1'), RDF_REIF, tt) in r.graph


@fuseki
class TestFusekiDatasetUpdate:
    """StarLayerDataset.update() against a remote store 400'd on any update
    text containing its own GRAPH <uri> {} clause, for *both* backends -
    rdflib's Dataset(store=...).update() always wraps the whole update in an
    extra GRAPH <urn:x-rdflib:default> {} block regardless, nesting illegally
    around one already present. Confirmed here (not just against Oxigraph)
    with a plain INSERT DATA containing no triple terms at all, on both
    rdf-1.1 and rdf-1.2. See TestOxigraphDatasetUpdate for the fuller
    rationale.
    """

    def _dataset(self, backend):
        _clear_graph()
        return StarLayerDataset(store=_make_store(), backend=backend)

    @pytest.mark.parametrize('backend', ['rdf-1.1', 'rdf-1.2'])
    def test_insert_data_with_graph_clause(self, backend):
        ds = self._dataset(backend)
        ds.update(f'INSERT DATA {{ GRAPH <{GRAPH_URI}> {{ <{EX}a> <{EX}b> <{EX}c> . }} }}')
        g1 = ds.get_context(GRAPH_URI)
        assert (URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')) in g1

    @pytest.mark.parametrize('backend', ['rdf-1.1', 'rdf-1.2'])
    def test_insert_where_with_graph_clause(self, backend):
        ds = self._dataset(backend)
        g1 = ds.get_context(GRAPH_URI)
        g1.add((URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')))
        ds.update(f"""
            INSERT {{ GRAPH <{GRAPH_URI}> {{ ?s <{EX}marked> ?o }} }}
            WHERE {{ GRAPH <{GRAPH_URI}> {{ ?s <{EX}b> ?o }} }}
        """)
        assert (URIRef(EX+'a'), URIRef(EX+'marked'), URIRef(EX+'c')) in g1


# ---------------------------------------------------------------------------
# TRIPLE()/isTRIPLE() and the RDF 1.2 base-direction SPARQL functions,
# passed through unchanged to Fuseki for the rdf-1.2 backend - confirmed
# 2026-07-16 all natively supported by Fuseki 5.5.0.
# ---------------------------------------------------------------------------

@fuseki
class TestFusekiRdf12SparqlFunctions:

    def test_triple_constructor_function(self, sg_rdf12):
        r = sg_rdf12.query(f"""
            SELECT (TRIPLE(<{EX}a>, <{EX}b>, <{EX}c>) AS ?t) WHERE {{}}
        """)
        assert r.bindings[0][r.vars[0]] == TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))

    def test_is_triple_spec_name(self, sg_rdf12):
        r = sg_rdf12.query(f"""
            SELECT (isTRIPLE(TRIPLE(<{EX}a>, <{EX}b>, <{EX}c>)) AS ?v) WHERE {{}}
        """)
        assert r.bindings[0][r.vars[0]] == Literal(True)

    def test_dirlangstring_write_read(self, sg_rdf12):
        from starlayergraph.model.dirlangstring import DirLangString
        d = DirLangString('hello', 'en', 'rtl')
        sg_rdf12.add((URIRef(EX+'s'), URIRef(EX+'p'), d))
        results = list(sg_rdf12.triples((URIRef(EX+'s'), URIRef(EX+'p'), None)))
        assert results == [(URIRef(EX+'s'), URIRef(EX+'p'), d)]

    def test_langdir_hasLangdir_strlangdir(self, sg_rdf12):
        r = sg_rdf12.query("""
            SELECT (LANGDIR("hi"@en--rtl) AS ?dir)
                   (hasLANGDIR("hi"@en--rtl) AS ?hd)
                   (STRLANGDIR("hi", "en", "ltr") AS ?sld)
                   (LANG("hi"@en--rtl) AS ?l)
                   (hasLANG("hi"@en--rtl) AS ?hl)
            WHERE {}
        """)
        from starlayergraph.model.dirlangstring import DirLangString
        row = r.bindings[0]
        assert row[r.vars[0]] == Literal('rtl')
        assert row[r.vars[1]] == Literal(True)
        assert row[r.vars[2]] == DirLangString('hi', 'en', 'ltr')
        assert row[r.vars[3]] == Literal('en')
        assert row[r.vars[4]] == Literal(True)


# ---------------------------------------------------------------------------
# Same four functions, but through the rdf-1.1 (default) backend against a
# real remote store - a genuinely different code path from
# TestFusekiRdf12SparqlFunctions above: rdf-1.2 mode sends the query text
# straight through unmodified (Fuseki understands it natively), while
# rdf-1.1 mode routes it through starlayergraph's own SPARQL 1.2->1.1 text
# rewriter (sparql12_to_11.py) first, then sends *that* rewritten text to
# Fuseki. That rewritten text - and its interaction with a real remote
# store specifically, not just the in-memory backend the unit suite already
# covers this against - had no live coverage at all before this: every
# TRIPLE()/isTRIPLE()/DirLangString/LANGDIR test in this file used
# sg_rdf12, never the plain sg fixture "full testing" (SQLite/Fuseki/
# Oxigraph plumbing, as opposed to purpose-2 cross-engine parity - see the
# project's own testing-strategy notes) is meant to close this kind of gap.
# ---------------------------------------------------------------------------

@fuseki
class TestFusekiRdf11SparqlFunctions:

    def test_triple_constructor_function(self, sg):
        r = sg.query(f"""
            SELECT (TRIPLE(<{EX}a>, <{EX}b>, <{EX}c>) AS ?t) WHERE {{}}
        """)
        assert r.bindings[0][r.vars[0]] == TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))

    def test_is_triple_spec_name(self, sg):
        r = sg.query(f"""
            SELECT (isTRIPLE(TRIPLE(<{EX}a>, <{EX}b>, <{EX}c>)) AS ?v) WHERE {{}}
        """)
        assert r.bindings[0][r.vars[0]] == Literal(True)

    def test_dirlangstring_write_read(self, sg):
        from starlayergraph.model.dirlangstring import DirLangString
        d = DirLangString('hello', 'en', 'rtl')
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), d))
        results = list(sg.triples((URIRef(EX+'s'), URIRef(EX+'p'), None)))
        assert results == [(URIRef(EX+'s'), URIRef(EX+'p'), d)]

    def test_dirlangstring_sparql_literal(self, sg):
        """A dirLangString literal written directly in query text (BIND),
        not via .add() - the rewriter has to correctly encode/decode it,
        and the value has to survive the round trip through a real remote
        rdf-1.1 store, not just local Python memory."""
        from starlayergraph.model.dirlangstring import DirLangString
        r = sg.query('SELECT (?x AS ?greeting) WHERE { BIND("hi"@en--ltr AS ?x) }')
        assert r.bindings[0][r.vars[0]] == DirLangString('hi', 'en', 'ltr')

    def test_langdir_hasLangdir_strlangdir(self, sg):
        r = sg.query("""
            SELECT (LANGDIR("hi"@en--rtl) AS ?dir)
                   (hasLANGDIR("hi"@en--rtl) AS ?hd)
                   (STRLANGDIR("hi", "en", "ltr") AS ?sld)
                   (LANG("hi"@en--rtl) AS ?l)
                   (hasLANG("hi"@en--rtl) AS ?hl)
            WHERE {}
        """)
        from starlayergraph.model.dirlangstring import DirLangString
        row = r.bindings[0]
        assert row[r.vars[0]] == Literal('rtl')
        assert row[r.vars[1]] == Literal(True)
        assert row[r.vars[2]] == DirLangString('hi', 'en', 'ltr')
        assert row[r.vars[3]] == Literal('en')
        assert row[r.vars[4]] == Literal(True)


# ---------------------------------------------------------------------------
# Coverage not already exercised by TestFusekiRdf11SparqlFunctions above:
# pattern-matching a stored triple term (not just constructing one) and the
# isTRIPLE+SUBJECT() combination, plus the generalized remote-store
# dispatch's own restrictions (starlayergraph.query.remote_decompose.
# decompose_for_remote is SELECT-only, so a CONSTRUCT template minting a
# fresh triple term must fail loudly against a remote store rather than
# silently dropping the triple).
# ---------------------------------------------------------------------------

@fuseki
class TestFusekiRemoteStoreSparqlCoverage:

    def test_triple_term_pattern_match(self, sg):
        tt = TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))
        sg.add((URIRef(EX+'stmt'), RDF_REIF, tt))
        r = sg.query(f"""
            PREFIX rdf: <{RDF_NS}>
            SELECT ?tt WHERE {{ ?stmt rdf:reifies ?tt }}
        """)
        assert r.bindings[0][r.vars[0]] == tt

    def test_is_triple_and_subject_accessor(self, sg):
        tt = TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))
        sg.add((URIRef(EX+'stmt'), RDF_REIF, tt))
        r = sg.query(f"""
            PREFIX rdf: <{RDF_NS}>
            SELECT ?s WHERE {{ ?stmt rdf:reifies ?tt .
                FILTER(isTRIPLE(?tt)) BIND(SUBJECT(?tt) AS ?s) }}
        """)
        assert r.bindings[0][r.vars[0]] == URIRef(EX+'a')

    def test_construct_minting_triple_term_not_yet_supported(self, sg):
        """decompose_for_remote is SELECT-only so far - a CONSTRUCT
        template minting a fresh triple term must fail loudly against a
        remote store, not silently drop the triple (confirmed as the
        actual pre-fix behavior: the BIND computing the term's hash left
        it unbound, and CONSTRUCT's own rule for an unbound template term
        silently dropped the whole triple)."""
        sg.add((URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')))
        with pytest.raises(NotImplementedError):
            sg.query(f"""
                PREFIX : <{EX}>
                CONSTRUCT {{ :dave :claims <<( :a :b :c )>> }} WHERE {{ :a :b :c }}
            """)

    def test_plain_construct_still_works(self, sg):
        sg.add((URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')))
        r = sg.query(f"""
            PREFIX : <{EX}> CONSTRUCT {{ ?s ?p ?o }} WHERE {{ ?s ?p ?o }}
        """)
        assert list(r.graph) == [(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))]
