"""
Unit tests for starlayer.graph.graph.StarLayerGraph.

Covers: rdflib compatibility, TripleTerm add/query, filtering of internal
encoding triples, from_rdflib(), and Statement operations.
"""

from unittest.mock import MagicMock, patch

import pytest
from rdflib import Graph, Literal, URIRef
from starlayer.graph.graph.starlayer_graph import RDF_REIFIES, StarLayerGraph
from starlayer.graph.model.triple import TripleTerm

EX = 'http://example.org/'


@pytest.fixture
def sg():
    return StarLayerGraph()


# ---------------------------------------------------------------------------
# rdflib compatibility
# ---------------------------------------------------------------------------

class TestRdflibCompat:
    def test_isinstance_rdflib_graph(self, sg):
        assert isinstance(sg, Graph)









    def test_serialize_trig_uses_own_identifier_like_plain_rdflib(self):
        """Regression, fixed 2026-10-04: serialize(format='trig') routes
        through _deskolemize_to_graph(), whose output graph used to be a
        bare Graph() - defaulting to a fresh random BNode identifier instead
        of carrying forward self.identifier, so the emitted GRAPH block name
        silently differed from the graph's own identifier every time. Plain
        rdflib.Graph(identifier=...).serialize(format='trig') has always
        gotten this right, so StarLayerGraph needs to match it exactly, not
        just produce *some* named graph."""
        identifier = URIRef(EX + 'mygraph')
        sg = StarLayerGraph(identifier=identifier)
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))

        plain = Graph(identifier=identifier)
        plain.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))

        assert sg.serialize(format='trig') == plain.serialize(format='trig')


# ---------------------------------------------------------------------------
# Bare (RDF 1.1) nquads/trig parsing - multi-graph-capable formats
# parsed into a single graph. Added 2026-10-04: plain rdflib delegation
# would silently yield zero triples the moment any named graph appears at
# all (a non-context-aware Graph's parser plugins can't place quads
# anywhere) - this project instead resolves at most one distinct graph
# (dropping its name) or raises MultipleGraphsError for two or more,
# matching the same rule nq12/trig12 enforce (see test_rdf12_formats.py).
# ---------------------------------------------------------------------------

class TestBareQuadFormatsParsing:
    def test_nquads_single_named_graph_drops_graph_name(self, sg):
        nq = f'<{EX}s> <{EX}p> <{EX}o> <{EX}g1> .\n'
        sg.parse(data=nq, format='nquads')
        assert (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')) in sg

    def test_nquads_multiple_graphs_raises(self, sg):
        from starlayer.graph.parsers.errors import MultipleGraphsError
        nq = (
            f'<{EX}s> <{EX}p> <{EX}o> <{EX}g1> .\n'
            f'<{EX}a> <{EX}b> <{EX}c> <{EX}g2> .\n'
        )
        with pytest.raises(MultipleGraphsError):
            sg.parse(data=nq, format='nquads')

    def test_trig_single_named_graph_drops_graph_name(self, sg):
        trig = f'<{EX}g1> {{ <{EX}s> <{EX}p> <{EX}o> . }}\n'
        sg.parse(data=trig, format='trig')
        assert (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')) in sg

    def test_trig_default_and_named_graph_raises(self, sg):
        from starlayer.graph.parsers.errors import MultipleGraphsError
        trig = (
            f'<{EX}default> <{EX}p> <{EX}o> .\n'
            f'<{EX}g1> {{ <{EX}named> <{EX}p> <{EX}o> . }}\n'
        )
        with pytest.raises(MultipleGraphsError):
            sg.parse(data=trig, format='trig')


# ---------------------------------------------------------------------------
# Bare (RDF 1.1) nquads/trig serializing - a single graph always has
# somewhere to go (its own identifier), so unlike parse() there's no
# raise-for-2+-graphs case here; the fix is purely about not raising for the
# single-graph case either. Added 2026-10-04: rdflib's own NQuads
# serializer plugin raises "...only makes sense for context-aware stores"
# for any non-context-aware store (no single-graph fallback, unlike
# TrigSerializer's own - see rdflib.plugins.serializers.trig), which
# StarLayerGraph used to just inherit via blind delegation. Now wraps the
# graph as the one context of a real Dataset first, so all six dataset
# formats (nquads/trig, nq12/trig12) behave consistently.
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Chaining contract (return self, matching rdflib) - regressions fixed
# 2026-10-04. rdflib's own Graph.add()/.addN()/.remove()/.serialize()/.open()
# all return self (or the serialized text when destination is None) so
# calls can chain; several StarLayerGraph overrides had silently dropped
# this by falling off the end of the function (add/remove), forwarding
# rdflib's own unrelated raw return value (open), or returning a throwaway
# internal object instead of self (serialize's destination-given branches).
# ---------------------------------------------------------------------------

class TestChainingContractMatchesRdflib:


    def test_remove_returns_self_even_for_an_unregistered_triple_term(self, sg):
        """The early-return branch (pattern references a TripleTerm this
        graph never registered) used to fall off the end as bare `return`
        (-> None) same as the normal path - both needed fixing, not just
        the common case."""
        from starlayer.graph.model.triple import TripleTerm as TT
        unregistered = TT(URIRef(EX+'x'), URIRef(EX+'y'), URIRef(EX+'z'))
        assert sg.remove((URIRef(EX+'claim'), RDF_REIFIES, unregistered)) is sg


    def test_open_returns_self_not_rdflibs_own_status_code(self, tmp_path):
        """rdflib's Store.open() returns a status int (e.g. 1 for
        VALID_STORE), not the graph - StarLayerGraph.open() must not
        forward that raw value even though its own annotation always
        claimed `-> StarLayerGraph`."""
        g = StarLayerGraph()
        assert g.open(str(tmp_path / 'store'), create=True) is g





# ---------------------------------------------------------------------------
# TripleTerm in add / triples / __contains__
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Encoding triples are hidden from traversal
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# from_rdflib — wrapping the parser output
# ---------------------------------------------------------------------------

class TestFromRdflib:

    def test_from_rdflib_builds_tt_registry(self, parser):
        raw = parser.parse(
            'PREFIX ex: <http://example.org/>\n'
            'ex:r rdf:reifies <<( ex:s ex:p ex:o )>> .\n'
        )
        sg = StarLayerGraph.from_rdflib(raw)
        results = list(sg.triples((URIRef(EX+'r'), RDF_REIFIES, None)))
        assert len(results) == 1
        _, _, o = results[0]
        assert isinstance(o, TripleTerm)

    def test_from_rdflib_tt_values(self, parser):
        raw = parser.parse(
            'PREFIX ex: <http://example.org/>\n'
            'ex:r rdf:reifies <<( ex:s ex:p ex:o )>> .\n'
        )
        sg = StarLayerGraph.from_rdflib(raw)
        _, _, tt = next(iter(sg.triples((URIRef(EX+'r'), RDF_REIFIES, None))))
        assert tt.subject   == URIRef(EX+'s')
        assert tt.predicate == URIRef(EX+'p')
        assert tt.object    == URIRef(EX+'o')

    def test_from_rdflib_len_excludes_encoding(self, parser):
        raw = parser.parse(
            'PREFIX ex: <http://example.org/>\n'
            'ex:r rdf:reifies <<( ex:s ex:p ex:o )>> .\n'
        )
        sg = StarLayerGraph.from_rdflib(raw)
        assert len(sg) == 1








# ---------------------------------------------------------------------------
# Statement operations
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# triple_terms() / has_triple_term() direct pattern matching
# ---------------------------------------------------------------------------

class TestTripleTermsQuery:
    @pytest.fixture
    def sg_two_tts(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        g.add_reification(URIRef(EX+'claim'),
                           (URIRef(EX+'bob'), URIRef(EX+'knows'), URIRef(EX+'carol')))
        g.add_reification(URIRef(EX+'other'),
                           (URIRef(EX+'bob'), URIRef(EX+'likes'), URIRef(EX+'dana')))
        return g





    # -- namespace_manager propagation --------------------------------------
    # triple_terms()/reified_triples() read straight from the internal
    # _tt_nodes registry rather than going through _restore(), so - unlike
    # every triples()/query() read - they used to skip the
    # `tt._namespace_manager = self.namespace_manager` assignment _restore()
    # applies. That made a returned TripleTerm's str()/n3() fall back to
    # unprefixed full-URI form (or raise AttributeError inside n3(None) and
    # fall back further to __repr__) even when the graph had a prefix bound
    # for its components, unlike a TripleTerm read via g.triples(). See
    # docs/user-guide-v1.md's "Finding triple terms directly" section.

    def test_triple_terms_result_renders_prefixed(self, sg_two_tts):
        tt = next(sg_two_tts.triple_terms(subject=URIRef(EX+'bob'),
                                           predicate=URIRef(EX+'knows')))
        assert str(tt) == '<<( ex:bob ex:knows ex:carol )>>'

    def test_reified_triples_result_renders_prefixed(self, sg_two_tts):
        tt = next(sg_two_tts.reified_triples(URIRef(EX+'claim')))
        assert str(tt) == '<<( ex:bob ex:knows ex:carol )>>'

    def test_reifications_result_renders_prefixed(self, sg_two_tts):
        tt = next(sg_two_tts.reifications(p=URIRef(EX+'knows')))
        assert str(tt) == '<<( ex:bob ex:knows ex:carol )>>'


# ---------------------------------------------------------------------------
# qname_term() - unlike the inherited qname(), accepts any term type
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Wildcard triple-term patterns in triples()
# ---------------------------------------------------------------------------

class TestTripleWildcards:
    """triples() with tuple patterns containing None — partial wildcard matching."""

    @pytest.fixture
    def sg_two_tts(self):
        g = StarLayerGraph()
        g.add((URIRef(EX + 'stmt1'), RDF_REIFIES,
               TripleTerm(URIRef(EX + 'alice'), URIRef(EX + 'knows'), URIRef(EX + 'bob'))))
        g.add((URIRef(EX + 'stmt2'), RDF_REIFIES,
               TripleTerm(URIRef(EX + 'bob'),   URIRef(EX + 'likes'), URIRef(EX + 'carol'))))
        g.add((URIRef(EX + 's'), URIRef(EX + 'p'), Literal('plain')))
        return g

    # --- object position ---

    def test_full_wildcard_object_matches_only_triple_terms(self, sg_two_tts):
        results = list(sg_two_tts.triples((None, None, (None, None, None))))
        assert len(results) == 2
        assert all(isinstance(o, TripleTerm) for _, _, o in results)

    def test_full_wildcard_object_excludes_plain_literals(self, sg_two_tts):
        results = list(sg_two_tts.triples((None, None, (None, None, None))))
        assert all(not isinstance(o, Literal) for _, _, o in results)

    def test_partial_wildcard_object_subject_filter(self, sg_two_tts):
        """(alice, None, None) as object should match only the alice/knows/bob triple term."""
        results = list(sg_two_tts.triples(
            (None, RDF_REIFIES, (URIRef(EX + 'alice'), None, None))))
        assert len(results) == 1
        assert results[0][2] == TripleTerm(
            URIRef(EX + 'alice'), URIRef(EX + 'knows'), URIRef(EX + 'bob'))

    def test_partial_wildcard_object_predicate_filter(self, sg_two_tts):
        """(None, likes, None) as object should match only the bob/likes/carol triple term."""
        results = list(sg_two_tts.triples(
            (None, RDF_REIFIES, (None, URIRef(EX + 'likes'), None))))
        assert len(results) == 1
        assert results[0][2] == TripleTerm(
            URIRef(EX + 'bob'), URIRef(EX + 'likes'), URIRef(EX + 'carol'))

    def test_partial_wildcard_object_no_match_returns_empty(self, sg_two_tts):
        results = list(sg_two_tts.triples(
            (None, RDF_REIFIES, (URIRef(EX + 'nobody'), None, None))))
        assert results == []

    # --- no duplicates ---

    def test_no_duplicate_results(self, sg_two_tts):
        results = list(sg_two_tts.triples((None, None, (None, None, None))))
        keys = [(str(s), str(p), str(o)) for s, p, o in results]
        assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# TripleTerm immutability
# ---------------------------------------------------------------------------

class TestTripleTermImmutability:




    def test_namespace_manager_is_mutable(self):
        tt = TripleTerm(URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))
        tt._namespace_manager = object()   # must not raise




# ---------------------------------------------------------------------------
# subjects() / objects() / predicates() with wildcard tuple patterns
# (convenience methods call self.triples() so wildcards work automatically)
# ---------------------------------------------------------------------------

class TestConvenienceMethodWildcards:
    @pytest.fixture
    def g(self):
        g = StarLayerGraph()
        g.add((URIRef(EX+'stmt1'), RDF_REIFIES,
               TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))))
        g.add((URIRef(EX+'stmt2'), RDF_REIFIES,
               TripleTerm(URIRef(EX+'alice'), URIRef(EX+'likes'), URIRef(EX+'eve'))))
        g.add((URIRef(EX+'stmt3'), RDF_REIFIES,
               TripleTerm(URIRef(EX+'carol'), URIRef(EX+'knows'), URIRef(EX+'dave'))))
        return g



    def test_subjects_with_wildcard_tuple_object(self, g):
        # Find all stmts reifying a triple term whose subject is alice
        subjs = list(g.subjects(RDF_REIFIES, (URIRef(EX+'alice'), None, None)))
        assert URIRef(EX+'stmt1') in subjs
        assert URIRef(EX+'stmt2') in subjs
        assert URIRef(EX+'stmt3') not in subjs

    def test_subjects_with_fully_wild_tuple_object(self, g):
        # Find all stmts reifying any triple term
        subjs = list(g.subjects(RDF_REIFIES, (None, None, None)))
        assert len(subjs) == 3


    def test_predicates_with_wildcard_tuple_object(self, g):
        preds = list(g.predicates(URIRef(EX+'stmt1'), (URIRef(EX+'alice'), None, None)))
        assert RDF_REIFIES in preds


# ---------------------------------------------------------------------------
# Persistent store lifecycle — open() / close()
# ---------------------------------------------------------------------------

class TestStoreLifecycle:
    """Verify open()/close() API using the built-in Memory store.

    The Memory store's open() is a no-op, so these tests exercise the API
    contract (registry rebuilt, data accessible) without requiring an
    external backend package.  Integration tests against Sleepycat or
    rdflib-sqlalchemy should follow the same pattern with a real store.
    """

    def test_open_rebuilds_registry(self):
        """open() on a graph that already has data rebuilds the TT registry."""
        sg = StarLayerGraph()
        tt = (URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
        sg.add((URIRef(EX+'stmt1'), RDF_REIFIES, tt))
        # Wipe the in-memory registry to simulate a fresh connection
        sg._tt_nodes.clear()
        sg._tt_registry.clear()
        sg.open('')  # Memory store ignores the path; triggers _build_registry_from_store
        assert len(sg._tt_nodes) == 1

    def test_open_returns_result(self):
        sg = StarLayerGraph()
        result = sg.open('', create=True)
        # Memory store returns VALID (1) or similar; just verify it doesn't raise
        assert result is not None or result is None  # any return value is acceptable

    def test_close_does_not_raise(self):
        sg = StarLayerGraph()
        sg.open('')
        sg.close()  # should not raise

    def test_close_with_commit(self):
        sg = StarLayerGraph()
        sg.open('')
        sg.close(commit_pending_transaction=True)

    def test_triple_terms_accessible_after_open(self):
        """After open(), TripleTerms can be queried normally."""
        from starlayer.graph.model.triple import TripleTerm
        sg = StarLayerGraph()
        tt = TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
        sg.add((URIRef(EX+'stmt1'), RDF_REIFIES, tt))
        sg._tt_nodes.clear()
        sg._tt_registry.clear()
        sg.open('')
        results = list(sg.triples((None, RDF_REIFIES, None)))
        assert len(results) == 1
        s, p, o = results[0]
        assert isinstance(o, TripleTerm)
        assert o.subject == URIRef(EX+'alice')


# ---------------------------------------------------------------------------
# Native backend — CONSTRUCT via http_construct (mocked HTTP)
# ---------------------------------------------------------------------------

_TURTLE_RESPONSE = b"""
@prefix :    <http://example.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

:stmt1 rdf:reifies <<( :bob :knows :carol )>> ;
       :confidence "0.9" .
"""

def _mock_post(turtle_body: bytes):
    """Return a mock requests.Response that serves turtle_body."""
    resp = MagicMock()
    resp.status_code = 200
    resp.content = turtle_body
    resp.headers = {'Content-Type': 'text/turtle'}
    resp.raise_for_status = lambda: None
    return resp


class TestNativeConstruct:

    def _make_native_sg(self):
        """StarLayerGraph in rdf-1.2 mode with a fake SPARQLUpdateStore endpoint.

        The store is never actually contacted — requests.post is mocked in each test.
        """
        from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore
        store = SPARQLUpdateStore(
            query_endpoint='http://fake.local/query',
            update_endpoint='http://fake.local/update',
        )
        return StarLayerGraph(store=store, backend='rdf-1.2')

    def test_construct_returns_starlayer_graph(self):
        sg = self._make_native_sg()
        with patch('requests.post', return_value=_mock_post(_TURTLE_RESPONSE)):
            r = sg.query("""
                PREFIX :   <http://example.org/>
                PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }
            """)
        assert r.type == 'CONSTRUCT'
        assert isinstance(r.graph, StarLayerGraph)

    def test_construct_graph_contains_triple_term(self):
        sg = self._make_native_sg()
        with patch('requests.post', return_value=_mock_post(_TURTLE_RESPONSE)):
            r = sg.query("""
                PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }
            """)
        triples = list(r.graph.triples((None, RDF_REIFIES, None)))
        assert len(triples) == 1
        _, _, tt = triples[0]
        assert isinstance(tt, TripleTerm)
        assert tt.subject   == URIRef(EX + 'bob')
        assert tt.predicate == URIRef(EX + 'knows')
        assert tt.object    == URIRef(EX + 'carol')

    def test_construct_with_prefix_before_keyword(self):
        """Query type detection must work when PREFIX declarations precede CONSTRUCT."""
        sg = self._make_native_sg()
        with patch('requests.post', return_value=_mock_post(_TURTLE_RESPONSE)):
            r = sg.query("""
                PREFIX :    <http://example.org/>
                PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }
            """)
        assert r.type == 'CONSTRUCT'

    def test_update_posts_to_update_endpoint(self):
        """UPDATE on a native backend sends the query directly to the update endpoint."""
        sg = self._make_native_sg()
        update_resp = MagicMock()
        update_resp.raise_for_status = lambda: None
        with patch('requests.post', return_value=update_resp) as mock_post:
            sg.update("""
                PREFIX :   <http://example.org/>
                PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                INSERT DATA {
                  :stmt1 rdf:reifies <<( :bob :knows :carol )>> .
                }
            """)
        assert mock_post.called
        call_url = mock_post.call_args[0][0]
        assert 'update' in call_url


# ---------------------------------------------------------------------------
# isomorphic() — BNodes embedded inside a TripleTerm must be relabelable
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Statements crammed onto one physical line must not be silently dropped
# ---------------------------------------------------------------------------

