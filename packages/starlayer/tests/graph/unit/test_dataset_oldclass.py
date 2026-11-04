"""
Unit tests for StarLayerDataset.

Covers: multi-graph TriG 1.2 parsing, named-graph context access,
quad iteration, TriG 1.2 / N-Quads 1.2 serialization, and round-trip.
"""

from rdflib import URIRef
from starlayer.graph.graph import StarLayerDataset, StarLayerGraph
from starlayer.graph.graph.starlayer_graph import RDF_REIFIES
from starlayer.graph.model.triple import TripleTerm

EX = 'http://example.org/'
G1 = URIRef(EX + 'graph1')
G2 = URIRef(EX + 'graph2')


def ex(local):
    return URIRef(EX + local)


TRIG_BASIC = f"""\
@prefix ex: <{EX}> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

GRAPH <{EX}graph1> {{
  ex:s ex:p ex:o .
  ex:stmt1 rdf:reifies <<( ex:alice ex:knows ex:bob )>> .
  ex:stmt1 ex:confidence "0.9" .
}}

GRAPH <{EX}graph2> {{
  ex:stmt2 rdf:reifies <<( ex:bob ex:likes ex:carol )>> .
  ex:stmt2 ex:source ex:newspaper .
}}
"""

TRIG_WITH_DEFAULT = f"""\
@prefix ex: <{EX}> .

ex:default_s ex:default_p ex:default_o .

GRAPH <{EX}named> {{
  ex:named_s ex:named_p ex:named_o .
}}
"""

TRIG_NESTED_TT = f"""\
@prefix ex: <{EX}> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

GRAPH <{EX}graph1> {{
  ex:stmt rdf:reifies <<( <<( ex:a ex:b ex:c )>> ex:p ex:o )>> .
}}
"""


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_is_dataset(self):
        from rdflib import Dataset
        ds = StarLayerDataset()
        assert isinstance(ds, Dataset)



# ---------------------------------------------------------------------------
# Parse TriG 1.2
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# StarLayerGraph API on named contexts
# ---------------------------------------------------------------------------

class TestContextAPI:



    def test_same_context_returned_on_repeated_get(self):
        ds = StarLayerDataset()
        ds.parse(data=TRIG_BASIC, format='trig12')
        g1a = ds.get_context(G1)
        g1b = ds.get_context(G1)
        assert g1a is g1b


# ---------------------------------------------------------------------------
# Dataset-wide reification lookups
# ---------------------------------------------------------------------------

TRIG_SAME_REIFIER_TWO_GRAPHS = f"""\
@prefix ex: <{EX}> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

GRAPH <{EX}graph1> {{
  ex:stmt rdf:reifies <<( ex:alice ex:knows ex:bob )>> .
  ex:stmt ex:source ex:sourceA .
}}

GRAPH <{EX}graph2> {{
  ex:stmt rdf:reifies <<( ex:carol ex:likes ex:dana )>> .
  ex:stmt ex:source ex:sourceB .
}}
"""




# ---------------------------------------------------------------------------
# Quad iteration
# ---------------------------------------------------------------------------







class TestDefaultGraphIsAStarLayerGraph:
    """rdflib's own Dataset.__init__ hardcodes self._default_context as a
    plain rdflib.Graph (default_graph/default_context both just return it
    directly) - a real, previously-undiscovered bug: ds.default_graph.add()
    crashed on a real TripleTerm, since plain Graph.add() rejects it as
    "not an rdflib term". Fixed in StarLayerDataset.__init__ by routing
    _default_context through get_context() instead, same as every other
    named context."""


    def test_default_context_is_a_starlayergraph(self):
        import warnings

        ds = StarLayerDataset()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            assert isinstance(ds.default_context, StarLayerGraph)









# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Single-graph format serialization (flattened, no GRAPH blocks)
# ---------------------------------------------------------------------------

class TestSerializeSingleGraphFormats:



    def test_longturtle12_one_triple_per_line(self):
        ds = StarLayerDataset()
        ds.parse(data=TRIG_BASIC, format='trig12')
        out = ds.serialize(format='longturtle12')
        assert 'rdf:reifies <<( ex:alice ex:knows ex:bob )>> .' in out
        assert 'rdf:reifies <<( ex:bob ex:likes ex:carol )>> .' in out






# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# N-Quads 1.2 multi-graph
# ---------------------------------------------------------------------------

NQ_BASIC = (
    f'<{EX}s> <{EX}p> <{EX}o> <{EX}graph1> .\n'
    f'<{EX}stmt1> <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> '
    f'<<( <{EX}alice> <{EX}knows> <{EX}bob> )>> <{EX}graph1> .\n'
    f'<{EX}stmt1> <{EX}confidence> "0.9" <{EX}graph1> .\n'
    f'<{EX}stmt2> <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> '
    f'<<( <{EX}bob> <{EX}likes> <{EX}carol> )>> <{EX}graph2> .\n'
    f'<{EX}stmt2> <{EX}source> <{EX}newspaper> <{EX}graph2> .\n'
)




# ---------------------------------------------------------------------------
# Persistent store lifecycle — open() / close()
# ---------------------------------------------------------------------------

TRIG_TWO_GRAPHS = f"""\
@prefix ex: <{EX}> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

GRAPH <{EX}graph1> {{
  ex:stmt1 rdf:reifies <<( ex:alice ex:knows ex:bob )>> .
}}

GRAPH <{EX}graph2> {{
  ex:stmt2 rdf:reifies <<( ex:bob ex:likes ex:carol )>> .
}}
"""


class TestDatasetStoreLifecycle:
    """Verify open()/close() API using the built-in Memory store.

    The Memory store's open() is a no-op so these tests exercise the API
    contract (registries rebuilt, contexts accessible) without requiring an
    external backend package.
    """

    def test_open_populates_sg_cache(self):
        """open() discovers all contexts and caches StarLayerGraph instances."""
        ds = StarLayerDataset()
        ds.parse(data=TRIG_TWO_GRAPHS, format='trig12')
        ds._sg_cache.clear()
        ds.open('')
        assert URIRef(str(G1)) in ds._sg_cache
        assert URIRef(str(G2)) in ds._sg_cache

    def test_open_rebuilds_tt_registries(self):
        """open() restores TripleTerm registries in each context."""
        ds = StarLayerDataset()
        ds.parse(data=TRIG_TWO_GRAPHS, format='trig12')
        for sg in list(ds._sg_cache.values()):
            sg._tt_nodes.clear()
            sg._tt_registry.clear()
        ds._sg_cache.clear()
        ds.open('')
        assert ds.get_context(G1).has_triple_term(
            URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob')
        )
        assert ds.get_context(G2).has_triple_term(
            URIRef(EX+'bob'), URIRef(EX+'likes'), URIRef(EX+'carol')
        )

    def test_open_invalidates_raw_cache(self):
        """open() clears the raw execution graph cache."""
        ds = StarLayerDataset()
        ds.parse(data=TRIG_TWO_GRAPHS, format='trig12')
        _ = ds._build_raw_execution_graph()
        assert ds._raw_execution_graph is not None
        ds.open('')
        assert ds._raw_execution_graph is None

    def test_close_does_not_raise(self):
        ds = StarLayerDataset()
        ds.open('')
        ds.close()

    def test_close_with_commit(self):
        ds = StarLayerDataset()
        ds.open('')
        ds.close(commit_pending_transaction=True)


# ---------------------------------------------------------------------------
# Raw execution graph cache invalidation on context mutation
# ---------------------------------------------------------------------------

class TestRawCacheInvalidation:
    """add()/addN()/remove() on a context must invalidate the dataset's raw cache."""

    def _ds_with_cache(self):
        ds = StarLayerDataset()
        ds.parse(data=TRIG_TWO_GRAPHS, format='trig12')
        _ = ds._build_raw_execution_graph()   # warm the cache
        assert ds._raw_execution_graph is not None
        return ds

    def test_add_invalidates_cache(self):
        ds = self._ds_with_cache()
        sg = ds.get_context(G1)
        sg.add((URIRef(EX+'x'), URIRef(EX+'p'), URIRef(EX+'y')))
        assert ds._raw_execution_graph is None

    def test_add_triple_term_invalidates_cache(self):
        ds = self._ds_with_cache()
        sg = ds.get_context(G1)
        sg.add((URIRef(EX+'s'), RDF_REIFIES,
                TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))))
        assert ds._raw_execution_graph is None

    def test_addN_invalidates_cache(self):
        ds = self._ds_with_cache()
        sg = ds.get_context(G1)
        sg.addN([(URIRef(EX+'x'), URIRef(EX+'p'), URIRef(EX+'y'), sg)])
        assert ds._raw_execution_graph is None

    def test_remove_invalidates_cache(self):
        ds = self._ds_with_cache()
        sg = ds.get_context(G1)
        sg.remove((URIRef(EX+'stmt1'), RDF_REIFIES, None))
        assert ds._raw_execution_graph is None

    def test_cache_rebuilt_on_next_query(self):
        """After invalidation, the next query rebuilds the cache with fresh data."""
        ds = self._ds_with_cache()
        sg = ds.get_context(G1)
        new_triple = (URIRef(EX+'x'), URIRef(EX+'p'), URIRef(EX+'y'))
        sg.add(new_triple)
        assert ds._raw_execution_graph is None   # invalidated
        # query forces rebuild
        q = f'SELECT ?s ?p ?o WHERE {{ GRAPH <{EX}graph1> {{ ?s ?p ?o }} }}'
        rows = list(ds.query(q))
        assert ds._raw_execution_graph is not None  # rebuilt
        assert any(str(r[0]) == EX+'x' for r in rows)

    def test_unregistered_sg_has_no_callback(self):
        """A StarLayerGraph not part of a dataset has no callback — no error."""
        sg = StarLayerGraph()
        assert sg._invalidate_callback is None
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))  # must not raise


class TestChainingContractMatchesRdflib:
    """rdflib's own ConjunctiveGraph.addN()/Graph.open() both return self;
    these two StarLayerDataset overrides had silently dropped that (fixed
    2026-10-04) - same bug class as StarLayerGraph's own add()/remove()/
    open()/serialize(), see test_starlayer_graph.py's own class of the same
    name."""


    def test_open_returns_self_not_rdflibs_own_status_code(self):
        ds = StarLayerDataset()
        assert ds.open('', create=True) is ds



class TestTriplesChoicesRestoresTripleTerms:
    """Regression, fixed 2026-10-04: triples_choices() wasn't defined on
    this class at all, so it fell through to rdflib's own
    ConjunctiveGraph.triples_choices(), which queries self.store directly
    and bypasses every context's own TripleTerm registry - the raw
    tt:HASH encoding URIRef leaked through unrestored, confirmed live
    side-by-side against this class's own triples() (which has always
    restored correctly)."""

    def _ds_with_reified_tt(self):
        ds = StarLayerDataset()
        ds.default_graph.add(
            (URIRef(EX+'claim'), RDF_REIFIES, TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')))
        )
        return ds

    def test_default_scope_restores_triple_term(self):
        ds = self._ds_with_reified_tt()
        (result,) = list(ds.triples_choices((None, RDF_REIFIES, [None])))
        assert isinstance(result[2], TripleTerm)

    def test_default_union_restores_triple_term(self):
        ds = StarLayerDataset(default_union=True)
        g1 = ds.get_context(URIRef(EX+'g1'))
        g1.add((URIRef(EX+'claim'), RDF_REIFIES, TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))))
        (result,) = list(ds.triples_choices((None, RDF_REIFIES, [None])))
        assert isinstance(result[2], TripleTerm)

    def test_explicit_context_restores_triple_term(self):
        ds = StarLayerDataset()
        g1 = ds.get_context(URIRef(EX+'g1'))
        g1.add((URIRef(EX+'claim'), RDF_REIFIES, TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))))
        (result,) = list(ds.triples_choices((None, RDF_REIFIES, [None]), context=g1))
        assert isinstance(result[2], TripleTerm)
