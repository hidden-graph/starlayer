"""The public surface applications use: everything importable from ``starlayer.shacl`` / ``starlayer.graph`` / ``starlayer.sparql``
(apps do not import submodules; the graph workbench's needs are in docs/working/workbench-api-needs.md)."""

from __future__ import annotations

import pytest
from rdflib import RDF, Literal, Namespace
from starlayer import StarLayerGraph
from starlayer.graph import isomorphic
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
from starlayer.sparql import check_query
from starlayer.shacl_engine.terms import from_engine, to_engine

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
    assert evaluate_expression(shapes, graph(""), concat, EX.a) == [Literal("ab")]

    shapes, via = expr("[ shnex:pathValues ex:p ]")
    assert set(evaluate_expression(shapes, graph("ex:a ex:p 1, 2 ."), via, EX.a)) == {Literal(1), Literal(2)}


def test_evaluate_expression_binds_variables_from_the_scope():
    shapes, var = expr('[ shnex:var "x" ]')
    assert evaluate_expression(shapes, graph(""), var, EX.a, scope={"x": Literal("v")}) == [Literal("v")]
    assert evaluate_expression(shapes, graph(""), var, EX.a, scope={"x": [Literal(1), Literal(2)]}) == [Literal(1), Literal(2)]


def test_the_function_and_operator_lists_name_iris():
    functions, operators = node_expression_functions(), node_expression_operators()
    assert "http://www.w3.org/ns/sparql#concat" in functions and functions == sorted(functions)
    assert "http://www.w3.org/ns/shacl-node-expr#pathValues" in operators
    assert not set(functions) & set(operators)


def test_infer_types_and_paths_and_members_are_public():
    g = graph("ex:S sh:property ex:P . ex:P sh:path ex:p . ex:a ex:p 1 .")
    assert (EX.P, RDF.type, SH.PropertyShape) in infer_types(g)
    assert path_values(g, EX.a, EX.p) == frozenset({to_engine(Literal(1))})
    assert is_inverse(g, EX.p) is False


def test_the_other_helpers_are_importable_and_callable():
    assert callable(select_widgets) and callable(shapes_graph_members) and callable(parameter_value_shapes)
    problems = list(sparql_query_problems(graph('ex:S sh:select "not sparql" .')))
    assert [(from_engine(node), from_engine(predicate)) for node, predicate, _message in problems] == [(EX.S, SH.select)]
    assert isomorphic(graph("ex:a ex:p [ ex:q 1 ] ."), graph("ex:a ex:p [ ex:q 1 ] ."))


def test_check_query_returns_none_for_good_text_and_the_parser_message_for_bad():
    assert check_query("SELECT * WHERE { ?s ?p ?o }") is None
    assert isinstance(check_query("SELEC"), str)
    assert check_query("SELECT * WHERE { ?s a nope:T }", prepare=True)  # a prefix nothing declares


def test_apps_can_reach_nothing_else_is_needed():
    with pytest.raises(ImportError):
        from starlayer.shacl import _ALL_PREDICATES  # noqa: F401
