"""Evaluation failures, unbound values and scope in node expressions (GitHub issues #95 and #124).

SHACL 1.2 Node Expressions 3.2.2 / 5 / 6.2 / 4.5.1 / 4.5.3 and SHACL 1.2 Core 3.1.3.1 (node targets).
A failure is a ``ValueError`` (``EvaluationFailure``); ``sh:values`` and the other callers treat it as "no value".
"""

from __future__ import annotations

import pytest
from rdflib import Graph, Literal, Namespace

pyshacl = pytest.importorskip("pyshacl")

from pyshacl.shapes_graph import ShapesGraph  # noqa: E402
from starlayer.shacl import validate  # noqa: E402
from starlayer.shacl.node_expressions import eval_expr  # noqa: E402

EX = Namespace("http://example.org/")

PREFIXES = """
@prefix ex: <http://example.org/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
@prefix sparql: <http://www.w3.org/ns/sparql#> .
"""


def _run(expr_ttl: str, extra: str = "", data: str = "", focus=None, scope=None) -> list:
    shapes = Graph()
    shapes.parse(data=PREFIXES + f"ex:root ex:e {expr_ttl} .\n" + extra, format="turtle")
    expr = next(shapes.objects(EX.root, EX.e))
    sg = ShapesGraph(shapes)
    list(sg.shapes)
    data_graph = Graph()
    data_graph.parse(data=PREFIXES + data, format="turtle")
    if scope is None and focus is not None:
        scope = {"focusNode": focus}
    return eval_expr(expr, focus, data_graph, sg, scope=scope)


# --- #95: SPARQL function expressions: a multi-valued argument is a SPARQL error ---


def test_multi_valued_argument_is_a_failure():
    with pytest.raises(ValueError):
        _run("[ sparql:abs ( [ shnex:concat ( 1 5 ) ] ) ]")
    with pytest.raises(ValueError):
        _run("[ sparql:plus ( [ shnex:concat ( 1 5 ) ] 1 ) ]")
    with pytest.raises(ValueError):
        _run('[ sparql:strlen ( [ shnex:concat ( "a" "bbb" ) ] ) ]')


def test_coalesce_skips_a_multi_valued_argument():
    # the spec's own example: [ sparql:coalesce ( ( 1 2 ) "ok" ) ] produces ( "ok" )
    assert _run('[ sparql:coalesce ( [ shnex:concat ( 1 5 ) ] 9 ) ]') == [Literal(9)]


def test_failure_takes_precedence_over_unbound():
    with pytest.raises(ValueError):
        _run('[ sparql:plus ( [ shnex:var "u" ] [ shnex:instancesOf 42 ] ) ]')
    with pytest.raises(ValueError):
        _run('[ sparql:plus ( [ shnex:instancesOf 42 ] [ shnex:var "u" ] ) ]')


def test_bound_and_coalesce_of_failures():
    assert _run('[ sparql:bound ( [ shnex:var "u" ] ) ]') == [Literal(False)]
    with pytest.raises(ValueError):
        _run("[ sparql:bound ( [ shnex:concat ( 1 2 ) ] ) ]")
    # "as does sparql:coalesce when all of its arguments are unbound"
    with pytest.raises(ValueError):
        _run("[ sparql:coalesce () ]")


def test_ordinary_function_with_unbound_argument_is_empty():
    assert _run('[ sparql:plus ( [ shnex:var "u" ] 1 ) ]') == []


# --- #95: logical-or / logical-and handle unbound and error arguments (SPARQL 17.3.1) ---


def test_logical_or_with_unbound_or_error():
    assert _run('[ sparql:logical-or ( [ shnex:var "u" ] true ) ]') == [Literal(True)]
    assert _run('[ sparql:logical-or ( true [ shnex:var "u" ] ) ]') == [Literal(True)]
    assert _run('[ sparql:logical-or ( [ sparql:plus ( "a" 1 ) ] true ) ]') == [Literal(True)]
    assert _run("[ sparql:logical-or ( false false ) ]") == [Literal(False)]
    with pytest.raises(ValueError):
        _run('[ sparql:logical-or ( [ shnex:var "u" ] false ) ]')


def test_logical_and_with_unbound_or_error():
    assert _run('[ sparql:logical-and ( [ shnex:var "u" ] false ) ]') == [Literal(False)]
    assert _run('[ sparql:logical-and ( [ sparql:plus ( "a" 1 ) ] false ) ]') == [Literal(False)]
    assert _run("[ sparql:logical-and ( true true ) ]") == [Literal(True)]
    with pytest.raises(ValueError):
        _run('[ sparql:logical-and ( [ shnex:var "u" ] true ) ]')


# --- #95: instancesOf with a non-IRI class is a failure ---


def test_instances_of_non_iri_is_a_failure():
    with pytest.raises(ValueError):
        _run('[ shnex:instancesOf "x" ]')
    with pytest.raises(ValueError):
        _run("[ shnex:instancesOf 42 ]")
    assert _run("[ shnex:instancesOf ex:C ]", data="ex:a a ex:C .") == [EX.a]


# --- #95: arguments of custom function calls see the caller's scope ---

NAMED_FN = """
ex:Id a sh:NamedParameterExpressionFunction ;
  rdfs:subClassOf sh:NamedParameterExpression ;
  sh:bodyExpression [ shnex:arg ex:p ] ;
  sh:parameter [ sh:path ex:p ; sh:keyParameter true ] .
"""

LIST_FN = """
ex:add a sh:ListParameterExpressionFunction ;
  rdfs:subClassOf sh:ListParameterExpression ;
  sh:bodyExpression [ sparql:plus ( [ shnex:arg 0 ] [ shnex:arg 1 ] ) ] .
"""


def test_named_custom_call_argument_sees_caller_scope():
    out = _run('[ ex:p [ shnex:var "x" ] ]', NAMED_FN, scope={"focusNode": EX.f, "x": Literal(5)})
    assert out == [Literal(5)]


def test_list_custom_call_argument_sees_caller_scope():
    out = _run('[ ex:add ( [ shnex:var "x" ] 4 ) ]', LIST_FN, scope={"focusNode": EX.f, "x": Literal(38)})
    assert out == [Literal(42)]


def test_list_custom_call_empty_argument_gives_empty_and_multi_valued_fails():
    assert _run('[ ex:add ( [ shnex:var "unbound" ] 4 ) ]', LIST_FN) == []
    with pytest.raises(ValueError):
        _run("[ ex:add ( [ shnex:concat ( 1 2 ) ] 4 ) ]", LIST_FN)


# --- #95: conformsToShape evaluates its shape argument as a node expression ---


def test_conforms_to_shape_shape_argument_is_an_expression():
    shape = "ex:S a sh:NodeShape ; sh:property [ sh:path ex:q ; sh:minCount 1 ] ."
    data = "ex:a ex:q 1 . ex:b ex:r 1 ."
    # shape given through a var (an expression), not as a literal blank node/IRI
    out = _run(
        '[ shnex:conformsToShape ( ex:a [ shnex:var "s" ] ) ]', shape, data, scope={"s": EX.S}
    )
    assert out == [Literal(True)]
    out = _run('[ shnex:conformsToShape ( ex:b [ shnex:var "s" ] ) ]', shape, data, scope={"s": EX.S})
    assert out == [Literal(False)]
    # an unbound shape gives no output
    assert _run('[ shnex:conformsToShape ( ex:b [ shnex:var "s" ] ) ]', shape, data) == []
    # a multi-valued node argument is a failure
    with pytest.raises(ValueError):
        _run("[ shnex:conformsToShape ( [ shnex:concat ( ex:a ex:b ) ] ex:S ) ]", shape, data)


# --- #124: unbound variable gives no nodes; sh:targetNode expression has the shape as focus node ---


def test_unbound_focus_node_var_gives_no_nodes():
    assert _run('[ shnex:var "focusNode" ]') == []
    assert _run('[ shnex:var "focusNode" ]', focus=EX.f) == [EX.f]


def test_target_node_expression_focus_is_the_shape():
    data = "ex:S ex:t ex:n1 , ex:n2 . ex:n1 ex:v 1 . ex:n2 ex:v 'x' ."
    shapes = """
    ex:S a sh:NodeShape ;
      sh:targetNode [ shnex:pathValues ex:t ] ;
      sh:property [ sh:path ex:v ; sh:datatype xsd:integer ] .
    """
    result = validate(
        _parsed(data),
        shacl_graph=_parsed(shapes),
    )
    # ex:n1, ex:n2 are targeted (values of ex:t at the shape ex:S); ex:n2 violates the datatype
    assert not result.conforms
    assert [str(f) for f in _focus_nodes(result)] == [str(EX.n2)]

    own = "ex:S a sh:NodeShape ; sh:targetNode [ shnex:var \"focusNode\" ] ; sh:property [ sh:path ex:t ; sh:maxCount 1 ] ."
    result = validate(_parsed(data), shacl_graph=_parsed(own))
    assert not result.conforms  # the shape ex:S itself is the target and has two ex:t values


def _parsed(ttl: str) -> Graph:
    g = Graph()
    g.parse(data=PREFIXES + ttl, format="turtle")
    return g


def _focus_nodes(result):
    g = result.report_graph
    SH = Namespace("http://www.w3.org/ns/shacl#")
    return sorted(g.objects(None, SH.focusNode))


class TestListParameterFunctionWithSparqlBody:
    """GitHub issues #175 and #176: a body written in SPARQL reads its arguments as ``$arg0``, ``$arg1`` (SPARQL Extensions 6.1, 7.2), and
    the function can be called by its IRI from SPARQL text (7.3)."""

    SHAPES = """
        @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.org/> .
        ex:spaced a sh:ListParameterExpressionFunction ; sh:bodyExpression [ sh:sparqlExpr "CONCAT($arg0, ' ', $arg1)" ] .
        ex:viaSelect a sh:ListParameterExpressionFunction ;
          sh:bodyExpression [ sh:select "SELECT ?v WHERE { BIND (CONCAT($arg0, '-', $arg1) AS ?v) }" ] .
        ex:call1 ex:p [ ex:spaced ( "John" "Doe" ) ] .
        ex:call2 ex:p [ ex:viaSelect ( "John" "Doe" ) ] .
    """

    @staticmethod
    def _value(shapes, call):
        from pyshacl.shapes_graph import ShapesGraph
        from rdflib import Namespace
        from starlayer.graph.graph.starlayer_graph import StarLayerGraph
        from starlayer.shacl.node_expressions import eval_expr

        ex = Namespace("http://example.org/")
        expr = next(iter(shapes.objects(ex[call], ex.p)))
        return [str(n) for n in eval_expr(expr, None, StarLayerGraph(), ShapesGraph(shapes))]

    def _shapes(self):
        from starlayer.graph.graph.starlayer_graph import StarLayerGraph

        shapes = StarLayerGraph()
        shapes.parse(data=self.SHAPES, format="turtle12")
        return shapes

    def test_a_sparql_expression_body_reads_its_arguments_as_variables(self) -> None:
        assert self._value(self._shapes(), "call1") == ["John Doe"]

    def test_a_select_body_reads_its_arguments_as_variables(self) -> None:
        assert self._value(self._shapes(), "call2") == ["John-Doe"]

    def test_the_function_can_be_called_by_its_iri_from_a_constraint_query(self) -> None:
        from starlayer.graph.graph.starlayer_graph import StarLayerGraph
        from starlayer.shacl import validate

        shapes = StarLayerGraph()
        shapes.parse(
            data=self.SHAPES
            + """
            ex:S a sh:NodeShape ; sh:targetNode ex:n ;
              sh:sparql [ sh:select "SELECT $this ?value WHERE { FILTER (ex:spaced('John', 'Doe') = 'John Doe') }" ;
                          sh:prefixes ex:P ; sh:message "called" ] .
            ex:P sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.org/"^^<http://www.w3.org/2001/XMLSchema#anyURI> ] .
            """,
            format="turtle12",
        )
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:n ex:q 1 .", format="turtle12")

        assert validate(data, shapes).conforms is False
