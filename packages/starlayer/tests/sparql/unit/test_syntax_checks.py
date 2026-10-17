"""Grammar rules rdflib accepts but SPARQL 1.2 forbids; see
starlayer/sparql/_syntax_checks.py."""

import pytest
import starlayer.graph  # noqa: F401  (applies the STRLANG patch)
from rdflib import Graph
from starlayer.sparql._syntax_checks import SPARQLSyntaxError
from starlayer.sparql.parse12 import prepare_query_12, prepare_update_12

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
    with pytest.raises(SPARQLSyntaxError):
        prepare_query_12(text)


@pytest.mark.parametrize("text", GOOD_QUERIES)
def test_good_query_accepted(text):
    prepare_query_12(text)


def test_bad_update_rejected():
    with pytest.raises(SPARQLSyntaxError):
        prepare_update_12('INSERT DATA { <http://ex/a> <http://ex/b> "\\uD800" }')


def test_strlang_empty_tag_is_an_error():
    row = list(
        Graph().query(
            'SELECT (STRLANG("a", "") AS ?r) (STRLANG("a", "EN") AS ?s) WHERE {}'
        )
    )[0]
    assert row[0] is None
    assert str(row[1]) == "a" and row[1].language == "en"


def test_escaped_backslash_before_u_is_not_an_escape():
    """The check pairs `\\\\` first; rdflib itself cannot parse this text, so test the check alone."""
    from starlayer.sparql._syntax_checks import reject_surrogate_escapes

    reject_surrogate_escapes('"\\\\uD800"')


def test_sameterm_treats_simple_literal_and_xsd_string_as_one_term():
    q = (
        "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> "
        'SELECT (sameTerm("a", "a"^^xsd:string) AS ?same) (sameTerm("a", "b") AS ?diff) '
        '(sameTerm("a", "a"@en) AS ?lang) WHERE {}'
    )
    same, diff, lang = list(Graph().query(q))[0]
    assert (bool(same), bool(diff), bool(lang)) == (True, False, False)
