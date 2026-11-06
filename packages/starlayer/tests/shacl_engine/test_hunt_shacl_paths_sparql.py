"""Regression tests from the bug hunt: SHACL engine paths, targets, SPARQL constraints, rules, expressions, subgraphs."""

from __future__ import annotations

import warnings

import pytest
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.shacl_engine import validate
from starlayer.shacl_engine.subgraph import extract_subgraph

warnings.simplefilter("ignore")

P = (
    "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.org/> . "
    "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
)


def G(text: str) -> StarLayerGraph:
    return StarLayerGraph().parse(data=P + text, format="turtle")


def _fragment_conforms(shapes: str, data: str) -> None:
    s, d = G(shapes), G(data)
    assert validate(d, s).conforms, "premise: the data conforms"
    frag = extract_subgraph(d, s)
    assert validate(frag, s).conforms, "the fragment of conforming data must conform"


@pytest.mark.parametrize("literal", ["1", '"1"', '"TRUE"'])
def test_failure_binding_only_boolean_true_aborts(literal):
    template = 'ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:sparql [ sh:select "SELECT $this ?failure WHERE { $this <http://example.org/p> ?o BIND(LIT AS ?failure) }" ] .'
    shapes = G(template.replace("LIT", literal.replace('"', '\\"')))
    validate(G("ex:n ex:p 1 ."), shapes, meta_shacl=False)


@pytest.mark.parametrize(
    "tail",
    [
        "ORDER BY (EXISTS { ?this ?q ?z MINUS { ?z ?a ?b } })",
        "ORDER BY (EXISTS { SERVICE <http://localhost:1/x> { ?a ?b ?c } })",
        "GROUP BY $this HAVING (EXISTS { ?this ?q ?z MINUS { ?z ?a ?b } })",
        "GROUP BY $this HAVING (EXISTS { SERVICE <http://localhost:1/x> { ?a ?b ?c } })",
    ],
)
def test_minus_and_service_rejected_in_order_by_and_having(tail):
    from starlayer.shacl_engine.plan import ShapeError

    shapes = G(f'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:select """SELECT $this WHERE {{ $this ?p ?o }} {tail}""" ; sh:message "m" ] .')
    with pytest.raises(ShapeError):
        validate(G("ex:a ex:p ex:b ."), shapes, meta_shacl=False)


def test_validate_each_shacl_function_uses_each_data_graph():
    from starlayer.shacl_engine import validate_each

    pfx = (
        "@prefix ex: <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .\n"
        'ex: a sh:ShapesGraph ; sh:declare [ sh:prefix "ex" ; sh:namespace "http://e/" ] .\n'
    )

    def g(t):
        return StarLayerGraph().parse(data=pfx + t, format="turtle")

    shapes = g(
        """ex:f a sh:ListParameterExpressionFunction ;
            sh:bodyExpression [ shnex:pathValues ex:p ; shnex:focusNode [ shnex:arg 0 ] ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:n ;
            sh:sparql [ sh:select "SELECT $this WHERE { FILTER(ex:f($this) = 5) }" ; sh:message "p is five" ] ."""
    )
    d1, d2 = g("ex:n ex:p 5 ."), g("ex:n ex:p 6 .")
    solo = [validate(d, shapes, meta_shacl=False).conforms for d in (d1, d2)]
    each = validate_each([d1, d2], shapes, meta_shacl=False)
    assert solo == [False, True]
    assert [each[0].conforms, each[1].conforms] == solo


ASK_SHAPES = """
ex:Comp a sh:ConstraintComponent ; sh:parameter [ sh:path ex:lim ] ;
  sh:validator [ sh:ask "PREFIX ex: <http://example.org/> ASK { $this ex:p ?v . FILTER(?v <= $lim) }" ] .
ex:S a sh:NodeShape ; sh:targetClass ex:C ; ex:lim 1 .
"""


@pytest.mark.parametrize("focus", ["[]", "ex:n"])
def test_sparql_ask_validator_blank_node_focus(focus):
    out = validate(G(f"{focus} a ex:C ; ex:p 2 ."), G(ASK_SHAPES))
    assert len(out.results) == 1


def test_sparql_ask_validator_blank_node_parameter():
    shapes = G(ASK_SHAPES.replace("ex:lim 1", "ex:lim _:b").replace("ex:S a", "_:b ex:v 1 . ex:S a"))
    out = validate(G("ex:n a ex:C ; ex:p 2 ."), shapes)
    assert len(out.results) == 1


NX = """@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
ex: a sh:ShapesGraph ; sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.org/" ] .
"""


@pytest.mark.parametrize(
    "shapes",
    [
        "ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:expression _:e . _:e shnex:exists _:e .",
        """ex:f a sh:ListParameterExpressionFunction ; sh:bodyExpression [ ex:f ( [ shnex:arg 0 ] ) ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:expression [ ex:f ( 1 ) ] .""",
    ],
)
def test_cyclic_expression_is_a_shape_error_not_recursion_error(shapes):
    from starlayer.shacl_engine.plan import ShapeError

    with pytest.raises(ShapeError):
        validate(G("ex:n ex:p 1 ."), G(NX + shapes), meta_shacl=False)


def test_subgraph_negated_closed_keeps_extra_triples():
    _fragment_conforms(
        "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:not [ sh:closed true ; sh:ignoredProperties ( rdf:type ) ] .",
        'ex:n a ex:T ; ex:p "extra" .',
    )


def test_subgraph_qualified_disjoint_keeps_sibling_evidence():
    _fragment_conforms(
        """ex:S a sh:NodeShape ; sh:targetNode ex:f ; sh:property ex:A , ex:B .
        ex:A sh:path ex:p ; sh:qualifiedValueShape [ sh:class ex:C ] ; sh:qualifiedValueShapesDisjoint true ; sh:qualifiedMinCount 1 .
        ex:B sh:path ex:p ; sh:qualifiedValueShape [ sh:property [ sh:path ex:z ; sh:maxCount 1 ] ] ; sh:qualifiedValueShapesDisjoint true ; sh:qualifiedMinCount 0 .""",
        "ex:f ex:p ex:v . ex:v a ex:C ; ex:z 1, 2 .",
    )


def test_subgraph_node_shape_equals_keeps_second_path():
    _fragment_conforms("ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:equals ex:self .", "ex:a ex:self ex:a .")
