"""Regression tests for the gaps the differential run (docs/working/shacl-engine-differential.md) found in the native
engine: report graph type, boolean parameters, custom node-expression functions, sh:deactivated expressions, sparql:tz,
prefix resolution."""

from __future__ import annotations

import pytest
from rdflib.namespace import Namespace
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.graph.model.triple import TripleTerm
from starlayer.shacl_engine import validate
from starlayer.shacl_engine.plan import ShapeError

EX = Namespace("http://example.com/")
SH = Namespace("http://www.w3.org/ns/shacl#")
PREFIXES = """
@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.com/> . @prefix sparql: <http://www.w3.org/ns/sparql#> .
@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
"""


def run(shapes: str, data: str = ""):
    s, d = StarLayerGraph(), StarLayerGraph()
    s.parse(data=PREFIXES + shapes, format="turtle12")  # keeps "1"^^xsd:boolean lexical
    d.parse(data=PREFIXES + data, format="turtle")
    return validate(d, s)


def test_report_holds_a_triple_term_value():
    s, d = StarLayerGraph(), StarLayerGraph()
    s.parse(data=PREFIXES + "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:nodeKind sh:IRI ] .", format="turtle")
    d.add((EX.a, EX.p, TripleTerm(EX.x, EX.y, EX.z)))
    out = validate(d, s)
    assert not out.conforms
    values = list(out.report_graph.objects(None, SH.value))
    assert values == [TripleTerm(EX.x, EX.y, EX.z)]
    assert isinstance(out.report_graph, StarLayerGraph)


@pytest.mark.parametrize(
    ("predicate", "data"),
    [
        ("sh:uniqueMembers", "ex:a ex:p ( 1 1 ) ."),
        ("sh:singleLine", 'ex:a ex:p """a\nb""" .'),
    ],
)
def test_boolean_parameter_is_active_only_for_exact_true(predicate, data):
    def shapes(v):
        return f"ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; {predicate} {v} ] ."

    assert not run(shapes('"true"^^xsd:boolean'), data).conforms
    assert run(shapes('"1"^^xsd:boolean'), data).conforms
    with pytest.raises(ShapeError):
        run(shapes('"yes"'), data)


def test_reification_required_is_active_only_for_exact_true():
    def shapes(v):
        return f"ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:reificationRequired {v} ] ."

    assert not run(shapes('"true"^^xsd:boolean'), "ex:a ex:p 1 .").conforms
    assert run(shapes('"1"^^xsd:boolean'), "ex:a ex:p 1 .").conforms


LIST_FN = """
ex:spacedConcat a sh:ListParameterExpressionFunction ;
  sh:bodyExpression [ sparql:concat ( [ shnex:arg 0 ] " " [ shnex:arg 1 ] ) ] ;
  sh:parameter [ a sh:Parameter ; sh:path shnex:arg0 ] ; sh:parameter [ a sh:Parameter ; sh:path shnex:arg1 ] .
"""
NAMED_FN = """
ex:AverageExpression a sh:NamedParameterExpressionFunction ; sh:parameter ex:AverageExpression-average ;
  sh:bodyExpression [ sparql:divide ( [ shnex:sum [ shnex:arg ex:average ] ] [ shnex:count [ shnex:arg ex:average ] ] ) ] .
ex:AverageExpression-average a sh:Parameter ; sh:path ex:average ; sh:keyParameter true .
"""


def test_list_parameter_function():
    ok = 'sparql:equals ( [ ex:spacedConcat ( "hello" "world" ) ] "hello world" )'
    bad = 'sparql:equals ( [ ex:spacedConcat ( "hello" "world" ) ] "nope" )'
    for expr, conforms in ((ok, True), (bad, False)):
        out = run(LIST_FN + f"ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:expression [ {expr} ] .")
        assert out.conforms is conforms


def test_named_parameter_function():
    data = "ex:a ex:e ex:b, ex:c . ex:b ex:i 10 . ex:c ex:i 20 ."
    shapes = NAMED_FN + "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:expression [ sparql:equals ( [ ex:average [ shnex:pathValues ( ex:e ex:i ) ] ] %s ) ] ."
    assert run(shapes % "15", data).conforms
    assert not run(shapes % "16", data).conforms


def test_deactivated_node_expression_is_evaluated_per_focus_node():
    shapes = """
    ex:S a sh:NodeShape ; sh:targetClass ex:P ; sh:deactivated [ shnex:exists [ shnex:filterShape ex:Legacy ; shnex:nodes [ shnex:var "focusNode" ] ] ] ;
      sh:property [ sh:path ex:age ; sh:minInclusive 18 ] .
    ex:Legacy a sh:NodeShape ; sh:property [ sh:path ex:legacy ; sh:hasValue true ] .
    """
    out = run(shapes, "ex:alice a ex:P ; ex:age 12 ; ex:legacy true . ex:dave a ex:P ; ex:age 12 ; ex:legacy false .")
    assert {r.focus for r in out.results} == {EX.dave}


def test_deactivated_literal_only_true_deactivates():
    shapes = 'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:deactivated %s ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .'
    assert run(shapes % '"true"^^xsd:boolean').conforms
    assert not run(shapes % '"1"^^xsd:boolean').conforms
    assert not run(shapes % "false").conforms


@pytest.mark.parametrize(
    ("lexical", "expected"),
    [("2024-01-15T10:20:30Z", "Z"), ("2024-01-15T10:20:30+00:00", "Z"), ("2024-01-15T10:20:30-05:00", "-05:00"), ("2024-01-15T10:20:30", "")],
)
def test_sparql_tz(lexical, expected):
    shapes = f'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:expression [ sparql:equals ( [ sparql:tz ( "{lexical}"^^xsd:dateTime ) ] "{expected}" ) ] .'
    assert run(shapes).conforms
    assert not run(shapes.replace(f'"{expected}" )', '"nope" )')).conforms


def test_prefixes_shapes_graph_declare_beats_ontology_distractor():
    shapes = """
    ex:Distractor a owl:Ontology ; sh:declare [ sh:prefix "t" ; sh:namespace "http://wrong.example/"^^xsd:anyURI ] .
    ex:G a sh:ShapesGraph ; sh:declare [ sh:prefix "t" ; sh:namespace "http://right.example/"^^xsd:anyURI ] .
    ex:S a sh:NodeShape ; sh:targetNode ex:a ;
      sh:sparql [ sh:select "SELECT $this ?value WHERE { $this <http://example.com/p> ?value . FILTER (?value = t:Bad) }" ] .
    """
    out = run(shapes, "ex:a ex:p <http://right.example/Bad> .")
    assert [r.focus for r in out.results] == [EX.a]


def test_a_node_shape_with_sh_path_is_an_ill_formed_shapes_graph():
    """Found by running the graph workbench on the engine: it refuses an edit that makes a property shape also a sh:NodeShape (Core 3.2)."""
    with pytest.raises(ShapeError, match="NodeShape cannot be the subject of sh:path"):
        run("ex:S a sh:NodeShape ; sh:path ex:p ; sh:minCount 1 ; sh:targetNode ex:a .", "ex:a ex:p 1 .")


def test_result_messages_use_prefixed_names_and_the_generic_wording():
    """Found by running the graph workbench on the engine: the report graph says what the old validator said."""
    result = run(
        "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:minCount 1 ; sh:datatype xsd:integer ] .",
        'ex:a ex:q 1 . ex:b ex:p "x" .',
    )
    messages = {str(m) for m in result.report_graph.objects(None, SH.resultMessage)}
    assert any(m.startswith("Less than 1 values on") for m in messages), messages
