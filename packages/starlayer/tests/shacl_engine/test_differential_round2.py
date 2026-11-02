"""Regression tests for the second differential run (docs/working/differential/results2.jsonl): target node expressions,
list parameter functions called from SPARQL, SPARQL-based custom components, conformsToShape arity, the harness snapshot."""

from __future__ import annotations

import pytest
from rdflib.namespace import Namespace
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl_engine import validate
from starlayer.shacl_engine.expressions import EvaluationFailure

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")
PREFIXES = """
@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.org/> .
@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""


def run(shapes: str, data: str = "", **kw):
    s, d = StarLayerGraph(), StarLayerGraph()
    s.parse(data=PREFIXES + shapes, format="turtle12")
    d.parse(data=PREFIXES + data, format="turtle")
    return validate(d, s, **kw)


def focus_nodes(result):
    return sorted(str(f) for f in result.report_graph.objects(None, SH.focusNode))


def test_target_node_expression_is_evaluated_with_the_shape_as_focus_node():
    # Core 3.1.3.1: "the output nodes of evalExpr(expr, data graph, s, {}) are targets", s being the shape.
    data = "ex:S ex:t ex:n1, ex:n2 . ex:n1 ex:v 1 . ex:n2 ex:v 'x' ."
    out = run(
        "ex:S a sh:NodeShape ; sh:targetNode [ shnex:pathValues ex:t ] ; sh:property [ sh:path ex:v ; sh:datatype xsd:integer ] .",
        data,
    )
    assert not out.conforms
    assert focus_nodes(out) == [str(EX.n2)]
    own = run('ex:S a sh:NodeShape ; sh:targetNode [ shnex:var "focusNode" ] ; sh:property [ sh:path ex:t ; sh:maxCount 1 ] .', data)
    assert not own.conforms
    assert focus_nodes(own) == [str(EX.S)]


def test_list_parameter_function_is_callable_by_iri_from_a_constraint_query():
    # SPARQL Extensions 7.3: an engine SHOULD register the function; the body must output exactly one node.
    shapes = """
    ex:spaced a sh:ListParameterExpressionFunction ; sh:bodyExpression [ sh:sparqlExpr "CONCAT($arg0, ' ', $arg1)" ] .
    ex:S a sh:NodeShape ; sh:targetNode ex:n ;
      sh:sparql [ sh:select "SELECT $this ?value WHERE { FILTER (ex:spaced('John', 'Doe') = 'John Doe') }" ;
                  sh:prefixes ex:P ; sh:message "called" ] .
    ex:P sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.org/"^^xsd:anyURI ] .
    """
    assert not run(shapes, "ex:n ex:q 1 .").conforms
    # and the registration does not leak into a later run
    from rdflib.plugins.sparql.operators import _CUSTOM_FUNCTIONS

    assert EX.spaced not in _CUSTOM_FUNCTIONS


ASK_COMPONENT = """
ex:MinScore a sh:ConstraintComponent ; sh:parameter [ sh:path ex:minScore ] ;
  sh:validator [ a sh:SPARQLAskValidator ; sh:ask "ASK { FILTER (?value >= ?minScore) }" ] .
ex:SelectScore a sh:ConstraintComponent ; sh:parameter [ sh:path ex:selMin ] ;
  sh:propertyValidator [ a sh:SPARQLSelectValidator ; sh:select "SELECT $this ?value WHERE { FILTER (?value < ?selMin) }" ] .
"""
SCORES = "ex:alice ex:score 80 . ex:bob ex:score 20 ."


def test_ask_validator_reports_the_value_node_as_sh_value():
    # SPARQL Extensions: ASK validators are given $value pre-bound, so sh:value is the value node.
    out = run(ASK_COMPONENT + "ex:Sh a sh:NodeShape ; sh:targetSubjectsOf ex:score ; sh:property [ sh:path ex:score ; ex:minScore 50 ] .", SCORES)
    assert not out.conforms
    assert focus_nodes(out) == [str(EX.bob)]
    assert [str(v) for v in out.report_graph.objects(None, SH.value)] == ["20"]


def test_select_validator_does_not_pre_bind_value():
    # SELECT validators pre-bind $this and the parameters only; ?value is unbound unless the query binds it, so a query
    # that merely FILTERs on ?value yields no solutions (the old validator pre-binds it, which the draft does not say).
    out = run(ASK_COMPONENT + "ex:Sh a sh:NodeShape ; sh:targetSubjectsOf ex:score ; sh:property [ sh:path ex:score ; ex:selMin 50 ] .", SCORES)
    assert out.conforms
    bound = ASK_COMPONENT.replace("WHERE { FILTER (?value < ?selMin) }", "WHERE { $this <http://example.org/score> ?value . FILTER (?value < ?selMin) }")
    out = run(bound + "ex:Sh a sh:NodeShape ; sh:targetSubjectsOf ex:score ; sh:property [ sh:path ex:score ; ex:selMin 50 ] .", SCORES)
    assert not out.conforms


def test_conformstoshape_with_several_output_nodes_is_an_evaluation_failure_and_a_validation_failure():
    # Node Expressions 4.5.3: the arguments "must produce at most one output node each"; 7.1: "A failure MUST be produced
    # if the evaluation of $expr produces an evaluation failure."
    shapes = """
    ex:P a sh:NodeShape ; sh:property [ sh:path ex:name ; sh:minCount 1 ] .
    ex:S a sh:NodeShape ; sh:targetNode ex:n ;
      sh:expression [ shnex:conformsToShape ( [ shnex:concat ( ex:a ex:b ) ] ex:P ) ] .
    """
    with pytest.raises(EvaluationFailure):
        run(shapes, "ex:n ex:q 1 .")


def test_rules_in_a_shapes_graph_do_not_change_a_blank_focus_node_description_unless_requested():
    # The old validator applies sh:rule before validating, so its report's blank-node focus node carries the inferred
    # triples; the engine runs rules only on request (rules=True) or when sh:entailment is declared.
    shapes = """
    ex:S a sh:NodeShape ; sh:targetClass ex:P ; sh:property [ sh:path ex:name ; sh:minCount 1 ] ;
      sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:seen ; sh:object ex:yes ] .
    """
    out = run(shapes, "[] a ex:P .")
    assert not out.conforms
    assert not list(out.report_graph.triples((None, EX.seen, None)))


@pytest.mark.parametrize("form", ["1", "true"])
def test_boolean_parameter_lexical_form_decides_activity(form):
    shapes = f'ex:S a sh:NodeShape ; sh:targetNode ex:t ; sh:property [ sh:path ex:title ; sh:singleLine "{form}"^^xsd:boolean ] .'
    s, d = StarLayerGraph(), StarLayerGraph()
    s.parse(data=PREFIXES + shapes, format="turtle12")
    d.parse(data=PREFIXES + 'ex:t ex:title """a\nb""" .', format="turtle")
    assert validate(d, s).conforms is (form == "1")
