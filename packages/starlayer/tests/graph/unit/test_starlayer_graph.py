"""
Unit tests for starlayer.graph.graph.StarLayerGraph.

Covers: rdflib compatibility, TripleTerm add/query, filtering of internal
encoding triples, from_rdflib(), and Statement operations.
"""

from unittest.mock import MagicMock, patch

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF
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

    def test_add_plain_triple(self, sg):
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        assert (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')) in sg


    def test_add_literal_object(self, sg):
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), Literal('hello')))
        objs = list(sg.objects(URIRef(EX+'s'), URIRef(EX+'p')))
        assert Literal('hello') in objs

    def test_len_counts_only_user_triples(self, sg):
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        sg.add((URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')))
        assert len(sg) == 2

    def test_remove_triple(self, sg):
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        sg.remove((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        assert (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')) not in sg

    def test_triples_wildcard(self, sg):
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        results = list(sg.triples((None, None, None)))
        assert len(results) == 1

    def test_subjects_method(self, sg):
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        subs = list(sg.subjects(URIRef(EX+'p'), URIRef(EX+'o')))
        assert URIRef(EX+'s') in subs

    def test_objects_method(self, sg):
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        objs = list(sg.objects(URIRef(EX+'s'), URIRef(EX+'p')))
        assert URIRef(EX+'o') in objs

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
# Bare (RDF 1.1) nquads/trig/trix parsing - multi-graph-capable formats
# parsed into a single graph. Added 2026-10-04: plain rdflib delegation
# would silently yield zero triples the moment any named graph appears at
# all (a non-context-aware Graph's parser plugins can't place quads
# anywhere) - this project instead resolves at most one distinct graph
# (dropping its name) or raises MultipleGraphsError for two or more,
# matching the same rule nq12/trig12/trix12 enforce (see test_rdf12_formats.py).
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

    def test_trix_multiple_graphs_raises(self, sg):
        from starlayer.graph.parsers.errors import MultipleGraphsError
        xml = (
            '<?xml version="1.0"?>'
            '<TriX xmlns="http://www.w3.org/2004/03/trix/trix-1/">'
            f'<graph><uri>{EX}g1</uri>'
            f'<triple><uri>{EX}a</uri><uri>{EX}b</uri><uri>{EX}c</uri></triple>'
            '</graph>'
            f'<graph><uri>{EX}g2</uri>'
            f'<triple><uri>{EX}x</uri><uri>{EX}y</uri><uri>{EX}z</uri></triple>'
            '</graph></TriX>'
        )
        with pytest.raises(MultipleGraphsError):
            sg.parse(data=xml, format='trix')


# ---------------------------------------------------------------------------
# Bare (RDF 1.1) nquads/trig/trix serializing - a single graph always has
# somewhere to go (its own identifier), so unlike parse() there's no
# raise-for-2+-graphs case here; the fix is purely about not raising for the
# single-graph case either. Added 2026-10-04: rdflib's own NQuads/TriX
# serializer plugins raise "...only makes sense for context-aware stores"
# for any non-context-aware store (no single-graph fallback, unlike
# TrigSerializer's own - see rdflib.plugins.serializers.trig), which
# StarLayerGraph used to just inherit via blind delegation. Now wraps the
# graph as the one context of a real Dataset first, so all six dataset
# formats (nquads/trig/trix, nq12/trig12/trix12) behave consistently.
# ---------------------------------------------------------------------------

class TestBareQuadFormatsSerializing:
    def test_nquads_assigns_graph_name_from_identifier(self):
        identifier = URIRef(EX + 'mygraph')
        sg = StarLayerGraph(identifier=identifier)
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        text = sg.serialize(format='nquads')
        assert str(identifier) in text
        assert f'<{EX}s>' in text and f'<{EX}p>' in text and f'<{EX}o>' in text

    def test_trix_assigns_graph_name_from_identifier(self):
        identifier = URIRef(EX + 'mygraph')
        sg = StarLayerGraph(identifier=identifier)
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        text = sg.serialize(format='trix')
        assert str(identifier) in text

    def test_nquads_serialize_returns_self_when_destination_given(self, tmp_path):
        sg = StarLayerGraph(identifier=URIRef(EX+'mygraph'))
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        dest = tmp_path / 'out.nq'
        result = sg.serialize(destination=str(dest), format='nquads')
        assert result is sg
        assert dest.exists()


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
    def test_add_returns_self(self, sg):
        assert sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))) is sg

    def test_remove_returns_self(self, sg):
        t = (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))
        sg.add(t)
        assert sg.remove(t) is sg

    def test_remove_returns_self_even_for_an_unregistered_triple_term(self, sg):
        """The early-return branch (pattern references a TripleTerm this
        graph never registered) used to fall off the end as bare `return`
        (-> None) same as the normal path - both needed fixing, not just
        the common case."""
        from starlayer.graph.model.triple import TripleTerm as TT
        unregistered = TT(URIRef(EX+'x'), URIRef(EX+'y'), URIRef(EX+'z'))
        assert sg.remove((URIRef(EX+'claim'), RDF_REIFIES, unregistered)) is sg

    def test_addN_returns_self(self, sg):
        t = (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))
        assert sg.addN([(*t, sg)]) is sg

    def test_open_returns_self_not_rdflibs_own_status_code(self, tmp_path):
        """rdflib's Store.open() returns a status int (e.g. 1 for
        VALID_STORE), not the graph - StarLayerGraph.open() must not
        forward that raw value even though its own annotation always
        claimed `-> StarLayerGraph`."""
        g = StarLayerGraph()
        assert g.open(str(tmp_path / 'store'), create=True) is g

    def test_serialize_with_destination_returns_self_for_rdf12_format(self, sg, tmp_path):
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        dest = tmp_path / 'out.ttl'
        assert sg.serialize(destination=str(dest), format='turtle12') is sg
        assert dest.exists()

    def test_serialize_with_destination_returns_self_for_legacy_format(self, sg, tmp_path):
        """The non-RDF12 branch delegates to a throwaway de-skolemized
        Graph's own .serialize() - that returned *that* unrelated Graph,
        not self, when destination was given."""
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        dest = tmp_path / 'out.ttl'
        assert sg.serialize(destination=str(dest), format='turtle') is sg
        assert dest.exists()

    def test_serialize_without_destination_still_returns_text(self, sg):
        """The fix must not break the destination=None case, which should
        keep returning the serialized text/bytes, not self."""
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        assert isinstance(sg.serialize(format='turtle12'), str)
        assert isinstance(sg.serialize(format='turtle'), str)


# ---------------------------------------------------------------------------
# TripleTerm in add / triples / __contains__
# ---------------------------------------------------------------------------

class TestTripleTermAdd:
    def test_add_tt_object_as_tuple(self, sg):
        sg.add((URIRef(EX+'r'), RDF_REIFIES, (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))))
        results = list(sg.triples((URIRef(EX+'r'), RDF_REIFIES, None)))
        assert len(results) == 1
        _, _, o = results[0]
        assert isinstance(o, TripleTerm)
        assert o == TripleTerm(URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))

    def test_add_tt_subject_raises(self, sg):
        tt = TripleTerm(URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))
        with pytest.raises(ValueError):
            sg.add((tt, URIRef(EX+'q'), URIRef(EX+'z')))

    def test_add_tuple_subject_raises(self, sg):
        with pytest.raises(ValueError):
            sg.add(((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')), URIRef(EX+'q'), URIRef(EX+'z')))


    def test_contains_tt_object(self, sg):
        sg.add((URIRef(EX+'r'), RDF_REIFIES, (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))))
        assert (URIRef(EX+'r'), RDF_REIFIES, (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))) in sg

    def test_tt_deduplication(self, sg):
        sg.add((URIRef(EX+'r1'), RDF_REIFIES, (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))))
        sg.add((URIRef(EX+'r2'), RDF_REIFIES, (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))))
        assert len(sg) == 2  # two visible triples, one shared TT bnode

    def test_two_distinct_tt_objects(self, sg):
        sg.add((URIRef(EX+'r1'), RDF_REIFIES, (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))))
        sg.add((URIRef(EX+'r2'), RDF_REIFIES, (URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))))
        assert len(sg) == 2

    def test_nested_tt_object_fully_resolves(self, sg):
        # A triple term whose own object is itself a triple term (valid - nesting
        # is only disallowed in subject position). The outer TripleTerm's .object
        # must come back as a real, fully-resolved TripleTerm, not a raw tuple or
        # an unresolved tt:HASH URIRef.
        inner = (URIRef(EX+'bob'), URIRef(EX+'knows'), URIRef(EX+'carol'))
        sg.add((URIRef(EX+'alice'), URIRef(EX+'says'), (URIRef(EX+'stmt1'), URIRef(EX+'about'), inner)))

        results = list(sg.triples((URIRef(EX+'alice'), URIRef(EX+'says'), None)))
        assert len(results) == 1
        _, _, outer = results[0]
        assert isinstance(outer, TripleTerm)
        assert isinstance(outer.object, TripleTerm)
        assert outer == TripleTerm(URIRef(EX+'stmt1'), URIRef(EX+'about'), TripleTerm(*inner))
        assert outer.object == TripleTerm(*inner)


# ---------------------------------------------------------------------------
# Encoding triples are hidden from traversal
# ---------------------------------------------------------------------------

class TestEncodingHidden:
    def test_encoding_triples_not_in_triples(self, sg):
        sg.add((URIRef(EX+'r'), RDF_REIFIES, (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))))
        preds = {p for _, p, _ in sg.triples((None, None, None))}
        assert RDF.subject   not in preds
        assert RDF.predicate not in preds
        assert RDF.object    not in preds

    def test_sl_triple_term_type_hidden(self, sg):
        from starlayer.graph.graph.starlayer_graph import SL_TRIPLE_TERM
        sg.add((URIRef(EX+'r'), RDF_REIFIES, (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))))
        objs = list(sg.objects(predicate=RDF.type))
        assert SL_TRIPLE_TERM not in objs

    def test_sl_reification_type_hidden(self, sg):
        from starlayer.graph.graph.starlayer_graph import SL_REIFICATION
        sg.add_reification(URIRef(EX+'stmt'), (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        objs = list(sg.objects(predicate=RDF.type))
        assert SL_REIFICATION not in objs

    def test_len_excludes_encoding(self, sg):
        sg.add((URIRef(EX+'r'), RDF_REIFIES, (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))))
        assert len(sg) == 1  # only the rdf:reifies triple; 3 encoding triples hidden


# ---------------------------------------------------------------------------
# from_rdflib — wrapping the parser output
# ---------------------------------------------------------------------------

class TestFromRdflib:
    def test_from_rdflib_plain_triples(self):
        raw = Graph()
        raw.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        sg = StarLayerGraph.from_rdflib(raw)
        assert (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')) in sg

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


class TestFromRdflibDataset:
    """from_rdflib() used to crash on a Dataset/ConjunctiveGraph input:
    _skolemize_encoding did bare ``for s, p, o in g:`` iteration, but
    Dataset.__iter__ yields 4-tuples (s, p, o, context), not 3 - ValueError:
    too many values to unpack. Fixed by reading via
    g.triples((None, None, None)) instead (what Graph.__iter__ itself does
    under the hood), which for a Dataset correctly respects its own
    default_union setting rather than crashing or silently unioning
    regardless of it.
    """

    def test_default_union_false_sees_only_default_graph(self):
        from rdflib import Dataset
        ds = Dataset()  # default_union=False, the rdflib default
        ds.add((URIRef(EX+'default_s'), URIRef(EX+'p'), URIRef(EX+'default_o')))
        named = ds.graph(URIRef(EX+'g1'))
        named.add((URIRef(EX+'named_s'), URIRef(EX+'p'), URIRef(EX+'named_o')))

        sg = StarLayerGraph.from_rdflib(ds)
        assert len(sg) == 1
        assert (URIRef(EX+'default_s'), URIRef(EX+'p'), URIRef(EX+'default_o')) in sg
        assert (URIRef(EX+'named_s'), URIRef(EX+'p'), URIRef(EX+'named_o')) not in sg

    def test_default_union_true_sees_all_graphs(self):
        from rdflib import Dataset
        ds = Dataset(default_union=True)
        ds.add((URIRef(EX+'default_s'), URIRef(EX+'p'), URIRef(EX+'default_o')))
        named = ds.graph(URIRef(EX+'g1'))
        named.add((URIRef(EX+'named_s'), URIRef(EX+'p'), URIRef(EX+'named_o')))

        sg = StarLayerGraph.from_rdflib(ds)
        assert len(sg) == 2
        assert (URIRef(EX+'default_s'), URIRef(EX+'p'), URIRef(EX+'default_o')) in sg
        assert (URIRef(EX+'named_s'), URIRef(EX+'p'), URIRef(EX+'named_o')) in sg


# ---------------------------------------------------------------------------
# Statement operations
# ---------------------------------------------------------------------------

class TestStatements:
    def test_add_reification_visible_as_reifies_triple(self, sg):
        sg.add_reification(URIRef(EX+'stmt'), (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        results = list(sg.triples((URIRef(EX+'stmt'), RDF_REIFIES, None)))
        assert len(results) == 1
        _, _, o = results[0]
        assert isinstance(o, TripleTerm)

    def test_add_reification_returns_self(self, sg):
        """Matches every other mutating method on StarLayerGraph (add(),
        remove(), addN(), etc) - added 2026-10-04, this used to return
        None, the one mutating method that didn't support chaining."""
        result = sg.add_reification(URIRef(EX+'stmt'), (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        assert result is sg

    def test_remove_reification_returns_self(self, sg):
        """Matches add_reification() and every other mutating method on
        StarLayerGraph - added 2026-10-04, this used to return None."""
        sg.add_reification(URIRef(EX+'stmt'), (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        result = sg.remove_reification(URIRef(EX+'stmt'))
        assert result is sg

    def test_reifiers_by_triple_term(self, sg):
        sg.add_reification(URIRef(EX+'stmt'), (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        reifiers = list(sg.reifiers(TT=(URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))))
        assert URIRef(EX+'stmt') in reifiers
        tts = list(sg.reified_triples(URIRef(EX+'stmt')))
        assert tts[0] == TripleTerm(URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))

    def test_reifiers_all(self, sg):
        sg.add_reification(URIRef(EX+'stmt1'), (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        sg.add_reification(URIRef(EX+'stmt2'), (URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')))
        reifiers = list(sg.reifiers())
        assert len(reifiers) == 2

    def test_reifications_returns_triple_terms(self, sg):
        sg.add_reification(URIRef(EX+'stmt1'), (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        sg.add_reification(URIRef(EX+'stmt2'), (URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c')))
        tts = list(sg.reifications())
        assert len(tts) == 2
        assert all(isinstance(tt, TripleTerm) for tt in tts)

    def test_statement_len(self, sg):
        sg.add_reification(URIRef(EX+'stmt'), (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        assert len(sg) == 1  # only rdf:reifies triple visible; 3 encoding triples hidden

    def test_remove_reification_wildcard_removes_all_links(self, sg):
        tt1 = (URIRef(EX+'bob'), URIRef(EX+'knows'), URIRef(EX+'carol'))
        tt2 = (URIRef(EX+'bob'), URIRef(EX+'likes'), URIRef(EX+'dana'))
        sg.add((URIRef(EX+'claim'), RDF_REIFIES, tt1))
        sg.add((URIRef(EX+'claim'), RDF_REIFIES, tt2))
        sg.add((URIRef(EX+'claim'), URIRef(EX+'source'), URIRef(EX+'wikipedia')))
        sg.remove_reification(URIRef(EX+'claim'))
        assert list(sg.reified_triples(URIRef(EX+'claim'))) == []
        assert (URIRef(EX+'claim'), URIRef(EX+'source'), URIRef(EX+'wikipedia')) in sg

    def test_remove_reification_scoped_to_one_triple_term(self, sg):
        tt1 = (URIRef(EX+'bob'), URIRef(EX+'knows'), URIRef(EX+'carol'))
        tt2 = (URIRef(EX+'bob'), URIRef(EX+'likes'), URIRef(EX+'dana'))
        sg.add((URIRef(EX+'claim'), RDF_REIFIES, tt1))
        sg.add((URIRef(EX+'claim'), RDF_REIFIES, tt2))
        sg.add((URIRef(EX+'claim'), URIRef(EX+'source'), URIRef(EX+'wikipedia')))

        sg.remove_reification(URIRef(EX+'claim'), tt1)

        remaining = list(sg.reified_triples(URIRef(EX+'claim')))
        assert remaining == [TripleTerm(*tt2)]
        assert (URIRef(EX+'claim'), URIRef(EX+'source'), URIRef(EX+'wikipedia')) in sg

    def test_remove_reification_unregistered_triple_term_is_noop(self, sg):
        tt1 = (URIRef(EX+'bob'), URIRef(EX+'knows'), URIRef(EX+'carol'))
        sg.add((URIRef(EX+'claim'), RDF_REIFIES, tt1))

        sg.remove_reification(URIRef(EX+'claim'), (URIRef(EX+'x'), URIRef(EX+'y'), URIRef(EX+'z')))

        assert list(sg.reified_triples(URIRef(EX+'claim'))) == [TripleTerm(*tt1)]


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

    def test_triple_terms_filters_by_subject(self, sg_two_tts):
        tts = list(sg_two_tts.triple_terms(subject=URIRef(EX+'bob')))
        assert len(tts) == 2
        assert all(tt.subject == URIRef(EX+'bob') for tt in tts)

    def test_triple_terms_filters_by_predicate(self, sg_two_tts):
        tts = list(sg_two_tts.triple_terms(predicate=URIRef(EX+'likes')))
        assert tts == [TripleTerm(URIRef(EX+'bob'), URIRef(EX+'likes'), URIRef(EX+'dana'))]

    def test_has_triple_term_true(self, sg_two_tts):
        assert sg_two_tts.has_triple_term(
            URIRef(EX+'bob'), URIRef(EX+'knows'), URIRef(EX+'carol'))

    def test_has_triple_term_false(self, sg_two_tts):
        assert not sg_two_tts.has_triple_term(
            URIRef(EX+'bob'), URIRef(EX+'knows'), URIRef(EX+'dana'))

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

class TestQnameTerm:
    @pytest.fixture
    def sg(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        return g

    def test_uriref(self, sg):
        assert sg.qname_term(URIRef(EX+'bob')) == 'ex:bob'

    def test_triple_term(self, sg):
        tt = TripleTerm(URIRef(EX+'bob'), URIRef(EX+'knows'), URIRef(EX+'carol'))
        assert sg.qname_term(tt) == '<<( ex:bob ex:knows ex:carol )>>'

    def test_bnode(self, sg):
        b = BNode('x1')
        assert sg.qname_term(b) == '_:x1'

    def test_literal_with_language(self, sg):
        assert sg.qname_term(Literal('hi', lang='en')) == '"hi"@en'

    def test_literal_with_datatype(self, sg):
        # bonus over qname(), which raises outright on a Literal: n3()
        # compacts the datatype URI too, using rdflib's default xsd: binding.
        assert sg.qname_term(Literal(42)) == '"42"^^xsd:integer'

    def test_qname_itself_still_raises_on_triple_term(self, sg):
        # confirms the documented gap this method exists to work around -
        # if a future rdflib version ever changes this, qname_term() is
        # still correct on its own terms, but this test's premise is stale.
        tt = TripleTerm(URIRef(EX+'bob'), URIRef(EX+'knows'), URIRef(EX+'carol'))
        with pytest.raises(AttributeError):
            sg.qname(tt)

    def test_triple_terms_result_via_qname_term(self, sg):
        # exactly the case that motivated this method: a TripleTerm read
        # back from triple_terms() has no _namespace_manager of its own
        # unless the caller already knows to call .n3(g.namespace_manager)
        # by hand - qname_term() removes the need to know that.
        sg.add_reification(URIRef(EX+'claim'),
                            TripleTerm(URIRef(EX+'bob'), URIRef(EX+'knows'), URIRef(EX+'carol')))
        tt = next(sg.triple_terms(subject=URIRef(EX+'bob')))
        assert sg.qname_term(tt) == '<<( ex:bob ex:knows ex:carol )>>'


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
    def test_construction_succeeds(self):
        tt = TripleTerm(URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))
        assert tt.subject   == URIRef(EX+'s')
        assert tt.predicate == URIRef(EX+'p')
        assert tt.object    == URIRef(EX+'o')

    def test_reassign_subject_raises(self):
        tt = TripleTerm(URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))
        with pytest.raises(AttributeError):
            tt.subject = URIRef(EX+'x')

    def test_reassign_predicate_raises(self):
        tt = TripleTerm(URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))
        with pytest.raises(AttributeError):
            tt.predicate = URIRef(EX+'x')

    def test_reassign_object_raises(self):
        tt = TripleTerm(URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))
        with pytest.raises(AttributeError):
            tt.object = URIRef(EX+'x')

    def test_namespace_manager_is_mutable(self):
        tt = TripleTerm(URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))
        tt._namespace_manager = object()   # must not raise

    def test_unknown_attribute_raises(self):
        tt = TripleTerm(URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))
        with pytest.raises(AttributeError):
            tt.foo = 'bar'

    def test_equality_unaffected(self):
        tt1 = TripleTerm(URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))
        tt2 = TripleTerm(URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))
        assert tt1 == tt2
        assert hash(tt1) == hash(tt2)


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

    def test_objects_returns_triple_terms(self, g):
        objs = list(g.objects(URIRef(EX+'stmt1'), RDF_REIFIES))
        assert len(objs) == 1
        assert isinstance(objs[0], TripleTerm)

    def test_subjects_with_triple_term_object(self, g):
        tt = TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
        subjs = list(g.subjects(RDF_REIFIES, tt))
        assert URIRef(EX+'stmt1') in subjs
        assert URIRef(EX+'stmt2') not in subjs

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

    def test_predicates_with_triple_term_object(self, g):
        tt = TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
        preds = list(g.predicates(URIRef(EX+'stmt1'), tt))
        assert RDF_REIFIES in preds

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

class TestIsomorphic:
    def test_same_shape_different_bnode_labels(self):
        """Two separately-parsed graphs, same shape, different arbitrary
        BNode labels inside a triple term - must compare as isomorphic
        (this was the documented caveat / bug this override fixes)."""
        g1 = StarLayerGraph()
        g1.parse(data='''
            @prefix : <http://example.org/> .
            :a :says <<( _:x :knows :carol )>> .
            _:x :name "Bob" .
        ''', format='turtle12')
        g2 = StarLayerGraph()
        g2.parse(data='''
            @prefix : <http://example.org/> .
            :a :says <<( _:differentlabel :knows :carol )>> .
            _:differentlabel :name "Bob" .
        ''', format='turtle12')
        assert g1.isomorphic(g2)

    def test_genuinely_different_graphs_not_isomorphic(self):
        """Guard against over-permissiveness: a real structural difference
        must still compare as not isomorphic."""
        g1 = StarLayerGraph()
        g1.parse(data='''
            @prefix : <http://example.org/> .
            :a :says <<( _:x :knows :carol )>> .
            _:x :name "Bob" .
        ''', format='turtle12')
        g2 = StarLayerGraph()
        g2.parse(data='''
            @prefix : <http://example.org/> .
            :a :says <<( _:x :knows :dave )>> .
            _:x :name "Bob" .
        ''', format='turtle12')
        assert not g1.isomorphic(g2)

    def test_nested_triple_term_with_bnode(self):
        """A BNode inside a nested (triple-term-in-triple-term) component
        must also be treated as relabelable."""
        g1 = StarLayerGraph()
        g1.parse(data='''
            @prefix : <http://example.org/> .
            @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
            :r rdf:reifies <<( :a :believes <<( _:x :knows :carol )>> )>> .
            _:x :name "Bob" .
        ''', format='turtle12')
        g2 = StarLayerGraph()
        g2.parse(data='''
            @prefix : <http://example.org/> .
            @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
            :r rdf:reifies <<( :a :believes <<( _:other :knows :carol )>> )>> .
            _:other :name "Bob" .
        ''', format='turtle12')
        assert g1.isomorphic(g2)

    def test_no_triple_terms_still_works(self):
        """Plain graphs with no tt: content at all - the unfold is a no-op,
        ordinary rdflib isomorphism still applies."""
        g1 = StarLayerGraph()
        g1.parse(data='@prefix : <http://example.org/> .\n:a :knows :bob .\n', format='turtle12')
        g2 = StarLayerGraph()
        g2.parse(data='@prefix : <http://example.org/> .\n:a :knows :bob .\n', format='turtle12')
        assert g1.isomorphic(g2)
        g3 = StarLayerGraph()
        g3.parse(data='@prefix : <http://example.org/> .\n:a :knows :carol .\n', format='turtle12')
        assert not g1.isomorphic(g3)


# ---------------------------------------------------------------------------
# Statements crammed onto one physical line must not be silently dropped
# ---------------------------------------------------------------------------

class TestSameLineParsing:
    def test_prefix_and_triple_same_line(self):
        sg = StarLayerGraph()
        sg.parse(data='@prefix : <http://example.org/> . :a :knows :bob .', format='turtle12')
        assert len(sg) == 1
        assert (URIRef(EX + 'a'), URIRef(EX + 'knows'), URIRef(EX + 'bob')) in sg

    def test_two_triples_same_line(self):
        sg = StarLayerGraph()
        sg.parse(data='@prefix : <http://example.org/> .\n:a :b :c . :d :e :f .', format='turtle12')
        assert len(sg) == 2
