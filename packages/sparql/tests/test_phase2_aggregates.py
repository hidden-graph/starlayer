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

from starsparql import query_to_rdf, rdf_to_query

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


def test_unaliased_expression_group_by_key_roundtrips():
    """`GROUP BY (?age+1)` — a parenthesized, computed grouping key with no
    `AS ?var` alias — is legal per SPARQL 1.1's own grammar, but confirmed
    to crash plain, unmodified rdflib's own evaluator outright
    (`evalAggregateJoin`: "Cannot eval thing: None"), independent of this
    project entirely — see the sibling `starlayergraph` repo's
    `docs/rdflib-upstream-issues.md` Issue 9 for the full trace. Unlike
    every other query in this file, this test needs `starlayergraph` imported
    (not just plain rdflib): the actual fix is a parse-tree patch applied
    at `import starlayergraph` time
    (`evaluate_patches.py::patch_group_by_unaliased_expression_key`), not
    something `to_rdf.py`/`from_rdf.py`'s own generic encoder/decoder can
    or should work around on their own — see `to_rdf._encode_list`'s own
    docstring for why. Confirms the *round-trip* (not just direct
    execution) works once the patch is active: encode, decode, execute
    both, compare results.
    """
    import starlayergraph  # noqa: F401 - import side effect: applies the patch

    query_text = (
        PREFIXES + "SELECT (COUNT(?p) AS ?n) WHERE { ?p foaf:team ?team ; foaf:age ?age } "
        "GROUP BY (?age - ?age + 1)"
    )
    from rdflib import Graph

    prepared = prepareQuery(query_text)
    graph = Graph()
    graph.parse(data=FIXTURE_TTL, format="turtle")
    original = evalQuery(graph, prepared)

    rdf_graph, root = query_to_rdf(prepared)
    reconstructed = rdf_to_query(rdf_graph, root)
    roundtripped = evalQuery(graph, reconstructed)

    canon_original = _canon(original)
    canon_roundtripped = _canon(roundtripped)
    assert canon_original == canon_roundtripped
    assert canon_original == [frozenset({("n", '"3"^^<http://www.w3.org/2001/XMLSchema#integer>')})]
