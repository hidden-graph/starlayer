"""
tests/graph/integration/test_oxigraph_embedded_backend.py

Tests for StarLayerGraph/StarLayerDataset backed by an embedded,
in-process pyoxigraph.Store via rdf-1.2 native mode - see
starlayer.graph.backends.native_pyoxigraph.

Mirrors test_oxigraph_backend.py's own representative scenarios (same
embedded-vs-HTTP engine, just a different transport), but needs no live
server and no pytest.mark.integration: each embedded_oxigraph_store() is a
fresh, ephemeral, in-process store (path=None - pyoxigraph's own in-memory
mode), so there's nothing to start, stop, or clear between tests.

Requires the optional pyoxigraph dependency:
    pip install starlayer.graph[oxigraph-embedded]

Run:
    .venv/bin/pytest tests/graph/integration/test_oxigraph_embedded_backend.py -v
"""

import pytest
from rdflib import RDF, RDFS, BNode, Literal, URIRef
from rdflib.namespace import OWL
from starlayer.graph.graph import StarLayerDataset, StarLayerGraph
from starlayer.graph.graph.entailment_regimes import ENTAILMENT
from starlayer.graph.model.triple import TripleTerm

pytest.importorskip('pyoxigraph')

from starlayer.graph.backends.native_pyoxigraph import embedded_oxigraph_store  # noqa: E402

try:
    import owlrl  # noqa: F401
    _OWLRL_AVAILABLE = True
except ImportError:
    _OWLRL_AVAILABLE = False

owlrl_extra = pytest.mark.skipif(
    not _OWLRL_AVAILABLE,
    reason='owlrl not installed — install with: pip install -e ".[reasoning]"',
)

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


@owlrl_extra
class TestEmbeddedEntailmentNoSpuriousTyping:
    """The same spurious-typing bug fixed for the generic (in-memory) path
    in test_infer.py, re-verified against the native-optimized
    decompose_for_entailment() in native.py - see that function's own
    docstring and starlayer/graph/CLAUDE.md's 2026-10-16 entry for the full
    account, including the documented sameAs-dedup trade-off this native
    path accepts (query 2 never fetches a triple term's own value, so
    unlike the generic path it cannot deduplicate placeholders by value)."""

    def test_term_only_inside_a_triple_term_is_not_spuriously_typed_resource(self, sg):
        sg.add((URIRef(EX + 'manages'), RDFS.domain, URIRef(EX + 'Manager')))
        sg.add((URIRef(EX + 'manages'), RDFS.range, URIRef(EX + 'Employee')))
        sg.add_reification(
            URIRef(EX + 'claim1'),
            TripleTerm(URIRef(EX + 'bob'), URIRef(EX + 'manages'), URIRef(EX + 'alice')),
        )

        closed = sg.infer(entailment=ENTAILMENT.RDFS)

        assert (URIRef(EX + 'bob'), RDF.type, RDFS.Resource) not in closed
        assert (URIRef(EX + 'alice'), RDF.type, RDFS.Resource) not in closed
        assert (URIRef(EX + 'claim1'), RDF.type, RDFS.Resource) in closed
        assert (URIRef(EX + 'manages'), RDFS.domain, URIRef(EX + 'Manager')) in closed
        assert (URIRef(EX + 'manages'), RDFS.range, URIRef(EX + 'Employee')) in closed

    def test_identical_triple_term_value_reified_twice_does_not_derive_sameas(self, sg):
        # The accepted trade-off, asserted explicitly (not just reasoned
        # about) so a future change to query 2 that silently starts
        # deduplicating doesn't go unnoticed either way: unlike the
        # generic/in-memory path (see
        # test_infer.py::test_identical_triple_term_value_reified_twice_still_derives_sameas),
        # a native graph's two reifiers of the identical triple-term value
        # get two different, undeduplicated placeholders - owl:sameAs is
        # NOT derived between them.
        sg.add((RDF_REIF, RDF.type, OWL.InverseFunctionalProperty))
        tt = TripleTerm(URIRef(EX + 'bob'), URIRef(EX + 'manages'), URIRef(EX + 'alice'))
        sg.add_reification(URIRef(EX + 'reifier1'), tt)
        sg.add_reification(URIRef(EX + 'reifier2'), tt)

        closed = sg.infer(entailment=ENTAILMENT["OWL-RDF-Based"])

        assert (URIRef(EX + 'reifier1'), OWL.sameAs, URIRef(EX + 'reifier2')) not in closed

    def test_decompose_for_entailment_never_fetches_triple_term_content(self, sg):
        # Direct check that the optimization is actually happening, not
        # just "correct by accident": decompose_for_entailment() mints a
        # fresh, unconnected placeholder per triple-term-valued row - no
        # tt:subject/predicate/object-style edges (or any edge at all)
        # ever added describing the placeholder's own structure, confirming
        # query 2's result never carried the triple term's content back.
        from starlayer.graph.backends.native import decompose_for_entailment

        sg.add_reification(
            URIRef(EX + 'claim1'),
            TripleTerm(URIRef(EX + 'bob'), URIRef(EX + 'manages'), URIRef(EX + 'alice')),
        )

        decomposed, placeholders = decompose_for_entailment(sg)

        assert len(placeholders) == 1
        placeholder = next(iter(placeholders))
        # The placeholder appears exactly once, as the object of the real
        # reification triple - never as a subject or object of anything
        # else (which is what a tt:subject/predicate/object expansion, or
        # any other leak of the triple term's own content, would look
        # like).
        as_subject = list(decomposed.triples((placeholder, None, None)))
        as_object = list(decomposed.triples((None, None, placeholder)))
        assert as_subject == []
        assert as_object == [(URIRef(EX + 'claim1'), RDF_REIF, placeholder)]
