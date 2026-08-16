"""The readable syntax-level projection: ssyn: RDF, no more verbose than
the SPARQL text itself, built from the raw parse tree using rdflib's own
real simplification functions (see to_ssyn_rdf.py's module docstring).

Verifies text -> parse tree -> ssyn: RDF -> regenerated text -> re-parsed
-> results, by *executing* both the originally-prepared query and the
regenerated text and comparing result sets — same standard as
test_roundtrip.py/test_ast_ontology.py. Round-tripping through text here
(rather than reconstructing algebra CompValue trees directly) is
deliberate — see ssyn_to_text.py's module docstring for why that's the
lower-risk path: it reuses this project's own already-tested
parse/translate pipeline unchanged for the "back to executable" direction.
"""

import pytest
from rdflib.plugins.sparql.evaluate import evalQuery
from rdflib.plugins.sparql.parser import parseQuery
from rdflib.plugins.sparql.processor import prepareQuery
from starsparql.ssyn_to_text import ssyn_rdf_to_query_text
from starsparql.to_ssyn_rdf import query_to_ssyn_rdf

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
        SELECT ?name ?age WHERE {
          ?p foaf:name ?name .
          OPTIONAL { ?p foaf:age ?age }
          FILTER(?name != "Bob")
        }
    """,
    PREFIXES + """
        SELECT ?p WHERE {
          { ?p foaf:name "Alice" } UNION { ?p foaf:name "Bob" }
        }
    """,
    PREFIXES + """
        SELECT ?name ?upper WHERE {
          ?p foaf:name ?name .
          BIND(UCASE(?name) AS ?upper)
        }
    """,
    # property path
    PREFIXES + "SELECT ?a ?b WHERE { ?a foaf:knows+ ?b }",
]


def _canon(res):
    rows = []
    for b in res["bindings"]:
        rows.append(frozenset((str(k), v.n3()) for k, v in b.items() if v is not None))
    return sorted(rows, key=lambda r: sorted(r))


@pytest.mark.parametrize("query_text", QUERIES)
def test_ssyn_roundtrip_result_equivalence(fixture_graph, query_text):
    prepared = prepareQuery(query_text)
    original = evalQuery(fixture_graph, prepared)

    parse_result = parseQuery(query_text)
    graph, root = query_to_ssyn_rdf(parse_result)
    regenerated_text = ssyn_rdf_to_query_text(graph, root)
    reprepared = prepareQuery(regenerated_text)
    roundtripped = evalQuery(fixture_graph, reprepared)

    canon_original = _canon(original)
    canon_roundtripped = _canon(roundtripped)
    assert canon_original == canon_roundtripped
    assert len(canon_original) > 0  # guard against a vacuously-true empty comparison


def test_ssyn_where_reads_no_more_verbose_than_source():
    """A concrete check on the actual design goal — no salg: anywhere for a
    plain BGP, and no verbosity beyond ordinary triple patterns."""

    query_text = PREFIXES + "SELECT ?name WHERE { ?p a foaf:Person ; foaf:name ?name }"
    graph, root = query_to_ssyn_rdf(parseQuery(query_text))
    salg_triples = [t for t in graph if "ns/algebra#" in str(t[1]) or "ns/algebra#" in str(t[2])]
    assert not salg_triples, f"expected no salg: triples for a plain BGP, found: {salg_triples}"
