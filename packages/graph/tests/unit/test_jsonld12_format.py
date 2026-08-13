"""
Unit tests for JSON-LD 1.2 parsing and serialization.

Covers: serialize to jsonld12, parse from jsonld12, round-trip,
encoding-triple filtering, nested triple terms, and cross-format checks.
"""

import json
import pytest
from rdflib import URIRef, Literal, BNode
from rdflib.namespace import RDF, XSD

from starlayergraph.graph.starlayer_graph import StarLayerGraph, RDF_REIFIES
from starlayergraph.model.triple import TripleTerm

EX   = 'http://example.org/'
TT_NS = 'https://github.com/hidden-graph/starlayergraph/ns/tt#'
RDF_TRIPLE_TERM = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#TripleTerm')


def ex(local):
    return URIRef(EX + local)


def round_trip(g):
    text = g.serialize(format='jsonld12')
    g2 = StarLayerGraph()
    g2.parse(data=text, format='jsonld12')
    return text, g2


# ---------------------------------------------------------------------------
# Serialization structure
# ---------------------------------------------------------------------------

class TestSerializeStructure:
    def test_output_is_valid_json(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        text = g.serialize(format='jsonld12')
        doc = json.loads(text)
        assert isinstance(doc, dict)

    def test_has_context_with_rdf_and_tt(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        doc = json.loads(g.serialize(format='jsonld12'))
        ctx = doc.get('@context', {})
        assert 'rdf' in ctx
        assert 'tt' in ctx

    def test_has_graph_array(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        doc = json.loads(g.serialize(format='jsonld12'))
        assert '@graph' in doc
        assert isinstance(doc['@graph'], list)

    def test_triple_term_node_has_rdf_triple_term_type(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        doc = json.loads(g.serialize(format='jsonld12'))
        tt_nodes = [n for n in doc['@graph'] if n.get('@id', '').startswith('tt:')]
        assert len(tt_nodes) == 1
        assert 'rdf:TripleTerm' in tt_nodes[0].get('@type', [])

    def test_triple_term_node_has_spo(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        doc = json.loads(g.serialize(format='jsonld12'))
        tt_nodes = [n for n in doc['@graph'] if n.get('@id', '').startswith('tt:')]
        node = tt_nodes[0]
        rdf_ns = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
        assert rdf_ns + 'subject' in node
        assert rdf_ns + 'predicate' in node
        assert rdf_ns + 'object' in node

    def test_no_encoding_triples_in_non_tt_nodes(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        doc = json.loads(g.serialize(format='jsonld12'))
        rdf_ns = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
        for node in doc['@graph']:
            if not node.get('@id', '').startswith('tt:'):
                assert rdf_ns + 'subject' not in node
                assert rdf_ns + 'predicate' not in node
                assert rdf_ns + 'object' not in node

    def test_plain_triple_emitted(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        doc = json.loads(g.serialize(format='jsonld12'))
        nodes = {n['@id']: n for n in doc['@graph'] if '@id' in n}
        assert EX + 's' in nodes
        assert EX + 'p' in nodes[EX + 's'] or \
               'rdf:' in ''.join(nodes[EX + 's'].keys())


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

class TestParse:
    def test_plain_triple_roundtrip(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        _, g2 = round_trip(g)
        assert (ex('s'), ex('p'), ex('o')) in g2

    def test_triple_term_as_object_roundtrip(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        _, g2 = round_trip(g)
        assert g2.has_triple_term(ex('alice'), ex('knows'), ex('bob'))
        objs = list(g2.objects(ex('stmt1'), RDF_REIFIES))
        assert tt in objs

    def test_encoding_triples_not_visible_after_parse(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        _, g2 = round_trip(g)
        enc_preds = {
            'http://www.w3.org/1999/02/22-rdf-syntax-ns#subject',
            'http://www.w3.org/1999/02/22-rdf-syntax-ns#predicate',
            'http://www.w3.org/1999/02/22-rdf-syntax-ns#object',
        }
        for _, p, _ in g2.triples((None, None, None)):
            assert str(p) not in enc_preds

    def test_rdf_type_triple_term_not_visible(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        _, g2 = round_trip(g)
        # rdf:type rdf:TripleTerm must be filtered
        for _, p, o in g2.triples((None, None, None)):
            assert not (p == RDF.type and o == RDF_TRIPLE_TERM)

    def test_triple_count_preserved(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        g.add((ex('stmt1'), ex('confidence'), Literal('0.9')))
        g.add((ex('alice'), ex('knows'), ex('bob')))
        _, g2 = round_trip(g)
        assert len(g2) == len(g)

    def test_literal_with_language_roundtrip(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('label'), Literal('hello', lang='en')))
        _, g2 = round_trip(g)
        objs = list(g2.objects(ex('s'), ex('label')))
        assert any(getattr(o, 'language', None) == 'en' for o in objs)

    def test_literal_with_datatype_roundtrip(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('age'), Literal(42, datatype=XSD.integer)))
        _, g2 = round_trip(g)
        objs = list(g2.objects(ex('s'), ex('age')))
        assert any(str(o) == '42' for o in objs)

    def test_multiple_triple_terms_roundtrip(self):
        g = StarLayerGraph()
        tt1 = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        tt2 = TripleTerm(ex('bob'), ex('likes'), ex('carol'))
        g.add((ex('stmt1'), RDF_REIFIES, tt1))
        g.add((ex('stmt2'), RDF_REIFIES, tt2))
        _, g2 = round_trip(g)
        assert g2.has_triple_term(ex('alice'), ex('knows'), ex('bob'))
        assert g2.has_triple_term(ex('bob'), ex('likes'), ex('carol'))

    def test_parse_from_hand_written_jsonld(self):
        """Parse JSON-LD written by hand (not by our serializer)."""
        data = json.dumps({
            '@context': {
                'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
                'tt':  'https://github.com/hidden-graph/starlayergraph/ns/tt#',
                'ex':  EX,
            },
            '@graph': [
                {
                    '@id':        'ex:stmt1',
                    'rdf:reifies': [{'@id': 'tt:deadbeef'}],
                },
                {
                    '@id':              'tt:deadbeef',
                    '@type':            ['rdf:TripleTerm'],
                    'rdf:subject':      [{'@id': 'ex:alice'}],
                    'rdf:predicate':    [{'@id': 'ex:knows'}],
                    'rdf:object':       [{'@id': 'ex:bob'}],
                },
            ],
        })
        g = StarLayerGraph()
        g.parse(data=data, format='jsonld12')
        # The graph should have exactly the two user-visible triples:
        # ex:stmt1 rdf:reifies <<( ex:alice ex:knows ex:bob )>>
        # (the tt: encoding triples and rdf:type rdf:TripleTerm are filtered)
        assert len(g) == 1
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        objs = list(g.objects(ex('stmt1'), RDF_REIFIES))
        assert tt in objs


# ---------------------------------------------------------------------------
# Cross-format checks
# ---------------------------------------------------------------------------

class TestCrossFormat:
    def test_jsonld12_same_triples_as_turtle12(self):
        """A graph serialized to jsonld12 and turtle12 should round-trip to
        the same set of triples."""
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        g.add((ex('stmt1'), ex('confidence'), Literal('0.9')))

        _, g_jld  = round_trip(g)
        text_ttl  = g.serialize(format='turtle12')
        g_ttl     = StarLayerGraph()
        g_ttl.parse(data=text_ttl, format='turtle12')

        assert set(g_jld.triples((None, None, None))) == \
               set(g_ttl.triples((None, None, None)))

    def test_jsonld12_to_nt12_roundtrip(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('s'), ex('p'), ex('o'))
        g.add((ex('stmt'), RDF_REIFIES, tt))
        jld_text = g.serialize(format='jsonld12')
        g2 = StarLayerGraph()
        g2.parse(data=jld_text, format='jsonld12')
        nt_text = g2.serialize(format='nt12')
        g3 = StarLayerGraph()
        g3.parse(data=nt_text, format='nt12')
        assert g3.has_triple_term(ex('s'), ex('p'), ex('o'))
