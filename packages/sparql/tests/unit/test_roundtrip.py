"""Phase 1 round-trip tests: SELECT + BGP + FILTER + OPTIONAL + UNION.

Verifies text -> algebra -> RDF -> algebra -> results, by *executing* both
the original prepared query and the RDF-round-tripped reconstruction against
the same fixture graph and comparing result sets — not by comparing
regenerated query text, which isn't guaranteed stable (see algebra.py's
translateAlgebra: it always emits full IRIs, never prefixed names).
"""

import pytest
from rdflib.plugins.sparql.algebra import translateAlgebra
from rdflib.plugins.sparql.evaluate import evalQuery
from rdflib.plugins.sparql.processor import prepareQuery
from starsparql import query_to_rdf, rdf_to_query

PREFIXES = """
PREFIX : <http://example.org/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
"""

QUERIES = [
    # plain BGP
    PREFIXES + "SELECT ?name WHERE { ?p a foaf:Person ; foaf:name ?name }",
    # FILTER (RelationalExpression)
    PREFIXES + """
        SELECT ?name WHERE {
          ?p foaf:name ?name ; foaf:age ?age .
          FILTER(?age > 26)
        }
    """,
    # FILTER with a boolean connective (ConditionalAndExpression)
    PREFIXES + """
        SELECT ?name WHERE {
          ?p foaf:name ?name ; foaf:age ?age .
          FILTER(?age > 20 && ?age < 30)
        }
    """,
    # OPTIONAL (LeftJoin with TrueFilter — Carol has no foaf:age)
    PREFIXES + """
        SELECT ?name ?age WHERE {
          ?p foaf:name ?name .
          OPTIONAL { ?p foaf:age ?age }
        }
    """,
    # OPTIONAL with an inline FILTER (LeftJoin with a real expr)
    PREFIXES + """
        SELECT ?name ?age WHERE {
          ?p foaf:name ?name .
          OPTIONAL { ?p foaf:age ?age . FILTER(?age < 28) }
        }
    """,
    # UNION
    PREFIXES + """
        SELECT ?p WHERE {
          { ?p foaf:name "Alice" } UNION { ?p foaf:name "Bob" }
        }
    """,
    # BGP + FILTER + OPTIONAL + UNION combined
    PREFIXES + """
        SELECT ?name ?age WHERE {
          ?p a foaf:Person ; foaf:name ?name .
          OPTIONAL { ?p foaf:age ?age }
          FILTER(?name != "Bob")
          { ?p foaf:knows :bob } UNION { ?p foaf:knows :carol }
        }
    """,
]


def _canon(res):
    rows = []
    for b in res["bindings"]:
        rows.append(frozenset((str(k), v.n3()) for k, v in b.items() if v is not None))
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
    assert len(canon_original) > 0  # guard against a vacuously-true empty comparison


# QUERIES[4] (OPTIONAL with an inline FILTER) is expected to fail this one:
# confirmed by direct comparison that rdflib's own algebra.translateAlgebra
# already drops a FILTER nested inside OPTIONAL for a query that never went
# through this project's round-trip at all (translateAlgebra(prepareQuery(q))
# on the plain original query loses it too) — a pre-existing limitation of
# rdflib's translator, not something introduced by encoding/decoding here.
_TRANSLATE_ALGEBRA_QUERIES = [
    pytest.param(
        q,
        marks=pytest.mark.xfail(
            reason="rdflib's algebra.translateAlgebra drops a FILTER nested "
            "inside OPTIONAL, independent of this project's round-trip",
            strict=True,
        ),
    )
    if i == 4
    else q
    for i, q in enumerate(QUERIES)
]


@pytest.mark.parametrize("query_text", _TRANSLATE_ALGEBRA_QUERIES)
def test_regenerated_text_is_also_executable(fixture_graph, query_text):
    """Bonus check: algebra.translateAlgebra (rdflib's own algebra -> text
    serializer) should also be able to turn the round-tripped algebra back
    into query text that re-parses and produces the same results."""
    prepared = prepareQuery(query_text)
    original = evalQuery(fixture_graph, prepared)

    graph, root = query_to_rdf(prepared)
    reconstructed = rdf_to_query(graph, root)
    regenerated_text = translateAlgebra(reconstructed)

    reprepared = prepareQuery(regenerated_text)
    regenerated = evalQuery(fixture_graph, reprepared)

    assert _canon(original) == _canon(regenerated)
