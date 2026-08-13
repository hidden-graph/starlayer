"""
tests/integration/test_oxigraph_backend.py

Integration tests for StarLayerGraph backed by Oxigraph via rdf-1.2 native mode.

Oxigraph speaks the final W3C RDF 1.2 <<( )>> syntax natively and returns
"type":"triple" in SPARQL JSON results.

Requires a running Oxigraph instance:
    docker run -d --name oxigraph-test -p 7878:7878 \\
      ghcr.io/oxigraph/oxigraph serve --location /data --bind 0.0.0.0:7878

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

# See test_fuseki_backend.py's identical pytestmark for why this is here.
pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Endpoint config
# ---------------------------------------------------------------------------

OXIGRAPH_BASE = 'http://localhost:7878'
QUERY_URL     = f'{OXIGRAPH_BASE}/query'
UPDATE_URL    = f'{OXIGRAPH_BASE}/update'
GRAPH_URI     = URIRef('http://example.org/test-graph')

EX       = 'http://example.org/'
RDF_NS   = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
RDF_REIF = URIRef(RDF_NS + 'reifies')
EX_CONF  = URIRef(EX + 'confidence')


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _oxigraph_available() -> bool:
    try:
        r = requests.get(OXIGRAPH_BASE, timeout=2)
        return r.status_code == 200
    except Exception:
        return False


oxigraph = pytest.mark.skipif(
    not _oxigraph_available(),
    reason='Oxigraph not running — start with: '
           'docker run -d --name oxigraph-test -p 7878:7878 '
           'ghcr.io/oxigraph/oxigraph serve --location /data --bind 0.0.0.0:7878',
)


def _make_store() -> SPARQLUpdateStore:
    return SPARQLUpdateStore(query_endpoint=QUERY_URL, update_endpoint=UPDATE_URL)


def _clear_graph():
    requests.post(
        UPDATE_URL,
        data=f'CLEAR SILENT GRAPH <{GRAPH_URI}>',
        headers={'Content-Type': 'application/sparql-update'},
        timeout=10,
    ).raise_for_status()


def _clear_all():
    """Clear the default graph and every named graph - needed for tests
    that span multiple/arbitrary graph names, unlike _clear_graph() which
    only clears the one fixed GRAPH_URI the `sg` fixture uses."""
    requests.post(
        UPDATE_URL,
        data='CLEAR SILENT ALL',
        headers={'Content-Type': 'application/sparql-update'},
        timeout=10,
    ).raise_for_status()


@pytest.fixture
def sg():
    """Fresh StarLayerGraph backed by Oxigraph in rdf-1.2 native mode."""
    _clear_graph()
    g = StarLayerGraph(store=_make_store(), identifier=GRAPH_URI, backend='rdf-1.2')
    g.bind('ex', EX)
    yield g


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

@oxigraph
class TestOxigraphRoundTrip:

    def test_plain_triple_write_read(self, sg):
        s, p, o = URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob')
        sg.add((s, p, o))
        assert (s, p, o) in sg

    def test_triple_term_write_read(self, sg):
        tt   = TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
        stmt = URIRef(EX+'stmt1')
        sg.add((stmt, RDF_REIF, tt))
        results = list(sg.triples((stmt, RDF_REIF, None)))
        assert len(results) == 1
        _, _, restored = results[0]
        assert isinstance(restored, TripleTerm)
        assert restored == tt

    def test_triple_term_in_subject_rejected(self, sg):
        """Triple terms in subject position are outside RDF 1.2 and must be rejected."""
        tt = TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))
        with pytest.raises(ValueError, match='subject position'):
            sg.add((tt, URIRef(EX+'prop'), URIRef(EX+'val')))

    def test_wildcard_triples(self, sg):
        sg.add((URIRef(EX+'s1'), URIRef(EX+'p'), URIRef(EX+'o1')))
        sg.add((URIRef(EX+'s2'), URIRef(EX+'p'), URIRef(EX+'o2')))
        results = list(sg.triples((None, URIRef(EX+'p'), None)))
        assert len(results) == 2

    def test_contains(self, sg):
        s, p, o = URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob')
        assert (s, p, o) not in sg
        sg.add((s, p, o))
        assert (s, p, o) in sg

    def test_triple_term_as_subject_of_triple_term_rejected(self, sg):
        """A triple term cannot be the subject component of another triple term (RDF 1.2)."""
        inner = TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))
        with pytest.raises(ValueError, match='subject of a triple term'):
            TripleTerm(inner, URIRef(EX+'says'), URIRef(EX+'d'))

    def test_triple_term_in_object_of_triple_term_allowed(self, sg):
        """A triple term IS allowed in the object position of another triple term."""
        inner = TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))
        outer = TripleTerm(URIRef(EX+'s'), URIRef(EX+'p'), inner)
        sg.add((URIRef(EX+'stmt'), RDF_REIF, outer))
        results = list(sg.triples((URIRef(EX+'stmt'), RDF_REIF, None)))
        assert len(results) == 1
        restored = results[0][2]
        assert isinstance(restored, TripleTerm)
        assert isinstance(restored.object, TripleTerm)
        assert restored.object == inner

    def test_no_encoding_triples_visible(self, sg):
        """Native rdf-1.2 mode stores no tt:HASH encoding triples."""
        tt = TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))
        sg.add((URIRef(EX+'stmt'), RDF_REIF, tt))
        predicates = {p for _, p, _ in sg.triples((None, None, None))}
        assert URIRef(RDF_NS + 'subject')   not in predicates
        assert URIRef(RDF_NS + 'predicate') not in predicates
        assert URIRef(RDF_NS + 'object')    not in predicates


@oxigraph
class TestOxigraphTurtle12Parse:
    """.parse(format='turtle12'/'trig12') on a native-backend graph used to
    write the rdf-1.1 backend's own tt:HASH skolemized encoding fragments
    directly into the store (StarLayerGraph.parse()'s turtle12/trig12
    branches called super().add(triple), bypassing the backend-aware
    StarLayerGraph.add() override that routes to _native_add()) - so a
    triple term parsed from text (as opposed to added via the .add()
    Python API, which was never affected) came back from .triples() as
    the raw rdf:subject/predicate/object encoding-triple fragments
    instead of a real TripleTerm object, and rdf:reifies lookups against
    such data never matched anything real. Confirmed to affect both
    simple and nested triple terms, and to break starShacl's
    sh:reifierShape/sh:reificationRequired end to end (the discovery
    path). Fixed by decoding the skolemized encoding back into real
    TripleTerm objects (turtle_parser.decode_tt_encoded_triples) before
    writing native-backend data, so it goes through self.add() ->
    _native_add() instead.
    """

    def test_simple_triple_term_decodes_correctly(self, sg):
        sg.parse(data='''
            @prefix ex: <http://example.org/> .
            ex:alice ex:says <<( ex:bob ex:knows ex:carol )>> .
        ''', format='turtle12')
        results = list(sg.triples((URIRef(EX + 'alice'), URIRef(EX + 'says'), None)))
        assert len(results) == 1
        restored = results[0][2]
        assert isinstance(restored, TripleTerm)
        assert restored == TripleTerm(URIRef(EX + 'bob'), URIRef(EX + 'knows'), URIRef(EX + 'carol'))

    def test_nested_triple_term_decodes_correctly(self, sg):
        sg.parse(data='''
            @prefix ex: <http://example.org/> .
            @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
            ex:reifier1 rdf:reifies <<( ex:stmt1 ex:claim <<( ex:bob ex:knows ex:carol )>> )>> .
        ''', format='turtle12')
        results = list(sg.triples((URIRef(EX + 'reifier1'), RDF_REIF, None)))
        assert len(results) == 1
        restored = results[0][2]
        assert isinstance(restored, TripleTerm)
        assert isinstance(restored.object, TripleTerm)
        assert restored == TripleTerm(
            URIRef(EX + 'stmt1'), URIRef(EX + 'claim'),
            TripleTerm(URIRef(EX + 'bob'), URIRef(EX + 'knows'), URIRef(EX + 'carol')),
        )

    def test_no_encoding_triples_visible_after_parse(self, sg):
        sg.parse(data='''
            @prefix ex: <http://example.org/> .
            @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
            ex:reifier1 rdf:reifies <<( ex:stmt1 ex:claim <<( ex:bob ex:knows ex:carol )>> )>> .
        ''', format='turtle12')
        predicates = {p for _, p, _ in sg.triples((None, None, None))}
        assert URIRef(RDF_NS + 'subject')   not in predicates
        assert URIRef(RDF_NS + 'predicate') not in predicates
        assert URIRef(RDF_NS + 'object')    not in predicates

    def test_rdf_reifies_lookup_matches_parsed_data(self, sg):
        """The end-to-end scenario that surfaced this bug: a shape checking
        for reifiers of a statement-level triple must actually find them
        when the data was loaded via .parse(), not just via .add()."""
        sg.parse(data='''
            @prefix ex: <http://example.org/> .
            @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
            ex:stmt1 ex:claim <<( ex:bob ex:knows ex:carol )>> .
            ex:reifier1 rdf:reifies <<( ex:stmt1 ex:claim <<( ex:bob ex:knows ex:carol )>> )>> ;
              ex:confidence "0.9" .
        ''', format='turtle12')
        target = TripleTerm(
            URIRef(EX + 'stmt1'), URIRef(EX + 'claim'),
            TripleTerm(URIRef(EX + 'bob'), URIRef(EX + 'knows'), URIRef(EX + 'carol')),
        )
        reifiers = [s for s, _, o in sg.triples((None, RDF_REIF, None)) if o == target]
        assert reifiers == [URIRef(EX + 'reifier1')]

    def test_trig12_parse_decodes_correctly(self, sg):
        sg.parse(data='''
            @prefix ex: <http://example.org/> .
            GRAPH ex:g1 { ex:alice ex:says <<( ex:bob ex:knows ex:carol )>> . }
        ''', format='trig12')
        results = list(sg.triples((URIRef(EX + 'alice'), URIRef(EX + 'says'), None)))
        assert len(results) == 1
        restored = results[0][2]
        assert isinstance(restored, TripleTerm)
        assert restored == TripleTerm(URIRef(EX + 'bob'), URIRef(EX + 'knows'), URIRef(EX + 'carol'))


@oxigraph
class TestOxigraphDatasetTrig12Parse:
    """StarLayerDataset.parse(format='trig12') had the same bug as
    StarLayerGraph.parse() above (see TestOxigraphTurtle12Parse), but in a
    separate code path: it called the module-level ``_raw_graph_add``
    (rdflib's base ``Graph.add()``) unconditionally, regardless of backend,
    instead of dispatching through the per-context StarLayerGraph's
    backend-aware ``.add()``. Same fix applied: on a native-backend context,
    decode the parser's tt:HASH encoding back into real TripleTerm objects
    before writing, so it goes through ``_native_add()``.
    """

    def _dataset(self):
        _clear_graph()
        store = _make_store()
        return StarLayerDataset(store=store, backend='rdf-1.2')

    def test_named_graph_triple_term_decodes_correctly(self):
        ds = self._dataset()
        ds.parse(data=f'''
            @prefix ex: <{EX}> .
            GRAPH <{GRAPH_URI}> {{ ex:alice ex:says <<( ex:bob ex:knows ex:carol )>> . }}
        ''', format='trig12')
        g1 = ds.get_context(GRAPH_URI)
        results = list(g1.triples((URIRef(EX + 'alice'), URIRef(EX + 'says'), None)))
        assert len(results) == 1
        restored = results[0][2]
        assert isinstance(restored, TripleTerm)
        assert restored == TripleTerm(URIRef(EX + 'bob'), URIRef(EX + 'knows'), URIRef(EX + 'carol'))

    def test_no_encoding_triples_visible_after_parse(self):
        ds = self._dataset()
        ds.parse(data=f'''
            @prefix ex: <{EX}> .
            @prefix rdf: <{RDF_NS}> .
            GRAPH <{GRAPH_URI}> {{
                ex:reifier1 rdf:reifies <<( ex:stmt1 ex:claim <<( ex:bob ex:knows ex:carol )>> )>> .
            }}
        ''', format='trig12')
        g1 = ds.get_context(GRAPH_URI)
        predicates = {p for _, p, _ in g1.triples((None, None, None))}
        assert URIRef(RDF_NS + 'subject')   not in predicates
        assert URIRef(RDF_NS + 'predicate') not in predicates
        assert URIRef(RDF_NS + 'object')    not in predicates


@oxigraph
class TestOxigraphDatasetQuery:
    """StarLayerDataset.query() had no native-backend dispatch at all: unlike
    StarLayerGraph.query() (which routed to its own native-only query logic
    for self._is_native), it always queried a plain in-memory copy built by
    _build_raw_execution_graph(). That copy is built via rdflib's base
    Graph.triples(), which for a native-backend context runs a plain SPARQL
    1.1 SELECT ?s ?p ?o against the remote store and cannot represent a
    "type":"triple" binding - so any dataset query whose result contained a
    triple-term-valued binding crashed with
    TypeError: unknown binding type. Fixed by giving StarLayerDataset and
    StarLayerGraph a shared starlayergraph.backends.native.native_query() (a
    native-backed dataset's contexts all share one store, so this is exactly
    the same underlying HTTP operation for both).
    """

    def _dataset(self):
        _clear_graph()
        store = _make_store()
        return StarLayerDataset(store=store, backend='rdf-1.2')

    def test_select_with_triple_term_binding(self):
        ds = self._dataset()
        g1 = ds.get_context(GRAPH_URI)
        tt = TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
        g1.add((URIRef(EX+'stmt1'), RDF_REIF, tt))

        q = f"""
        PREFIX rdf: <{RDF_NS}>
        SELECT ?tt WHERE {{
            GRAPH <{GRAPH_URI}> {{ <{EX}stmt1> rdf:reifies ?tt }}
        }}
        """
        rows = list(ds.query(q))
        assert len(rows) == 1
        assert isinstance(rows[0][0], TripleTerm)
        assert rows[0][0] == tt

    def test_ask(self):
        ds = self._dataset()
        g1 = ds.get_context(GRAPH_URI)
        g1.add((URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')))
        r = ds.query(f'ASK {{ GRAPH <{GRAPH_URI}> {{ ?s ?p ?o }} }}')
        assert r.askAnswer is True

    def test_construct_restores_triple_terms(self):
        ds = self._dataset()
        g1 = ds.get_context(GRAPH_URI)
        tt = TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
        g1.add((URIRef(EX+'stmt1'), RDF_REIF, tt))

        q = f"""
        PREFIX rdf: <{RDF_NS}>
        CONSTRUCT {{ ?s rdf:reifies ?tt }} WHERE {{
            GRAPH <{GRAPH_URI}> {{ ?s rdf:reifies ?tt }}
        }}
        """
        r = ds.query(q)
        results = list(r.graph.triples((None, RDF_REIF, None)))
        assert len(results) == 1
        assert results[0][2] == tt


@oxigraph
class TestOxigraphRemove:
    """StarLayerGraph.remove() on the native backend used to call
    super().remove() directly - bypassing sparql_term()/skolemize_bnode()
    entirely - which reaches rdflib's own SPARQLUpdateStore._node_to_sparql()
    and crashes outright on any BNode ("SPARQLStore does not support
    BNodes!"), confirmed live against Oxigraph before this fix. Also had no
    live test coverage of any kind (BNode or not). Fixed with a dedicated
    _native_remove() mirroring _native_add()/_native_triples()'s own
    sparql_term()-based dispatch.
    """

    def test_remove_plain_triple(self, sg):
        t = (URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))
        sg.add(t)
        assert t in sg
        sg.remove(t)
        assert t not in sg

    def test_remove_bnode_triple(self, sg):
        from rdflib import BNode
        b = BNode()
        t = (b, URIRef(EX+'r'), URIRef(EX+'o'))
        sg.add(t)
        assert t in sg
        sg.remove(t)
        assert list(sg.triples((None, None, None))) == []

    def test_remove_triple_term_valued_triple(self, sg):
        tt = TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))
        t = (URIRef(EX+'stmt'), RDF_REIF, tt)
        sg.add(t)
        assert list(sg.triples((URIRef(EX+'stmt'), RDF_REIF, None)))
        sg.remove(t)
        assert list(sg.triples((URIRef(EX+'stmt'), RDF_REIF, None))) == []

    def test_remove_wildcard_pattern(self, sg):
        sg.add((URIRef(EX+'x1'), URIRef(EX+'p'), URIRef(EX+'y')))
        sg.add((URIRef(EX+'x2'), URIRef(EX+'p'), URIRef(EX+'y')))
        sg.add((URIRef(EX+'x3'), URIRef(EX+'other'), URIRef(EX+'y')))
        sg.remove((None, URIRef(EX+'p'), None))
        remaining = list(sg.triples((None, None, None)))
        assert remaining == [(URIRef(EX+'x3'), URIRef(EX+'other'), URIRef(EX+'y'))]


@oxigraph
class TestOxigraphAddN:
    """addN() on the native backend batches through
    StarLayerGraph._native_add_many() (added alongside parse()'s own
    batching, same session) but had no live test calling addN() directly -
    only exercised indirectly via parse(). Confirmed here against a real
    endpoint, including a triple-term-valued quad.
    """

    def test_addN_plain_and_triple_term(self, sg):
        tt = TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))
        quads = [
            (URIRef(EX+'x'), URIRef(EX+'p'), URIRef(EX+'y'), sg),
            (URIRef(EX+'stmt'), RDF_REIF, tt, sg),
        ]
        sg.addN(quads)
        assert (URIRef(EX+'x'), URIRef(EX+'p'), URIRef(EX+'y')) in sg
        results = list(sg.triples((URIRef(EX+'stmt'), RDF_REIF, None)))
        assert len(results) == 1
        assert results[0][2] == tt

    def test_addN_shared_bnode_identity(self, sg):
        """A blank node referenced by more than one quad in the same addN()
        call must keep its identity - the whole point of batching into one
        request rather than one _native_add() HTTP call per quad (see
        _native_add_many()'s own docstring)."""
        from rdflib import BNode
        b = BNode()
        quads = [
            (b, URIRef(EX+'r'), URIRef(EX+'o1'), sg),
            (b, URIRef(EX+'r'), URIRef(EX+'o2'), sg),
        ]
        sg.addN(quads)
        subjects = {s for s, _, _ in sg.triples((None, URIRef(EX+'r'), None))}
        assert len(subjects) == 1

    def test_addN_ignores_quads_for_other_graphs(self, sg):
        other = StarLayerGraph(identifier=URIRef(EX+'other'))
        sg.addN([(URIRef(EX+'x'), URIRef(EX+'p'), URIRef(EX+'y'), other)])
        assert list(sg.triples((None, None, None))) == []


@oxigraph
class TestOxigraphJsonld12Parse:
    """parse(format='jsonld12') never checked self._is_native at all - it
    unconditionally called super().parse(data=text, format='json-ld'),
    which writes through a bypassed rdflib-internal ConjunctiveGraph wrapper
    (rdflib's json-ld parser's own sink), never through _native_add(). On a
    native backend this would write the raw rdf:subject/predicate/object
    tt:HASH encoding fragments directly into the live store instead of real
    <<( )>> syntax, and _build_registry_from_store() (a no-op for native
    backends) would never reconstruct them - a real, previously-untested
    correctness gap. Fixed by parsing into a throwaway plain Graph and
    decoding it exactly like the trig12/turtle12 branches already do.
    """

    def test_plain_triple_round_trips(self, sg):
        src = StarLayerGraph()
        src.add((URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')))
        jsonld_text = src.serialize(format='jsonld12')
        sg.parse(data=jsonld_text, format='jsonld12')
        assert (URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')) in sg

    def test_triple_term_round_trips(self, sg):
        src = StarLayerGraph()
        tt = TripleTerm(URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))
        src.add((URIRef(EX+'stmt'), RDF_REIF, tt))
        jsonld_text = src.serialize(format='jsonld12')
        sg.parse(data=jsonld_text, format='jsonld12')
        results = list(sg.triples((URIRef(EX+'stmt'), RDF_REIF, None)))
        assert len(results) == 1
        restored = results[0][2]
        assert isinstance(restored, TripleTerm)
        assert restored == tt

    def test_no_encoding_triples_visible_after_parse(self, sg):
        src = StarLayerGraph()
        tt = TripleTerm(URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))
        src.add((URIRef(EX+'stmt'), RDF_REIF, tt))
        jsonld_text = src.serialize(format='jsonld12')
        sg.parse(data=jsonld_text, format='jsonld12')
        predicates = {p for _, p, _ in sg.triples((None, None, None))}
        assert URIRef(RDF_NS + 'subject')   not in predicates
        assert URIRef(RDF_NS + 'predicate') not in predicates
        assert URIRef(RDF_NS + 'object')    not in predicates
        types = {o for _, p, o in sg.triples((None, None, None)) if p == URIRef(RDF_NS + 'type')}
        assert URIRef(RDF_NS + 'TripleTerm') not in types


@oxigraph
class TestOxigraphNt12Parse:
    """parse(format='nt12') already branches on self._is_native correctly
    (routes through _native_add_many()), unlike jsonld12's historical bug -
    this had simply never been run against a live endpoint at all."""

    def test_triple_term_decodes_correctly(self, sg):
        nt = f'<{EX}stmt1> <{RDF_NS}reifies> <<( <{EX}alice> <{EX}knows> <{EX}bob> )>> .\n'
        sg.parse(data=nt, format='nt12')
        results = list(sg.triples((URIRef(EX+'stmt1'), RDF_REIF, None)))
        assert len(results) == 1
        assert results[0][2] == TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))


@oxigraph
class TestOxigraphNq12Parse:
    """parse(format='nq12') merges every named graph into this one graph
    (per its own docstring) - confirmed here with a 2-distinct-graph
    fixture that a live native backend accepts and merges without error,
    same as the in-memory backend already does."""

    def test_multi_graph_data_merges_correctly(self, sg):
        nq = (
            f'<{EX}s> <{EX}p> <{EX}o> <{EX}graph1> .\n'
            f'<{EX}stmt1> <{RDF_NS}reifies> <<( <{EX}alice> <{EX}knows> <{EX}bob> )>> <{EX}graph1> .\n'
            f'<{EX}stmt2> <{RDF_NS}reifies> <<( <{EX}bob> <{EX}likes> <{EX}carol> )>> <{EX}graph2> .\n'
        )
        sg.parse(data=nq, format='nq12')
        assert (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')) in sg
        r1 = list(sg.triples((URIRef(EX+'stmt1'), RDF_REIF, None)))
        r2 = list(sg.triples((URIRef(EX+'stmt2'), RDF_REIF, None)))
        assert r1 and r1[0][2] == TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
        assert r2 and r2[0][2] == TripleTerm(URIRef(EX+'bob'), URIRef(EX+'likes'), URIRef(EX+'carol'))


@oxigraph
class TestOxigraphTrix12Parse:

    def test_triple_term_decodes_correctly(self, sg):
        xml = (
            '<?xml version="1.0"?>'
            '<trix xmlns="http://www.w3.org/2004/03/trix/trix-1/">'
            '<graph>'
            f'<triple><uri>{EX}stmt</uri>'
            f'<uri>{RDF_NS}reifies</uri>'
            f'<triple><uri>{EX}alice</uri><uri>{EX}knows</uri><uri>{EX}bob</uri></triple>'
            '</triple></graph></trix>'
        )
        sg.parse(data=xml, format='trix12')
        results = list(sg.triples((URIRef(EX+'stmt'), RDF_REIF, None)))
        assert len(results) == 1
        assert results[0][2] == TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))


@oxigraph
class TestOxigraphRdfxml12Parse:

    def test_triple_term_decodes_correctly(self, sg):
        xml = (
            '<?xml version="1.0"?>'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'
            f' xmlns:ex="{EX}">'
            f'<rdf:Description rdf:about="{EX}stmt">'
            '<rdf:reifies>'
            '<rdf:TripleTerm>'
            f'<rdf:subject rdf:resource="{EX}alice"/>'
            f'<rdf:predicate rdf:resource="{EX}knows"/>'
            f'<rdf:object rdf:resource="{EX}bob"/>'
            '</rdf:TripleTerm>'
            '</rdf:reifies>'
            '</rdf:Description></rdf:RDF>'
        )
        sg.parse(data=xml, format='rdfxml12')
        results = list(sg.triples((URIRef(EX+'stmt'), RDF_REIF, None)))
        assert len(results) == 1
        assert results[0][2] == TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))


@oxigraph
class TestOxigraphReconnect:
    """A SPARQLUpdateStore-backed StarLayerGraph has no real open/close
    lifecycle of its own (HTTP is stateless per-call, unlike a file-backed
    store such as Sleepycat) - the meaningful equivalent for this backend
    is confirming a *second*, independent StarLayerGraph/store/process
    reconnecting to the same live endpoint sees data a first one wrote,
    with nothing cached in-process bridging the two. Previously untested
    from any angle.
    """

    def test_second_graph_object_sees_data_from_first(self):
        _clear_graph()
        g1 = StarLayerGraph(store=_make_store(), identifier=GRAPH_URI, backend='rdf-1.2')
        tt = TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
        g1.add((URIRef(EX+'stmt1'), RDF_REIF, tt))

        # A brand new StarLayerGraph, brand new SPARQLUpdateStore, same
        # endpoint/identifier - nothing shared with g1 except the live
        # Oxigraph store itself.
        g2 = StarLayerGraph(store=_make_store(), identifier=GRAPH_URI, backend='rdf-1.2')
        results = list(g2.triples((URIRef(EX+'stmt1'), RDF_REIF, None)))
        assert len(results) == 1
        assert results[0][2] == tt

    def test_close_does_not_lose_or_corrupt_data(self):
        _clear_graph()
        g1 = StarLayerGraph(store=_make_store(), identifier=GRAPH_URI, backend='rdf-1.2')
        g1.add((URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')))
        g1.close()

        g2 = StarLayerGraph(store=_make_store(), identifier=GRAPH_URI, backend='rdf-1.2')
        assert (URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')) in g2


@oxigraph
class TestOxigraphDatasetUpdate:
    """StarLayerDataset.update() against a remote store 400'd on any update
    text containing its own ``GRAPH <uri> { }`` clause - the normal way to
    target a named graph from dataset-level SPARQL - because rdflib's own
    ``Dataset(store=...).update()`` always wraps the whole update in an
    extra ``GRAPH <urn:x-rdflib:default> { }`` block (SPARQLStore's
    ``_is_contextual()`` doesn't recognize ``Dataset``'s default-graph
    sentinel as exempt), producing an illegal nested GRAPH block. Confirmed
    against real Oxigraph with a plain (no triple terms) INSERT DATA.  Fixed
    by bypassing rdflib's dispatch and sending the update over HTTP directly
    for any store with query/update endpoints - same as
    StarLayerGraph.update()'s existing native-backend path.
    """

    def _dataset(self):
        _clear_graph()
        store = _make_store()
        return StarLayerDataset(store=store, backend='rdf-1.2')

    def test_insert_data_with_graph_clause(self):
        ds = self._dataset()
        ds.update(f'INSERT DATA {{ GRAPH <{GRAPH_URI}> {{ <{EX}a> <{EX}b> <{EX}c> . }} }}')
        g1 = ds.get_context(GRAPH_URI)
        assert (URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')) in g1

    def test_insert_where_with_graph_clause(self):
        ds = self._dataset()
        g1 = ds.get_context(GRAPH_URI)
        g1.add((URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')))
        ds.update(f"""
            INSERT {{ GRAPH <{GRAPH_URI}> {{ ?s <{EX}marked> ?o }} }}
            WHERE {{ GRAPH <{GRAPH_URI}> {{ ?s <{EX}b> ?o }} }}
        """)
        assert (URIRef(EX+'a'), URIRef(EX+'marked'), URIRef(EX+'c')) in g1

    def test_delete_data_with_graph_clause(self):
        """DELETE DATA had no live coverage at all (only INSERT variants
        did) - native_update() forwards DELETE the same mechanical way as
        INSERT, but that was an untested assumption, not a verified fact."""
        ds = self._dataset()
        g1 = ds.get_context(GRAPH_URI)
        g1.add((URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')))
        ds.update(f'DELETE DATA {{ GRAPH <{GRAPH_URI}> {{ <{EX}a> <{EX}b> <{EX}c> . }} }}')
        assert (URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')) not in g1

    def test_delete_where_with_graph_clause(self):
        ds = self._dataset()
        g1 = ds.get_context(GRAPH_URI)
        g1.add((URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')))
        g1.add((URIRef(EX+'x'), URIRef(EX+'y'), URIRef(EX+'z')))
        ds.update(f"""
            DELETE {{ GRAPH <{GRAPH_URI}> {{ ?s <{EX}b> ?o }} }}
            WHERE {{ GRAPH <{GRAPH_URI}> {{ ?s <{EX}b> ?o }} }}
        """)
        assert (URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')) not in g1
        assert (URIRef(EX+'x'), URIRef(EX+'y'), URIRef(EX+'z')) in g1


@oxigraph
class TestOxigraphGraphUpdate:
    """StarLayerGraph.update() (as opposed to StarLayerDataset.update(),
    already covered by TestOxigraphDatasetUpdate) had no live-backend test
    coverage at all - the only existing test of it mocked requests.post
    outright and asserted just "a POST happened", not that INSERT/DELETE
    semantics actually round-trip against a real endpoint.
    """

    def test_insert_data(self, sg):
        sg.update(f'INSERT DATA {{ GRAPH <{GRAPH_URI}> {{ <{EX}a> <{EX}b> <{EX}c> . }} }}')
        assert (URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')) in sg

    def test_delete_data(self, sg):
        sg.add((URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')))
        sg.update(f'DELETE DATA {{ GRAPH <{GRAPH_URI}> {{ <{EX}a> <{EX}b> <{EX}c> . }} }}')
        assert (URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')) not in sg

    def test_delete_where(self, sg):
        sg.add((URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')))
        sg.add((URIRef(EX+'x'), URIRef(EX+'y'), URIRef(EX+'z')))
        sg.update(f"""
            DELETE {{ GRAPH <{GRAPH_URI}> {{ ?s <{EX}b> ?o }} }}
            WHERE {{ GRAPH <{GRAPH_URI}> {{ ?s <{EX}b> ?o }} }}
        """)
        assert (URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')) not in sg
        assert (URIRef(EX+'x'), URIRef(EX+'y'), URIRef(EX+'z')) in sg

    def test_insert_where(self, sg):
        sg.add((URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')))
        sg.update(f"""
            INSERT {{ GRAPH <{GRAPH_URI}> {{ ?s <{EX}marked> ?o }} }}
            WHERE {{ GRAPH <{GRAPH_URI}> {{ ?s <{EX}b> ?o }} }}
        """)
        assert (URIRef(EX+'a'), URIRef(EX+'marked'), URIRef(EX+'c')) in sg


# ---------------------------------------------------------------------------
# SPARQL queries — rdf-1.2 syntax passed through unchanged
# ---------------------------------------------------------------------------

@oxigraph
class TestOxigraphSPARQL:

    def _load(self, sg):
        sg.add((URIRef(EX+'stmt1'), RDF_REIF,
                TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))))
        sg.add((URIRef(EX+'stmt1'), EX_CONF,
                Literal('0.9', datatype=XSD.decimal)))
        sg.add((URIRef(EX+'stmt2'), RDF_REIF,
                TripleTerm(URIRef(EX+'bob'), URIRef(EX+'likes'), URIRef(EX+'carol'))))
        sg.add((URIRef(EX+'stmt2'), EX_CONF,
                Literal('0.4', datatype=XSD.decimal)))

    def test_select_reified_triples(self, sg):
        self._load(sg)
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <{RDF_NS}>
        SELECT ?stmt ?tt WHERE {{
            GRAPH <{GRAPH_URI}> {{
                ?stmt rdf:reifies ?tt .
            }}
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
        PREFIX rdf: <{RDF_NS}>
        SELECT ?tt WHERE {{
            GRAPH <{GRAPH_URI}> {{
                <{EX}stmt1> rdf:reifies ?tt .
            }}
        }}
        """
        rows = list(sg.query(q))
        assert len(rows) == 1
        assert isinstance(rows[0][0], TripleTerm)
        assert rows[0][0] == TripleTerm(
            URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob')
        )

    def test_sparql12_triple_term_pattern(self, sg):
        """SPARQL 1.2 <<( )>> syntax is sent directly to Oxigraph unchanged."""
        self._load(sg)
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <{RDF_NS}>
        SELECT ?stmt ?s ?o WHERE {{
            GRAPH <{GRAPH_URI}> {{
                ?stmt rdf:reifies <<( ?s ex:knows ?o )>> .
            }}
        }}
        """
        rows = list(sg.query(q))
        assert len(rows) == 1
        assert rows[0][1] == URIRef(EX+'alice')
        assert rows[0][2] == URIRef(EX+'bob')

    def test_filter_by_confidence(self, sg):
        self._load(sg)
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <{RDF_NS}>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        SELECT ?stmt WHERE {{
            GRAPH <{GRAPH_URI}> {{
                ?stmt rdf:reifies <<( ?s ?p ?o )>> .
                ?stmt ex:confidence ?conf .
                FILTER(xsd:decimal(?conf) > 0.5)
            }}
        }}
        """
        rows = list(sg.query(q))
        assert len(rows) == 1
        assert rows[0][0] == URIRef(EX+'stmt1')

    def test_ask_query(self, sg):
        sg.add((URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob')))
        q = f'ASK {{ GRAPH <{GRAPH_URI}> {{ <{EX}alice> <{EX}knows> <{EX}bob> . }} }}'
        r = sg.query(q)
        assert r.askAnswer is True

    def test_12_syntax_passed_through_unchanged(self, sg):
        """<<( )>> SPARQL 1.2 syntax goes straight to Oxigraph - no rewriting layer."""
        sg.add((URIRef(EX+'stmt'), RDF_REIF, TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))))
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <{RDF_NS}>
        SELECT ?x WHERE {{
            GRAPH <{GRAPH_URI}> {{
                ?x rdf:reifies <<( ex:a ex:b ex:c )>> .
            }}
        }}
        """
        rows = list(sg.query(q))
        assert len(rows) == 1
        assert rows[0][0] == URIRef(EX+'stmt')


# ---------------------------------------------------------------------------
# TRIPLE()/isTRIPLE() and the RDF 1.2 base-direction SPARQL functions,
# passed through unchanged to Oxigraph - confirmed 2026-07-16, Oxigraph 0.5.9
# natively supports all of them.
# ---------------------------------------------------------------------------

@oxigraph
class TestOxigraphRdf12SparqlFunctions:

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

    def test_dirlangstring_construct_round_trip(self, sg):
        from starlayergraph.model.dirlangstring import DirLangString
        d = DirLangString('hola', 'es', 'ltr')
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), d))
        r = sg.query(f'CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH <{GRAPH_URI}> {{ ?s ?p ?o }} }}')
        assert (URIRef(EX+'s'), URIRef(EX+'p'), d) in r.graph

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
# Backend gaps unrelated to SPARQL parsing/translation - the reification
# convenience API, triples_choices(), isomorphic(), non-RDF12 serialize(),
# and __len__ all had zero (or silently wrong) native-backend dispatch.
# ---------------------------------------------------------------------------

@oxigraph
class TestOxigraphReificationAPI:
    """add_reification/reifiers/reifications/reifier_annotations/
    reified_triples/triple_terms/has_triple_term/remove_reification had no
    _is_native awareness at all. add_reification() wrote the rdf-1.1
    backend's own tt:HASH encoding fragments (rdf:subject/predicate/object
    on a synthetic tt: URIRef) directly into the live native store instead
    of a real <<( )>> triple term, and every read method keyed off
    self._tt_registry/_tt_nodes, which are always empty for native (see
    StarLayerGraph._build_registry_from_store()'s own no-op there) - so
    reads only ever "worked" by accident, off the same process's stale
    local state. Confirmed live: a second StarLayerGraph object (same
    store, no shared in-process state) read back nothing.  Each test here
    uses a fresh object with no shared state to guard against exactly that
    false-positive.
    """

    def _fresh(self):
        return StarLayerGraph(store=_make_store(), identifier=GRAPH_URI, backend='rdf-1.2')

    def test_add_and_find_reification(self, sg):
        tt = TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))
        r1 = sg.add_reifier_annotation(EX_CONF, Literal('0.9'), name=URIRef(EX+'r1'))
        sg.add_reification(r1, tt)

        fresh = self._fresh()
        assert list(fresh.reifiers(TT=tt)) == [URIRef(EX+'r1')]
        assert list(fresh.reifications()) == [tt]
        assert list(fresh.reifier_annotations(tt)) == [(URIRef(EX+'r1'), EX_CONF, Literal('0.9'))]
        assert list(fresh.reified_triples(URIRef(EX+'r1'))) == [tt]
        assert list(fresh.triple_terms()) == [tt]
        assert fresh.has_triple_term(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')) is True
        assert fresh.has_triple_term(URIRef(EX+'x'), URIRef(EX+'y'), URIRef(EX+'z')) is False

    def test_no_raw_encoding_fragments_written(self, sg):
        """add_reification() must write a real <<( )>> triple term, not the
        rdf-1.1 backend's rdf:subject/predicate/object encoding fragments."""
        tt = TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))
        r1 = sg.add_reifier_annotation(EX_CONF, Literal('0.9'), name=URIRef(EX+'r1'))
        sg.add_reification(r1, tt)
        predicates = {p for _, p, _ in sg.triples((None, None, None))}
        assert URIRef(RDF_NS + 'subject')   not in predicates
        assert URIRef(RDF_NS + 'predicate') not in predicates
        assert URIRef(RDF_NS + 'object')    not in predicates

    def test_remove_reification(self, sg):
        tt = TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))
        r1 = sg.add_reifier_annotation(EX_CONF, Literal('0.9'), name=URIRef(EX+'r1'))
        sg.add_reification(r1, tt)
        sg.remove_reification(URIRef(EX+'r1'))
        assert list(self._fresh().reifiers(TT=tt)) == []


@oxigraph
class TestOxigraphTriplesChoices:
    """triples_choices() had no native dispatch and fell through to
    SPARQLStore.triples_choices(), an unconditional
    raise NotImplementedError - confirmed live before this fix."""

    def test_list_valued_predicate(self, sg):
        sg.add((URIRef(EX+'a'), URIRef(EX+'p'), URIRef(EX+'x')))
        sg.add((URIRef(EX+'b'), URIRef(EX+'p'), URIRef(EX+'y')))
        sg.add((URIRef(EX+'c'), URIRef(EX+'other'), URIRef(EX+'z')))
        results = set(sg.triples_choices((None, [URIRef(EX+'p')], None)))
        assert results == {
            (URIRef(EX+'a'), URIRef(EX+'p'), URIRef(EX+'x')),
            (URIRef(EX+'b'), URIRef(EX+'p'), URIRef(EX+'y')),
        }

    def test_list_valued_object(self, sg):
        sg.add((URIRef(EX+'a'), URIRef(EX+'p'), URIRef(EX+'x')))
        sg.add((URIRef(EX+'a'), URIRef(EX+'p'), URIRef(EX+'y')))
        sg.add((URIRef(EX+'a'), URIRef(EX+'p'), URIRef(EX+'z')))
        results = set(sg.triples_choices((None, None, [URIRef(EX+'x'), URIRef(EX+'z')])))
        assert results == {
            (URIRef(EX+'a'), URIRef(EX+'p'), URIRef(EX+'x')),
            (URIRef(EX+'a'), URIRef(EX+'p'), URIRef(EX+'z')),
        }


@oxigraph
class TestOxigraphIsomorphicAndSerialize:
    """isomorphic() and serialize() to a non-RDF12 format (e.g. 'xml',
    'turtle') both bypassed native dispatch via raw store.triples()/
    Graph.triples() - which can't parse a "type":"triple" SPARQL JSON
    binding at all (see starlayergraph.backends.native's own module docstring) -
    so both would mishandle or crash on any native-backend graph containing
    a triple term. Also covers the turtle12 serializer's @version "1.2"
    directive, which used to check self._tt_nodes (always empty for native)
    and so silently omitted the directive for native-backend graphs that
    did contain real triple terms.
    """

    def test_isomorphic_native_vs_in_memory(self, sg):
        tt = TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))
        sg.add((URIRef(EX+'stmt'), RDF_REIF, tt))

        other = StarLayerGraph()  # in-memory, structurally identical
        other.add((URIRef(EX+'stmt'), RDF_REIF, tt))
        assert sg.isomorphic(other) is True

        different = StarLayerGraph()
        different.add((URIRef(EX+'stmt'), RDF_REIF,
                        TripleTerm(URIRef(EX+'x'), URIRef(EX+'y'), URIRef(EX+'z'))))
        assert sg.isomorphic(different) is False

    def test_serialize_non_rdf12_format_with_triple_term(self, sg):
        tt = TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))
        sg.add((URIRef(EX+'stmt'), RDF_REIF, tt))
        xml = sg.serialize(format='xml')
        assert 'rdf:RDF' in xml
        reparsed = StarLayerGraph()
        reparsed.parse(data=xml, format='xml')
        # De-skolemized to a BNode-based reification - the base triple
        # itself is not asserted by rdf:subject/predicate/object alone,
        # just confirm parsing the native-backend graph's XML output at
        # all succeeds and carries the reifies edge through.
        assert (URIRef(EX+'stmt'), RDF_REIF, None) in reparsed or \
               any(p == RDF_REIF for _, p, _ in reparsed)

    def test_turtle12_version_directive_present_for_native_triple_term(self, sg):
        tt = TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))
        sg.add((URIRef(EX+'stmt'), RDF_REIF, tt))
        ttl = sg.serialize(format='turtle12')
        assert '@version "1.2"' in ttl


@oxigraph
class TestOxigraphLen:
    """__len__ fetched and Python-counted every triple over HTTP instead of
    using the store's already-available COUNT(*) support (what
    SPARQLStore.__len__ already does for a non-native graph)."""

    def test_graph_len(self, sg):
        sg.add((URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')))
        sg.add((URIRef(EX+'x'), URIRef(EX+'y'), URIRef(EX+'z')))
        assert len(sg) == 2

    def test_dataset_len_sums_across_all_graphs(self):
        """StarLayerDataset had no __len__ override at all, so it inherited
        Dataset.__len__ -> store.__len__(context=None), which for
        SPARQLStore queries only the endpoint's true default graph -
        GRAPH-scoped content is invisible to it. Confirmed live: 3 triples
        (1 default + 1 each in two named graphs) came back as 1 via
        inheritance before this fix."""
        _clear_all()
        store = _make_store()
        ds = StarLayerDataset(store=store, backend='rdf-1.2')
        ds.default_graph.add((URIRef(EX+'d'), URIRef(EX+'e'), URIRef(EX+'f')))
        g1 = ds.get_context(URIRef(EX+'g1'))
        g1.add((URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')))
        g2 = ds.get_context(URIRef(EX+'g2'))
        g2.add((URIRef(EX+'x'), URIRef(EX+'y'), URIRef(EX+'z')))
        assert len(ds) == 3
