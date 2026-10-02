"""Regression coverage for a real, general bug in from_rdf.py's algebra
decoder: `_decode()` used to treat *any* node equal to `rdf:nil` as the
empty Python list `[]`, unconditionally - correct for the handful of
algebra fields that are genuinely list-valued (BGP.triples, Project.PV,
...), but wrong for every ordinary term-valued field, silently corrupting
any query referencing the literal `rdf:nil` URIRef as real data (a common
RDF-List-processing idiom: `?s ?p rdf:nil`, `FILTER(?x != rdf:nil)`, an
empty `IN ()`/`GROUP_CONCAT`/`COUNT(...)` with no DISTINCT, an UPDATE whose
INSERT DATA/DELETE DATA is entirely inside `GRAPH <...> { }` blocks, ...).

Found while routing starlayer.ontology.manchester_shapes.validate()
through starlayer.shacl (never bare pyshacl) - an adversarial SHACL test with a
deliberately malformed `rdf:List` (`?this rdf:rest* ?cell . FILTER NOT
EXISTS { ?cell rdf:first ?x }`) silently stopped detecting the malformed
cell once StarLayerGraph.query() was in the loop, because the query's own
`rdf:nil` comparison got corrupted the same way.

Verified by *executing* both the original prepared query/update and the
RDF-round-tripped reconstruction and comparing real results, not by
inspecting the decoded algebra tree directly - the same discipline
test_roundtrip.py's own module docstring documents and this file mirrors.
"""

import pytest
from rdflib import Dataset, Graph, URIRef
from rdflib.plugins.sparql.evaluate import evalQuery
from rdflib.plugins.sparql.processor import prepareQuery
from rdflib.plugins.sparql.sparql import Query
from rdflib.plugins.sparql.update import evalUpdate

from starlayer.sparql import prepare_update_12, query_to_rdf, rdf_to_query, rdf_to_update, update_to_rdf

PREFIXES = "PREFIX : <http://example.org/>\nPREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"

# A deliberately malformed rdf:List: :items has TWO rdf:rest values (one
# straight to rdf:nil, one through :extra, which has no rdf:first at all) -
# the same adversarial shape the manch:/skos: SHACL shapes use to detect a
# broken mid-chain list cell.
_MALFORMED_LIST_DATA = """
    @prefix : <http://example.org/> .
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    :items rdf:rest rdf:nil, :extra .
    :extra rdf:rest rdf:nil .
"""

QUERIES = [
    # A triple pattern whose object is the literal rdf:nil - not a list at all.
    PREFIXES + "SELECT ?s WHERE { ?s rdf:rest rdf:nil }",
    # FILTER comparing against the literal rdf:nil.
    PREFIXES + "SELECT ?s WHERE { ?s rdf:rest ?o . FILTER(?o = rdf:nil) }",
    PREFIXES + "SELECT ?s WHERE { ?s rdf:rest ?o . FILTER(?o != rdf:nil) }",
    # The actual adversarial shape: a zero-or-more path reaching a
    # malformed mid-chain cell, detected via FILTER NOT EXISTS.
    PREFIXES + """
        SELECT ?cell WHERE {
            ?this rdf:rest* ?cell .
            FILTER(?cell != rdf:nil)
            FILTER NOT EXISTS { ?cell rdf:first ?x }
        }
    """,
    # COUNT with no DISTINCT (Aggregate_Count.distinct - the empty
    # ParseResults case, unrelated to rdf:nil as *data* but decoded through
    # the exact same code path).
    PREFIXES + "SELECT (COUNT(?s) AS ?c) WHERE { ?s rdf:rest ?o }",
    # COUNT(DISTINCT ...) - the non-empty case, must keep working too.
    PREFIXES + "SELECT (COUNT(DISTINCT ?s) AS ?c) WHERE { ?s rdf:rest ?o }",
    # ?x = rdf:nil on the *left*-hand operand (RelationalExpression.expr,
    # never list-valued - a plain sanity check alongside .other above).
    PREFIXES + "SELECT ?s WHERE { ?s rdf:rest ?o . FILTER(rdf:nil = ?o) }",
]


def _canon(res):
    rows = []
    for b in res["bindings"]:
        rows.append(frozenset((str(k), v.n3()) for k, v in b.items() if v is not None))
    return sorted(rows, key=lambda r: sorted(r))


@pytest.fixture
def malformed_list_graph() -> Graph:
    g = Graph()
    g.parse(data=_MALFORMED_LIST_DATA, format="turtle")
    return g


@pytest.mark.parametrize("query_text", QUERIES)
def test_rdf_nil_as_literal_term_roundtrips(malformed_list_graph, query_text):
    prepared = prepareQuery(query_text)
    original = evalQuery(malformed_list_graph, prepared)

    graph, root = query_to_rdf(prepared)
    reconstructed = rdf_to_query(graph, root)
    roundtripped = evalQuery(malformed_list_graph, reconstructed)

    assert _canon(original) == _canon(roundtripped)


def test_malformed_cell_is_still_detected_after_roundtrip(malformed_list_graph):
    """The adversarial case, in isolation: the round-tripped query must
    still find *both* :items (the zero-length path) and :extra (the
    malformed cell) - the exact result plain, un-round-tripped rdflib
    produces against the same data."""
    query_text = QUERIES[3]
    prepared = prepareQuery(query_text)
    graph, root = query_to_rdf(prepared)
    reconstructed = rdf_to_query(graph, root)
    rows = list(evalQuery(malformed_list_graph, reconstructed)["bindings"])
    found = {str(b[list(b)[0]]) for b in rows}
    assert found == {"http://example.org/items", "http://example.org/extra"}


# (update text, initial data, expected presence of :a :b :c in <g> afterward)
# entirely inside a GRAPH block - the top-level (default graph) `triples`
# list is genuinely empty (InsertData.triples/DeleteData.triples) - exactly
# the shape that regressed in this project's own test_dataset_query.py
# while building this fix.
UPDATES = [
    (PREFIXES + "INSERT DATA { GRAPH <http://example.org/g> { :a :b :c } }", "", True),
    (PREFIXES + "DELETE DATA { GRAPH <http://example.org/g> { :a :b :c } }", ":a :b :c .", False),
]


@pytest.mark.parametrize("update_text,initial_data,expect_present", UPDATES)
def test_update_with_empty_default_graph_triples_roundtrips(update_text, initial_data, expect_present):
    ds = Dataset()
    ds.parse(data=PREFIXES + initial_data, format="turtle", publicID="http://example.org/g")

    prepared = prepare_update_12(update_text)
    graph, root = update_to_rdf(prepared)
    reconstructed = rdf_to_update(graph, root)
    evalUpdate(ds, reconstructed)

    triple = (URIRef("http://example.org/a"), URIRef("http://example.org/b"), URIRef("http://example.org/c"))
    assert (triple in ds.get_context("http://example.org/g")) == expect_present
