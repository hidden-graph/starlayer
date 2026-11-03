"""Unit tests for SPARQL-related features of the native SHACL engine (sparql_support, sparql_constraints,
sparql_components), run through StarLayer's own query layer."""

from __future__ import annotations

import pytest
import pyoxigraph as ox
from rdflib import Graph
from starlayer.shacl_engine.terms import NS as Namespace
from starlayer.graph.oxgraph import OxGraph
from starlayer.shacl_engine import validate
from starlayer.shacl_engine.interface import Solutions
from starlayer.shacl_engine.plan import Path, ShapeError
from starlayer.shacl_engine.sparql_support import fill_template, path_to_sparql
from starlayer.shacl_engine.terms import integer, text

EX = Namespace("http://example.com/")
SH = Namespace("http://www.w3.org/ns/shacl#")
PREFIXES = """
@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.com/> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex: a owl:Ontology ; sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.com/"^^xsd:anyURI ] .
"""


def run(shapes: str, data: str = "", graph_cls=OxGraph):
    s = graph_cls()
    s.parse(data=PREFIXES + shapes, format="turtle")
    d = graph_cls()
    d.parse(data=PREFIXES + data, format="turtle")
    return validate(d, s)


def pairs(outcome):
    return sorted((text(r.focus), None if not r.has_value else text(r.value)) for r in outcome.results)


def test_sparql_constraint_maps_variables_and_message_template():
    out = run(
        """ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [
             sh:message "bad {?value} on {$this}" ; sh:select "SELECT $this ?value WHERE { $this ex:p ?value }" ] .""",
        "ex:a ex:p 1, 2 .",
    )
    assert pairs(out) == [(text(EX.a), "1"), (text(EX.a), "2")]
    assert {text(m) for r in out.results for m in r.messages} == {
        f"bad 1 on {text(EX.a)}",
        f"bad 2 on {text(EX.a)}",
    }
    assert all(r.source_constraint is not None for r in out.results)


def test_message_binding_and_constraint_severity_override():
    out = run(
        """ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:severity sh:Info ; sh:message "no"
             ; sh:select "SELECT $this ('yes' AS ?message) WHERE { }" ] .""",
    )
    assert [text(m) for m in out.results[0].messages] == ["yes"]
    assert out.results[0].severity == SH.Info


def test_deactivated_sparql_constraint():
    out = run(
        """ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:deactivated true ; sh:select "SELECT $this WHERE {}" ] .""",
    )
    assert out.conforms


def test_property_shape_path_substitution_with_sequence_path():
    shapes = """ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ( ex:p ex:q ) ; sh:sparql [
        sh:select "SELECT $this ?value WHERE { $this $PATH ?value FILTER(?value > 5) }" ] ] ."""
    out = run(shapes, "ex:a ex:p [ ex:q 3, 9 ] .")
    assert [text(r.value) for r in out.results] == ["9"]
    assert out.results[0].path.kind == "seq"


@pytest.mark.parametrize(
    "select",
    [
        "SELECT $this WHERE { $this ?p ?o MINUS { $this ex:p ?o } }",
        "SELECT $this WHERE { VALUES $this { 1 } }",  # VALUES over a pre-bound variable (a VALUES over others is allowed)
        "SELECT $this WHERE { SERVICE <http://example.org/> { ?s ?p ?o } }",
        "SELECT $this WHERE { BIND (1 AS $this) }",
        "SELECT ?x WHERE { ?x ?p ?o }",  # does not project ?this
        "SELECT $this WHERE { this is not sparql",
        "ASK { }",
    ],
)
def test_forbidden_or_malformed_queries_fail(select):
    with pytest.raises(ShapeError):
        run(f'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:select """{select}""" ] .')


def test_failure_variable_fails_validation():
    with pytest.raises(ShapeError):
        run('ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:select "SELECT $this (true AS ?failure) WHERE {}" ] .')


def test_prefix_conflict_is_an_error():
    shapes = """ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:select "SELECT $this WHERE {}" ; sh:prefixes ex:P ] .
      ex:P sh:declare [ sh:prefix "x" ; sh:namespace "http://a/" ], [ sh:prefix "x" ; sh:namespace "http://b/" ] ."""
    with pytest.raises(ShapeError):
        run(shapes)


def test_prefixes_follow_owl_imports():
    shapes = """ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:prefixes ex:P ;
        sh:select "SELECT $this WHERE { $this a z:T }" ] .
      ex:P owl:imports ex:Q . ex:Q sh:declare [ sh:prefix "z" ; sh:namespace "http://z/" ] ."""
    assert not run(shapes, "ex:a a <http://z/T> .").conforms


COMPONENT = """
ex:C a sh:ConstraintComponent ;
  sh:parameter [ sh:path ex:min ] ;
  sh:parameter [ sh:path ex:opt ; sh:optional true ] ;
  sh:%s [ a sh:%s ; sh:%s \"\"\"%s\"\"\" ] .
"""


def comp(kind_cls, pred, query, validator="validator"):
    return COMPONENT % (validator, kind_cls, pred, query)


def test_ask_validator_with_optional_parameter_and_component_requirement():
    shapes = comp("SPARQLAskValidator", "ask", "ASK { FILTER ($value >= $min && $value != COALESCE(?opt, -1)) }") + """
      ex:S1 a sh:NodeShape ; sh:targetNode 1, 5, 7 ; ex:min 5 ; ex:opt 7 .
      ex:S2 a sh:NodeShape ; sh:targetNode 1 ; ex:opt 7 ."""  # S2 lacks the required parameter: ignored
    out = run(shapes)
    assert sorted(text(r.value) for r in out.results) == ["1", "7"]
    assert {r.shape for r in out.results} == {EX.S1}
    assert all(r.component == EX.C for r in out.results)


def test_select_node_validator_and_validator_choice():
    shapes = comp("SPARQLSelectValidator", "select", "SELECT $this WHERE { FILTER ($this != $min) }", "nodeValidator") + """
      ex:S a sh:NodeShape ; sh:targetNode 1, 2 ; ex:min 1 .
      ex:P a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; ex:min 1 ] ."""
    out = run(shapes, "ex:a ex:p 3 .")
    # node shape S: nodeValidator runs, focus 2 differs; property shape in P has no propertyValidator/validator: ignored
    assert [text(r.focus) for r in out.results] == ["2"]


def test_sparql_expr_values_extend_the_value_nodes():
    shapes = """ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:len ;
        sh:values [ sh:prefixes ex: ; sh:sparqlExpr "STRLEN(STR($this))" ] ; sh:hasValue 20 ] ."""
    assert run(shapes).conforms
    assert not run(shapes.replace("20", "21")).conforms


def test_select_expression_target():
    shapes = """ex:S a sh:NodeShape ; sh:targetNode [ sh:select "SELECT ?s WHERE { ?s ex:p 1 }" ; sh:prefixes ex: ] ;
        sh:property [ sh:path ex:q ; sh:minCount 1 ] ."""
    out = run(shapes, "ex:a ex:p 1 . ex:b ex:p 2 . ex:b ex:q 1 .")
    assert [text(r.focus) for r in out.results] == [text(EX.a)]


def test_plain_rdflib_data_graph_works():
    shapes = 'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:select "SELECT $this WHERE { $this ex:p 1 }" ] .'
    assert not run(shapes, "ex:a ex:p 1 .", graph_cls=Graph).conforms


def test_data_graph_native_sparql_query_takes_precedence():
    class Native(OxGraph):
        calls = 0

        def sparql_query(self, text, init_bindings=None, custom_functions=None):
            type(self).calls += 1
            return super().sparql_query(text, init_bindings, custom_functions)

    d = Native()
    d.parse(data=PREFIXES + "ex:a ex:p 1 .", format="turtle")
    s = Graph().parse(
        data=PREFIXES + 'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:select "SELECT $this WHERE {}" ] .',
        format="turtle",
    )
    assert not validate(d, s).conforms
    assert Native.calls == 1


def test_oxgraph_sparql_query_solutions():
    g = OxGraph()
    g.parse(data=PREFIXES + "ex:a ex:p 1 .", format="turtle")
    sel = g.sparql_query("SELECT $this ?o WHERE { $this <http://example.com/p> ?o }", {"this": EX.a})
    assert sel == Solutions(variables=("this", "o"), rows=({"this": EX.a, "o": integer(1)},))  # engine terms in and out
    ask = g.sparql_query("ASK { $this <http://example.com/p> 1 }", {"this": EX.a})
    assert ask.boolean is True


def test_path_to_sparql_and_fill_template():
    p = Path(kind="pred", iri=EX.p)
    q = Path(kind="inverse", args=(p,))
    assert path_to_sparql(Path(kind="seq", args=(p, q))) == f"(<{EX.p.value}>/^(<{EX.p.value}>))"
    assert path_to_sparql(Path(kind="zero_or_more", args=(p,))) == f"(<{EX.p.value}>)*"
    t = fill_template(ox.Literal("a {?x} {$y} {?z}", language="en"), {"x": ox.Literal("1"), "y": EX.b})
    assert t.value == f"a 1 {EX.b.value} {{?z}}" and t.language == "en"
