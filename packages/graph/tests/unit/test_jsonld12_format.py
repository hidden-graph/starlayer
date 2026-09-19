"""
Unit tests for the jsonld12 format: plain RDF 1.1 content serializes as
ordinary JSON-LD (delegating to rdflib's own writer), and RDF 1.2 content
(a triple term or a direction-tagged literal) raises ValueError instead of
being encoded - see starlayergraph/serializers/jsonld12.py's own docstring
for why there's no fallback encoding to fall back on.
"""

import json

import pytest
from rdflib import Literal, URIRef
from rdflib.namespace import XSD
from starlayergraph.graph.starlayer_graph import RDF_REIFIES, StarLayerGraph
from starlayergraph.model.dirlangstring import DirLangString
from starlayergraph.model.triple import TripleTerm

EX = 'http://example.org/'


def ex(local):
    return URIRef(EX + local)


def round_trip(g):
    text = g.serialize(format='jsonld12')
    g2 = StarLayerGraph()
    g2.parse(data=text, format='jsonld12')
    return text, g2


# ---------------------------------------------------------------------------
# Plain RDF 1.1 content: ordinary JSON-LD, no starlayergraph-specific shape
# ---------------------------------------------------------------------------

class TestPlainContent:
    def test_output_is_valid_json(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        doc = json.loads(g.serialize(format='jsonld12'))
        assert doc

    def test_plain_triple_roundtrip(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        _, g2 = round_trip(g)
        assert (ex('s'), ex('p'), ex('o')) in g2

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

    def test_triple_count_preserved(self):
        g = StarLayerGraph()
        g.add((ex('alice'), ex('knows'), ex('bob')))
        g.add((ex('alice'), ex('confidence'), Literal('0.9')))
        _, g2 = round_trip(g)
        assert len(g2) == len(g)

    def test_parse_from_hand_written_jsonld(self):
        """Parse ordinary JSON-LD written by hand (not by our serializer) -
        jsonld12 no longer means anything beyond plain JSON-LD, so any real
        JSON-LD document is valid input."""
        data = json.dumps({
            '@context': {'ex': EX},
            '@id': 'ex:alice',
            'ex:knows': {'@id': 'ex:bob'},
        })
        g = StarLayerGraph()
        g.parse(data=data, format='jsonld12')
        assert (ex('alice'), ex('knows'), ex('bob')) in g

    def test_same_triples_as_turtle12(self):
        g = StarLayerGraph()
        g.add((ex('alice'), ex('knows'), ex('bob')))
        g.add((ex('alice'), ex('confidence'), Literal('0.9')))

        _, g_jld = round_trip(g)
        text_ttl = g.serialize(format='turtle12')
        g_ttl = StarLayerGraph()
        g_ttl.parse(data=text_ttl, format='turtle12')

        assert set(g_jld.triples((None, None, None))) == \
               set(g_ttl.triples((None, None, None)))


# ---------------------------------------------------------------------------
# RDF 1.2 content: explicit ValueError, not a fallback encoding
# ---------------------------------------------------------------------------

class TestRdf12ContentRejected:
    def test_triple_term_raises(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        with pytest.raises(ValueError, match='RDF 1.2'):
            g.serialize(format='jsonld12')

    def test_nested_triple_term_raises(self):
        g = StarLayerGraph()
        inner = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        outer = TripleTerm(ex('claim'), ex('says'), inner)
        g.add((ex('stmt1'), RDF_REIFIES, outer))
        with pytest.raises(ValueError, match='RDF 1.2'):
            g.serialize(format='jsonld12')

    def test_direction_tagged_literal_raises(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('label'), DirLangString('hi', 'en', 'ltr')))
        with pytest.raises(ValueError, match='RDF 1.2'):
            g.serialize(format='jsonld12')

    def test_plain_content_alongside_rdf12_content_still_raises(self):
        """One triple term anywhere in the graph is enough to refuse the
        whole document - there's no partial/best-effort serialization."""
        g = StarLayerGraph()
        g.add((ex('a'), ex('p'), ex('b')))
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        with pytest.raises(ValueError, match='RDF 1.2'):
            g.serialize(format='jsonld12')
