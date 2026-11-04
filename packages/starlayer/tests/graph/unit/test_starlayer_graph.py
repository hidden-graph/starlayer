"""
Unit tests for starlayer.graph.graph.OxGraph.

Covers: rdflib compatibility, TripleTerm add/query, filtering of internal
encoding triples, from_rdflib(), and Statement operations.
"""

from unittest.mock import MagicMock

import pyoxigraph as ox
import pytest
from rdflib import Graph
from rdflib import URIRef as RdURIRef
from starlayer.graph import isomorphic
from starlayer.graph.oxgraph import OxGraph

_XSD = "http://www.w3.org/2001/XMLSchema#"


def URIRef(iri):  # noqa: N802
    return ox.NamedNode(str(iri))


def BNode(label=None):  # noqa: N802
    return ox.BlankNode(label) if label else ox.BlankNode()


def Literal(value, lang=None, datatype=None):  # noqa: N802
    if lang:
        return ox.Literal(str(value), language=lang)
    if datatype is not None:
        return ox.Literal(str(value), datatype=ox.NamedNode(str(datatype)))
    if isinstance(value, bool):
        return ox.Literal("true" if value else "false", datatype=ox.NamedNode(_XSD + "boolean"))
    if isinstance(value, int):
        return ox.Literal(str(value), datatype=ox.NamedNode(_XSD + "integer"))
    if isinstance(value, float):
        return ox.Literal(repr(value), datatype=ox.NamedNode(_XSD + "double"))
    return ox.Literal(value)


def TripleTerm(s, p, o):  # noqa: N802
    return ox.Triple(s, p, o)

RDF_REIFIES = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDF_TYPE = ox.NamedNode(RDF + "type")

EX = 'http://example.org/'


@pytest.fixture
def sg():
    return OxGraph()


# ---------------------------------------------------------------------------
# rdflib compatibility
# ---------------------------------------------------------------------------

class TestRdflibCompat:

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



# ---------------------------------------------------------------------------
# Bare (RDF 1.1) nquads/trig parsing - multi-graph-capable formats
# parsed into a single graph. Added 2026-10-04: plain rdflib delegation
# would silently yield zero triples the moment any named graph appears at
# all (a non-context-aware Graph's parser plugins can't place quads
# anywhere) - this project instead resolves at most one distinct graph
# (dropping its name) or raises MultipleGraphsError for two or more,
# matching the same rule nq12/trig12 enforce (see test_rdf12_formats.py).
# ---------------------------------------------------------------------------



class TestNamedViewAndQuadFormats:
    def test_serialize_trig_uses_own_identifier(self):
        """A named-graph view writes its own identifier as the GRAPH block name (the old class compared with plain rdflib)."""
        identifier = URIRef(EX + 'mygraph')
        sg = OxGraph(identifier=identifier)
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        out = sg.serialize(format='trig')
        assert f'<{EX}mygraph> {{' in out
        from starlayer.graph.oxgraph import OxDataset
        ds = OxDataset().parse(data=out, format='trig')
        assert [(q.subject.value, q.graph_name.value) for q in ds.quads()] == [(EX + 's', EX + 'mygraph')]

    @pytest.mark.parametrize('fmt, data', [
        ('nquads', f'<{EX}s> <{EX}p> <{EX}o> <{EX}g1> .\n'),
        ('nquads', f'<{EX}s> <{EX}p> <{EX}o> <{EX}g1> .\n<{EX}a> <{EX}b> <{EX}c> <{EX}g2> .\n'),
        ('trig', f'<{EX}g1> {{ <{EX}s> <{EX}p> <{EX}o> . }}\n'),
        ('trig', f'<{EX}default> <{EX}p> <{EX}o> .\n<{EX}g1> {{ <{EX}named> <{EX}p> <{EX}o> . }}\n'),
    ])
    def test_a_document_with_named_graphs_is_refused_by_a_graph_view(self, sg, fmt, data):
        # The old class dropped a single graph's name and raised MultipleGraphsError for two; an OxGraph refuses any
        # named graph (parse into an OxDataset), and the graph is left unchanged.
        with pytest.raises(ValueError, match='named graphs'):
            sg.parse(data=data, format=fmt)
        assert len(sg) == 0


# ---------------------------------------------------------------------------
# Bare (RDF 1.1) nquads/trig serializing - a single graph always has
# somewhere to go (its own identifier), so unlike parse() there's no
# raise-for-2+-graphs case here; the fix is purely about not raising for the
# single-graph case either. Added 2026-10-04: rdflib's own NQuads
# serializer plugin raises "...only makes sense for context-aware stores"
# for any non-context-aware store (no single-graph fallback, unlike
# TrigSerializer's own - see rdflib.plugins.serializers.trig), which
# OxGraph used to just inherit via blind delegation. Now wraps the
# graph as the one context of a real Dataset first, so all six dataset
# formats (nquads/trig, nq12/trig12) behave consistently.
# ---------------------------------------------------------------------------

class TestBareQuadFormatsSerializing:
    def test_nquads_assigns_graph_name_from_identifier(self):
        identifier = URIRef(EX + 'mygraph')
        sg = OxGraph(identifier=identifier)
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        text = sg.serialize(format='nquads')
        assert str(identifier) in text
        assert f'<{EX}s>' in text and f'<{EX}p>' in text and f'<{EX}o>' in text

    @pytest.mark.parametrize('fmt', ['trix', 'trix12'])
    def test_trix_is_refused(self, fmt):
        """TriX was dropped (decision 2026-10-31): a clear error, not rdflib's plugin."""
        sg = OxGraph(identifier=URIRef(EX + 'mygraph'))
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        with pytest.raises(ValueError, match='unknown RDF format'):
            sg.serialize(format=fmt)
        with pytest.raises(ValueError, match='unknown RDF format'):
            sg.parse(data='<trix/>', format=fmt)

    def test_nquads_serialize_returns_self_when_destination_given(self, tmp_path):
        sg = OxGraph(identifier=URIRef(EX+'mygraph'))
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        dest = tmp_path / 'out.nq'
        result = sg.serialize(destination=str(dest), format='nquads')
        assert result is None  # the old class returned the graph
        assert dest.exists()


# ---------------------------------------------------------------------------
# Chaining contract (return self, matching rdflib) - regressions fixed
# 2026-10-04. rdflib's own Graph.add()/.addN()/.remove()/.serialize()/.open()
# all return self (or the serialized text when destination is None) so
# calls can chain; several OxGraph overrides had silently dropped
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


    def test_addN_returns_self(self, sg):
        t = (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))
        assert sg.addN([(*t, sg)]) is sg


    def test_serialize_with_destination_returns_self_for_rdf12_format(self, sg, tmp_path):
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        dest = tmp_path / 'out.ttl'
        assert sg.serialize(destination=str(dest), format='turtle12') is None  # the old class returned the graph
        assert dest.exists()

    def test_serialize_with_destination_returns_self_for_legacy_format(self, sg, tmp_path):
        """The non-RDF12 branch delegates to a throwaway de-skolemized
        Graph's own .serialize() - that returned *that* unrelated Graph,
        not self, when destination was given."""
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        dest = tmp_path / 'out.ttl'
        assert sg.serialize(destination=str(dest), format='turtle') is None  # the old class returned the graph
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
        assert isinstance(o, ox.Triple)
        assert o == TripleTerm(URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))

    def test_add_tt_subject_raises(self, sg):
        tt = TripleTerm(URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))
        with pytest.raises(TypeError):
            sg.add((tt, URIRef(EX+'q'), URIRef(EX+'z')))

    def test_add_tuple_subject_raises(self, sg):
        with pytest.raises(TypeError):
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
        assert isinstance(outer, ox.Triple)
        assert isinstance(outer.object, ox.Triple)
        assert outer == TripleTerm(URIRef(EX+'stmt1'), URIRef(EX+'about'), TripleTerm(*inner))
        assert outer.object == TripleTerm(*inner)


# ---------------------------------------------------------------------------
# Encoding triples are hidden from traversal
# ---------------------------------------------------------------------------

class TestEncodingHidden:
    def test_encoding_triples_not_in_triples(self, sg):
        sg.add((URIRef(EX+'r'), RDF_REIFIES, (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))))
        preds = {p for _, p, _ in sg.triples((None, None, None))}
        for pred in ('propositionFormSubject', 'propositionFormPredicate', 'propositionFormObject'):
            assert URIRef(RDF + pred) not in preds
        # the type triple that marks a triple term is hidden too
        assert not list(sg.triples((None, RDF_TYPE, URIRef(RDF + 'PropositionForm'))))

    def test_sl_triple_term_type_hidden(self, sg):
        sg.add((URIRef(EX+'r'), RDF_REIFIES, (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))))
        assert list(sg.objects(predicate=RDF_TYPE)) == []  # no marker type of any kind (the old class hid sl:TripleTerm)

    def test_sl_reification_type_hidden(self, sg):
        sg.add_reification(URIRef(EX+'stmt'), (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        assert list(sg.objects(predicate=RDF_TYPE)) == []  # no marker type of any kind (the old class hid sl:Reification)

    def test_len_excludes_encoding(self, sg):
        sg.add((URIRef(EX+'r'), RDF_REIFIES, (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))))
        assert len(sg) == 1  # only the rdf:reifies triple; 3 encoding triples hidden


# ---------------------------------------------------------------------------
# from_rdflib — wrapping the parser output
# ---------------------------------------------------------------------------

class TestFromRdflib:
    def test_from_rdflib_plain_triples(self):
        raw = Graph()
        raw.add((RdURIRef(EX+'s'), RdURIRef(EX+'p'), RdURIRef(EX+'o')))
        sg = OxGraph.from_rdflib(raw)
        assert (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')) in sg

    def test_from_rdflib_preserves_a_real_identifier(self):
        """A source graph's own caller-given .identifier is preserved onto the converted OxGraph (2026-10-09)."""
        raw = Graph(identifier=RdURIRef(EX + 's'))
        raw.add((RdURIRef(EX+'s'), RdURIRef(EX+'p'), RdURIRef(EX+'o')))
        sg = OxGraph.from_rdflib(raw)
        assert sg.identifier == URIRef(EX + 's')

    def test_from_rdflib_default_bnode_identifier_still_works(self):
        """A source graph with no caller-given identifier (a random BNode) converts to the default graph."""
        raw = Graph()
        raw.add((RdURIRef(EX+'s'), RdURIRef(EX+'p'), RdURIRef(EX+'o')))
        sg = OxGraph.from_rdflib(raw)
        assert isinstance(sg.identifier, ox.DefaultGraph)

    def test_from_rdflib_dataset_source_does_not_preserve_identifier(self):
        """A whole Dataset has no single identity of its own: the OxGraph is the default graph (it is empty here: the
        triples are in a named graph and an rdflib Dataset is not a union by default)."""
        from rdflib import Dataset

        ds = Dataset()
        named = ds.graph(RdURIRef(EX + 'named1'))
        named.add((RdURIRef(EX+'s'), RdURIRef(EX+'p'), RdURIRef(EX+'o')))
        sg = OxGraph.from_rdflib(ds)
        assert isinstance(sg.identifier, ox.DefaultGraph)

    def test_from_rdflib_named_graph_pulled_from_dataset_preserves_identifier(self):
        """A single named graph *retrieved* from a Dataset already carries its own real identifier."""
        from rdflib import Dataset

        ds = Dataset()
        named = ds.graph(RdURIRef(EX + 'named1'))
        named.add((RdURIRef(EX+'s'), RdURIRef(EX+'p'), RdURIRef(EX+'o')))
        sg = OxGraph.from_rdflib(named)
        assert sg.identifier == URIRef(EX + 'named1')


class TestFromRdflibDataset:
    """from_rdflib() of a Dataset respects its default_union setting."""

    def test_default_union_false_sees_only_default_graph(self):
        from rdflib import Dataset
        ds = Dataset()  # default_union=False, the rdflib default
        ds.add((RdURIRef(EX+'default_s'), RdURIRef(EX+'p'), RdURIRef(EX+'default_o')))
        named = ds.graph(RdURIRef(EX+'g1'))
        named.add((RdURIRef(EX+'named_s'), RdURIRef(EX+'p'), RdURIRef(EX+'named_o')))

        sg = OxGraph.from_rdflib(ds)
        assert len(sg) == 1
        assert (URIRef(EX+'default_s'), URIRef(EX+'p'), URIRef(EX+'default_o')) in sg
        assert (URIRef(EX+'named_s'), URIRef(EX+'p'), URIRef(EX+'named_o')) not in sg

    def test_default_union_true_sees_all_graphs(self):
        from rdflib import Dataset
        ds = Dataset(default_union=True)
        ds.add((RdURIRef(EX+'default_s'), RdURIRef(EX+'p'), RdURIRef(EX+'default_o')))
        named = ds.graph(RdURIRef(EX+'g1'))
        named.add((RdURIRef(EX+'named_s'), RdURIRef(EX+'p'), RdURIRef(EX+'named_o')))

        sg = OxGraph.from_rdflib(ds)
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
        assert isinstance(o, ox.Triple)

    def test_add_reification_returns_self(self, sg):
        """Matches every other mutating method on OxGraph (add(),
        remove(), addN(), etc) - added 2026-10-04, this used to return
        None, the one mutating method that didn't support chaining."""
        result = sg.add_reification(URIRef(EX+'stmt'), (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        assert result is sg

    def test_remove_reification_returns_self(self, sg):
        """Matches add_reification() and every other mutating method on
        OxGraph - added 2026-10-04, this used to return None."""
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
        assert all(isinstance(tt, ox.Triple) for tt in tts)

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
        g = OxGraph()
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





# ---------------------------------------------------------------------------
# qname_term() - unlike the inherited qname(), accepts any term type
# ---------------------------------------------------------------------------

class TestQnameTerm:
    @pytest.fixture
    def sg(self):
        g = OxGraph()
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
        # bonus over qname(), which raises outright on a Literal: the datatype IRI is compacted too (an OxGraph has no
        # default xsd binding, so the test binds it).
        sg.bind('xsd', _XSD)
        assert sg.qname_term(Literal(42)) == '"42"^^xsd:integer'

    def test_qname_itself_still_raises_on_triple_term(self, sg):
        # confirms the documented gap this method exists to work around -
        # if a future rdflib version ever changes this, qname_term() is
        # still correct on its own terms, but this test's premise is stale.
        tt = TripleTerm(URIRef(EX+'bob'), URIRef(EX+'knows'), URIRef(EX+'carol'))
        with pytest.raises(TypeError):
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
        g = OxGraph()
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
        assert isinstance(objs[0], ox.Triple)

    def test_subjects_with_triple_term_object(self, g):
        tt = TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
        subjs = list(g.subjects(RDF_REIFIES, tt))
        assert URIRef(EX+'stmt1') in subjs
        assert URIRef(EX+'stmt2') not in subjs



    def test_predicates_with_triple_term_object(self, g):
        tt = TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
        preds = list(g.predicates(URIRef(EX+'stmt1'), tt))
        assert RDF_REIFIES in preds



# ---------------------------------------------------------------------------
# Persistent store lifecycle — open() / close()
# ---------------------------------------------------------------------------



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




# ---------------------------------------------------------------------------
# isomorphic() — BNodes embedded inside a TripleTerm must be relabelable
# ---------------------------------------------------------------------------

class TestIsomorphic:
    def test_same_shape_different_bnode_labels(self):
        """Two separately-parsed graphs, same shape, different arbitrary
        BNode labels inside a triple term - must compare as isomorphic
        (this was the documented caveat / bug this override fixes)."""
        g1 = OxGraph()
        g1.parse(data='''
            @prefix : <http://example.org/> .
            :a :says <<( _:x :knows :carol )>> .
            _:x :name "Bob" .
        ''', format='turtle12')
        g2 = OxGraph()
        g2.parse(data='''
            @prefix : <http://example.org/> .
            :a :says <<( _:differentlabel :knows :carol )>> .
            _:differentlabel :name "Bob" .
        ''', format='turtle12')
        assert isomorphic(g1, g2)

    def test_genuinely_different_graphs_not_isomorphic(self):
        """Guard against over-permissiveness: a real structural difference
        must still compare as not isomorphic."""
        g1 = OxGraph()
        g1.parse(data='''
            @prefix : <http://example.org/> .
            :a :says <<( _:x :knows :carol )>> .
            _:x :name "Bob" .
        ''', format='turtle12')
        g2 = OxGraph()
        g2.parse(data='''
            @prefix : <http://example.org/> .
            :a :says <<( _:x :knows :dave )>> .
            _:x :name "Bob" .
        ''', format='turtle12')
        assert not isomorphic(g1, g2)

    def test_nested_triple_term_with_bnode(self):
        """A BNode inside a nested (triple-term-in-triple-term) component
        must also be treated as relabelable."""
        g1 = OxGraph()
        g1.parse(data='''
            @prefix : <http://example.org/> .
            @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
            :r rdf:reifies <<( :a :believes <<( _:x :knows :carol )>> )>> .
            _:x :name "Bob" .
        ''', format='turtle12')
        g2 = OxGraph()
        g2.parse(data='''
            @prefix : <http://example.org/> .
            @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
            :r rdf:reifies <<( :a :believes <<( _:other :knows :carol )>> )>> .
            _:other :name "Bob" .
        ''', format='turtle12')
        assert isomorphic(g1, g2)

    def test_no_triple_terms_still_works(self):
        """Plain graphs with no tt: content at all - the unfold is a no-op,
        ordinary rdflib isomorphism still applies."""
        g1 = OxGraph()
        g1.parse(data='@prefix : <http://example.org/> .\n:a :knows :bob .\n', format='turtle12')
        g2 = OxGraph()
        g2.parse(data='@prefix : <http://example.org/> .\n:a :knows :bob .\n', format='turtle12')
        assert isomorphic(g1, g2)
        g3 = OxGraph()
        g3.parse(data='@prefix : <http://example.org/> .\n:a :knows :carol .\n', format='turtle12')
        assert not isomorphic(g1, g3)


# ---------------------------------------------------------------------------
# Statements crammed onto one physical line must not be silently dropped
# ---------------------------------------------------------------------------

class TestSameLineParsing:
    def test_prefix_and_triple_same_line(self):
        sg = OxGraph()
        sg.parse(data='@prefix : <http://example.org/> . :a :knows :bob .', format='turtle12')
        assert len(sg) == 1
        assert (URIRef(EX + 'a'), URIRef(EX + 'knows'), URIRef(EX + 'bob')) in sg

    def test_two_triples_same_line(self):
        sg = OxGraph()
        sg.parse(data='@prefix : <http://example.org/> .\n:a :b :c . :d :e :f .', format='turtle12')
        assert len(sg) == 2
