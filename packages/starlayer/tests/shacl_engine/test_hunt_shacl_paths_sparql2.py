"""Regression tests from the bug hunt (second batch): SHACL engine paths, targets, SPARQL constraints, rules, expressions."""

from __future__ import annotations

import warnings

import pyoxigraph as ox
import pytest
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.shacl_engine import validate
from starlayer.shacl_engine.executor import Context
from starlayer.shacl_engine.expressions import evaluate_expression
from starlayer.shacl_engine.plan import Plan
from starlayer.shacl_engine.subgraph import extract_subgraph
from starlayer.shacl_engine.terms import NS

warnings.simplefilter("ignore")


EX = NS("http://example.com/")


P = (
    "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.com/> . "
    "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "
    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> . @prefix sparql: <http://www.w3.org/ns/sparql#> . "
    "@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .\n"
)


def G(text: str) -> StarLayerGraph:
    return StarLayerGraph().parse(data=P + text, format="turtle")


def ev(expr_ttl, data="", focus=None, bindings=None):
    g = G("ex:root ex:expr " + expr_ttl + " . " + data)
    expr = next(g.objects(EX.root, EX.expr))
    return list(evaluate_expression(Context(data=g, plan=Plan(shapes_graph=g)), expr, focus, bindings))


def _fragment_conforms(shapes: str, data: str) -> None:
    s, d = G(shapes), G(data)
    assert validate(d, s).conforms, "premise: the data conforms"
    frag = extract_subgraph(d, s)
    assert validate(frag, s).conforms, "the fragment of conforming data must conform"


@pytest.mark.parametrize("deact", ["true", "[ shnex:exists ( 1 ) ]"])
def test_sparql_constraint_deactivated_node_expression(deact):
    s = G(
        f'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:deactivated {deact} ; sh:select "SELECT $this WHERE {{ $this ?p ?o }}" ] .'
    )
    assert validate(G("ex:a ex:p 1 ."), s).conforms


def test_implicit_class_target_through_subclass_of_shape_type():
    shapes = (
        "ex:K rdfs:subClassOf sh:NodeShape . ex:Person a rdfs:Class, ex:K ; sh:property [ sh:path ex:name ; sh:minCount 1 ] ."
    )
    assert not validate(G("ex:bob a ex:Person ."), G(shapes)).conforms


_NAMED_FN = """
ex:G a sh:NamedParameterExpressionFunction; rdfs:subClassOf sh:NamedParameterExpression; sh:parameter ex:Ga;
  sh:bodyExpression [ shnex:flatMap [ shnex:arg ex:a ]; shnex:nodes [ shnex:pathValues ex:items ] ] .
ex:Ga a sh:Parameter; sh:path ex:a; sh:keyParameter true .
ex:f ex:name "F"; ex:items ex:i1 . ex:i1 ex:name "I1" .
"""


_FN_PRE = 'ex: sh:declare [ sh:prefix "ex"; sh:namespace "http://example.com/" ] .\n'


def _sparql_expr_value(param: str):
    shapes = G(
        f"""
ex:f a sh:NamedParameterExpressionFunction ; sh:parameter [ sh:path ex:{param} ; sh:keyParameter true ] ;
  sh:bodyExpression [ sh:sparqlExpr "?{param} + 1" ] .
ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:out ; sh:values [ ex:{param} 41 ] ] ."""
    )
    from starlayer.shacl_engine import evaluate

    out = evaluate(G("ex:a ex:q 1 ."), shapes)
    return [t[2].value for t in out.triples((None, ox.NamedNode("http://example.com/out"), None))]
