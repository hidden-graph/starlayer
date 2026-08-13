"""Phase 2a: query forms and operators that turned out to already work with
the generic encoder/decoder from Phase 1, with no new vocabulary or code —
CONSTRUCT, ASK, DESCRIBE (with and without WHERE), and MINUS. Locked in here
as regression tests.

SERVICE is checked structurally only (algebra tree equality after decode),
not executed — evaluating it would require a live network call to a SPARQL
endpoint, which this test suite must not do.
"""

import pytest
from rdflib.plugins.sparql.evaluate import evalQuery
from rdflib.plugins.sparql.processor import prepareQuery

from starsparql import query_to_rdf, rdf_to_query

PREFIXES = """
PREFIX : <http://example.org/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
"""

QUERIES = [
    PREFIXES + 'ASK { ?p foaf:age 30 }',
    PREFIXES + 'CONSTRUCT { ?p :hasName ?n } WHERE { ?p foaf:name ?n }',
    PREFIXES + 'DESCRIBE ?p WHERE { ?p foaf:name "Alice" }',
    PREFIXES + 'DESCRIBE :alice',  # bare DESCRIBE, no WHERE clause
    PREFIXES + 'SELECT ?p WHERE { ?p a foaf:Person MINUS { ?p foaf:age 25 } }',
]


def _canon(res):
    if res.get("type_") == "ASK":
        return res["askAnswer"]
    if res.get("type_") == "DESCRIBE":
        return sorted(res["graph"])
    if res.get("type_") == "CONSTRUCT":
        return sorted(res["graph"])
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
    assert canon_original not in (None, [], False)


def _strip_bookkeeping(node):
    """Deep-copy an algebra tree with the _vars/lazy bookkeeping keys removed
    and None-valued keys dropped, so two independently-built trees (one via
    translateQuery, one via rdf_to_query) can be compared by their real
    structure/content. A key explicitly set to None (translateQuery always
    sets "datasetClause", even when there's no FROM clause) and an absent
    key are behaviorally identical everywhere in rdflib — CompValue.__getattr__
    returns None for a missing key too — so encoding skips None values
    entirely rather than emitting a triple that would just decode back to
    the same key: None."""
    from rdflib.plugins.sparql.parserutils import CompValue

    if isinstance(node, CompValue):
        return {
            "__name__": node.name,
            **{
                k: _strip_bookkeeping(v)
                for k, v in node.items()
                if k not in ("_vars", "lazy") and v is not None
            },
        }
    if isinstance(node, (list, tuple)):
        return [_strip_bookkeeping(v) for v in node]
    return node


def test_service_structural_roundtrip():
    """SERVICE isn't executed (would require a live network call); this
    checks the decoded algebra tree matches the original structurally."""
    query_text = (
        PREFIXES
        + "SELECT ?x WHERE { SERVICE <http://example.org/sparql> { ?x :p ?y } }"
    )
    prepared = prepareQuery(query_text)
    graph, root = query_to_rdf(prepared)
    reconstructed = rdf_to_query(graph, root)

    assert _strip_bookkeeping(prepared.algebra) == _strip_bookkeeping(reconstructed.algebra)
