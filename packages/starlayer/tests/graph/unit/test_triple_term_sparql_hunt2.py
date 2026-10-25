"""Triple terms in SPARQL on the rdf-1.1 representation (GitHub issue #74): they are not IRIs, a negated property set does
not see the encoding, and a triple term can sit in a pattern beside an IRI object."""

import warnings

import pytest
from starlayer.graph import StarLayerGraph

warnings.simplefilter("ignore")
DATA = "@prefix : <http://x/> . :s :q :o . << :s :q :o >> :cert 0.9 . :a :q <<(:s :p 123)>> ."


def _graph():
    g = StarLayerGraph()
    g.parse(data=DATA, format="turtle12")
    return g


def _row(g, query):
    return [tuple(None if v is None else str(v) for v in r) for r in g.query(query)]


def test_a_triple_term_is_not_an_iri_a_literal_or_a_blank_node():
    row = _row(
        StarLayerGraph(),
        "PREFIX : <http://x/> SELECT (isIRI(TRIPLE(:a,:b,:c)) AS ?i) (isLiteral(TRIPLE(:a,:b,:c)) AS ?l) "
        "(isBlank(TRIPLE(:a,:b,:c)) AS ?b) (isIRI(:a) AS ?j) {}",
    )
    assert row == [("false", "false", "false", "true")]


def test_str_of_a_triple_term_is_an_error_and_str_of_an_iri_is_not():
    row = _row(StarLayerGraph(), "PREFIX : <http://x/> SELECT (STR(TRIPLE(:a,:b,:c)) AS ?w) (STR(:a) AS ?v) {}")
    assert row == [(None, "http://x/a")]


def test_is_iri_over_a_stored_triple_term():
    rows = _row(_graph(), "PREFIX : <http://x/> SELECT ?x (isIRI(?o) AS ?i) { ?x :q ?o }")
    assert sorted(rows) == [("http://x/a", "false"), ("http://x/s", "true")]


def test_filter_is_iri_does_not_return_a_triple_term():
    rows = _row(_graph(), "PREFIX : <http://x/> SELECT ?o { ?x :q ?o FILTER(isIRI(?o)) }")
    assert rows == [("http://x/o",)]


def test_negated_property_set_matches_only_asserted_triples():
    g = _graph()
    negated = _row(g, "SELECT ?x ?y WHERE { ?x !(<http://x/zz>) ?y }")
    plain = _row(g, "SELECT ?x ?y WHERE { ?x ?p ?y }")
    assert sorted(negated) == sorted(plain)


def test_negated_property_set_still_excludes_the_listed_predicate():
    rows = _row(_graph(), "PREFIX : <http://x/> SELECT ?x ?y WHERE { ?x !(:q) ?y }")
    assert all("cert" not in r[0] for r in rows)
    assert len(rows) == 2  # the reifier's rdf:reifies and :cert triples


@pytest.mark.parametrize(
    "query",
    [
        'SELECT * { ?s <http://p> <http://b> . ?s <http://p> <<( <http://x> <http://y> "z" )>> }',
        'SELECT * { ?s <http://p> <http://b> , <<( <http://x> <http://y> "z" )>> }',
    ],
)
def test_a_triple_term_object_beside_an_iri_object(query):
    g = StarLayerGraph()
    g.update('INSERT DATA { <http://a> <http://p> <http://b> . <http://a> <http://p> <<( <http://x> <http://y> "z" )>> }')
    assert len(g) == 2
    assert len(list(g.query(query))) == 1
    g.update('DELETE DATA { <http://a> <http://p> <http://b> . <http://a> <http://p> <<( <http://x> <http://y> "z" )>> }')
    assert len(g) == 0
