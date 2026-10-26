"""Regression tests for GitHub issues #66 (target forms beyond the four target predicates) and #67 item 3 (a list-valued
``sh:condition``): ``target_nodes()`` returns the nodes ``validate()`` reports on for every target form, the meta-shapes
accept a node expression as the value of ``sh:targetNode``, and a rule condition list means "conforms to ALL listed shapes"
(SHACL 1.2 Inference Rules, ``sh:condition``)."""

from __future__ import annotations

import pytest
from rdflib import Namespace, URIRef
from starlayer import StarLayerGraph
from starlayer.shacl import StarShaclSchema, apply_rules, target_nodes, validate

pytestmark = pytest.mark.shacl

SH = Namespace("http://www.w3.org/ns/shacl#")
EX = Namespace("http://e/")
PREFIXES = (
    "@prefix ex: <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
)


def g(text: str) -> StarLayerGraph:
    return StarLayerGraph().parse(data=PREFIXES + text, format="turtle12")


DATA = """
ex:a a ex:T ; ex:p 1 .
ex:b a ex:T .
ex:c a ex:U ; ex:p 2 .
ex:d ex:q ex:e .
ex:s a ex:Sub . ex:Sub rdfs:subClassOf ex:T .
"""

# Every shape always fails on its focus nodes (sh:class ex:Never), so each focus node validate() visits is reported.
FORMS = {
    "targetClass_with_subclass": "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:class ex:Never .",
    "targetNode_iri": "ex:S a sh:NodeShape ; sh:targetNode ex:a, ex:zzz ; sh:class ex:Never .",
    "targetSubjectsOf": "ex:S a sh:NodeShape ; sh:targetSubjectsOf ex:p ; sh:class ex:Never .",
    "targetObjectsOf": "ex:S a sh:NodeShape ; sh:targetObjectsOf ex:q ; sh:class ex:Never .",
    "targetWhere": "ex:S a sh:NodeShape ; sh:targetWhere [ sh:property [ sh:path ex:p ; sh:minCount 1 ] ] ; sh:class ex:Never .",
    "sparql_target": (
        "ex:S a sh:NodeShape ; sh:target [ a sh:SPARQLTarget ; "
        "sh:select 'SELECT ?this WHERE { ?this <http://e/p> ?v }' ] ; sh:class ex:Never ."
    ),
    "targetNode_expression": "ex:S a sh:NodeShape ; sh:targetNode [ shnex:instancesOf ex:T ] ; sh:class ex:Never .",
    "targetNode_select": (
        "ex:S a sh:NodeShape ; sh:targetNode [ sh:select 'SELECT ?x WHERE { ?x <http://e/p> ?v }' ] ; sh:class ex:Never ."
    ),
    "implicit_class": "ex:T a rdfs:Class, sh:NodeShape ; sh:class ex:Never .",
}


def _validated_focus_nodes(data: StarLayerGraph, shapes: StarLayerGraph) -> set:
    result = validate(data, shapes, advanced=True)
    return {o for _, _, o in result.report_graph.triples((None, SH.focusNode, None))}


@pytest.mark.parametrize("name", sorted(FORMS))
def test_target_nodes_equals_the_focus_nodes_validate_reports_on(name: str) -> None:
    shapes = g(FORMS[name])
    shape = EX.T if name == "implicit_class" else EX.S
    expected = _validated_focus_nodes(g(DATA), shapes)
    assert expected, "the fixture must target something, or the comparison proves nothing"
    assert set(target_nodes(data_graph=g(DATA), shacl_graph=shapes, shape_node=shape)) == expected
    assert set(StarShaclSchema(shapes, data_graph=g(DATA)).target_nodes(shape_node=shape)) == expected


def test_expression_target_is_not_the_blank_node_itself() -> None:
    nodes = target_nodes(data_graph=g(DATA), shacl_graph=g(FORMS["targetNode_expression"]), shape_node=EX.S)
    assert all(isinstance(n, URIRef) for n in nodes)
    assert set(nodes) == {EX.a, EX.b, EX.s}


def test_target_class_includes_subclass_instances() -> None:
    nodes = target_nodes(data_graph=g(DATA), shacl_graph=g(FORMS["targetClass_with_subclass"]), shape_node=EX.S)
    assert EX.s in nodes


def test_one_shapes_dynamic_targets_do_not_leak_into_another() -> None:
    shapes = g(
        FORMS["targetWhere"]
        + " ex:S2 a sh:NodeShape ; sh:targetNode [ shnex:instancesOf ex:U ] ; sh:class ex:Never ."
    )
    assert set(target_nodes(data_graph=g(DATA), shacl_graph=shapes, shape_node=EX.S)) == {EX.a, EX.c}
    assert set(target_nodes(data_graph=g(DATA), shacl_graph=shapes, shape_node=EX.S2)) == {EX.c}


class TestMetaShapesAcceptTargetNodeExpression:
    def _meta_errors(self, shapes_text: str) -> bool:
        from pyshacl.errors import ReportableRuntimeError
        from starlayer.shacl.meta_shapes import meta_validate

        try:
            meta_validate(g(shapes_text))
        except ReportableRuntimeError:
            return False
        return True

    def test_node_expression_is_accepted(self) -> None:
        assert self._meta_errors(FORMS["targetNode_expression"])

    def test_iri_and_literal_are_still_accepted(self) -> None:
        assert self._meta_errors("ex:S a sh:NodeShape ; sh:targetNode ex:a, 'x' .")

    def test_blank_node_without_a_defining_predicate_is_still_rejected(self) -> None:
        assert not self._meta_errors("ex:S a sh:NodeShape ; sh:targetNode [ ex:random 1 ] .")


COND_SHAPES = """
ex:HasP a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .
ex:HasQ a sh:NodeShape ; sh:property [ sh:path ex:q ; sh:minCount 1 ] .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:rule ex:R .
ex:R a sh:TripleRule ; sh:condition COND ; sh:subject sh:this ; sh:predicate ex:derived ; sh:object ex:o .
"""
COND_DATA = """
ex:both a ex:T ; ex:p 1 ; ex:q 1 .
ex:onlyP a ex:T ; ex:p 1 .
ex:onlyQ a ex:T ; ex:q 1 .
ex:none a ex:T .
"""


def _derived(cond: str) -> set:
    result = apply_rules(g(COND_DATA), g(COND_SHAPES.replace("COND", cond)))
    return {s for s, p, _ in result.inferred_graph if p == EX.derived}


class TestRuleConditionList:
    def test_list_means_conforms_to_all_listed_shapes(self) -> None:
        assert _derived("( ex:HasP ex:HasQ )") == {EX.both}

    def test_single_shape_condition_unchanged(self) -> None:
        assert _derived("ex:HasP") == {EX.both, EX.onlyP}

    def test_one_element_list_equals_single(self) -> None:
        assert _derived("( ex:HasP )") == _derived("ex:HasP")

    def test_validate_over_a_list_condition_reports(self) -> None:
        result = validate(g(COND_DATA), g(COND_SHAPES.replace("COND", "( ex:HasP ex:HasQ )")))
        assert result.conforms is True
