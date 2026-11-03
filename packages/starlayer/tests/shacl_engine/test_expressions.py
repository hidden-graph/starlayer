"""Unit tests for the native node-expression evaluator (``starlayer.shacl_engine.expressions``) and the constraint
components and value-node rules built on it. The W3C fixtures are in ``w3c_shacl12/test_w3c_engine_node_expr.py``."""

from __future__ import annotations

import pytest
from pyoxigraph import BlankNode as BNode
from pyoxigraph import Literal
from starlayer.graph.oxgraph import OxGraph
from starlayer.shacl_engine import validate
from starlayer.shacl_engine.executor import Context
from starlayer.shacl_engine.expressions import (
    OPERATORS,
    EvaluationFailure,
    evaluate_expression,
)
from starlayer.shacl_engine.plan import Plan, ShapeError
from starlayer.shacl_engine.terms import NS as Namespace
from starlayer.shacl_engine.terms import XSD, boolean, integer, lexical, text

EX = Namespace("http://example.com/")
PREFIXES = """
@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.com/> . @prefix sparql: <http://www.w3.org/ns/sparql#> .
@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""


def graph(ttl: str) -> OxGraph:
    g = OxGraph()
    g.parse(data=PREFIXES + ttl, format="turtle")
    return g


def ev(ttl_expr: str, data: str = "", focus=None, bindings=None):
    """Evaluate the blank-node expression ``ttl_expr`` (Turtle for a ``[ ... ]`` or a constant)."""
    g = graph(f"ex:root ex:expr {ttl_expr} . {data}")
    expr = next(g.objects(EX.root, EX.expr))
    bindings = {k: (v if isinstance(v, list) else [v]) for k, v in (bindings or {}).items()}
    out = evaluate_expression(
        Context(data=g, plan=Plan(shapes_graph=g)), expr, focus, bindings
    )
    return list(out)


def test_registry_is_a_table_of_shnex_and_sparql_iris():
    names = {k.value.rsplit("#", 1)[-1] for k in OPERATORS}
    assert {
        "pathValues",
        "flatMap",
        "conformsToShape",
        "coalesce",
        "strlen",
        "select",
        "sparqlExpr",
    } <= names


def test_bindings_accept_a_term_or_a_list_and_focus_node_is_the_focus():
    assert ev('[ shnex:var "x" ]', bindings={"x": integer(1)}) == [integer(1)]
    assert ev('[ shnex:var "x" ]', bindings={"x": [integer(1), integer(2)]}) == [
        integer(1),
        integer(2),
    ]
    assert ev('[ shnex:var "focusNode" ]', focus=EX.a) == [EX.a]
    assert ev('[ shnex:var "focusNode" ]') == []


def test_if_is_lazy_and_errors_in_the_unselected_branch_do_not_matter():
    assert ev(
        "[ shnex:if true ; shnex:then 1 ; shnex:else [ sparql:abs ( [ shnex:concat ( 1 2 ) ] ) ] ]"
    ) == [integer(1)]


def test_path_values_focus_node_with_several_nodes_is_a_failure():
    data = "ex:a ex:p ex:b, ex:c ."
    with pytest.raises(EvaluationFailure):
        ev(
            "[ shnex:pathValues ex:q ; shnex:focusNode [ shnex:pathValues ex:p ] ]",
            data,
            EX.a,
        )


def test_sum_promotes_types():
    assert ev("[ shnex:sum ( 1 2 ) ]") == [integer(3)]
    assert ev("[ shnex:sum ( 1 2.5 ) ]") == [Literal("3.5", datatype=XSD.decimal)]
    assert ev("[ shnex:sum ( 1 2.5e0 ) ]")[0].datatype == XSD.double
    with pytest.raises(EvaluationFailure):
        ev('[ shnex:sum ( 1 "a" ) ]')


def test_order_by_sorts_unbound_first_and_desc_reverses():
    data = "ex:a ex:h 3 . ex:b ex:h 1 . ex:c a ex:T ."
    assert ev(
        "[ shnex:nodes ( ex:a ex:b ex:c ) ; shnex:orderBy [ shnex:pathValues ex:h ] ]",
        data,
    ) == [EX.c, EX.b, EX.a]
    assert ev(
        "[ shnex:nodes ( ex:a ex:b ex:c ) ; shnex:orderBy [ shnex:pathValues ex:h ] ; shnex:desc true ]",
        data,
    ) == [EX.a, EX.b, EX.c]


def test_min_max_use_sparql_ordering_across_types():
    assert ev('[ shnex:min ( 3 "a" ex:i ) ]') == [EX.i]
    assert ev('[ shnex:max ( 3 "a" ex:i ) ]') == [Literal("a")]


def test_sparql_function_argument_rules():
    assert ev('[ sparql:coalesce ( [] "ok" ) ]') == [Literal("ok")]
    assert ev("[ sparql:strlen ( [] ) ]") == []  # an unbound argument gives no output
    with pytest.raises(EvaluationFailure):
        ev("[ sparql:abs ( ( -1 -2 ) ) ]")  # two output nodes: an error
    with pytest.raises(EvaluationFailure):
        ev("[ sparql:abs ( ( -1 -2 ) [] ) ]")  # an error beats an unbound argument
    with pytest.raises(EvaluationFailure):
        ev('[ sparql:if ( true [] "no" ) ]')  # the selected branch is unbound
    assert ev("[ sparql:logical-or ( [ sparql:abs ( ( 1 2 ) ) ] true ) ]") == [
        boolean(True)
    ]


def test_triple_terms_flow_through_sparql_functions():
    assert ev("[ sparql:subject ( [ sparql:triple ( ex:s ex:p ex:o ) ] ) ]") == [EX.s]


def test_malformed_expressions_are_shape_errors():
    with pytest.raises(ShapeError):
        ev("[ shnex:nodes ( 1 2 ) ]")  # no operator predicate
    with pytest.raises(ShapeError):
        ev("[ shnex:count 1 ; shnex:sum 2 ]")  # two operators
    with pytest.raises(ShapeError):
        ev("[ shnex:limit -1 ; shnex:nodes ( 1 ) ]")
    with pytest.raises(ShapeError):
        ev("[ sparql:strlen 1 ]")  # a sparql: function takes a list


def test_legacy_sh_forms_are_not_expressions():
    with pytest.raises(ShapeError):
        ev("[ sh:union ( ( 1 ) ( 2 ) ) ]")


def test_sh_select_sees_scope_variables():
    r = ev(
        '[ sh:select "SELECT ?x WHERE { BIND($value + 1 AS ?x) }" ]',
        bindings={"value": integer(1)},
    )
    assert r == [integer(2)]


# --- constraint components and value nodes -------------------------------------------------------------------------


def test_sh_expression_scope_has_value_and_reports_the_expression():
    shapes = """ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:n ;
        sh:expression [ sparql:greater-than ( [ shnex:var "value" ] 5 ) ] ] ."""
    out = validate(
        graph("ex:a a ex:T ; ex:n 7 . ex:b a ex:T ; ex:n 3 ."), graph(shapes)
    )
    assert [(text(r.focus), lexical(r.value)) for r in out.results] == [(text(EX.b), "3")]
    assert all(isinstance(r.source_constraint, BNode) for r in out.results)


def test_sh_expression_failure_propagates():
    shapes = """ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:expression [ sparql:abs ( ( 1 2 ) ) ] ."""
    with pytest.raises(EvaluationFailure):
        validate(graph("ex:a ex:p 1 ."), graph(shapes))


def test_node_by_expression_computes_the_shape_per_value_node():
    shapes = """ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ;
        sh:nodeByExpression [ shnex:pathValues ex:shape ] ] .
        ex:Needs sh:property [ sh:path ex:name ; sh:minCount 1 ] ."""
    data = "ex:a ex:p ex:ok, ex:bad . ex:ok ex:shape ex:Needs ; ex:name 'x' . ex:bad ex:shape ex:Needs ."
    out = validate(graph(data), graph(shapes))
    assert [(text(r.value), text(r.source_constraint)) for r in out.results] == [
        (text(EX.bad), text(EX.Needs))
    ]


def test_values_and_default_values_use_the_evaluator_for_every_kind():
    shapes = """ex:S a sh:NodeShape ; sh:targetNode ex:a ;
        sh:property [ sh:path ex:p ; sh:values [ shnex:concat ( 1 2 ) ] ; sh:hasValue 2 ] ;
        sh:property [ sh:path ex:q ; sh:defaultValue [ sparql:str ( 9 ) ] ; sh:hasValue "9" ] ;
        sh:property [ sh:path ex:r ; sh:defaultValue 8 ; sh:hasValue 8 ] ."""
    assert validate(
        graph("ex:a ex:r 1 ."), graph(shapes)
    ).results  # r has a stored value, so no default: hasValue 8 fails
    assert len(validate(graph("ex:a ex:r 1 ."), graph(shapes)).results) == 1
    assert validate(graph("ex:a ex:other 1 ."), graph(shapes)).conforms


def test_failing_values_expression_gives_no_values():
    shapes = """ex:S a sh:NodeShape ; sh:targetNode ex:a ;
        sh:property [ sh:path ex:p ; sh:values [ sparql:abs ( ( 1 2 ) ) ] ; sh:minCount 1 ] ."""
    assert not validate(graph("ex:a ex:o 1 ."), graph(shapes)).conforms


def test_a_list_member_that_is_a_node_expression_is_not_a_constant():
    """Node Expressions 4.1.3: a list expression's members are constants. The workbench shows this error to the user."""
    from starlayer.shacl_engine.plan import ShapeError

    assert ev("( 1 2 )") == [integer(1), integer(2)]
    with pytest.raises(ShapeError, match="not a constant"):
        ev("( ex:a [ shnex:instancesOf ex:Person ] )")
