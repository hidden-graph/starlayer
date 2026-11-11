"""SHACL UI, Property Roles: the property shapes that play a role, in the draft's order (``property_shapes_for_role``), and the shape of
the ``shui:propertyRole`` annotation (direct, qualified, RDF 1.2 triple annotation)."""

import pytest
from starlayer import starontology
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.shacl import property_shapes_for_role, validate
from starlayer.shacl.ui_property_roles import CLASSIFICATION_ROLE, LABEL_ROLE
from starlayer.shacl_engine.terms import NS

EX = NS("http://example.org/")
PREFIXES = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix shui: <http://www.w3.org/ns/shacl-ui/> . @prefix skos: <http://www.w3.org/2004/02/skos/core#> .\n"
)


def _g(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PREFIXES + ttl, format="turtle12")
    return g


def _order(ttl: str, role=LABEL_ROLE):
    shapes = _g("ex:S a sh:NodeShape ; sh:property ex:A, ex:B, ex:C, ex:D .\n" + ttl)
    return [str(p.value).rsplit("/", 1)[-1] for p in property_shapes_for_role(shape_node=EX.S, role=role, shapes_graph=shapes)]


def test_a_direct_annotation_is_found():
    assert _order("ex:A sh:path skos:prefLabel ; shui:propertyRole shui:LabelRole . ex:B sh:path ex:other .") == ["A"]


def test_qualified_annotations_are_ordered_by_sh_order():
    ttl = """
        ex:A sh:path ex:a ; shui:propertyRole [ shui:propertyRole shui:LabelRole ; sh:order 1 ] .
        ex:B sh:path ex:b ; shui:propertyRole [ shui:propertyRole shui:LabelRole ; sh:order 0 ] ."""
    assert _order(ttl) == ["B", "A"]


def test_a_qualified_annotation_comes_before_a_direct_one():
    ttl = """
        ex:A sh:path ex:a ; shui:propertyRole shui:LabelRole .
        ex:B sh:path ex:b ; shui:propertyRole [ shui:propertyRole shui:LabelRole ; sh:order 5 ] ."""
    assert _order(ttl) == ["B", "A"]


def test_a_triple_annotation_with_an_order_counts_as_qualified():
    ttl = """
        ex:A sh:path ex:a ; shui:propertyRole shui:LabelRole .
        ex:B sh:path ex:b ; shui:propertyRole shui:LabelRole {| sh:order 0 |} .
        ex:C sh:path ex:c ; shui:propertyRole shui:LabelRole {| sh:order 2.5 |} ."""
    assert _order(ttl) == ["B", "C", "A"]


def test_only_the_asked_role_is_returned():
    ttl = """
        ex:A sh:path ex:a ; shui:propertyRole shui:LabelRole .
        ex:B sh:path ex:b ; shui:propertyRole shui:ClassificationRole .
        ex:C sh:path ex:c ; shui:propertyRole [ shui:propertyRole shui:ClassificationRole ; sh:order 0 ] ."""
    assert _order(ttl, CLASSIFICATION_ROLE) == ["C", "B"]
    assert _order(ttl) == ["A"]


def test_a_shape_with_two_annotations_of_one_role_is_listed_once_at_its_best_rank():
    ttl = "ex:A sh:path ex:a ; shui:propertyRole shui:LabelRole, [ shui:propertyRole shui:LabelRole ; sh:order 0 ] ."
    assert _order(ttl) == ["A"]


def test_no_shape_plays_the_role():
    assert _order("ex:A sh:path ex:a .") == []


def test_a_role_from_another_namespace_works_and_a_string_is_an_iri():
    ttl = "ex:A sh:path ex:a ; shui:propertyRole ex:MyRole ."
    shapes = _g("ex:S a sh:NodeShape ; sh:property ex:A .\n" + ttl)
    assert property_shapes_for_role(shape_node=EX.S, role="http://example.org/MyRole", shapes_graph=shapes) == [EX.A]


# ---- the shape of the annotation, checked by shacl_shacl_ui

def _conforms(ttl: str) -> bool:
    return validate(_g(ttl), starontology.get_ontology_graph("shacl_shacl_ui"), meta_shacl=False).conforms


@pytest.mark.parametrize(
    "annotation",
    [
        "shui:propertyRole shui:LabelRole",
        "shui:propertyRole [ shui:propertyRole shui:LabelRole ; sh:order 0 ]",
        "shui:propertyRole [ shui:propertyRole shui:LabelRole ; sh:order 0.5 ]",
        "shui:propertyRole shui:LabelRole {| sh:order 0 |}",
        "shui:propertyRole ex:MyRole",
    ],
)
def test_the_annotation_forms_the_draft_defines_are_well_formed(annotation):
    assert _conforms(f"ex:P a sh:PropertyShape ; sh:path ex:p ; {annotation} .")


@pytest.mark.parametrize(
    "annotation",
    [
        'shui:propertyRole "label"',  # a literal is no role
        "shui:propertyRole [ sh:order 0 ]",  # a qualified annotation must name its role
        "shui:propertyRole [ shui:propertyRole shui:LabelRole, shui:ClassificationRole ]",  # exactly one role
        'shui:propertyRole [ shui:propertyRole shui:LabelRole ; sh:order "first" ]',  # the order is a number
        "shui:propertyRole [ shui:propertyRole shui:LabelRole ; sh:order 0, 1 ]",  # at most one order
    ],
)
def test_a_malformed_annotation_is_a_violation(annotation):
    assert not _conforms(f"ex:P a sh:PropertyShape ; sh:path ex:p ; {annotation} .")
