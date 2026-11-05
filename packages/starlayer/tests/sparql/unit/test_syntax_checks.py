"""Grammar rules rdflib's parser accepted but SPARQL 1.2 forbids (once starlayer/sparql/_syntax_checks.py), now enforced by
StarLayer's own parser (``parse_sparql``)."""

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.sparql.parse_sparql import SparqlSyntaxError
from starlayer.sparql.parse_sparql import parse_sparql as prepare_query_12
from starlayer.sparql.parse_sparql import parse_sparql_update as prepare_update_12

BAD_QUERIES = {
    "nested aggregate": "SELECT (COUNT(COUNT(*)) AS ?c) WHERE { ?s ?p ?o }",
    "repeated VALUES variable": "SELECT * WHERE { VALUES (?a ?a) { (1 2) } }",
    "alias reuses GROUP BY variable": "SELECT (1 AS ?s) WHERE { ?s ?p ?o } GROUP BY ?s",
    "alias reuses GROUP BY alias": "SELECT (1 AS ?z) WHERE { ?s ?p ?o } GROUP BY (?s AS ?z)",
    "surrogate escape in string": 'SELECT * WHERE { ?s ?p "\\uD800" }',
    "valid surrogate pair": 'SELECT * WHERE { ?s ?p "\\uD83C\\uDCA1" }',
    "surrogate escape in IRI": "SELECT * WHERE { ?s ?p <http://example/\\uDCA1> }",
    "nested aggregate in subquery": "SELECT * WHERE { { SELECT (SUM(MAX(?o)) AS ?x) WHERE { ?s ?p ?o } } }",
}

GOOD_QUERIES = [
    "SELECT ?s (COUNT(?o) AS ?c) WHERE { ?s ?p ?o } GROUP BY ?s",
    "SELECT (SUM(?o) AS ?t) WHERE { ?s ?p ?o } GROUP BY (?s AS ?k)",
    "SELECT * WHERE { VALUES (?a ?b) { (1 1) } }",
    "SELECT (COUNT(*) AS ?c) (MAX(?o) AS ?m) WHERE { ?s ?p ?o }",
    'SELECT * WHERE { ?s ?p "\\U0001F0A1" }',
    'SELECT * WHERE { ?s ?p "\\u00E9" }',
]


@pytest.mark.parametrize("text", BAD_QUERIES.values(), ids=BAD_QUERIES.keys())
def test_bad_query_rejected(text):
    with pytest.raises(SparqlSyntaxError):
        prepare_query_12(text)


@pytest.mark.parametrize("text", GOOD_QUERIES)
def test_good_query_accepted(text):
    prepare_query_12(text)


def test_bad_update_rejected():
    with pytest.raises(SparqlSyntaxError):
        prepare_update_12('INSERT DATA { <http://ex/a> <http://ex/b> "\\uD800" }')


def test_strlang_empty_tag_is_an_error():
    row = list(
        StarLayerGraph().query(
            'SELECT (STRLANG("a", "") AS ?r) (STRLANG("a", "EN") AS ?s) WHERE {}'
        )
    )[0]
    assert row[0] is None
    assert row[1].value == "a" and row[1].language == "en"


def test_escaped_backslash_before_u_is_not_an_escape():
    """The text ``"\\\\uD800"`` is an escaped backslash followed by ``uD800``, not a surrogate escape."""
    prepare_query_12('SELECT * WHERE { ?s ?p "\\\\uD800" }')


def test_sameterm_treats_simple_literal_and_xsd_string_as_one_term():
    q = (
        "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> "
        'SELECT (sameTerm("a", "a"^^xsd:string) AS ?same) (sameTerm("a", "b") AS ?diff) '
        '(sameTerm("a", "a"@en) AS ?lang) WHERE {}'
    )
    same, diff, lang = list(StarLayerGraph().query(q))[0]
    assert (same.value, diff.value, lang.value) == ("true", "false", "false")
