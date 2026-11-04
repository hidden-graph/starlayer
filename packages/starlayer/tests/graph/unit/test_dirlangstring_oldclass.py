"""
Unit tests for rdf:dirLangString (RDF 1.2 base-direction-tagged literals).

Covers the DirLangString value type, StarLayerGraph read/write interception,
Turtle/N-Triples/N-Quads/TriG/RDF-XML/TriX/JSON-LD 1.2 parser and serializer
round-trips, and the SPARQL 1.2 base-direction functions.
"""

from rdflib import Literal, URIRef
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.graph.model.dirlangstring import (
    DirLangString,
)

EX = 'http://example.org/'


def ex(local):
    return URIRef(EX + local)


def round_trip(g, fmt):
    text = g.serialize(format=fmt)
    g2 = StarLayerGraph()
    g2.parse(data=text, format=fmt)
    return text, g2


# ---------------------------------------------------------------------------
# Model type
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# StarLayerGraph read/write
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Turtle 1.2
# ---------------------------------------------------------------------------

class TestTurtle12:




    def test_round_trip_longturtle12(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), DirLangString('hello', 'en', 'ltr')))
        text, g2 = round_trip(g, 'longturtle12')
        assert '"hello"@en--ltr' in text
        assert list(g2.triples((None, None, None))) == list(g.triples((None, None, None)))



# ---------------------------------------------------------------------------
# N-Triples 1.2 / N-Quads 1.2
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# TriG 1.2 (via StarLayerDataset)
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# RDF/XML 1.2, TriX 1.2
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# SPARQL 1.2 base-direction functions
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Native backend (rdf-1.2) term serialization + JSON parsing
# ---------------------------------------------------------------------------

class TestNativeBackend:
    def test_sparql_term_emits_real_lexical_form(self):
        from starlayer.graph.backends.native import sparql_term
        d = DirLangString('hello', 'en', 'rtl')
        assert sparql_term(d) == '"hello"@en--rtl'

    def test_sparql_term_escapes_quotes(self):
        from starlayer.graph.backends.native import sparql_term
        d = DirLangString('say "hi"', 'en', 'ltr')
        assert sparql_term(d) == '"say \\"hi\\""@en--ltr'

    def test_parse_json_term_with_its_dir_key(self):
        # "its:dir" confirmed 2026-07-16 against live Fuseki 5.5.0 and
        # Oxigraph 0.5.9 (both agree independently).
        from starlayer.graph.backends.native import _parse_json_term
        term = _parse_json_term({'type': 'literal', 'value': 'hello', 'xml:lang': 'en', 'its:dir': 'rtl'})
        assert term == DirLangString('hello', 'en', 'rtl')

    def test_parse_json_term_without_direction_key_is_plain_lang_literal(self):
        from starlayer.graph.backends.native import _parse_json_term
        term = _parse_json_term({'type': 'literal', 'value': 'hello', 'xml:lang': 'en'})
        assert term == Literal('hello', lang='en')
        assert not isinstance(term, DirLangString)
