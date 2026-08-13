"""
Unit tests for RDF 1.2 format parsing and serialization.

Covers N-Triples 1.2 (nt12), N-Quads 1.2 (nq12), and TriG 1.2 (trig12)
via StarLayerGraph.parse() and StarLayerGraph.serialize().
"""

import pytest
from rdflib import URIRef, BNode, Literal
from rdflib.namespace import RDF, XSD

from starlayergraph.graph.starlayergraph_graph import StarLayerGraph, RDF_REIFIES
from starlayergraph.model.triple import TripleTerm

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

class TestNT12Parse:
    def test_plain_triple(self):
        nt = '<http://example.org/s> <http://example.org/p> <http://example.org/o> .\n'
        g = StarLayerGraph()
        g.parse(data=nt, format='nt12')
        assert (ex('s'), ex('p'), ex('o')) in g

    def test_literal_object(self):
        nt = '<http://example.org/s> <http://example.org/p> "hello" .\n'
        g = StarLayerGraph()
        g.parse(data=nt, format='nt12')
        assert Literal('hello') in list(g.objects(ex('s'), ex('p')))

    def test_typed_literal(self):
        nt = f'<{EX}s> <{EX}age> "42"^^<{XSD}integer> .\n'
        g = StarLayerGraph()
        g.parse(data=nt, format='nt12')
        objs = list(g.objects(ex('s'), ex('age')))
        assert any(str(o) == '42' for o in objs)

    def test_lang_tagged_literal(self):
        nt = f'<{EX}s> <{EX}label> "hello"@en .\n'
        g = StarLayerGraph()
        g.parse(data=nt, format='nt12')
        objs = list(g.objects(ex('s'), ex('label')))
        assert any(getattr(o, 'language', None) == 'en' for o in objs)

    def test_bnode_subject(self):
        nt = '_:b0 <http://example.org/p> <http://example.org/o> .\n'
        g = StarLayerGraph()
        g.parse(data=nt, format='nt12')
        assert len(g) == 1

    def test_triple_term_object(self):
        nt = f'<{EX}stmt1> <{RDF_REIFIES}> <<( <{EX}alice> <{EX}knows> <{EX}bob> )>> .\n'
        g = StarLayerGraph()
        g.parse(data=nt, format='nt12')
        assert g.has_triple_term(ex('alice'), ex('knows'), ex('bob'))
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        objs = list(g.objects(ex('stmt1'), RDF_REIFIES))
        assert tt in objs

    def test_comment_lines_ignored(self):
        nt = f'# This is a comment\n<{EX}p> <{EX}q> <{EX}r> .\n'
        g = StarLayerGraph()
        g.parse(data=nt, format='nt12')
        assert len(g) == 1

    def test_escape_in_literal(self):
        nt = f'<{EX}s> <{EX}p> "line1\\nline2" .\n'
        g = StarLayerGraph()
        g.parse(data=nt, format='nt12')
        objs = list(g.objects(ex('s'), ex('p')))
        assert any('\n' in str(o) for o in objs)


# ---------------------------------------------------------------------------
# N-Triples 1.2 — serialization
# ---------------------------------------------------------------------------

class TestNT12Serialize:
    def test_plain_triple(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        text = g.serialize(format='nt12')
        assert f'<{EX}s>' in text
        assert f'<{EX}p>' in text
        assert f'<{EX}o>' in text
        assert text.endswith('\n')

    def test_triple_term_as_object(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        text = g.serialize(format='nt12')
        assert '<<(' in text
        assert f'<{EX}alice>' in text

    def test_literal_serialized_with_datatype(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), Literal('hello')))
        text = g.serialize(format='nt12')
        assert '"hello"' in text
        assert 'xsd' in text.lower() or 'XMLSchema' in text

    def test_bnode_serialized(self):
        g = StarLayerGraph()
        bn = BNode()
        g.add((bn, ex('p'), ex('o')))
        text = g.serialize(format='nt12')
        assert '_:' in text


# ---------------------------------------------------------------------------
# N-Triples 1.2 — round-trip
# ---------------------------------------------------------------------------

class TestNT12RoundTrip:
    def test_plain_triple_roundtrip(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        _, g2 = round_trip(g, 'nt12')
        assert (ex('s'), ex('p'), ex('o')) in g2

    def test_triple_term_object_roundtrip(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('s'), ex('p'), ex('o'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        _, g2 = round_trip(g, 'nt12')
        objs = list(g2.objects(ex('stmt1'), RDF_REIFIES))
        assert tt in objs

    def test_length_preserved(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('s'), ex('p'), ex('o'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        g.add((ex('stmt1'), ex('confidence'), Literal('0.9')))
        g.add((ex('s'), ex('p'), ex('o')))
        _, g2 = round_trip(g, 'nt12')
        assert len(g2) == len(g)


# ---------------------------------------------------------------------------
# N-Quads 1.2
# ---------------------------------------------------------------------------

class TestNQ12:
    def test_parse_ignores_graph_name(self):
        nq = (
            f'<{EX}s> <{EX}p> <{EX}o> <{EX}graph1> .\n'
            f'<{EX}a> <{EX}b> <{EX}c> <{EX}graph2> .\n'
        )
        g = StarLayerGraph()
        g.parse(data=nq, format='nq12')
        # Both triples should be merged into this graph
        assert (ex('s'), ex('p'), ex('o')) in g
        assert (ex('a'), ex('b'), ex('c')) in g

    def test_parse_triple_term_in_nquads(self):
        nq = (
            f'<{EX}stmt1> <{RDF_REIFIES}> '
            f'<<( <{EX}alice> <{EX}knows> <{EX}bob> )>> '
            f'<{EX}graph1> .\n'
        )
        g = StarLayerGraph()
        g.parse(data=nq, format='nq12')
        assert g.has_triple_term(ex('alice'), ex('knows'), ex('bob'))

    def test_serialize_includes_graph_name(self):
        g = StarLayerGraph(identifier=ex('mygraph'))
        g.add((ex('s'), ex('p'), ex('o')))
        text = g.serialize(format='nq12')
        assert f'<{EX}mygraph>' in text
        assert f'<{EX}s>' in text

    def test_serialize_triple_term_nquads(self):
        g = StarLayerGraph(identifier=ex('mygraph'))
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        text = g.serialize(format='nq12')
        assert '<<(' in text
        assert f'<{EX}mygraph>' in text

    def test_roundtrip_nquads(self):
        g = StarLayerGraph(identifier=ex('mygraph'))
        tt = TripleTerm(ex('s'), ex('p'), ex('o'))
        g.add((ex('stmt'), RDF_REIFIES, tt))
        g.add((ex('a'), ex('b'), ex('c')))
        text = g.serialize(format='nq12')
        g2 = StarLayerGraph()
        g2.parse(data=text, format='nq12')
        assert (ex('a'), ex('b'), ex('c')) in g2
        assert g2.has_triple_term(ex('s'), ex('p'), ex('o'))


# ---------------------------------------------------------------------------
# TriG 1.2 — parsing
# ---------------------------------------------------------------------------

class TestTriG12Parse:
    def test_default_graph_triple(self):
        trig = f'<{EX}s> <{EX}p> <{EX}o> .\n'
        g = StarLayerGraph()
        g.parse(data=trig, format='trig12')
        assert (ex('s'), ex('p'), ex('o')) in g

    def test_named_graph_block(self):
        trig = (
            f'@prefix ex: <{EX}> .\n'
            f'GRAPH <{EX}g1> {{\n'
            f'  ex:s ex:p ex:o .\n'
            f'}}\n'
        )
        g = StarLayerGraph()
        g.parse(data=trig, format='trig12')
        assert (ex('s'), ex('p'), ex('o')) in g

    def test_triple_term_in_named_graph(self):
        trig = (
            f'@prefix ex: <{EX}> .\n'
            f'@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n'
            f'GRAPH <{EX}g1> {{\n'
            f'  ex:stmt1 rdf:reifies <<( ex:alice ex:knows ex:bob )>> .\n'
            f'}}\n'
        )
        g = StarLayerGraph()
        g.parse(data=trig, format='trig12')
        assert g.has_triple_term(ex('alice'), ex('knows'), ex('bob'))

    def test_multiple_named_graphs_merged(self):
        trig = (
            f'@prefix ex: <{EX}> .\n'
            f'GRAPH <{EX}g1> {{\n'
            f'  ex:a ex:b ex:c .\n'
            f'}}\n'
            f'GRAPH <{EX}g2> {{\n'
            f'  ex:x ex:y ex:z .\n'
            f'}}\n'
        )
        g = StarLayerGraph()
        g.parse(data=trig, format='trig12')
        assert (ex('a'), ex('b'), ex('c')) in g
        assert (ex('x'), ex('y'), ex('z')) in g

    def test_default_and_named_graph_merged(self):
        trig = (
            f'@prefix ex: <{EX}> .\n'
            f'ex:default ex:graph ex:triple .\n'
            f'GRAPH <{EX}g1> {{\n'
            f'  ex:named ex:graph ex:triple .\n'
            f'}}\n'
        )
        g = StarLayerGraph()
        g.parse(data=trig, format='trig12')
        assert (ex('default'), ex('graph'), ex('triple')) in g
        assert (ex('named'), ex('graph'), ex('triple')) in g


# ---------------------------------------------------------------------------
# TriG 1.2 — serialization
# ---------------------------------------------------------------------------

class TestTriG12Serialize:
    def test_default_graph_is_plain_turtle(self):
        g = StarLayerGraph()  # default BNode identifier
        g.add((ex('s'), ex('p'), ex('o')))
        text = g.serialize(format='trig12')
        assert 'GRAPH' not in text
        assert f'<{EX}' in text

    def test_named_graph_wrapped(self):
        g = StarLayerGraph(identifier=ex('mygraph'))
        g.add((ex('s'), ex('p'), ex('o')))
        text = g.serialize(format='trig12')
        assert 'GRAPH' in text
        assert f'<{EX}mygraph>' in text

    def test_triple_term_in_trig(self):
        g = StarLayerGraph(identifier=ex('mygraph'))
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        text = g.serialize(format='trig12')
        assert '<<(' in text
        assert 'GRAPH' in text

    def test_prefixes_before_graph_block(self):
        g = StarLayerGraph(identifier=ex('mygraph'))
        g.bind('ex', EX)
        g.add((ex('s'), ex('p'), ex('o')))
        text = g.serialize(format='trig12')
        lines = text.strip().splitlines()
        # Prefix declarations should come before GRAPH block
        prefix_idx = next((i for i, l in enumerate(lines) if '@prefix' in l), None)
        graph_idx  = next((i for i, l in enumerate(lines) if 'GRAPH' in l), None)
        if prefix_idx is not None and graph_idx is not None:
            assert prefix_idx < graph_idx


# ---------------------------------------------------------------------------
# TriG 1.2 — round-trip
# ---------------------------------------------------------------------------

class TestTriG12RoundTrip:
    def test_plain_triple_roundtrip(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        _, g2 = round_trip(g, 'trig12')
        assert (ex('s'), ex('p'), ex('o')) in g2

    def test_triple_term_roundtrip(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        _, g2 = round_trip(g, 'trig12')
        assert g2.has_triple_term(ex('alice'), ex('knows'), ex('bob'))
        objs = list(g2.objects(ex('stmt1'), RDF_REIFIES))
        assert tt in objs

    def test_length_preserved(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('s'), ex('p'), ex('o'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        g.add((ex('stmt1'), ex('confidence'), Literal('0.9')))
        g.add((ex('s'), ex('p'), ex('o')))
        _, g2 = round_trip(g, 'trig12')
        assert len(g2) == len(g)


# ---------------------------------------------------------------------------
# RDF 1.2 version declaration — nt12, nq12, trig12
# ---------------------------------------------------------------------------

class TestVersionDeclarationNT12:
    def test_emitted_when_triple_terms_present(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('s'), ex('p'), ex('o'))
        g.add((ex('stmt'), RDF_REIFIES, tt))
        text = g.serialize(format='nt12')
        assert text.startswith('VERSION "1.2"')

    def test_not_emitted_for_plain_graph(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        text = g.serialize(format='nt12')
        assert 'VERSION' not in text

    def test_version_line_before_triples(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('s'), ex('p'), ex('o'))
        g.add((ex('stmt'), RDF_REIFIES, tt))
        text = g.serialize(format='nt12')
        lines = [l for l in text.splitlines() if l.strip()]
        assert lines[0].startswith('VERSION')

    def test_parser_skips_version_line(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('s'), ex('p'), ex('o'))
        g.add((ex('stmt'), RDF_REIFIES, tt))
        text = g.serialize(format='nt12')
        g2 = StarLayerGraph()
        g2.parse(data=text, format='nt12')
        assert g2.has_triple_term(ex('s'), ex('p'), ex('o'))

    def test_round_trip_preserves_triple_term(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        _, g2 = round_trip(g, 'nt12')
        assert g2.has_triple_term(ex('alice'), ex('knows'), ex('bob'))


class TestVersionDeclarationNQ12:
    def test_emitted_when_triple_terms_present(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('s'), ex('p'), ex('o'))
        g.add((ex('stmt'), RDF_REIFIES, tt))
        text = g.serialize(format='nq12')
        assert text.startswith('VERSION "1.2"')

    def test_not_emitted_for_plain_graph(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        text = g.serialize(format='nq12')
        assert 'VERSION' not in text

    def test_parser_skips_version_line(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('s'), ex('p'), ex('o'))
        g.add((ex('stmt'), RDF_REIFIES, tt))
        text = g.serialize(format='nq12')
        g2 = StarLayerGraph()
        g2.parse(data=text, format='nq12')
        assert g2.has_triple_term(ex('s'), ex('p'), ex('o'))

    def test_round_trip_preserves_triple_term(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        _, g2 = round_trip(g, 'nq12')
        assert g2.has_triple_term(ex('alice'), ex('knows'), ex('bob'))


class TestVersionDeclarationTriG12:
    def test_emitted_when_triple_terms_present(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('s'), ex('p'), ex('o'))
        g.add((ex('stmt'), RDF_REIFIES, tt))
        text = g.serialize(format='trig12')
        assert '@version "1.2" .' in text

    def test_not_emitted_for_plain_graph(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        text = g.serialize(format='trig12')
        assert '@version' not in text

    def test_version_before_prefix_declarations(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        tt = TripleTerm(ex('s'), ex('p'), ex('o'))
        g.add((ex('stmt'), RDF_REIFIES, tt))
        text = g.serialize(format='trig12')
        lines = [l for l in text.splitlines() if l.strip()]
        version_idx = next((i for i, l in enumerate(lines) if '@version' in l), None)
        prefix_idx  = next((i for i, l in enumerate(lines) if '@prefix' in l), None)
        assert version_idx is not None
        if prefix_idx is not None:
            assert version_idx < prefix_idx

    def test_parser_handles_version_directive(self):
        trig = (
            f'@version "1.2" .\n'
            f'@prefix ex: <{EX}> .\n'
            f'@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n'
            f'ex:stmt rdf:reifies <<( ex:s ex:p ex:o )>> .\n'
        )
        g = StarLayerGraph()
        g.parse(data=trig, format='trig12')
        assert g.has_triple_term(ex('s'), ex('p'), ex('o'))

    def test_round_trip_preserves_triple_term(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        _, g2 = round_trip(g, 'trig12')
        assert g2.has_triple_term(ex('alice'), ex('knows'), ex('bob'))


# ---------------------------------------------------------------------------
# TriX 1.2 — StarLayerGraph (single graph)
# ---------------------------------------------------------------------------

class TestTriX12Parse:
    """Uses starlayergraph's original <TriX>/<tripleTerm> spelling - kept working
    for backward compatibility only, no longer emitted by the serializer
    (see TestTriX12ParseJenaConvention for the current, Jena-matching form
    and docs/future_enhancements.md for why the switch happened)."""

    def test_plain_triple(self):
        xml = (
            '<?xml version="1.0"?>'
            '<TriX xmlns="http://www.w3.org/2004/03/trix/trix-1/">'
            '<graph>'
            f'<triple><uri>{EX}s</uri><uri>{EX}p</uri><uri>{EX}o</uri></triple>'
            '</graph></TriX>'
        )
        g = StarLayerGraph()
        g.parse(data=xml, format='trix12')
        assert (ex('s'), ex('p'), ex('o')) in g

    def test_literal_plain(self):
        xml = (
            '<?xml version="1.0"?>'
            '<TriX xmlns="http://www.w3.org/2004/03/trix/trix-1/">'
            '<graph>'
            f'<triple><uri>{EX}s</uri><uri>{EX}p</uri>'
            '<plainLiteral>hello</plainLiteral></triple>'
            '</graph></TriX>'
        )
        g = StarLayerGraph()
        g.parse(data=xml, format='trix12')
        objs = list(g.objects(ex('s'), ex('p')))
        assert Literal('hello') in objs

    def test_typed_literal(self):
        xml = (
            '<?xml version="1.0"?>'
            '<TriX xmlns="http://www.w3.org/2004/03/trix/trix-1/">'
            '<graph>'
            f'<triple><uri>{EX}s</uri><uri>{EX}p</uri>'
            '<typedLiteral datatype="http://www.w3.org/2001/XMLSchema#integer">42</typedLiteral>'
            '</triple></graph></TriX>'
        )
        g = StarLayerGraph()
        g.parse(data=xml, format='trix12')
        from rdflib.namespace import XSD as XSD2
        assert (ex('s'), ex('p'), Literal(42, datatype=XSD2.integer)) in g

    def test_triple_term_as_object(self):
        xml = (
            '<?xml version="1.0"?>'
            '<TriX xmlns="http://www.w3.org/2004/03/trix/trix-1/">'
            '<graph>'
            f'<triple><uri>{EX}stmt</uri>'
            '<uri>http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies</uri>'
            f'<tripleTerm><uri>{EX}alice</uri><uri>{EX}knows</uri><uri>{EX}bob</uri></tripleTerm>'
            '</triple></graph></TriX>'
        )
        g = StarLayerGraph()
        g.parse(data=xml, format='trix12')
        assert g.has_triple_term(ex('alice'), ex('knows'), ex('bob'))

    def test_named_graph_triples_merged(self):
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
        g = StarLayerGraph()
        g.parse(data=xml, format='trix12')
        assert (ex('a'), ex('b'), ex('c')) in g
        assert (ex('x'), ex('y'), ex('z')) in g


class TestTriX12ParseJenaConvention:
    """Lowercase <trix> root element, and a nested <triple> (not a distinct
    <tripleTerm> tag) for an RDF 1.2 triple term - matches Apache Jena's real
    TriX writer, confirmed live against Fuseki 5.5.0 2026-07-16/17 (the only
    production TriX implementation found to support triple terms at all;
    Oxigraph doesn't implement TriX). This is what starlayergraph's own
    serializer now emits - see TestTriX12Serialize below."""

    def test_lowercase_root_element(self):
        xml = (
            '<?xml version="1.0"?>'
            '<trix xmlns="http://www.w3.org/2004/03/trix/trix-1/">'
            '<graph>'
            f'<triple><uri>{EX}s</uri><uri>{EX}p</uri><uri>{EX}o</uri></triple>'
            '</graph></trix>'
        )
        g = StarLayerGraph()
        g.parse(data=xml, format='trix12')
        assert (ex('s'), ex('p'), ex('o')) in g

    def test_nested_triple_as_triple_term(self):
        xml = (
            '<?xml version="1.0"?>'
            '<trix xmlns="http://www.w3.org/2004/03/trix/trix-1/">'
            '<graph>'
            f'<triple><uri>{EX}stmt</uri>'
            '<uri>http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies</uri>'
            f'<triple><uri>{EX}alice</uri><uri>{EX}knows</uri><uri>{EX}bob</uri></triple>'
            '</triple></graph></trix>'
        )
        g = StarLayerGraph()
        g.parse(data=xml, format='trix12')
        assert g.has_triple_term(ex('alice'), ex('knows'), ex('bob'))

    def test_parses_real_fuseki_output_verbatim(self):
        # Captured live from a running Fuseki 5.5.0 (secoresearch/fuseki:latest)
        # 2026-07-17: INSERT DATA a triple term, then CONSTRUCT it back out
        # with Accept: application/trix+xml. This is the exact bytes Fuseki
        # produced, not a hand-written approximation of its format.
        fuseki_output = (
            '<trix xmlns="http://www.w3.org/2004/03/trix/trix-1/">\n'
            '  <graph>\n'
            '    <triple>\n'
            f'      <uri>{EX}stmt</uri>\n'
            '      <uri>http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies</uri>\n'
            '      <triple>\n'
            f'        <uri>{EX}a</uri>\n'
            f'        <uri>{EX}b</uri>\n'
            f'        <uri>{EX}c</uri>\n'
            '      </triple>\n'
            '    </triple>\n'
            '  </graph>\n'
            '</trix>'
        )
        g = StarLayerGraph()
        g.parse(data=fuseki_output, format='trix12')
        assert g.has_triple_term(ex('a'), ex('b'), ex('c'))
        assert (ex('stmt'), RDF_REIFIES, TripleTerm(ex('a'), ex('b'), ex('c'))) in g


class TestTriX12Serialize:
    def test_plain_triple(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        out = g.serialize(format='trix12')
        assert f'{EX}s' in out
        assert f'{EX}p' in out
        assert f'{EX}o' in out
        assert '<triple>' in out

    def test_triple_term_as_object(self):
        # Jena convention: a triple term is a nested <triple>, not a distinct
        # <tripleTerm> tag - confirmed against a live Fuseki 5.5.0 2026-07-17.
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt'), RDF_REIFIES, tt))
        out = g.serialize(format='trix12')
        assert out.count('<triple>') == 2  # outer statement + nested triple term
        assert f'{EX}alice' in out

    def test_named_graph_identifier_in_output(self):
        g = StarLayerGraph(identifier=ex('mygraph'))
        g.add((ex('s'), ex('p'), ex('o')))
        out = g.serialize(format='trix12')
        assert f'{EX}mygraph' in out
        assert '<uri>' in out

    def test_xml_declaration(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        out = g.serialize(format='trix12')
        assert out.startswith('<?xml')

    def test_trix_namespace(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        out = g.serialize(format='trix12')
        assert 'http://www.w3.org/2004/03/trix/trix-1/' in out


class TestTriX12RoundTrip:
    def test_plain_triple(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        _, g2 = round_trip(g, 'trix12')
        assert (ex('s'), ex('p'), ex('o')) in g2

    def test_triple_term_object(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt'), RDF_REIFIES, tt))
        _, g2 = round_trip(g, 'trix12')
        assert g2.has_triple_term(ex('alice'), ex('knows'), ex('bob'))
        assert tt in list(g2.objects(ex('stmt'), RDF_REIFIES))

    def test_literal_types_preserved(self):
        from rdflib.namespace import XSD as XSD2
        g = StarLayerGraph()
        g.add((ex('s'), ex('p1'), Literal('hello', lang='en')))
        g.add((ex('s'), ex('p2'), Literal(42, datatype=XSD2.integer)))
        _, g2 = round_trip(g, 'trix12')
        assert (ex('s'), ex('p1'), Literal('hello', lang='en')) in g2
        assert (ex('s'), ex('p2'), Literal(42, datatype=XSD2.integer)) in g2

    def test_length_preserved(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('s'), ex('p'), ex('o'))
        g.add((ex('stmt'), RDF_REIFIES, tt))
        g.add((ex('stmt'), ex('confidence'), Literal('0.9')))
        g.add((ex('s'), ex('p'), ex('o')))
        _, g2 = round_trip(g, 'trix12')
        assert len(g2) == len(g)


# ---------------------------------------------------------------------------
# TriX 1.2 — StarLayerDataset (named graphs)
# ---------------------------------------------------------------------------

class TestTriX12Dataset:
    def _make_ds(self):
        from starlayergraph.graph import StarLayerDataset
        ds = StarLayerDataset()
        g1 = StarLayerGraph(identifier=ex('g1'))
        g1.add((ex('s'), ex('p'), ex('o')))
        g2 = StarLayerGraph(identifier=ex('g2'))
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g2.add((ex('stmt'), RDF_REIFIES, tt))
        ds.add_graph(g1)
        ds.add_graph(g2)
        return ds

    def test_serialize_contains_both_graphs(self):
        ds = self._make_ds()
        out = ds.serialize(format='trix12')
        assert f'{EX}g1' in out
        assert f'{EX}g2' in out

    def test_serialize_triple_term_present(self):
        ds = self._make_ds()
        out = ds.serialize(format='trix12')
        # g1's plain triple (1) + g2's reification statement (1) + its
        # nested triple term (1) = 3 <triple> elements total.
        assert out.count('<triple>') == 3

    def test_parse_preserves_graph_count(self):
        from starlayergraph.graph import StarLayerDataset
        ds = self._make_ds()
        out = ds.serialize(format='trix12')
        ds2 = StarLayerDataset()
        ds2.parse(data=out, format='trix12')
        non_empty = [sg for sg in ds2.contexts() if len(sg) > 0]
        assert len(non_empty) == 2

    def test_parse_triple_term_survives_dataset_roundtrip(self):
        from starlayergraph.graph import StarLayerDataset
        ds = self._make_ds()
        out = ds.serialize(format='trix12')
        ds2 = StarLayerDataset()
        ds2.parse(data=out, format='trix12')
        g2 = ds2.get_context(ex('g2'))
        assert g2.has_triple_term(ex('alice'), ex('knows'), ex('bob'))


# ---------------------------------------------------------------------------
# RDF/XML 1.2
# ---------------------------------------------------------------------------

class TestRDFXML12Parse:
    def test_plain_triple(self):
        xml = (
            '<?xml version="1.0"?>'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'
            f' xmlns:ex="{EX}">'
            f'<rdf:Description rdf:about="{EX}s">'
            f'<ex:p rdf:resource="{EX}o"/>'
            '</rdf:Description></rdf:RDF>'
        )
        g = StarLayerGraph()
        g.parse(data=xml, format='rdfxml12')
        assert (ex('s'), ex('p'), ex('o')) in g

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

    def test_typed_literal(self):
        xml = (
            '<?xml version="1.0"?>'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'
            f' xmlns:ex="{EX}"'
            ' xmlns:xsd="http://www.w3.org/2001/XMLSchema#">'
            f'<rdf:Description rdf:about="{EX}s">'
            '<ex:age rdf:datatype="http://www.w3.org/2001/XMLSchema#integer">42</ex:age>'
            '</rdf:Description></rdf:RDF>'
        )
        g = StarLayerGraph()
        g.parse(data=xml, format='rdfxml12')
        assert (ex('s'), ex('age'), Literal(42, datatype=XSD.integer)) in g


class TestRDFXML12Serialize:
    def test_plain_triple_in_output(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        out = g.serialize(format='rdfxml12')
        assert f'{EX}s' in out
        assert f'{EX}o' in out

    def test_xml_declaration(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        out = g.serialize(format='rdfxml12')
        assert out.startswith('<?xml')

    def test_rdf_namespace_declared(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        out = g.serialize(format='rdfxml12')
        assert 'http://www.w3.org/1999/02/22-rdf-syntax-ns#' in out

    def test_triple_term_object_emitted(self):
        # RDF 1.2 XML Syntax sec 2.19: a triple term is rdf:parseType="Triple"
        # wrapping a single <rdf:Description>, not an invented element name.
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt'), RDF_REIFIES, tt))
        out = g.serialize(format='rdfxml12')
        assert 'rdf:parseType="Triple"' in out
        assert 'rdf:TripleTerm' not in out
        assert f'{EX}alice' in out


class TestRDFXML12RoundTrip:
    def test_plain_triple(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        _, g2 = round_trip(g, 'rdfxml12')
        assert (ex('s'), ex('p'), ex('o')) in g2

    def test_triple_term_object(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt'), RDF_REIFIES, tt))
        _, g2 = round_trip(g, 'rdfxml12')
        assert g2.has_triple_term(ex('alice'), ex('knows'), ex('bob'))
        assert tt in list(g2.objects(ex('stmt'), RDF_REIFIES))

    def test_typed_literal(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), Literal(42, datatype=XSD.integer)))
        _, g2 = round_trip(g, 'rdfxml12')
        assert (ex('s'), ex('p'), Literal(42, datatype=XSD.integer)) in g2

    def test_lang_literal(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), Literal('bonjour', lang='fr')))
        _, g2 = round_trip(g, 'rdfxml12')
        assert (ex('s'), ex('p'), Literal('bonjour', lang='fr')) in g2

    def test_length_preserved(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('s'), ex('p'), ex('o'))
        g.add((ex('stmt'), RDF_REIFIES, tt))
        g.add((ex('stmt'), ex('confidence'), Literal('0.9')))
        g.add((ex('s'), ex('p'), ex('o')))
        _, g2 = round_trip(g, 'rdfxml12')
        assert len(g2) == len(g)

    def test_nested_triple_term_object(self):
        # The inner property's own object is itself a triple term - recursive
        # rdf:parseType="Triple" nesting (an extrapolation beyond the spec's
        # single-level example, since RDF 1.2's abstract model permits nesting
        # and nothing in the XML grammar forbids it).
        g = StarLayerGraph()
        inner = TripleTerm(ex('bob'), ex('knows'), ex('dave'))
        outer = TripleTerm(ex('alice'), ex('believes'), inner)
        g.add((ex('r'), ex('about'), outer))
        _, g2 = round_trip(g, 'rdfxml12')
        result = next(g2.objects(ex('r'), ex('about')))
        assert result == outer
        assert result.object == inner


class TestRDFXML12SpecInterop:
    """Interop with the RDF 1.2 XML Syntax spec's own examples (sec 2.19-2.20) -
    starlayergraph's serializer never emits rdf:annotation/rdf:annotationNodeID
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

    def test_rdf_annotation_iri_reifier_matches_spec_example(self):
        # Verbatim shape from RDF 1.2 XML Syntax sec 2.20.
        xml = (
            '<?xml version="1.0"?>'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'
            ' xmlns:ex="http://example.org/stuff/1.0/">'
            '<rdf:Description rdf:about="http://example.org/">'
            '<ex:prop rdf:annotation="http://example.org/triple1">blah</ex:prop>'
            '</rdf:Description>'
            '<rdf:Description rdf:about="http://example.org/triple1">'
            '<ex:prop>foo</ex:prop>'
            '</rdf:Description></rdf:RDF>'
        )
        g = StarLayerGraph()
        g.parse(data=xml, format='rdfxml12')
        base = URIRef('http://example.org/')
        prop = URIRef('http://example.org/stuff/1.0/prop')
        reifier = URIRef('http://example.org/triple1')
        # Base triple still asserted
        assert (base, prop, Literal('blah')) in g
        # Reifier reifies exactly that triple term
        assert list(g.reified_triples(reifier)) == [TripleTerm(base, prop, Literal('blah'))]
        # Reifier's own separately-declared property survives
        assert (reifier, prop, Literal('foo')) in g

    def test_rdf_annotation_node_id_reifier_matches_spec_example(self):
        # Verbatim shape from RDF 1.2 XML Syntax sec 2.20 (blank-node reifier variant).
        xml = (
            '<?xml version="1.0"?>'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'
            ' xmlns:ex="http://example.org/stuff/1.0/">'
            '<rdf:Description rdf:about="http://example.org/">'
            '<ex:prop rdf:annotationNodeID="triple1">blah</ex:prop>'
            '</rdf:Description>'
            '<rdf:Description rdf:nodeID="triple1">'
            '<ex:prop>foo</ex:prop>'
            '</rdf:Description></rdf:RDF>'
        )
        g = StarLayerGraph()
        g.parse(data=xml, format='rdfxml12')
        base = URIRef('http://example.org/')
        prop = URIRef('http://example.org/stuff/1.0/prop')
        assert (base, prop, Literal('blah')) in g
        reifiers = list(g.reifiers(TT=TripleTerm(base, prop, Literal('blah'))))
        assert len(reifiers) == 1
        assert isinstance(reifiers[0], BNode)
        assert (reifiers[0], prop, Literal('foo')) in g
