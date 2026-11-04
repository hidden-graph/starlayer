"""
Unit tests for RDF 1.2 format parsing and serialization.

Covers N-Triples 1.2 (nt12), N-Quads 1.2 (nq12), and TriG 1.2 (trig12)
via StarLayerGraph.parse() and StarLayerGraph.serialize().
"""

from rdflib import URIRef
from starlayer.graph.graph.starlayer_graph import RDF_REIFIES, StarLayerGraph
from starlayer.graph.model.triple import TripleTerm

EX = 'http://example.org/'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ex(local):
    return URIRef(EX + local)


def round_trip(g, fmt):
    """Serialize g to fmt, parse into a fresh graph, return both serialized text and new graph."""
    text = g.serialize(format=fmt)
    g2 = StarLayerGraph()
    g2.parse(data=text, format=fmt)
    return text, g2


# ---------------------------------------------------------------------------
# N-Triples 1.2 — parsing
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# N-Triples 1.2 — serialization
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# N-Triples 1.2 — round-trip
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# N-Quads 1.2
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# TriG 1.2 — parsing
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# TriG 1.2 — serialization
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# TriG 1.2 — round-trip
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# RDF 1.2 version declaration — nt12, nq12, trig12
# ---------------------------------------------------------------------------







# ---------------------------------------------------------------------------
# RDF/XML 1.2
# ---------------------------------------------------------------------------

class TestRDFXML12Parse:

    def test_triple_term_as_object(self):
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
        g = StarLayerGraph()
        g.parse(data=xml, format='rdfxml12')
        assert g.has_triple_term(ex('alice'), ex('knows'), ex('bob'))







class TestRDFXML12SpecInterop:
    """Interop with the RDF 1.2 XML Syntax spec's own examples (sec 2.19-2.20) -
    starlayer.graph's serializer never emits rdf:annotation/rdf:annotationNodeID
    (it always uses the formal rdf:reifies + parseType="Triple" pattern), but
    the parser accepts them so documents from other spec-conformant tools
    still parse correctly.
    """

    def test_parse_type_triple_matches_spec_example(self):
        # Verbatim shape from RDF 1.2 XML Syntax sec 2.19.
        xml = (
            '<?xml version="1.0"?>'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'
            ' xmlns:ex="http://example.org/stuff/1.0/">'
            '<rdf:Description rdf:about="http://example.org/">'
            '<ex:prop rdf:parseType="Triple">'
            '<rdf:Description rdf:about="http://example.org/stuff/1.0/s">'
            '<ex:p rdf:resource="http://example.org/stuff/1.0/o" />'
            '</rdf:Description>'
            '</ex:prop>'
            '</rdf:Description></rdf:RDF>'
        )
        g = StarLayerGraph()
        g.parse(data=xml, format='rdfxml12')
        expected_tt = TripleTerm(
            URIRef('http://example.org/stuff/1.0/s'),
            URIRef('http://example.org/stuff/1.0/p'),
            URIRef('http://example.org/stuff/1.0/o'),
        )
        assert (URIRef('http://example.org/'), URIRef('http://example.org/stuff/1.0/prop'), expected_tt) in g




# ---------------------------------------------------------------------------
# N3 — aliased straight to turtle12 (plain-triples subset only, not real N3)
# ---------------------------------------------------------------------------



def round_trip_graph_with_tt(format):
    g = StarLayerGraph()
    g.add((ex('claim'), RDF_REIFIES, TripleTerm(ex('bob'), ex('knows'), ex('carol'))))
    text, g2 = round_trip(g, format)
    return text, g2




class TestN3AliasGraph:
    """The `n3-12` format alias of the old class (an OxGraph does not know it: ValueError unknown format)."""

    def test_parse_n3_dash_12_alias(self):
        g = StarLayerGraph()
        g.parse(data=f'@prefix ex: <{EX}> . ex:s ex:p ex:o .', format='n3-12')
        assert (ex('s'), ex('p'), ex('o')) in g
