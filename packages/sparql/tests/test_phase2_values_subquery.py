"""Phase 2b: VALUES (including UNDEF) and subquery round-trip."""

import pytest
from rdflib.plugins.sparql.evaluate import evalQuery
from rdflib.plugins.sparql.processor import prepareQuery

from starsparql import query_to_rdf, rdf_to_query

PREFIXES = """
PREFIX : <http://example.org/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
"""

QUERIES = [
    # inline VALUES
    PREFIXES + """
        SELECT ?p ?name WHERE {
          ?p foaf:name ?name .
          VALUES ?name { "Alice" "Bob" }
        }
    """,
    # VALUES over two variables, tuple rows
    PREFIXES + """
        SELECT ?p ?name WHERE {
          VALUES (?p ?name) { (:alice "Alice") (:bob "Bob") }
          ?p foaf:name ?name .
        }
    """,
    # VALUES with UNDEF
    PREFIXES + """
        SELECT ?a ?b WHERE {
          VALUES (?a ?b) { (1 2) (3 UNDEF) }
        }
    """,
    # subquery
    PREFIXES + """
        SELECT ?name WHERE {
          ?p foaf:name ?name .
          {
            SELECT ?p WHERE { ?p foaf:age ?age } ORDER BY ?age LIMIT 1
          }
        }
    """,
]


def _canon(res):
    rows = [
        frozenset((str(k), v.n3()) for k, v in b.items() if v is not None)
        for b in res["bindings"]
    ]
    return sorted(rows, key=lambda r: sorted(r))


@pytest.mark.parametrize("query_text", QUERIES)
def test_roundtrip_result_equivalence(fixture_graph, query_text):
    prepared = prepareQuery(query_text)
    original = evalQuery(fixture_graph, prepared)

    graph, root = query_to_rdf(prepared)
    reconstructed = rdf_to_query(graph, root)
    roundtripped = evalQuery(fixture_graph, reconstructed)

    canon_original = _canon(original)
    canon_roundtripped = _canon(roundtripped)
    assert canon_original == canon_roundtripped
    assert len(canon_original) > 0
