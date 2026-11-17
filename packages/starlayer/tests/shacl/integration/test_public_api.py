"""The public surface applications use: everything importable from ``starlayer.shacl`` / ``starlayer.graph`` / ``starlayer.sparql``
(apps do not import submodules; the graph workbench's needs are in docs/working/workbench-api-needs.md)."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph, isomorphic
from starlayer.shacl import (
    evaluate_expression,
    infer_types,
    is_inverse,
    node_expression_functions,
    node_expression_operators,
    parameter_value_shapes,
    path_values,
    select_widgets,
    shapes_graph_members,
    sparql_query_problems,
)
from starlayer.shacl.engine.terms import to_engine
from starlayer.sparql import check_query
from tests.support.terms import RDF, Namespace, lit

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")
PRE = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . @prefix sparql: <http://www.w3.org/ns/sparql#> . "
)


def graph(turtle: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PRE + turtle, format="turtle12")
    return g


def expr(turtle: str):
    """The node of ``ex:E sh:values <expression>`` and the graph holding it."""
    g = graph("ex:E sh:values " + turtle + " .")
    return g, next(g.objects(EX.E, SH["values"]))


def test_evaluate_expression_calls_a_sparql_function_and_follows_a_path():
    shapes, concat = expr('[ sparql:concat ( "a" "b" ) ]')
    assert evaluate_expression(shapes, graph(""), concat, EX.a) == [lit("ab")]

    shapes, via = expr("[ shnex:pathValues ex:p ]")
    assert set(evaluate_expression(shapes, graph("ex:a ex:p 1, 2 ."), via, EX.a)) == {lit(1), lit(2)}


def test_evaluate_expression_binds_variables_from_the_scope():
    shapes, var = expr('[ shnex:var "x" ]')
    assert evaluate_expression(shapes, graph(""), var, EX.a, scope={"x": lit("v")}) == [lit("v")]
    assert evaluate_expression(shapes, graph(""), var, EX.a, scope={"x": [lit(1), lit(2)]}) == [lit(1), lit(2)]


def test_the_function_and_operator_lists_name_iris():
    functions, operators = node_expression_functions(), node_expression_operators()
    assert "http://www.w3.org/ns/sparql#concat" in functions and functions == sorted(functions)
    assert "http://www.w3.org/ns/shacl-node-expr#pathValues" in operators
    assert not set(functions) & set(operators)


def test_infer_types_and_paths_and_members_are_public():
    g = graph("ex:S sh:property ex:P . ex:P sh:path ex:p . ex:a ex:p 1 .")
    assert (EX.P, RDF.type, SH.PropertyShape) in infer_types(g)
    assert path_values(g, EX.a, EX.p) == frozenset({to_engine(lit(1))})
    assert is_inverse(g, EX.p) is False


def test_the_other_helpers_are_importable_and_callable():
    assert callable(select_widgets) and callable(shapes_graph_members) and callable(parameter_value_shapes)
    problems = list(sparql_query_problems(graph('ex:S sh:select "not sparql" .')))
    assert [(node, predicate) for node, predicate, _message in problems] == [(EX.S, SH.select)]
    assert isomorphic(graph("ex:a ex:p [ ex:q 1 ] ."), graph("ex:a ex:p [ ex:q 1 ] ."))


def test_check_query_says_what_a_text_is_and_what_is_wrong_with_it():
    good = check_query("SELECT * WHERE { ?s ?p ?o }")
    assert good.ok and good.form == "SELECT" and good.problems == ()
    assert check_query("INSERT DATA { <urn:a> <urn:b> <urn:c> }").form == "UPDATE"
    bad = check_query("SELECT ?s WHERE { ?s <urn:p> }")
    assert not bad.ok and bad.form is None
    (problem,) = bad.errors
    assert (problem.kind, problem.line, problem.column) == ("syntax", 1, 30)


def test_check_query_treats_an_undeclared_prefix_as_a_warning_until_the_graphs_prefixes_are_given():
    text = "SELECT ?s WHERE { ?s ex:name ?n . ?n foaf:x ?z FILTER(?q > 1) }"
    check = check_query(text)
    assert check.ok and check.form == "SELECT"  # the graph it runs against may declare them
    assert [p.kind for p in check.warnings] == ["prefix", "prefix", "shape"]  # and the rest of the text was still checked
    assert (check.warnings[0].line, check.warnings[0].column) == (1, 22)
    declared = {"ex": "http://example.org/", "foaf": "http://xmlns.com/foaf/0.1/"}
    assert check_query(text, prefixes=declared).warnings[0].kind == "shape"
    (error,) = check_query("SELECT * WHERE { ?s a nope:T }", prefixes=declared).errors  # given prefixes, one it lacks is an error
    assert error.kind == "prefix"
    update = "INSERT DATA { ex:a ex:b ex:c }"
    assert check_query(update).ok and check_query(update).form == "UPDATE"
    assert check_query(update, prefixes=declared).problems == ()
    assert not check_query(update, prefixes={"foo": "urn:f/"}).ok


def test_check_query_warns_about_unbound_variables_without_failing_the_text():
    check = check_query("SELECT ?z WHERE { ?s ?p ?o }")
    assert check.ok and check.errors == ()
    assert [p.kind for p in check.warnings] == ["shape"]
    assert "never bound" in check.warnings[0].message


def test_check_query_reports_a_version_directive_the_text_contradicts():
    triple_term = "SELECT * WHERE { ?s ?p <<( <urn:a> <urn:b> <urn:c> )>> }"
    contradicted = check_query(f'VERSION "1.1"\n{triple_term}')
    assert not contradicted.ok and contradicted.errors[0].kind == "version" and "triple term" in contradicted.errors[0].message
    assert "unrecognized VERSION" in check_query('VERSION "9.9"\nSELECT * WHERE { ?s ?p ?o }').errors[0].message
    assert check_query(f'VERSION "1.2"\n{triple_term}').ok
    assert check_query(triple_term).ok
    assert not check_query('VERSION "1.1"\nINSERT DATA { <urn:a> <urn:b> <<( <urn:a> <urn:b> <urn:c> )>> }').ok


def test_check_query_has_oxigraph_check_the_query_and_takes_the_functions_it_calls():
    text = "SELECT ?s WHERE { ?s ?p ?o FILTER(<urn:fn:unknown>(?o)) }"
    assert check_query(text).errors[0].kind == "engine"
    assert check_query(text, custom_functions={"urn:fn:unknown": lambda term: term}).ok
    assert check_query("INSERT DATA { <urn:a> <urn:b> <urn:c> }").ok  # an update is not run



def test_apps_can_reach_nothing_else_is_needed():
    with pytest.raises(ImportError):
        from starlayer.shacl import _ALL_PREDICATES  # noqa: F401


def test_check_query_flags_distinct_in_an_extension_function_call_in_a_text_oxigraph_never_runs():
    update = "INSERT { ?s <urn:p> ?o } WHERE { ?s ?p ?o FILTER(<urn:fn:f>(DISTINCT ?o)) }"
    check = check_query(update)
    assert check.form == "UPDATE" and check.ok
    assert [p.kind for p in check.warnings] == ["shape"] and "DISTINCT" in check.warnings[0].message
