"""
tests/graph/integration/test_oxigraph_store_rdf12.py

StarLayerGraph/StarLayerDataset backed by oxrdflib's standard OxigraphStore
(an in-process pyoxigraph engine) in rdf-1.2 native mode - real triple terms
and SPARQL 1.2, no HTTP. See starlayer.graph.backends.native_oxigraph.

The store is chosen explicitly at construction (store=..., backend='rdf-1.2');
nothing here relies on, or sets, a global default. No live server needed, so
no pytest.mark.integration.

Requires: pip install oxrdflib pyoxigraph
"""

import pytest
from rdflib import RDF, RDFS, BNode, Literal, Namespace, URIRef
from rdflib.namespace import OWL
from starlayer.graph.graph import StarLayerDataset, StarLayerGraph
from starlayer.graph.graph.entailment_regimes import ENTAILMENT
from starlayer.graph.model.dirlangstring import DirLangString
from starlayer.graph.model.triple import TripleTerm

pyoxigraph = pytest.importorskip('pyoxigraph')
OxigraphStore = pytest.importorskip('oxrdflib').OxigraphStore

def embedded_oxigraph_store(path=None):
    """A standard oxrdflib OxigraphStore wrapping a fresh pyoxigraph engine."""
    return OxigraphStore(store=pyoxigraph.Store(path))

EX       = 'http://example.org/'
RDF_NS   = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
RDF_REIF = URIRef(RDF_NS + 'reifies')


@pytest.fixture
def sg():
    """Fresh StarLayerGraph backed by an embedded pyoxigraph store in
    rdf-1.2 native mode."""
    g = StarLayerGraph(store=embedded_oxigraph_store(), backend='rdf-1.2')
    g.bind('ex', EX)
    yield g
    g.close()


class TestEmbeddedRoundTrip:

    def test_plain_triple_write_read(self, sg):
        s, p, o = URIRef(EX + 'alice'), URIRef(EX + 'knows'), URIRef(EX + 'bob')
        sg.add((s, p, o))
        assert (s, p, o) in sg

    def test_triple_term_write_read(self, sg):
        tt   = TripleTerm(URIRef(EX + 'alice'), URIRef(EX + 'knows'), URIRef(EX + 'bob'))
        stmt = URIRef(EX + 'stmt1')
        sg.add((stmt, RDF_REIF, tt))
        results = list(sg.triples((stmt, RDF_REIF, None)))
        assert len(results) == 1
        _, _, restored = results[0]
        assert isinstance(restored, TripleTerm)
        assert restored == tt

    def test_triple_term_in_subject_rejected(self, sg):
        tt = TripleTerm(URIRef(EX + 'a'), URIRef(EX + 'b'), URIRef(EX + 'c'))
        with pytest.raises(ValueError, match='subject position'):
            sg.add((tt, URIRef(EX + 'prop'), URIRef(EX + 'val')))

    def test_wildcard_triples(self, sg):
        sg.add((URIRef(EX + 's1'), URIRef(EX + 'p'), URIRef(EX + 'o1')))
        sg.add((URIRef(EX + 's2'), URIRef(EX + 'p'), URIRef(EX + 'o2')))
        results = list(sg.triples((None, URIRef(EX + 'p'), None)))
        assert len(results) == 2

    def test_contains(self, sg):
        s, p, o = URIRef(EX + 'alice'), URIRef(EX + 'knows'), URIRef(EX + 'bob')
        assert (s, p, o) not in sg
        sg.add((s, p, o))
        assert (s, p, o) in sg

    def test_no_encoding_triples_visible(self, sg):
        """Native rdf-1.2 mode stores no tt:HASH encoding triples."""
        tt = TripleTerm(URIRef(EX + 'a'), URIRef(EX + 'b'), URIRef(EX + 'c'))
        sg.add((URIRef(EX + 'stmt'), RDF_REIF, tt))
        predicates = {p for _, p, _ in sg.triples((None, None, None))}
        assert URIRef(RDF_NS + 'subject')   not in predicates
        assert URIRef(RDF_NS + 'predicate') not in predicates
        assert URIRef(RDF_NS + 'object')    not in predicates

    def test_remove(self, sg):
        s, p, o = URIRef(EX + 'alice'), URIRef(EX + 'knows'), URIRef(EX + 'bob')
        sg.add((s, p, o))
        sg.remove((s, p, o))
        assert (s, p, o) not in sg


class TestEmbeddedTurtle12Parse:
    """.parse(format='turtle12') on an embedded native-backend graph -
    mirrors test_oxigraph_backend.py's own TestOxigraphTurtle12Parse
    (the same StarLayerGraph.parse() codepath, decode_tt_encoded_triples
    then _native_add_many(), regardless of which transport _native_add_many
    itself ultimately dispatches to)."""

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


class TestEmbeddedBoundBnodeQuery:
    """Mirrors test_oxigraph_backend.py's own TestOxigraphBoundBnodeQuery -
    a bound BNode learned from an earlier wildcard read must still match in
    a later pattern query, for content loaded via .parse()/.addN() (which
    writes real, unskolemized blank nodes via _native_add_many())."""

    def test_bound_bnode_object_query_after_parse(self, sg):
        SH_NS = 'http://www.w3.org/ns/shacl#'
        sg.parse(data='''
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:PersonRule a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:isPerson ; sh:object true ] .
        ''', format='turtle12')
        bnode = next(sg.objects(None, URIRef(SH_NS + 'rule')))
        types = list(sg.objects(bnode, RDF.type))
        assert types == [URIRef(SH_NS + 'TripleRule')]

    def test_bound_bnode_subject_query_matches_only_the_correct_node(self, sg):
        sg.parse(data='''
            @prefix ex: <http://example.org/> .
            ex:a ex:hasThing [ ex:label "first" ] .
            ex:b ex:hasThing [ ex:label "second" ] .
        ''', format='turtle12')
        first_bnode = next(sg.objects(URIRef(EX + 'a'), URIRef(EX + 'hasThing')))
        second_bnode = next(sg.objects(URIRef(EX + 'b'), URIRef(EX + 'hasThing')))
        assert first_bnode != second_bnode
        assert list(sg.objects(first_bnode, URIRef(EX + 'label'))) == [Literal('first')]
        assert list(sg.objects(second_bnode, URIRef(EX + 'label'))) == [Literal('second')]


class TestEmbeddedLen:

    def test_graph_len(self, sg):
        sg.add((URIRef(EX + 'a'), URIRef(EX + 'b'), URIRef(EX + 'c')))
        sg.add((URIRef(EX + 'x'), URIRef(EX + 'y'), URIRef(EX + 'z')))
        assert len(sg) == 2

    def test_dataset_len_sums_across_all_graphs(self):
        """StarLayerDataset.__len__'s native branch must also work over the
        embedded transport (see starlayer_dataset.py's __len__ fix) - 1
        triple in the default graph plus 1 each in two named graphs."""
        store = embedded_oxigraph_store()
        ds = StarLayerDataset(store=store, backend='rdf-1.2')
        ds.add((URIRef(EX + 'default'), URIRef(EX + 'p'), URIRef(EX + 'o')))
        ds.get_context(URIRef(EX + 'g1')).add((URIRef(EX + 'a'), URIRef(EX + 'p'), URIRef(EX + 'o')))
        ds.get_context(URIRef(EX + 'g2')).add((URIRef(EX + 'b'), URIRef(EX + 'p'), URIRef(EX + 'o')))
        assert len(ds) == 3
        ds.close()


class TestEmbeddedCloseReopen:
    """EmbeddedOxigraphStore.close() must actually release pyoxigraph's
    RocksDB single-writer lock, not just no-op - confirmed live elsewhere
    this session that the lock is held for the Store object's own lifetime,
    released only on GC, with no close() on pyoxigraph's own Store at all.
    A silent no-op here would make this test hang or raise
    intermittently (GC-timing-dependent), not reliably."""

    def test_close_releases_lock_for_reopen_on_same_path(self, tmp_path):
        path = str(tmp_path / 'ox-embedded-test-db')
        store1 = embedded_oxigraph_store(path)
        g1 = StarLayerGraph(store=store1, backend='rdf-1.2')
        g1.add((URIRef(EX + 'a'), URIRef(EX + 'b'), URIRef(EX + 'c')))
        g1.close()

        store2 = embedded_oxigraph_store(path)
        g2 = StarLayerGraph(store=store2, backend='rdf-1.2')
        assert (URIRef(EX + 'a'), URIRef(EX + 'b'), URIRef(EX + 'c')) in g2
        g2.close()


# ---------------------------------------------------------------------------
# Derived graphs are created like their source
# ---------------------------------------------------------------------------

REIFIES = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')


def _oxigraph_graph():
    g = StarLayerGraph(store=embedded_oxigraph_store(), backend='rdf-1.2')
    g.bind('ex', Namespace(EX))
    return g


def _is_oxigraph_backed(g) -> bool:
    return type(g.store).__name__ == 'OxigraphStore' and g._backend == 'rdf-1.2'


class TestEmptyLike:
    def test_oxigraph_source_gives_independent_oxigraph(self):
        src = _oxigraph_graph()
        new = src.empty_like()
        assert _is_oxigraph_backed(new)
        assert new.store is not src.store
        assert len(new) == 0
        new.add((URIRef(EX + 'a'), URIRef(EX + 'p'), Literal('x')))
        assert len(src) == 0                      # the two stores are independent

    def test_namespaces_are_copied(self):
        assert 'ex' in dict(_oxigraph_graph().empty_like().namespaces())

    def test_default_source_gives_default_graph(self):
        new = StarLayerGraph().empty_like()
        assert not new._is_native
        assert type(new.store).__name__ == 'Memory'


class TestQueryConstructIsCreatedLikeTheSource:
    def test_graph_construct_result_is_oxigraph_backed_with_triple_terms(self):
        g = _oxigraph_graph()
        tt = TripleTerm(URIRef(EX + 's'), URIRef(EX + 'p'), URIRef(EX + 'o'))
        g.add((URIRef(EX + 'r'), REIFIES, tt))
        g.add((URIRef(EX + 'a'), URIRef(EX + 'p'), Literal('x')))
        result = g.query('CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }').graph
        assert _is_oxigraph_backed(result)
        assert result.store is not g.store
        assert set(result) == set(g)

    def test_dataset_construct_result_is_oxigraph_backed(self):
        ds = StarLayerDataset(store=embedded_oxigraph_store(), backend='rdf-1.2')
        ds.default_graph.add((URIRef(EX + 'a'), URIRef(EX + 'p'), Literal('x')))
        result = ds.query('CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }').graph
        assert _is_oxigraph_backed(result)
        assert len(result) == 1


@pytest.mark.skipif(not pytest.importorskip('owlrl', reason='owlrl not installed'), reason='owlrl')
class TestInferIsCreatedLikeTheSource:
    @staticmethod
    def _data(g):
        g.add((URIRef(EX + 'A'), RDFS.subClassOf, URIRef(EX + 'B')))
        g.add((URIRef(EX + 'x'), RDF.type, URIRef(EX + 'A')))
        return g

    @pytest.mark.parametrize('mode', ['full', 'delta'])
    def test_result_is_oxigraph_backed_and_source_untouched(self, mode):
        src = self._data(_oxigraph_graph())
        before = set(src)
        out = src.infer(ENTAILMENT.RDFS, mode=mode)
        assert _is_oxigraph_backed(out)
        assert out.store is not src.store
        assert set(src) == before
        assert 'ex' in dict(out.namespaces())

    @pytest.mark.parametrize('mode', ['full', 'delta'])
    def test_matches_the_default_store_result_exactly(self, mode):
        ox_out = self._data(_oxigraph_graph()).infer(ENTAILMENT.RDFS, mode=mode)
        default_out = self._data(StarLayerGraph()).infer(ENTAILMENT.RDFS, mode=mode)
        assert set(ox_out) == set(default_out)

    def test_default_source_still_yields_default_graph(self):
        out = self._data(StarLayerGraph()).infer(ENTAILMENT.RDFS)
        assert not out._is_native

    def test_in_place_mutates_the_source_and_returns_it(self):
        src = self._data(_oxigraph_graph())
        assert src.infer(ENTAILMENT.RDFS, mode='in-place') is src
        assert (URIRef(EX + 'x'), RDF.type, URIRef(EX + 'B')) in src


# ---------------------------------------------------------------------------
# Known Oxigraph engine bug: SPARQL `=` panics on any dirLangString term
# (docs/upstream-issues/oxigraph-upstream-issues.md, Issue 1)
# ---------------------------------------------------------------------------
#
# Why this lives here: the dirLangString coverage elsewhere against Oxigraph
# (cross-backend parity's write/read and function scenarios, the W3C
# lang-basedir fixtures) never compares two dirLangString values with `=`, the
# one operation that aborts the whole process. So the engine's weak spot sat
# in a gap between tests that all passed. It was first noticed only because a
# since-removed diagnostic redirected the default-store test
# tests/graph/unit/test_dirlangstring.py::TestSparqlFunctions::
# test_strlangdir_constructs_matching_value onto Oxigraph.

_TITLE = 'http://example.org/title'

_ABORT_REPRO = '''
import pyoxigraph
from oxrdflib import OxigraphStore
from starlayer.graph.graph import StarLayerGraph
from starlayer.graph.model.dirlangstring import DirLangString
from rdflib import URIRef

g = StarLayerGraph(store=OxigraphStore(store=pyoxigraph.Store()), backend='rdf-1.2')
g.add((URIRef('http://example.org/s'), URIRef('{title}'), DirLangString('HTML page', 'en', 'ltr')))
list(g.query({query!r}))
print('SURVIVED')
'''


class TestDirLangStringEquality:
    def test_sameterm_on_dirlangstring_works(self):
        """The workaround the upstream-issue doc recommends: sameTerm() is
        exact-term equality, a different operator, and is unaffected."""
        g = StarLayerGraph(store=embedded_oxigraph_store(), backend='rdf-1.2')
        g.add((URIRef(EX + 's'), URIRef(_TITLE), DirLangString('HTML page', 'en', 'ltr')))
        rows = list(g.query(f'SELECT ?s WHERE {{ ?s <{_TITLE}> ?t . FILTER(sameTerm(?t, ?t)) }}'))
        assert len(rows) == 1

    @pytest.mark.parametrize('query', [
        f'SELECT ?s WHERE {{ ?s <{_TITLE}> ?t . FILTER(?t = ?t) }}',
        f'SELECT ?s WHERE {{ ?s <{_TITLE}> ?t . FILTER(?t = STRLANGDIR("HTML page", "en", "ltr")) }}',
    ], ids=['self_equality', 'strlangdir_comparison'])
    def test_value_equality_aborts_the_process_known_engine_bug(self, query):
        """Documents the engine bug by running it in a subprocess (a panic is
        a hard process abort, not a catchable exception). If this starts
        PASSING the query - Oxigraph fixed it upstream - update
        docs/upstream-issues/oxigraph-upstream-issues.md and replace this
        test with a plain equality assertion."""
        import subprocess
        import sys
        proc = subprocess.run(
            [sys.executable, '-c', _ABORT_REPRO.format(title=_TITLE, query=query)],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode == 0 and 'SURVIVED' in proc.stdout:
            pytest.fail(
                "Oxigraph no longer aborts on `=` over a dirLangString - the upstream bug "
                "appears fixed. Update docs/upstream-issues/oxigraph-upstream-issues.md "
                "(Issue 1) and turn this into a normal equality test."
            )
        assert proc.returncode != 0
        assert 'unreachable' in proc.stderr or 'panicked' in proc.stderr or 'Abort' in proc.stderr
