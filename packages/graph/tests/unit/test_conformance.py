"""
End-to-end tests for VERSION-directive handling and RDF12ConformanceWarning.

RDF 1.2 Concepts sec 2.1 and SPARQL 1.2 Query sec 4.3 define three version
labels - "1.2" (full), "1.2-basic" (excludes triple terms and dirLangString),
"1.1" (legacy) - and explicitly say the VERSION directive is only a hint: a
processor "is not required to reject features that are outside the
announced version (but could signal them with a warning)". StarLayer signals
via RDF12ConformanceWarning, never a hard error - see
starlayergraph/model/conformance.py.

Also regression-tests a real bug found while checking this against the live
spec text: a SPARQL 1.2 query starting with VERSION "1.2" (the spec's own
example form) previously raised a ParseException on the in-memory backend,
since sparql12_to_11.py never stripped the directive before handing the
query to rdflib's SPARQL 1.1 parser.
"""

import pytest
from rdflib import URIRef

from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starlayergraph.graph.starlayer_dataset import StarLayerDataset
from starlayergraph.backends.native import check_native_version_conformance
from starlayergraph.model.conformance import RDF12ConformanceWarning

EX = 'http://example.org/'


def ex(local: str) -> URIRef:
    return URIRef(EX + local)


class TestSparqlVersionDirective:
    def test_version_directive_no_longer_raises(self):
        # The exact motivating bug: this is valid SPARQL 1.2 syntax (the
        # spec's own example form) and previously raised ParseException.
        g = StarLayerGraph()
        r = g.query('VERSION "1.2"\nSELECT * WHERE { ?s ?p ?o }')
        assert list(r) == []

    def test_version_directive_single_quoted(self):
        g = StarLayerGraph()
        r = g.query("VERSION '1.2'\nSELECT * WHERE { ?s ?p ?o }")
        assert list(r) == []

    def test_version_1_2_basic_with_triple_term_warns(self):
        g = StarLayerGraph()
        q = f"""VERSION "1.2-basic"
            PREFIX : <{EX}>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?s WHERE {{ ?s rdf:reifies <<( :a :b :c )>> . }}
        """
        with pytest.warns(RDF12ConformanceWarning, match='1.2-basic'):
            g.query(q)

    def test_version_1_2_basic_without_triple_term_does_not_warn(self, recwarn):
        g = StarLayerGraph()
        q = f'VERSION "1.2-basic"\nPREFIX : <{EX}>\nSELECT * WHERE {{ ?s ?p ?o }}'
        g.query(q)
        assert not any(issubclass(w.category, RDF12ConformanceWarning) for w in recwarn.list)

    def test_version_1_2_full_with_triple_term_does_not_warn(self, recwarn):
        g = StarLayerGraph()
        q = f"""VERSION "1.2"
            PREFIX : <{EX}>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?s WHERE {{ ?s rdf:reifies <<( :a :b :c )>> . }}
        """
        g.query(q)
        assert not any(issubclass(w.category, RDF12ConformanceWarning) for w in recwarn.list)

    def test_unrecognized_version_label_warns(self):
        g = StarLayerGraph()
        q = 'VERSION "9.9"\nSELECT * WHERE { ?s ?p ?o }'
        with pytest.warns(RDF12ConformanceWarning, match='unrecognized'):
            g.query(q)

    def test_no_version_directive_does_not_warn(self, recwarn):
        g = StarLayerGraph()
        g.query('SELECT * WHERE { ?s ?p ?o }')
        assert not any(issubclass(w.category, RDF12ConformanceWarning) for w in recwarn.list)

    def test_version_1_1_with_triple_term_warns(self):
        # "1.1" means plain RDF 1.1 syntax/semantics - it excludes triple
        # terms/dirLangString at least as strictly as "1.2-basic" does, so a
        # query declaring "1.1" but using a triple term should warn too, not
        # just "1.2-basic".
        g = StarLayerGraph()
        q = f"""VERSION "1.1"
            PREFIX : <{EX}>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?s WHERE {{ ?s rdf:reifies <<( :a :b :c )>> . }}
        """
        with pytest.warns(RDF12ConformanceWarning, match='1.1'):
            g.query(q)


class TestNativeBackendVersionConformance:
    """StarLayerGraph(backend='rdf-1.2') sends SPARQL straight through to a
    real endpoint via HTTP with zero rewriting (correct - Fuseki/Oxigraph
    understand VERSION natively), which means query()/update() never call
    rewrite_sparql12_to_11 and so never ran this check at all until fixed.

    Confirmed live 2026-07-17 against Fuseki 5.5.0 and Oxigraph: both
    execute a VERSION "1.2-basic" + <<( )>> query normally (HTTP 200) with
    no warning or error signal anywhere in the response - so without this
    fix, a native-backend StarLayerGraph would silently never emit
    RDF12ConformanceWarning for the identical query the default in-memory
    backend does warn on, an inconsistency this project otherwise takes
    care to avoid (see tests/integration/test_cross_backend_parity.py).

    check_native_version_conformance() is pure Python logic with no network
    dependency (the network call happens after it, in native_query()/
    http_update()), so it's tested directly here rather than requiring a
    live backend.
    """

    def test_1_2_basic_with_triple_term_warns(self):
        q = f"""VERSION "1.2-basic"
            PREFIX : <{EX}>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?s WHERE {{ ?s rdf:reifies <<( :a :b :c )>> . }}
        """
        with pytest.warns(RDF12ConformanceWarning, match='1.2-basic'):
            check_native_version_conformance(q)

    def test_1_2_basic_without_triple_term_does_not_warn(self, recwarn):
        q = f'VERSION "1.2-basic"\nPREFIX : <{EX}>\nSELECT * WHERE {{ ?s ?p ?o }}'
        check_native_version_conformance(q)
        assert not any(issubclass(w.category, RDF12ConformanceWarning) for w in recwarn.list)

    def test_no_version_directive_does_not_warn(self, recwarn):
        check_native_version_conformance('SELECT * WHERE { ?s ?p ?o }')
        assert not any(issubclass(w.category, RDF12ConformanceWarning) for w in recwarn.list)

    def test_unrecognized_version_label_warns(self):
        with pytest.warns(RDF12ConformanceWarning, match='unrecognized'):
            check_native_version_conformance('VERSION "9.9"\nSELECT * WHERE { ?s ?p ?o }')


class TestTurtleVersionDirective:
    def test_1_2_basic_with_triple_term_warns(self):
        data = f"""@version "1.2-basic" .
            @prefix : <{EX}> .
            :stmt rdf:reifies <<( :bob :knows :carol )>> .
        """
        g = StarLayerGraph()
        with pytest.warns(RDF12ConformanceWarning, match='1.2-basic'):
            g.parse(data=data, format='turtle12')

    def test_1_2_full_with_triple_term_does_not_warn(self, recwarn):
        data = f"""@version "1.2" .
            @prefix : <{EX}> .
            :stmt rdf:reifies <<( :bob :knows :carol )>> .
        """
        g = StarLayerGraph()
        g.parse(data=data, format='turtle12')
        assert not any(issubclass(w.category, RDF12ConformanceWarning) for w in recwarn.list)

    def test_no_version_directive_does_not_warn(self, recwarn):
        data = f'@prefix : <{EX}> .\n:s :p :o .\n'
        g = StarLayerGraph()
        g.parse(data=data, format='turtle12')
        assert not any(issubclass(w.category, RDF12ConformanceWarning) for w in recwarn.list)

    def test_unrecognized_version_label_warns(self):
        data = f'@version "9.9" .\n@prefix : <{EX}> .\n:s :p :o .\n'
        g = StarLayerGraph()
        with pytest.warns(RDF12ConformanceWarning, match='unrecognized'):
            g.parse(data=data, format='turtle12')

    def test_1_1_with_triple_term_warns(self):
        # "1.1" excludes RDF 1.2 features at least as strictly as
        # "1.2-basic" - see TestSparqlVersionDirective.test_version_1_1_with_triple_term_warns.
        data = f"""@version "1.1" .
            @prefix : <{EX}> .
            :stmt rdf:reifies <<( :bob :knows :carol )>> .
        """
        g = StarLayerGraph()
        with pytest.warns(RDF12ConformanceWarning, match='1.1'):
            g.parse(data=data, format='turtle12')


class TestNTriplesNQuadsVersionDirective:
    """N-Triples/N-Quads: the VERSION line was already recognized by the
    parser but only to discard it like a comment, never extracting the
    label - found by asking "does our VERSION support extend to other
    formats?" and actually checking, same day as the Turtle/SPARQL fix."""

    def test_1_2_basic_with_triple_term_warns_nt(self):
        data = (
            'VERSION "1.2-basic"\n'
            f'<{EX}stmt> <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> '
            f'<<( <{EX}a> <{EX}b> <{EX}c> )>> .\n'
        )
        g = StarLayerGraph()
        with pytest.warns(RDF12ConformanceWarning, match='1.2-basic'):
            g.parse(data=data, format='nt12')

    def test_1_2_basic_with_triple_term_warns_nq(self):
        data = (
            'VERSION "1.2-basic"\n'
            f'<{EX}stmt> <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> '
            f'<<( <{EX}a> <{EX}b> <{EX}c> )>> <{EX}g> .\n'
        )
        g = StarLayerGraph()
        with pytest.warns(RDF12ConformanceWarning, match='1.2-basic'):
            g.parse(data=data, format='nq12')

    def test_no_version_directive_does_not_warn(self, recwarn):
        data = f'<{EX}s> <{EX}p> <{EX}o> .\n'
        g = StarLayerGraph()
        g.parse(data=data, format='nt12')
        assert not any(issubclass(w.category, RDF12ConformanceWarning) for w in recwarn.list)

    def test_version_1_2_full_does_not_warn(self, recwarn):
        data = (
            'VERSION "1.2"\n'
            f'<{EX}stmt> <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> '
            f'<<( <{EX}a> <{EX}b> <{EX}c> )>> .\n'
        )
        g = StarLayerGraph()
        g.parse(data=data, format='nt12')
        assert not any(issubclass(w.category, RDF12ConformanceWarning) for w in recwarn.list)

    def test_dataset_nq12_warns(self):
        data = (
            'VERSION "1.2-basic"\n'
            f'<{EX}stmt> <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> '
            f'<<( <{EX}a> <{EX}b> <{EX}c> )>> <{EX}g> .\n'
        )
        ds = StarLayerDataset()
        with pytest.warns(RDF12ConformanceWarning, match='1.2-basic'):
            ds.parse(data=data, format='nq12')


class TestTrigVersionDirective:
    """TriG: the document-level VERSION directive was silently dropped
    entirely - the per-GRAPH-block Turtle parser calls never surfaced it to
    either StarLayerGraph.parse() or StarLayerDataset.parse()."""

    def test_starlayer_graph_trig12_warns(self):
        data = f"""VERSION "1.2-basic"
            PREFIX : <{EX}>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            GRAPH :g1 {{
              :stmt rdf:reifies <<( :bob :knows :carol )>> .
            }}
        """
        g = StarLayerGraph()
        with pytest.warns(RDF12ConformanceWarning, match='1.2-basic'):
            g.parse(data=data, format='trig12')

    def test_starlayer_dataset_trig12_warns(self):
        data = f"""VERSION "1.2-basic"
            PREFIX : <{EX}>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            GRAPH :g1 {{
              :stmt rdf:reifies <<( :bob :knows :carol )>> .
            }}
        """
        ds = StarLayerDataset()
        with pytest.warns(RDF12ConformanceWarning, match='1.2-basic'):
            ds.parse(data=data, format='trig12')

    def test_no_version_directive_does_not_warn(self, recwarn):
        data = f"""PREFIX : <{EX}>
            GRAPH :g1 {{ :s :p :o . }}
        """
        g = StarLayerGraph()
        g.parse(data=data, format='trig12')
        assert not any(issubclass(w.category, RDF12ConformanceWarning) for w in recwarn.list)

    def test_version_1_2_full_does_not_warn(self, recwarn):
        data = f"""VERSION "1.2"
            PREFIX : <{EX}>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            GRAPH :g1 {{
              :stmt rdf:reifies <<( :bob :knows :carol )>> .
            }}
        """
        g = StarLayerGraph()
        g.parse(data=data, format='trig12')
        assert not any(issubclass(w.category, RDF12ConformanceWarning) for w in recwarn.list)


class TestRdfXmlVersionAttribute:
    """RDF/XML's version mechanism is structurally different from every
    other format's - an rdf:version XML attribute on a node/property
    element (confirmed via spec fetch), not a prologue-line directive.

    Found via a live Oxigraph 0.5.9 round trip (2026-07-17): it genuinely
    emits rdf:version on the property element wrapping rdf:parseType="Triple"
    for a reified triple term. Feeding that real output into starlayergraph's own
    parser revealed this wasn't just "unimplemented" - it was actively wrong:
    rdflib's real 'xml' parser treats any attribute it doesn't specifically
    recognize as ordinary RDF/XML "property attribute" shorthand, so an
    unstripped rdf:version asserted a bogus extra triple
    (subject, rdf:version, "1.2") into the graph.
    """

    # Captured verbatim from a live Oxigraph 0.5.9 CONSTRUCT response
    # (Accept: application/rdf+xml) for a graph containing one reified
    # triple term - not a hand-written approximation.
    _OXIGRAPH_OUTPUT = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:its="http://www.w3.org/2005/11/its">\n'
        f'\t<rdf:Description rdf:about="{EX}stmt">\n'
        '\t\t<rdf:reifies rdf:version="1.2" rdf:parseType="Triple">\n'
        f'\t\t\t<rdf:Description rdf:about="{EX}a">\n'
        f'\t\t\t\t<b xmlns="{EX}" rdf:resource="{EX}c"/>\n'
        '\t\t\t</rdf:Description>\n'
        '\t\t</rdf:reifies>\n'
        '\t</rdf:Description>\n'
        '</rdf:RDF>'
    )

    def test_real_oxigraph_output_does_not_produce_bogus_triple(self):
        g = StarLayerGraph()
        g.parse(data=self._OXIGRAPH_OUTPUT, format='rdfxml12')
        # Exactly the one real triple (stmt rdf:reifies <<(a b c)>>) - no
        # extra (TripleTerm(a,b,c), rdf:version, "1.2") triple.
        assert len(g) == 1
        assert g.has_triple_term(ex('a'), ex('b'), ex('c'))
        rdf_version = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#version')
        assert list(g.triples((None, rdf_version, None))) == []

    def test_real_oxigraph_output_extracts_declared_version(self):
        from starlayergraph.parsers.rdfxml12 import extract_version_directive
        assert extract_version_directive(self._OXIGRAPH_OUTPUT) == '1.2'

    def test_1_2_basic_with_triple_term_warns(self):
        data = self._OXIGRAPH_OUTPUT.replace('rdf:version="1.2"', 'rdf:version="1.2-basic"')
        g = StarLayerGraph()
        with pytest.warns(RDF12ConformanceWarning, match='1.2-basic'):
            g.parse(data=data, format='rdfxml12')

    def test_no_version_attribute_does_not_warn(self, recwarn):
        data = self._OXIGRAPH_OUTPUT.replace(' rdf:version="1.2"', '')
        g = StarLayerGraph()
        g.parse(data=data, format='rdfxml12')
        assert not any(issubclass(w.category, RDF12ConformanceWarning) for w in recwarn.list)

    def test_version_1_2_full_does_not_warn(self, recwarn):
        g = StarLayerGraph()
        g.parse(data=self._OXIGRAPH_OUTPUT, format='rdfxml12')
        assert not any(issubclass(w.category, RDF12ConformanceWarning) for w in recwarn.list)
