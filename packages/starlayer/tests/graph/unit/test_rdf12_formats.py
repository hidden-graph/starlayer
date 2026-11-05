"""
Unit tests for RDF 1.2 format parsing and serialization.

Covers N-Triples 1.2 (nt12), N-Quads 1.2 (nq12), and TriG 1.2 (trig12)
via StarLayerGraph.parse() and StarLayerGraph.serialize().
"""

import pyoxigraph as ox
import pytest
from starlayer.graph.oxgraph import StarLayerDataset, StarLayerGraph

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


class XSD:  # the XSD namespace: XSD.integer is the datatype IRI
    integer = _XSD + "integer"


RDF_REIFIES = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")

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
        nt = f'<{EX}s> <{EX}age> "42"^^<{XSD.integer}> .\n'
        g = StarLayerGraph()
        g.parse(data=nt, format='nt12')
        objs = list(g.objects(ex('s'), ex('age')))
        assert any(o.value == '42' for o in objs)

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
        nt = f'<{EX}stmt1> <{RDF_REIFIES.value}> <<( <{EX}alice> <{EX}knows> <{EX}bob> )>> .\n'
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
        assert any('\n' in o.value for o in objs)


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
        assert '"hello"' in text  # N-Triples writes an xsd:string literal plain (the old writer spelled the datatype out)

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
    def test_parse_single_named_graph_is_refused_by_a_graph_view(self):
        """The old class dropped a single graph's name; an StarLayerGraph refuses any named graph (parse into an StarLayerDataset)."""
        nq = (
            f'<{EX}s> <{EX}p> <{EX}o> <{EX}graph1> .\n'
            f'<{EX}a> <{EX}b> <{EX}c> <{EX}graph1> .\n'
        )
        g = StarLayerGraph()
        with pytest.raises(ValueError, match='named graphs'):
            g.parse(data=nq, format='nq12')
        assert len(g) == 0
        ds = StarLayerDataset().parse(data=nq, format='nq12')
        assert {q.graph_name.value for q in ds.quads()} == {EX + 'graph1'}

    def test_parse_multiple_distinct_graphs_into_a_dataset_keeps_them_apart(self):
        nq = (
            f'<{EX}s> <{EX}p> <{EX}o> <{EX}graph1> .\n'
            f'<{EX}a> <{EX}b> <{EX}c> <{EX}graph2> .\n'
        )
        with pytest.raises(ValueError, match='named graphs'):
            StarLayerGraph().parse(data=nq, format='nq12')
        ds = StarLayerDataset().parse(data=nq, format='nq12')
        assert {(q.subject.value, q.graph_name.value) for q in ds.quads()} == {(EX + 's', EX + 'graph1'), (EX + 'a', EX + 'graph2')}

    def test_parse_triple_term_in_nquads(self):
        nq = (
            f'<{EX}stmt1> <{RDF_REIFIES.value}> '
            f'<<( <{EX}alice> <{EX}knows> <{EX}bob> )>> '
            f'<{EX}graph1> .\n'
        )
        g = StarLayerDataset()
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
        g2 = StarLayerDataset()
        g2.parse(data=text, format='nq12')
        assert (ex('a'), ex('b'), ex('c')) in g2.graph(ex('mygraph'))
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
        with pytest.raises(ValueError, match='named graphs'):  # an StarLayerGraph refuses named graphs (the old one flattened one)
            StarLayerGraph().parse(data=trig, format='trig12')
        g = StarLayerDataset()
        g.parse(data=trig, format='trig12')
        assert (ex('s'), ex('p'), ex('o')) in g.graph(ex('g1'))

    def test_triple_term_in_named_graph(self):
        trig = (
            f'@prefix ex: <{EX}> .\n'
            f'@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n'
            f'GRAPH <{EX}g1> {{\n'
            f'  ex:stmt1 rdf:reifies <<( ex:alice ex:knows ex:bob )>> .\n'
            f'}}\n'
        )
        g = StarLayerDataset()
        g.parse(data=trig, format='trig12')
        assert g.graph(ex('g1')).has_triple_term(ex('alice'), ex('knows'), ex('bob'))

    def test_multiple_named_graphs_are_refused_by_a_graph_view(self):
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
        with pytest.raises(ValueError, match='named graphs'):
            g.parse(data=trig, format='trig12')
        assert len(g) == 0

    def test_default_and_named_graph_are_refused_by_a_graph_view(self):
        trig = (
            f'@prefix ex: <{EX}> .\n'
            f'ex:default ex:graph ex:triple .\n'
            f'GRAPH <{EX}g1> {{\n'
            f'  ex:named ex:graph ex:triple .\n'
            f'}}\n'
        )
        g = StarLayerGraph()
        with pytest.raises(ValueError, match='named graphs'):
            g.parse(data=trig, format='trig12')
        assert len(g) == 0


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
        assert f'<{EX}mygraph> {{' in text  # Oxigraph's TriG writer has no GRAPH keyword

    def test_triple_term_in_trig(self):
        g = StarLayerGraph(identifier=ex('mygraph'))
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('stmt1'), RDF_REIFIES, tt))
        text = g.serialize(format='trig12')
        assert '<<(' in text
        assert f'<{EX}mygraph> {{' in text  # Oxigraph's TriG writer has no GRAPH keyword

    def test_prefixes_before_graph_block(self):
        g = StarLayerGraph(identifier=ex('mygraph'))
        g.bind('ex', EX)
        g.add((ex('s'), ex('p'), ex('o')))
        text = g.serialize(format='trig12')
        lines = text.strip().splitlines()
        # Prefix declarations should come before the graph block
        prefix_idx = next((i for i, line in enumerate(lines) if '@prefix' in line), None)
        graph_idx  = next((i for i, line in enumerate(lines) if line.endswith(' {')), None)
        assert prefix_idx is not None and graph_idx is not None
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
        lines = [line for line in text.splitlines() if line.strip()]
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
        lines = [line for line in text.splitlines() if line.strip()]
        version_idx = next((i for i, line in enumerate(lines) if '@version' in line), None)
        prefix_idx  = next((i for i, line in enumerate(lines) if '@prefix' in line), None)
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
    starlayer.graph's serializer never emits rdf:annotation/rdf:annotationNodeID
    (it always uses the formal rdf:reifies + parseType="Triple" pattern), but
    the parser accepts them so documents from other spec-conformant tools
    still parse correctly.
    """


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
        assert isinstance(reifiers[0], ox.BlankNode)
        assert (reifiers[0], prop, Literal('foo')) in g


# ---------------------------------------------------------------------------
# N3 — aliased straight to turtle12 (plain-triples subset only, not real N3)
# ---------------------------------------------------------------------------

class TestN3AliasGraph:
    def test_parse_plain_triples(self):
        g = StarLayerGraph()
        g.parse(data=f'@prefix ex: <{EX}> . ex:s ex:p ex:o .', format='n3')
        assert (ex('s'), ex('p'), ex('o')) in g

    def test_parse_text_n3_mimetype_alias(self):
        g = StarLayerGraph()
        g.parse(data=f'@prefix ex: <{EX}> . ex:s ex:p ex:o .', format='text/n3')
        assert (ex('s'), ex('p'), ex('o')) in g

    def test_parse_triple_term_content(self):
        g = StarLayerGraph()
        g.parse(
            data=(
                f'@prefix ex: <{EX}> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . '
                'ex:claim rdf:reifies <<( ex:bob ex:knows ex:carol )>> .'
            ),
            format='n3',
        )
        assert g.has_triple_term(ex('bob'), ex('knows'), ex('carol'))

    def test_parse_real_n3_rule_fails(self):
        n3_rule = (
            f'@prefix ex: <{EX}> . '
            '{ ?x ex:parent ?y . ?y ex:parent ?z } => { ?x ex:grandparent ?z } .'
        )
        g = StarLayerGraph()
        with pytest.raises(SyntaxError):
            g.parse(data=n3_rule, format='n3')

    def test_serialize_default(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        out = g.serialize(format='n3')
        assert f'<{EX}' in out

    def test_serialize_triple_term_as_turtle12_syntax(self):
        g = StarLayerGraph()
        g.add((ex('claim'), RDF_REIFIES, TripleTerm(ex('bob'), ex('knows'), ex('carol'))))
        out = g.serialize(format='n3')
        assert '<<(' in out

    def test_round_trip(self):
        text, g2 = round_trip_graph_with_tt(format='n3')
        assert g2.has_triple_term(ex('bob'), ex('knows'), ex('carol'))


def round_trip_graph_with_tt(format):
    g = StarLayerGraph()
    g.add((ex('claim'), RDF_REIFIES, TripleTerm(ex('bob'), ex('knows'), ex('carol'))))
    text, g2 = round_trip(g, format)
    return text, g2


class TestN3AliasDataset:
    def test_parse_lands_in_default_graph(self):
        ds = StarLayerDataset()
        ds.parse(data=f'@prefix ex: <{EX}> . ex:s ex:p ex:o .', format='n3')
        assert (ex('s'), ex('p'), ex('o')) in ds.default_graph

    def test_parse_triple_term_content(self):
        ds = StarLayerDataset()
        ds.parse(
            data=(
                f'@prefix ex: <{EX}> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . '
                'ex:claim rdf:reifies <<( ex:bob ex:knows ex:carol )>> .'
            ),
            format='n3',
        )
        assert ds.default_graph.has_triple_term(ex('bob'), ex('knows'), ex('carol'))

    def test_serialize_flattens_like_turtle12(self):
        ds = StarLayerDataset()
        ds.default_graph.add((ex('s'), ex('p'), ex('o')))
        out = ds.serialize(format='n3')
        assert f'<{EX}' in out

    def test_round_trip(self):
        n3_text = (
            f'@prefix ex: <{EX}> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . '
            'ex:claim rdf:reifies <<( ex:bob ex:knows ex:carol )>> .'
        )
        ds = StarLayerDataset()
        ds.parse(data=n3_text, format='n3')
        out = ds.serialize(format='n3')
        ds2 = StarLayerDataset()
        ds2.parse(data=out, format='n3')
        assert ds2.default_graph.has_triple_term(ex('bob'), ex('knows'), ex('carol'))
