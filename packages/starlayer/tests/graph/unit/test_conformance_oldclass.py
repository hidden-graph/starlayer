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

import pytest
from rdflib import BNode, URIRef
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.graph.model.conformance import SPARQL12ConformanceWarning

EX = 'http://example.org/'


def ex(local: str) -> URIRef:
    return URIRef(EX + local)






class TestSparqlApiVersionDirective:
    """starlayer.graph.query.sparql_api's four public SPARQL-1.2-aware
    wrappers (parseQuery/prepareQuery/parseUpdate/prepareUpdate) - this
    module's own docstring advertises them as drop-in replacements for
    rdflib's originals "when working with SPARQL 1.2 queries", yet none
    stripped VERSION before this fix, unlike StarLayerGraph.query()/
    .update() (same package, same advertised purpose). Found 2026-10-13.
    """

    def test_parse_query_version_directive_no_longer_raises(self):
        from starlayer.graph.query.sparql_api import parseQuery
        parseQuery('VERSION "1.2"\nSELECT * WHERE { ?s ?p ?o }')

    def test_prepare_query_version_directive_no_longer_raises(self):
        from starlayer.graph.query.sparql_api import prepareQuery
        prepareQuery('VERSION "1.2"\nSELECT * WHERE { ?s ?p ?o }')

    def test_prepare_query_version_1_1_with_triple_term_warns(self):
        from starlayer.graph.query.sparql_api import prepareQuery
        q = f"""VERSION "1.1"
            PREFIX : <{EX}>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?s WHERE {{ ?s rdf:reifies <<( :a :b :c )>> . }}
        """
        with pytest.warns(SPARQL12ConformanceWarning, match='1.1'):
            prepareQuery(q)

    def test_parse_update_version_directive_no_longer_raises(self):
        from starlayer.graph.query.sparql_api import parseUpdate
        parseUpdate('VERSION "1.2"\nPREFIX ex: <http://example.org/>\nINSERT DATA { ex:a ex:b ex:c }')

    def test_prepare_update_version_directive_no_longer_raises(self):
        from starlayer.graph.query.sparql_api import prepareUpdate
        prepareUpdate('VERSION "1.2"\nPREFIX ex: <http://example.org/>\nINSERT DATA { ex:a ex:b ex:c }')

    def test_prepare_update_version_1_1_with_triple_term_warns(self):
        from starlayer.graph.query.sparql_api import prepareUpdate
        u = f"""VERSION "1.1"
            PREFIX : <{EX}>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            INSERT DATA {{ :s rdf:reifies <<( :a :b :c )>> }}
        """
        with pytest.warns(SPARQL12ConformanceWarning, match='1.1'):
            prepareUpdate(u)

    def test_no_version_directive_does_not_warn(self, recwarn):
        from starlayer.graph.query.sparql_api import prepareQuery
        prepareQuery('SELECT * WHERE { ?s ?p ?o }')
        assert not any(issubclass(w.category, SPARQL12ConformanceWarning) for w in recwarn.list)


class TestNativeBackendRemoteRdf11UpdateVersionDirective:
    """native_update()'s backend='rdf-1.1' (remote, non-native) branch -
    unlike the backend='rdf-1.2' branch (which sends VERSION straight
    through unmodified, see TestNativeBackendVersionConformance above),
    this branch locally parses the text via prepare_update_12() first (to
    re-render it as plain SPARQL 1.1 text for a remote endpoint with no
    triple-term notion at all) - the exact same local-parse gap
    TestSparqlUpdateVersionDirective found in StarLayerGraph.update(),
    just reached through native_update() instead. Found 2026-10-13.

    http_update() itself is monkeypatched to capture the final text
    instead of making a real HTTP request - resolve_store_http() only
    needs query_endpoint/update_endpoint attributes to exist, not a live
    server.
    """

    def test_remote_rdf11_update_version_directive_no_longer_raises(self, monkeypatch):
        from types import SimpleNamespace

        from starlayer.graph.backends import native

        captured = {}

        def fake_http_update(update_url, sparql, extra_headers=None):
            captured['sparql'] = sparql

        monkeypatch.setattr(native, 'http_update', fake_http_update)
        store = SimpleNamespace(query_endpoint='http://x/query', update_endpoint='http://x/update', kwargs={})
        native.native_update(
            store, 'rdf-1.1', 'VERSION "1.2"\nPREFIX ex: <http://example.org/>\nINSERT DATA { ex:a ex:b ex:c }'
        )
        assert 'VERSION' not in captured['sparql']
        assert 'INSERT' in captured['sparql']

    def test_remote_rdf11_update_version_1_1_with_triple_term_warns(self, monkeypatch):
        from types import SimpleNamespace

        from starlayer.graph.backends import native

        monkeypatch.setattr(native, 'http_update', lambda *a, **kw: None)
        store = SimpleNamespace(query_endpoint='http://x/query', update_endpoint='http://x/update', kwargs={})
        u = f"""VERSION "1.1"
            PREFIX : <{EX}>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            INSERT DATA {{ :s rdf:reifies <<( :a :b :c )>> }}
        """
        with pytest.warns(SPARQL12ConformanceWarning, match='1.1'):
            native.native_update(store, 'rdf-1.1', u)




class TestNativeIdentifierDefault:
    """A native (backend='rdf-1.2') StarLayerGraph constructed with no
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




    def test_native_backend_respects_positional_identifier(self):
        # Proves the len(args) < 2 guard doesn't clobber an identifier
        # passed positionally (Graph.__init__(store, identifier, ...)).
        g = StarLayerGraph('default', URIRef(EX + "someGraph"), backend='rdf-1.2')
        assert g.identifier == URIRef(EX + "someGraph")

    def test_default_backend_still_gets_random_bnode(self):
        # Regression guard: the new conditional is gated on backend=='rdf-1.2'
        # and must not touch the default backend's own per-instance BNode.
        g = StarLayerGraph()
        assert isinstance(g.identifier, BNode)






class TestRdfXmlHandParserVersionExtraction:
    """Moved from test_conformance.py: the hand-written RDF/XML parser helper goes with the parsers at D1."""

    def test_real_oxigraph_output_extracts_declared_version(self):
        from starlayer.graph.parsers.rdfxml12 import extract_version_directive
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
            '<rdf:Description rdf:about="http://example.org/stmt">'
            '<rdf:reifies rdf:version="1.2" rdf:parseType="Triple"></rdf:reifies></rdf:Description></rdf:RDF>'
        )
        assert extract_version_directive(xml) == '1.2'
