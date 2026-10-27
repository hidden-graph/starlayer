"""``eval_expr`` evaluates ``sh:select`` and ``sh:sparqlExpr`` node expressions (GitHub issue #129).

The vocabulary defines ``sh:SelectExpression`` and ``sh:SPARQLExprExpression``. They used to fall through to pySHACL,
which raised a bare ``StopIteration``; they now evaluate wherever a node expression can appear, including as the
argument of another expression.
"""

from __future__ import annotations

import pytest
from rdflib import Graph, Literal, Namespace

pyshacl = pytest.importorskip("pyshacl")

from pyshacl.shapes_graph import ShapesGraph  # noqa: E402
from starlayer.shacl.node_expressions import eval_expr  # noqa: E402

EX = Namespace("http://example.org/")

PREFIXES = """
@prefix ex: <http://example.org/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
"""

DATA = PREFIXES + """
ex:alice a ex:Person ; ex:age 30 .
ex:bob a ex:Person ; ex:age 40 .
ex:acme a ex:Org .
"""


def _run(expr_ttl: str, extra: str = "", focus=None) -> list:
    shapes = Graph()
    shapes.parse(data=PREFIXES + f"ex:root ex:e {expr_ttl} .\n" + extra, format="turtle")
    expr = next(shapes.objects(EX.root, EX.e))
    sg = ShapesGraph(shapes)
    list(sg.shapes)
    data = Graph()
    data.parse(data=DATA, format="turtle")
    return eval_expr(expr, focus, data, sg)


def test_select_expression_lists_the_first_column():
    out = _run('[ sh:select "SELECT ?this WHERE { ?this a <http://example.org/Person> } ORDER BY ?this" ]')
    assert out == [EX.alice, EX.bob]


def test_sparql_expr_expression_evaluates_the_expression():
    assert _run('[ sh:sparqlExpr "1 + 2" ]') == [Literal(3)]


def test_this_is_bound_to_the_focus_node():
    out = _run('[ sh:select "SELECT ?age WHERE { $this <http://example.org/age> ?age }" ]', focus=EX.bob)
    assert out == [Literal(40)]


def test_without_a_focus_node_this_is_unbound():
    out = _run('[ sh:select "SELECT ?this WHERE { ?this <http://example.org/age> ?a } ORDER BY ?this" ]')
    assert out == [EX.alice, EX.bob]


def test_prefixes_are_honoured():
    extra = """
    ex:pfx sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.org/"^^xsd:anyURI ] .
    """
    out = _run('[ sh:select "SELECT ?this WHERE { ?this a ex:Org }" ; sh:prefixes ex:pfx ]', extra=extra)
    assert out == [EX.acme]


def test_works_as_the_argument_of_another_expression():
    out = _run('[ shnex:count [ sh:select "SELECT ?this WHERE { ?this a <http://example.org/Person> }" ] ]')
    assert out == [Literal(2)]


def test_a_broken_query_raises_a_named_error_not_stopiteration():
    with pytest.raises(ValueError, match="sh:select"):
        _run('[ sh:select "SELECT ?this WHERE { ?this a" ]')


def test_both_predicates_on_one_node_is_rejected():
    with pytest.raises(ValueError, match="may be only one"):
        _run('[ sh:select "SELECT ?x WHERE {}" ; sh:sparqlExpr "1" ]')


# --- GitHub issue #123: a bare list expression holds constants only ---
# SHACL 1.2 Node Expressions: rdf:first of a list expression is a constant (a literal, an IRI or a triple term).
# A member that is an expression, or a nested list, is an error; shnex:concat combines expressions.


def test_list_of_constants():
    assert _run("( 1 2 3 )") == [Literal(1), Literal(2), Literal(3)]
    assert _run("( ex:a ex:b )") == [EX.a, EX.b]


def test_list_member_that_is_an_expression_is_an_error():
    with pytest.raises(ValueError, match="not a constant"):
        _run('( [ sh:select "SELECT ?this WHERE { ?this a <http://example.org/Org> }" ] 7 )')


def test_nested_list_is_an_error():
    with pytest.raises(ValueError, match="not a constant"):
        _run("( ( 1 2 ) 3 )")


def test_concat_is_the_way_to_combine_expressions():
    out = _run('[ shnex:concat ( [ sh:sparqlExpr "1 + 1" ] 5 ) ]')
    assert out == [Literal(2), Literal(5)]
