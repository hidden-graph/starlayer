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
