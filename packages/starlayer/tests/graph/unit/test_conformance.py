"""
End-to-end tests for VERSION-directive handling and SPARQL12ConformanceWarning.

RDF 1.2 Concepts sec 2.1 and SPARQL 1.2 Query sec 4.3 define three version
labels - "1.2" (full), "1.2-basic" (excludes triple terms and dirLangString),
"1.1" (legacy) - and explicitly say the VERSION directive is only a hint: a
processor "is not required to reject features that are outside the
announced version (but could signal them with a warning)". StarLayer signals
via a warning, never a hard error - see starlayer.graph/model/conformance.py.

A SPARQL query/update's own VERSION directive can warn (SPARQL12ConformanceWarning). An RDF document's VERSION label
never does (the RDF warning was dropped, 2026-11-06): it is a hint, and a mismatch is not signalled.

Also regression-tests a real bug found while checking this against the live
spec text: a SPARQL 1.2 query starting with VERSION "1.2" (the spec's own
example form) previously raised a ParseException on the in-memory backend,
since sparql12_to_11.py never stripped the directive before handing the
query to rdflib's SPARQL 1.1 parser.
"""

import pyoxigraph as ox
import pytest
from rdflib import URIRef
from starlayer.graph.model.conformance import SPARQL12ConformanceWarning
from starlayer.graph.oxgraph import StarLayerDataset, StarLayerGraph
from starlayer.graph.oxgraph.sparql_text import check_native_version_conformance

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
        with pytest.warns(SPARQL12ConformanceWarning, match='1.2-basic'):
            g.query(q)

    def test_version_1_2_basic_without_triple_term_does_not_warn(self, recwarn):
        g = StarLayerGraph()
        q = f'VERSION "1.2-basic"\nPREFIX : <{EX}>\nSELECT * WHERE {{ ?s ?p ?o }}'
        g.query(q)
        assert not any(issubclass(w.category, SPARQL12ConformanceWarning) for w in recwarn.list)

    def test_version_1_2_full_with_triple_term_does_not_warn(self, recwarn):
        g = StarLayerGraph()
        q = f"""VERSION "1.2"
            PREFIX : <{EX}>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?s WHERE {{ ?s rdf:reifies <<( :a :b :c )>> . }}
        """
        g.query(q)
        assert not any(issubclass(w.category, SPARQL12ConformanceWarning) for w in recwarn.list)

    def test_unrecognized_version_label_warns(self):
        g = StarLayerGraph()
        q = 'VERSION "9.9"\nSELECT * WHERE { ?s ?p ?o }'
        with pytest.warns(SPARQL12ConformanceWarning, match='unrecognized'):
            g.query(q)

    def test_no_version_directive_does_not_warn(self, recwarn):
        g = StarLayerGraph()
        g.query('SELECT * WHERE { ?s ?p ?o }')
        assert not any(issubclass(w.category, SPARQL12ConformanceWarning) for w in recwarn.list)

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
        with pytest.warns(SPARQL12ConformanceWarning, match='1.1'):
            g.query(q)


class TestSparqlUpdateVersionDirective:
    """StarLayerGraph.update()/StarLayerDataset.update() - found 2026-10-13
    to have the identical gap TestSparqlVersionDirective's own docstring
    already documented for .query(): both called prepare_update_12()
    directly with no VERSION-stripping at all, so a VERSION-prefixed
    Update (legal per the same SPARQL 1.2 Query sec 4.3 prologue grammar
    Update shares) raised a bare ParseException. Checked precisely which
    entry points were actually affected before fixing (not assumed
    symmetric with .query()) - StarLayerDataset.update()'s own *remote*
    HTTP-store branch is unaffected (it POSTs text directly, no local
    parse at all), only its local-store branch shares this bug with
    StarLayerGraph.update().
    """

    def test_update_version_directive_no_longer_raises(self):
        g = StarLayerGraph()
        g.update('VERSION "1.2"\nPREFIX ex: <http://example.org/>\nINSERT DATA { ex:a ex:b ex:c }')
        assert (ex('a'), ex('b'), ex('c')) in g

    def test_update_version_1_1_with_triple_term_warns(self):
        g = StarLayerGraph()
        u = f"""VERSION "1.1"
            PREFIX : <{EX}>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            INSERT DATA {{ :s rdf:reifies <<( :a :b :c )>> }}
        """
        with pytest.warns(SPARQL12ConformanceWarning, match='1.1'):
            g.update(u)

    def test_update_no_version_directive_does_not_warn(self, recwarn):
        g = StarLayerGraph()
        g.update('PREFIX ex: <http://example.org/>\nINSERT DATA { ex:a ex:b ex:c }')
        assert not any(issubclass(w.category, SPARQL12ConformanceWarning) for w in recwarn.list)

    def test_dataset_update_version_directive_no_longer_raises(self):
        ds = StarLayerDataset()
        ds.update('VERSION "1.2"\nPREFIX ex: <http://example.org/>\nINSERT DATA { ex:a ex:b ex:c }')
        assert (ex('a'), ex('b'), ex('c')) in ds.default_graph

    def test_dataset_update_version_1_1_with_triple_term_warns(self):
        ds = StarLayerDataset()
        u = f"""VERSION "1.1"
            PREFIX : <{EX}>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            INSERT DATA {{ :s rdf:reifies <<( :a :b :c )>> }}
        """
        with pytest.warns(SPARQL12ConformanceWarning, match='1.1'):
            ds.update(u)






class TestNativeBackendVersionConformance:
    """StarLayerGraph() sends SPARQL straight through to a
    real endpoint via HTTP with zero rewriting (correct - Fuseki/Oxigraph
    understand VERSION natively), which means query()/update() never call
    rewrite_sparql12_to_11 and so never ran this check at all until fixed.

    Confirmed live 2026-07-17 against Fuseki 5.5.0 and Oxigraph: both
    execute a VERSION "1.2-basic" + <<( )>> query normally (HTTP 200) with
    no warning or error signal anywhere in the response - so without this
    fix, a native-backend StarLayerGraph would silently never emit
    SPARQL12ConformanceWarning for the identical query the default in-memory
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
        with pytest.warns(SPARQL12ConformanceWarning, match='1.2-basic'):
            check_native_version_conformance(q)

    def test_1_2_basic_without_triple_term_does_not_warn(self, recwarn):
        q = f'VERSION "1.2-basic"\nPREFIX : <{EX}>\nSELECT * WHERE {{ ?s ?p ?o }}'
        check_native_version_conformance(q)
        assert not any(issubclass(w.category, SPARQL12ConformanceWarning) for w in recwarn.list)

    def test_no_version_directive_does_not_warn(self, recwarn):
        check_native_version_conformance('SELECT * WHERE { ?s ?p ?o }')
        assert not any(issubclass(w.category, SPARQL12ConformanceWarning) for w in recwarn.list)

    def test_unrecognized_version_label_warns(self):
        with pytest.warns(SPARQL12ConformanceWarning, match='unrecognized'):
            check_native_version_conformance('VERSION "9.9"\nSELECT * WHERE { ?s ?p ?o }')


class TestIdentifierDefault:
    """A native () StarLayerGraph constructed with no
    explicit identifier= used to get rdflib's own default (a fresh random
    BNode) - but query()/update() send SPARQL text straight through
    unscoped (the endpoint's own default graph), while infer()/triples()/
    plain iteration wrap every pattern in GRAPH <self.identifier> { ... }
    via _native_scoped() unless self.identifier is exactly
    DATASET_DEFAULT_GRAPH_ID. A random BNode identifier satisfied neither
    exemption, so those two halves of the API silently disagreed about
    which graph is "self's data" - confirmed live, and previously worked
    around explicitly in tests/integration/test_entailment_native.py by
    always passing identifier=DATASET_DEFAULT_GRAPH_ID. Fixed by
    defaulting to it automatically whenever the caller supplies no
    identifier of their own, so the common case agrees by construction.
    """

    def test_native_backend_defaults_identifier_to_dataset_default_graph_id(self):
        g = StarLayerGraph()
        assert g.identifier == ox.DefaultGraph()

    def test_native_backend_explicit_none_identifier_also_defaults(self):
        # rdflib's own Graph.__init__ treats an omitted identifier= and an
        # explicit identifier=None identically (identifier or BNode()) -
        # this confirms the same equivalence holds for the new default.
        g = StarLayerGraph(identifier=None)
        assert g.identifier == ox.DefaultGraph()

    def test_native_backend_respects_explicit_identifier(self):
        g = StarLayerGraph(identifier=URIRef(EX + "someGraph"))
        assert g.identifier == ox.NamedNode(EX + "someGraph")




class TestRdfXmlVersionAttribute:
    """RDF/XML's version mechanism is structurally different from every
    other format's - an rdf:version XML attribute on a node/property
    element (confirmed via spec fetch), not a prologue-line directive.

    Found via a live Oxigraph 0.5.9 round trip (2026-07-17): it genuinely
    emits rdf:version on the property element wrapping rdf:parseType="Triple"
    for a reified triple term. Feeding that real output into starlayer.graph's own
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


class TestVersionLabelIsAHint:
    """A VERSION label is only a hint (RDF 1.2 Concepts sec 2.1): a document labelled "1.2-basic" that uses a triple term
    is read as it stands, with no warning and no error."""

    def test_1_2_basic_with_triple_term_is_read(self, recwarn):
        data = f"""@version "1.2-basic" .
            @prefix : <{EX}> .
            :stmt <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> <<( :bob :knows :carol )>> .
        """
        g = StarLayerGraph()
        g.parse(data=data, format='turtle12')
        assert g.has_triple_term(ex('bob'), ex('knows'), ex('carol'))
        assert not [w for w in recwarn.list if 'VERSION' in str(w.message)]
