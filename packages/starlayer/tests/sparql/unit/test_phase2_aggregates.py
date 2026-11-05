"""Phase 2c: aggregates, GROUP BY, HAVING, ORDER BY, LIMIT — another set that
turned out to already work with the generic encoder/decoder from Phase 1
(Aggregate_Count/Sum/Avg/GroupConcat/... are plain CompValue nodes in
rdflib, not Expr — dispatched by name via aggregates.Aggregator's own dict,
not via a bound evalfn — so the generic CompValue path already covers them).
Locked in here as regression tests.
"""

import pytest
from rdflib.plugins.sparql.evaluate import evalQuery
from rdflib.plugins.sparql.processor import prepareQuery
from starlayer.sparql import query_to_rdf, rdf_to_query

FIXTURE_TTL = """
@prefix : <http://example.org/> .
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
:alice a foaf:Person ; foaf:name "Alice" ; foaf:age 30 ; foaf:team :red .
:bob a foaf:Person ; foaf:name "Bob" ; foaf:age 25 ; foaf:team :red .
:carol a foaf:Person ; foaf:name "Carol" ; foaf:age 40 ; foaf:team :blue .
"""

PREFIXES = "PREFIX : <http://example.org/>\nPREFIX foaf: <http://xmlns.com/foaf/0.1/>\n"

QUERIES = [
    PREFIXES + "SELECT ?team (COUNT(?p) AS ?n) WHERE { ?p foaf:team ?team } GROUP BY ?team",
    PREFIXES + """
        SELECT ?team (SUM(?age) AS ?total) (AVG(?age) AS ?avg) WHERE {
          ?p foaf:team ?team ; foaf:age ?age
        } GROUP BY ?team
    """,
    PREFIXES + "SELECT (COUNT(DISTINCT ?team) AS ?n) WHERE { ?p foaf:team ?team }",
    PREFIXES + """
        SELECT ?team (GROUP_CONCAT(?name; SEPARATOR=",") AS ?names) WHERE {
          ?p foaf:team ?team ; foaf:name ?name
        } GROUP BY ?team
    """,
    PREFIXES + """
        SELECT ?team (COUNT(?p) AS ?n) WHERE { ?p foaf:team ?team }
        GROUP BY ?team HAVING (COUNT(?p) > 1)
    """,
    PREFIXES + "SELECT ?name WHERE { ?p foaf:name ?name } ORDER BY ?name LIMIT 2",
    PREFIXES + "SELECT ?name WHERE { ?p foaf:name ?name } ORDER BY DESC(?name)",
]


@pytest.fixture
def team_graph():
    from rdflib import Graph

    g = Graph()
    g.parse(data=FIXTURE_TTL, format="turtle")
    return g


def _canon(res):
    rows = [
        frozenset((str(k), v.n3()) for k, v in b.items() if v is not None)
        for b in res["bindings"]
    ]
    return sorted(rows, key=lambda r: sorted(r))


@pytest.mark.parametrize("query_text", QUERIES)
def test_roundtrip_result_equivalence(team_graph, query_text):
    prepared = prepareQuery(query_text)
    original = evalQuery(team_graph, prepared)

    graph, root = query_to_rdf(prepared)
    reconstructed = rdf_to_query(graph, root)
    roundtripped = evalQuery(team_graph, reconstructed)

    canon_original = _canon(original)
    canon_roundtripped = _canon(roundtripped)
    assert canon_original == canon_roundtripped
    assert len(canon_original) > 0
