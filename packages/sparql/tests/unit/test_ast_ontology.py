"""Prototype: encode/decode a *raw parse tree* (rdflib's parseQuery output,
before translateQuery) as sast: RDF — one layer below salg:'s algebra.

Verifies text -> parse tree -> sast: RDF -> parse tree -> translateQuery ->
results, by *executing* both the originally-prepared query and the
RDF-round-tripped reconstruction and comparing result sets — same standard
as test_roundtrip.py.
"""

import pytest
from rdflib.plugins.sparql.evaluate import evalQuery
from rdflib.plugins.sparql.parser import parseQuery
from rdflib.plugins.sparql.processor import prepareQuery
from starsparql.from_ast_rdf import rdf_ast_to_query
from starsparql.to_ast_rdf import query_ast_to_rdf

PREFIXES = """
PREFIX : <http://example.org/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
"""

QUERIES = [
    PREFIXES + "SELECT ?name WHERE { ?p a foaf:Person ; foaf:name ?name }",
    PREFIXES + """
        SELECT ?name WHERE {
          ?p foaf:name ?name ; foaf:age ?age .
          FILTER(?age > 26)
        }
    """,
    PREFIXES + """
        SELECT ?name WHERE {
          ?p foaf:name ?name ; foaf:age ?age .
          FILTER(?age > 20 && ?age < 30)
        }
    """,
    PREFIXES + """
        SELECT ?name ?age WHERE {
          ?p foaf:name ?name .
          OPTIONAL { ?p foaf:age ?age }
        }
    """,
    PREFIXES + """
        SELECT ?p WHERE {
          { ?p foaf:name "Alice" } UNION { ?p foaf:name "Bob" }
        }
    """,
    # property path — needs no special-casing at this layer (see
    # to_ast_rdf.py's module docstring)
    PREFIXES + "SELECT ?a ?b WHERE { ?a foaf:knows+ ?b }",
]


def _canon(res):
    rows = []
    for b in res["bindings"]:
        rows.append(frozenset((str(k), v.n3()) for k, v in b.items() if v is not None))
    return sorted(rows, key=lambda r: sorted(r))


@pytest.mark.parametrize("query_text", QUERIES)
def test_ast_roundtrip_result_equivalence(fixture_graph, query_text):
    prepared = prepareQuery(query_text)
    original = evalQuery(fixture_graph, prepared)

    parse_result = parseQuery(query_text)
    graph, root = query_ast_to_rdf(parse_result)
    reconstructed = rdf_ast_to_query(graph, root)
    roundtripped = evalQuery(fixture_graph, reconstructed)

    canon_original = _canon(original)
    canon_roundtripped = _canon(roundtripped)
    assert canon_original == canon_roundtripped
    assert len(canon_original) > 0  # guard against a vacuously-true empty comparison
