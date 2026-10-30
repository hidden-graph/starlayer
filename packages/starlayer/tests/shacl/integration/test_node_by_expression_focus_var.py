"""shnex:var "focusNode" inside sh:nodeByExpression is the value node (GitHub issue #95): evalExpr($expr, data graph, v, {}) binds it."""

from rdflib import Graph
from starlayer.shacl import validate

P = (
    "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://ex/> . "
    "@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . "
)
DATA = "ex:f ex:p ex:o . ex:o ex:shape ex:Sh1 ."
SH1 = "ex:Sh1 a sh:NodeShape ; sh:nodeKind sh:Literal ."


def _conforms(expr: str) -> bool:
    shapes = Graph().parse(data=P + f"ex:S a sh:NodeShape ; sh:targetNode ex:f ; sh:property [ sh:path ex:p ; sh:nodeByExpression {expr} ] . " + SH1, format="turtle")
    return validate(Graph().parse(data=P + DATA, format="turtle"), shapes, meta_shacl=False).conforms


def test_the_value_node_is_the_focus_node_of_the_expression() -> None:
    assert not _conforms("[ shnex:pathValues ex:shape ]")


def test_a_focus_node_variable_in_the_expression_is_the_value_node() -> None:
    assert not _conforms('[ shnex:pathValues ex:shape ; shnex:focusNode [ shnex:var "focusNode" ] ]')
