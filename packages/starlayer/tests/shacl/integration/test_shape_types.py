"""infer_types(): the rdf:type triples a shapes graph's structure entails (GitHub issues #24, #27, #28)."""

import pytest
from rdflib import RDF, Namespace
from starlayer import StarLayerGraph, starontology
from starlayer.shacl.shape_types import infer_types

pytest.importorskip("owlrl")

SH = Namespace("http://www.w3.org/ns/shacl#")
SHSH = Namespace("http://www.w3.org/ns/shacl-shacl#")
EX = Namespace("http://e/")
PREFIXES = "@prefix ex: <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "


def _types(ttl: str) -> set[tuple]:
    graph = StarLayerGraph()
    graph.parse(data=PREFIXES + ttl, format="turtle12")
    return {(s, o) for s, _, o in infer_types(graph)}


def test_a_shape_with_a_target_and_no_path_is_a_node_shape() -> None:
    assert (EX.S, SH.NodeShape) in _types("ex:S sh:targetClass ex:C .")


def test_a_shape_with_sh_path_is_a_property_shape_and_not_a_node_shape() -> None:
    types = _types("ex:P sh:path ex:p ; sh:minCount 1 .")
    assert (EX.P, SH.PropertyShape) in types
    assert (EX.P, SH.NodeShape) not in types


def test_the_value_of_a_shape_valued_parameter_is_a_shape_even_with_no_constraints() -> None:
    assert (EX.Inner, SH.NodeShape) in _types("ex:S sh:node ex:Inner .")


def test_every_member_of_an_or_list_is_a_shape_including_one_with_no_constraints() -> None:
    types = _types("ex:S sh:or ( ex:A ex:B ex:Empty ) .")
    assert {(EX.A, SH.NodeShape), (EX.B, SH.NodeShape), (EX.Empty, SH.NodeShape)} <= types


def test_and_and_xone_lists_are_walked_too() -> None:
    types = _types("ex:S sh:and ( ex:A ) ; sh:xone ( ex:B ex:C ) .")
    assert {(EX.A, SH.Shape), (EX.B, SH.Shape), (EX.C, SH.Shape)} <= types


def test_a_property_shape_that_is_the_value_of_sh_property_is_typed() -> None:
    assert (EX.P, SH.PropertyShape) in _types("ex:S sh:property ex:P . ex:P sh:path ex:p .")


def test_a_node_that_is_only_an_ordinary_resource_is_not_a_shape() -> None:
    assert not {(s, o) for s, o in _types("ex:Thing ex:label 'x' .") if o in (SH.Shape, SH.NodeShape, SH.PropertyShape)}


def test_a_property_group_with_a_name_is_not_made_a_shape() -> None:
    """The vocabulary's domain for sh:name is sh:Shape; a property group has a name too."""
    types = _types("ex:P sh:path ex:p ; sh:group ex:G . ex:G sh:name 'Group' ; sh:order 1 .")
    assert (EX.G, SH.PropertyGroup) in types
    assert (EX.G, SH.Shape) not in types and (EX.G, SH.NodeShape) not in types


def test_non_shapes_get_their_type_from_the_vocabulary() -> None:
    types = _types('ex:CC sh:validator ex:V . ex:V sh:ask "ASK {}" .')
    assert (EX.CC, SH.ConstraintComponent) in types
    assert (EX.V, SH.SPARQLAskValidator) in types


def test_a_type_the_graph_already_states_is_not_returned() -> None:
    assert (EX.S, SH.NodeShape) not in _types("ex:S a sh:NodeShape ; sh:targetClass ex:C .")


def test_the_shapes_graph_is_not_changed() -> None:
    graph = StarLayerGraph()
    graph.parse(data=PREFIXES + "ex:S sh:targetClass ex:C .", format="turtle12")
    before = set(graph)
    infer_types(graph)
    assert set(graph) == before


def test_the_result_holds_only_rdf_type_triples_in_the_sh_namespace() -> None:
    graph = StarLayerGraph()
    graph.parse(data=PREFIXES + "ex:S sh:targetClass ex:C ; sh:property ex:P . ex:P sh:path ex:p .", format="turtle12")
    result = infer_types(graph)
    assert len(result) > 0
    assert all(p == RDF.type and str(o).startswith(str(SH)) for _, p, o in result)


def test_the_rules_cover_every_constraint_parameter_shacl_shacl_names() -> None:
    """Drift guard: a predicate shacl_shacl treats as a shape's parameter must make its subject a shape here too."""
    shacl_shacl = starontology.get_ontology_graph("shacl_shacl")
    rules = starontology.get_ontology_graph("shacl_shacl_rules")
    by_subject = set(rules.objects(None, SH.targetSubjectsOf))
    by_value = set(rules.objects(None, SH.targetObjectsOf))
    required = set(shacl_shacl.objects(SHSH.ShapeShape, SH.targetSubjectsOf))
    assert required <= by_subject, f"missing from shacl_shacl_rules: {sorted(required - by_subject)}"
    assert set(shacl_shacl.objects(SHSH.ShapeShape, SH.targetObjectsOf)) <= by_value | by_subject
