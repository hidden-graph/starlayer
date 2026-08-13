"""Phase 3: RDF 1.2 (triple-term / base-direction) queries and updates.

Finding, not new code: at the algebra layer, an RDF 1.2 SPARQL 1.2 query
prepared via starlayergraph's own `starlayergraph.query.sparql_api.prepareQuery` is
*already* plain SPARQL 1.1 shape. starlayergraph rewrites `<<( s p o )>>`
triple-term patterns to ordinary BGP triples over its internal
rdf:subject/predicate/object encoding *before* calling rdflib's real
`translateQuery` — so the resulting `query.algebra` contains no `TripleTerm`
CompValue node anywhere, just Extend/Function/BGP/Join, all of which
Phase 1/2's generic encoder/decoder already covers. Confirmed empirically:
every query form here round-trips with zero changes to this project's code.

The more ambitious alternative — encode the *surface* `<<( )>>` syntax
directly as a `salg:TripleTerm` pattern node in the algebra, rather than
starlayergraph's lowered encoding — was tried and doesn't work: feeding
starlayergraph's `parseQuery()` (which *does* restore `TripleTerm` CompValue
nodes, but only in the pre-algebra parse tree) into rdflib's own
`algebra.translateQuery()` crashes inside `reorderTriples`/`_knownTerms`
with `TypeError: cannot use 'CompValue' as a set element (unhashable
type)` — rdflib's algebra translator assumes every triple-pattern term is a
hashable RDF identifier (Variable/URIRef/BNode/Literal), not an arbitrary
CompValue. This is a real limitation of rdflib's algebra machinery itself,
not something starlayergraph left undone — it's exactly why starlayergraph lowers to
SPARQL 1.1 before calling translateQuery in the first place. Patching
rdflib's algebra translator to accept TripleTerm nodes is out of scope here.
"""

import pytest
from rdflib import Graph
from starlayergraph.graph.starlayergraph_graph import StarLayerGraph
from starlayergraph.query.sparql_api import prepareQuery as starlayergraph_prepare_query
from starlayergraph.query.sparql_api import prepareUpdate as starlayergraph_prepare_update

from starsparql import query_to_rdf, rdf_to_query, rdf_to_update, update_to_rdf

FIXTURE_TTL12 = """
@prefix : <http://example.org/> .
:bob :knows :carol {| :since "2020" ; :source :Wikipedia |} .
:alice :says <<( :bob :knows :carol )>> .
:alice :believes <<( :bob :knows :mike )>> .
:alice :saysDir "hi"@en--ltr .
"""

QUERIES = [
    # triple-term pattern via rdf:reifies
    """
    PREFIX : <http://example.org/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    SELECT ?source WHERE {
      ?stmt rdf:reifies <<( :bob :knows :carol )>> .
      ?stmt :source ?source .
    }
    """,
    # ground triple-term value (compiles to the tt:fn/hash custom Function)
    "PREFIX : <http://example.org/> SELECT ?p WHERE { ?p :says <<( :bob :knows :carol )>> }",
    "PREFIX : <http://example.org/> SELECT ?o WHERE { ?s ?p ?o . FILTER(isTRIPLE(?o)) }",
    "PREFIX : <http://example.org/> SELECT ?s WHERE { ?x :says ?tt . BIND(SUBJECT(?tt) AS ?s) }",
    # base-direction (DirLangString) functions
    "PREFIX : <http://example.org/> SELECT ?s ?dir WHERE { ?s :saysDir ?o . BIND(LANGDIR(?o) AS ?dir) }",
    "PREFIX : <http://example.org/> SELECT ?s WHERE { ?s :saysDir ?o . FILTER(hasLANGDIR(?o)) }",
]

CONSTRUCT_QUERIES = [
    # CONSTRUCT that mints a triple term never previously written to the graph
    """
    PREFIX : <http://example.org/>
    CONSTRUCT { :dave :claims <<( :bob :knows :carol )>> }
    WHERE { :bob :knows :carol }
    """,
]

UPDATES = [
    """
    PREFIX : <http://example.org/>
    INSERT { :dave :claims <<( :bob :knows :carol )>> }
    WHERE { :bob :knows :carol }
    """,
]


@pytest.fixture
def starlayergraph_graph():
    g = StarLayerGraph()
    g.parse(data=FIXTURE_TTL12, format="turtle12")
    return g


@pytest.mark.parametrize("query_text", QUERIES)
def test_rdf12_query_roundtrip(starlayergraph_graph, query_text):
    prepared = starlayergraph_prepare_query(query_text)
    original_rows = sorted(str(row) for row in starlayergraph_graph.query(prepared))

    # A plain Graph(), not to_rdf's own StarLayerGraph default: prepared's
    # algebra can contain a ground triple term already substituted as a
    # literal tt:HASH URIRef (starlayergraph.query.sparql_api.prepareQuery now
    # goes through starsparql's own lowering, which - correctly, for
    # a real, separate reason, see lower_rdf11.py::_lower_pattern_term's
    # own docstring - computes a ground pattern-position triple term's
    # hash eagerly and substitutes it as a plain URIRef term, not a
    # Function-call expression). Encoding that into a StarLayerGraph and
    # reading it back would let StarLayerGraph's own tt:HASH auto-
    # resolution "helpfully" turn the encoding's own term back into a
    # TripleTerm object mid-decode - the exact hazard update_to_rdf11's own
    # docstring already documents and avoids the same way.
    graph, root = query_to_rdf(prepared, graph=Graph())
    reconstructed = rdf_to_query(graph, root)
    roundtripped_rows = sorted(str(row) for row in starlayergraph_graph.query(reconstructed))

    assert original_rows == roundtripped_rows
    assert len(original_rows) > 0


@pytest.mark.parametrize("query_text", CONSTRUCT_QUERIES)
def test_rdf12_construct_roundtrip(starlayergraph_graph, query_text):
    prepared = starlayergraph_prepare_query(query_text)
    original = sorted(starlayergraph_graph.query(prepared).graph)

    graph, root = query_to_rdf(prepared, graph=Graph())
    reconstructed = rdf_to_query(graph, root)
    roundtripped = sorted(starlayergraph_graph.query(reconstructed).graph)

    assert original == roundtripped
    assert len(original) > 0


@pytest.mark.parametrize("update_text", UPDATES)
def test_rdf12_update_roundtrip(update_text):
    g_original = StarLayerGraph()
    g_original.parse(data=FIXTURE_TTL12, format="turtle12")
    g_original.update(starlayergraph_prepare_update(update_text))

    g_roundtripped = StarLayerGraph()
    g_roundtripped.parse(data=FIXTURE_TTL12, format="turtle12")
    graph, root = update_to_rdf(starlayergraph_prepare_update(update_text), graph=Graph())
    reconstructed = rdf_to_update(graph, root)
    g_roundtripped.update(reconstructed)

    assert set(g_original) == set(g_roundtripped)
