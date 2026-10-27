"""Leftovers of issue #93: annotations and reifiers wherever the grammar allows
them, MINUS over a triple-term pattern, TRIPLE() arguments, and the syntax rules
for VALUES triple terms, BIND scope and SELECT * with grouping."""

from __future__ import annotations

import pytest
from pyparsing import ParseBaseException
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.sparql._syntax_checks import SPARQLSyntaxError
from starlayer.sparql.lower_rdf11 import query_to_rdf11, rdf11_to_sparql11_text
from starlayer.sparql.parse12 import prepare_query_12, prepare_update_12

P = "PREFIX : <http://e/> "
REIFIES = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies>"

ANNOTATION_FORMS = [
    ":a :p :b ~ :r , :c",
    ":a :p :b ~ :r ; :q 1",
    ":a :p :b {| :c 1 |} ; :q 1",
    ":a :p :b , :c ~ :r",
    ":a :p :b ; :q 1 ~ :r",
    ":a a :T ~ :r",
    ":a a :T {| :c 1 |}",
    ":a :p :b {| :c 1 , 2 |}",
    ":a :p :b {| :c 1 ; |}",
    ":a :p :b {| :c 1 {| :d 2 |} |}",
    "[ :p :b ~ :r ] :q 1",
    "( :a :b ) :p :b {| :c 1 |}",
    ":a :p ( 1 2 ) ~ :r",
    ":a :p [ :q :x ] ~ :r",
    ":a :p :b {| :c 1 ~ :r2 |}",
]


@pytest.mark.parametrize("body", ANNOTATION_FORMS)
def test_annotation_forms_parse_in_a_query_and_in_insert_data(body):
    prepare_query_12(P + "SELECT * { " + body.replace(":r2", "?r2").replace(":r", "?r") + " }")
    prepare_update_12(P + "INSERT DATA { " + body + " }")
    prepare_update_12(P + "INSERT DATA { GRAPH :g { " + body + " } }")


def test_annotation_forms_parse_in_a_construct_template():
    prepare_query_12(P + "CONSTRUCT { ?s :p ?o ~ ?r , ?o2 ; :q 1 {| :c 2 |} } WHERE { ?s :p ?o , ?o2 }")


def test_a_reifier_and_annotation_after_a_list_continuation_mean_the_expanded_triples():
    g = StarLayerGraph()
    g.parse(
        data="@prefix : <http://e/> .\n"
        ":a :p :b ~ :r1 {| :c 5 |} , :c ~ :r2 ; :q 1 {| :w 2 {| :z 3 |} |} .\n:d a :T ~ :r3 .",
        format="turtle12",
    )

    def rows(q):
        return {tuple(str(v) for v in r) for r in g.query(P + q)}

    # annotation after "," and "a", before ";", and nested
    assert rows("SELECT ?o ?r WHERE { ?r " + REIFIES + " <<( :a :p ?o )>> }") == {("http://e/b", "http://e/r1"), ("http://e/c", "http://e/r2")}
    assert rows("SELECT ?o ?r ?c { :a :p ?o ~ ?r {| :c ?c |} , :c }") == {("http://e/b", "http://e/r1", "5")}
    assert rows("SELECT ?o ?w ?z { :a :q ?o {| :w ?w {| :z ?z |} |} ; :p :b }") == {("1", "2", "3")}
    assert rows("SELECT ?s ?r { ?s a :T ~ ?r }") == {("http://e/d", "http://e/r3")}
    assert rows("SELECT ?o { ?s :p ?o {| :c 1 , 5 |} }") == set()
    assert rows("SELECT ?o { ?s :p ?o {| :c 5 |} }") == {("http://e/b",)}


def test_a_bare_reifier_inside_a_reified_triple_parses():
    prepare_query_12(P + "SELECT * { << ?s :p ?o ~ >> :q ?z }")


@pytest.mark.parametrize("reifier", ["1", '"x"', "( )"])
def test_a_reifier_cannot_be_a_literal_or_nil(reifier):
    with pytest.raises(ParseBaseException):
        prepare_query_12(P + "SELECT * { :a :p :b ~ " + reifier + " }")


def test_a_reifier_on_a_property_path_is_rejected():
    with pytest.raises(ValueError, match="property path"):
        prepare_query_12(P + "SELECT * { ?s ^:p ?o ~ ?r }")


def test_minus_over_a_triple_term_pattern_removes_the_matching_solution():
    g = StarLayerGraph()
    g.parse(data="@prefix : <http://e/> .\n:a :p :b ~ :r1 .\n:a :p :c .\n<< :a :p :b >> :src :s1 .", format="turtle12")
    assert list(g.query(P + "SELECT ?x WHERE { ?x :p :b . MINUS { ?r " + REIFIES + " <<( ?x :p :b )>> } }")) == []
    rows = list(g.query(P + "SELECT ?x ?o WHERE { ?x :p ?o . MINUS { << ?x :p ?o >> :src ?s } }"))
    assert [(str(r.x), str(r.o)) for r in rows] == [("http://e/a", "http://e/c")]


def test_triple_accepts_triple_term_and_accessor_arguments():
    g = StarLayerGraph()
    g.parse(data="@prefix : <http://e/> .\n:a :r <<( :a :p :b )>> .", format="turtle12")
    # a triple term as subject or predicate is a type error: one row, ?u unbound
    for q in (
        "SELECT ?u WHERE { BIND(TRIPLE(<<( :a :p :b )>>, :p, :b) AS ?u) }",
        "SELECT ?u WHERE { BIND(TRIPLE(:a, <<( :a :p :b )>>, :b) AS ?u) }",
    ):
        rows = list(g.query(P + q))
        assert len(rows) == 1 and rows[0].u is None
    rows = list(g.query(P + "SELECT ?t ?u WHERE { ?s :r ?t BIND(TRIPLE(SUBJECT(?t), PREDICATE(?t), OBJECT(?t)) AS ?u) FILTER(?t = ?u) }"))
    assert len(rows) == 1


@pytest.mark.parametrize("form", ["ASK { ?s :p ?o }", "DESCRIBE :a"])
def test_sparql11_text_for_ask_and_describe_is_not_implemented(form):
    graph, root = query_to_rdf11(prepare_query_12(P + form))
    with pytest.raises(NotImplementedError):
        rdf11_to_sparql11_text(graph, root)


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * { VALUES ?t { <<( _:a :p 1 )>> } }",
        "SELECT * { VALUES ?t { <<( :a ?p 1 )>> } }",
        "SELECT * { VALUES ?t { <<( :a :p ?b )>> } }",
        "SELECT * { VALUES ?t { <<( :a :p <<( :b :q _:c )>> )>> } }",
        "SELECT * { BIND(<<( :a :p [] )>> AS ?t) }",
        "SELECT * { ?s ?p ?o BIND(1 AS ?o) }",
        "SELECT * { ?s ?p ?o BIND(1 AS ?x) BIND(2 AS ?x) }",
        "SELECT * { { ?s ?p ?o } BIND(1 AS ?o) }",
        "SELECT * { ?s ?p ?o OPTIONAL { ?o :q ?z } BIND(1 AS ?z) }",
        "SELECT * { ?s ?p ?o } HAVING (COUNT(?o) > 1)",
        "SELECT * { ?s ?p ?o } ORDER BY COUNT(?o)",
        "SELECT * { ?s ?p ?o } GROUP BY ?s",
    ],
)
def test_syntax_rules_the_grammar_states_are_enforced(query):
    with pytest.raises(SPARQLSyntaxError):
        prepare_query_12(P + query)


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * { VALUES ?t { <<( :a :p 1 )>> <<( :a :p <<( :b :q 'x' )>> )>> } }",
        "SELECT * { ?s ?p ?o BIND(1 AS ?x) BIND(?x AS ?y) }",
        "SELECT * { ?s ?p ?o FILTER(?o > 1) BIND(1 AS ?f) }",
        "SELECT * { ?s ?p ?o MINUS { ?o :q ?z } BIND(1 AS ?z) }",
        "SELECT * { BIND(1 AS ?x) ?s ?p ?x }",
        "SELECT ?s (COUNT(?o) AS ?c) { ?s ?p ?o } GROUP BY ?s HAVING (COUNT(?o) > 1)",
    ],
)
def test_valid_forms_next_to_those_rules_still_parse(query):
    prepare_query_12(P + query)
