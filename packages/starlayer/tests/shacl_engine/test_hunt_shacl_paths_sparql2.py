"""Regression tests from the bug hunt (second batch): SHACL engine paths, targets, SPARQL constraints, rules, expressions."""


from __future__ import annotations


import warnings


import pyoxigraph as ox


import pytest


from starlayer.graph.oxgraph import StarLayerGraph


from starlayer.shacl_engine import validate


from starlayer.shacl_engine.executor import Context


from starlayer.shacl_engine.expressions import EvaluationFailure, evaluate_expression


from starlayer.shacl_engine.plan import Plan, ShapeError


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
    s = G(f'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:deactivated {deact} ; sh:select "SELECT $this WHERE {{ $this ?p ?o }}" ] .')
    assert validate(G("ex:a ex:p 1 ."), s).conforms


def test_implicit_class_target_through_subclass_of_shape_type():
    shapes = "ex:K rdfs:subClassOf sh:NodeShape . ex:Person a rdfs:Class, ex:K ; sh:property [ sh:path ex:name ; sh:minCount 1 ] ."
    assert not validate(G("ex:bob a ex:Person ."), G(shapes)).conforms


@pytest.mark.parametrize("lex", ["²", "--1", "1²"])
@pytest.mark.parametrize("op", ["limit", "offset"])
def test_ill_formed_limit_offset_is_shape_error(lex, op):
    with pytest.raises(ShapeError):
        ev(f'[ shnex:{op} "{lex}"^^xsd:integer ; shnex:nodes ( 1 2 3 ) ]')


def test_inference_names_error_names_the_regimes():
    g = G("ex:a ex:p 1 .")
    with pytest.raises(ValueError, match="entailment regime"):
        validate(g, g, inference="rdfs")


def test_subgraph_reifier_shape_triples_kept():
    _fragment_conforms(
        "ex:S a sh:NodeShape; sh:targetNode ex:a; sh:property [sh:path ex:p; sh:reificationRequired true; sh:reifierShape [sh:property [sh:path ex:src; sh:minCount 1]]] .",
        "ex:a ex:p ex:b . _:r rdf:reifies <<( ex:a ex:p ex:b )>> ; ex:src ex:s1 .",
    )


def test_subgraph_subset_of_keeps_second_path():
    _fragment_conforms("ex:S a sh:NodeShape; sh:targetNode ex:a; sh:property [sh:path ex:p; sh:subsetOf ex:q] .", "ex:a ex:p 1 ; ex:q 1, 2 .")


def test_subgraph_some_value_keeps_evidence():
    _fragment_conforms(
        "ex:S a sh:NodeShape; sh:targetNode ex:a; sh:property [sh:path ex:p; sh:someValue [sh:property [sh:path ex:q; sh:minCount 1]]] .",
        "ex:a ex:p ex:b, ex:c . ex:b ex:q 1 . ex:c ex:r 2 .",
    )


@pytest.mark.parametrize(
    "constraint",
    ["sh:memberShape [sh:datatype xsd:integer]", "sh:minListLength 2", "sh:uniqueMembers true"],
)
def test_subgraph_list_constraints_keep_list_cells(constraint):
    _fragment_conforms(f"ex:S a sh:NodeShape; sh:targetNode ex:a; sh:property [sh:path ex:l; {constraint}] .", "ex:a ex:l (1 2 3) .")


_NAMED_FN = """
ex:G a sh:NamedParameterExpressionFunction; rdfs:subClassOf sh:NamedParameterExpression; sh:parameter ex:Ga;
  sh:bodyExpression [ shnex:flatMap [ shnex:arg ex:a ]; shnex:nodes [ shnex:pathValues ex:items ] ] .
ex:Ga a sh:Parameter; sh:path ex:a; sh:keyParameter true .
ex:f ex:name "F"; ex:items ex:i1 . ex:i1 ex:name "I1" .
"""


def test_min_max_keep_blank_nodes_like_sparql():
    out = ev("[ shnex:min [ shnex:pathValues ex:v ] ]", "ex:f ex:v [], 5 .", focus=EX.f)
    assert len(out) == 1 and isinstance(out[0], ox.BlankNode)
    out = ev("[ shnex:max [ shnex:pathValues ex:v ] ]", "ex:f ex:v [], 5 .", focus=EX.f)
    assert [o.value for o in out] == ["5"]


def test_sum_of_floats_is_a_float_lexical_form():
    out = ev('[ shnex:sum [ shnex:pathValues ex:v ] ]', 'ex:f ex:v "0.1"^^xsd:float, "0.2"^^xsd:float .', focus=EX.f)
    sparql = list(ox.Store().query('SELECT (SUM(?x) AS ?s) { VALUES ?x { "0.1"^^<http://www.w3.org/2001/XMLSchema#float> "0.2"^^<http://www.w3.org/2001/XMLSchema#float> } }'))[0]["s"]
    assert out[0] == sparql


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
