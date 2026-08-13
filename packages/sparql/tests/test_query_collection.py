"""``salg:QueryCollection`` — serializing a *set* of independent queries as
one RDF graph (goal 4 from todos.md: "creates an rdf/sparql version to
serialize sets of queries"). The vocabulary (``salg:QueryCollection``/
``salg:queries``) already existed in ``salg-ontology.ttl``; this is the
first code that actually produces/consumes it.

Verifies the full loop the user asked for directly: take this project's own
existing test queries (``test_roundtrip.QUERIES``), encode them all as one
collection, round-trip through real Turtle *text* (not just an in-memory
Graph — the point of the feature is a ``.ttl`` file readable independently
of this project's own code), decode back, and confirm each decoded query
still *executes* to the same result as the original — the same
execution-based verification standard every other round-trip test in this
project uses, not a text- or structure-only comparison.
"""

from rdflib import Graph
from rdflib.namespace import RDF
from rdflib.plugins.sparql.evaluate import evalQuery
from rdflib.plugins.sparql.processor import prepareQuery

from starsparql import queries_to_collection, rdf_to_collection
from starsparql.vocab import QUERY_COLLECTION

from test_roundtrip import QUERIES, _canon


def test_collection_roundtrips_through_turtle_text(fixture_graph):
    prepared = [prepareQuery(q) for q in QUERIES]
    originals = [evalQuery(fixture_graph, p) for p in prepared]

    graph, root = queries_to_collection(prepared)
    ttl_text = graph.serialize(format="turtle")

    # The whole point: re-parse from plain Turtle *text*, as a standalone
    # .ttl file would be read by any RDF tool — not the same in-memory
    # Graph object queries_to_collection built.
    reparsed = Graph()
    reparsed.parse(data=ttl_text, format="turtle")

    roots = list(reparsed.subjects(RDF.type, QUERY_COLLECTION))
    assert len(roots) == 1
    decoded_queries = rdf_to_collection(reparsed, roots[0])

    assert len(decoded_queries) == len(QUERIES)
    for original, decoded in zip(originals, decoded_queries):
        roundtripped = evalQuery(fixture_graph, decoded)
        canon_original = _canon(original)
        canon_roundtripped = _canon(roundtripped)
        assert canon_original == canon_roundtripped
        assert len(canon_original) > 0


def test_collection_root_is_typed_and_distinct_from_member_queries():
    prepared = [prepareQuery(q) for q in QUERIES[:2]]
    graph, root = queries_to_collection(prepared)

    assert (root, RDF.type, QUERY_COLLECTION) in graph
    # The collection root itself must not also be typed salg:Query — it's a
    # container, not a query (mirrors salg:Update's own root, which is
    # likewise never typed as any individual operation).
    from starsparql.vocab import QUERY

    assert (root, RDF.type, QUERY) not in graph


def test_empty_collection_roundtrips():
    graph, root = queries_to_collection([])
    assert (root, RDF.type, QUERY_COLLECTION) in graph
    assert rdf_to_collection(graph, root) == []
