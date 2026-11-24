"""``candidate_values``: what an editor can offer for a field (a property shape)."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl import Candidates, StarShaclProcessor, candidate_values
from starlayer.shacl.engine.terms import NS, literal

EX = NS("http://example.org/")
XSD = NS("http://www.w3.org/2001/XMLSchema#")
SH = NS("http://www.w3.org/ns/shacl#")
PFX = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
)


def g(turtle: str) -> StarLayerGraph:
    return StarLayerGraph().parse(data=PFX + turtle, format="turtle")


SHAPES = """
ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ;
  sh:property ex:PetShape .
ex:PetShape sh:path ex:pet ; sh:class ex:Animal ; sh:disjoint ex:allergicTo .
"""
DATA = """
ex:Dog rdfs:subClassOf ex:Animal . ex:Cat rdfs:subClassOf ex:Animal .
ex:Rex a ex:Dog . ex:Tom a ex:Cat . ex:Happy a ex:Animal . ex:Fern a ex:Plant .
ex:Ann a ex:Person ; ex:allergicTo ex:Tom .
"""


def values(shapes: str, data: str = DATA, shape=EX.PetShape, **kw):
    return candidate_values(g(shapes), shape, g(data), **kw)


def test_instances_include_subclasses_and_never_the_classes_or_other_types():
    found = values(SHAPES)
    assert found == Candidates("instances", (EX.Happy, EX.Rex, EX.Tom), False, ())


def test_only_valid_drops_what_the_other_constraints_reject():
    found = values(SHAPES, only_valid=True, focus=EX.Ann)
    assert found.values == (EX.Happy, EX.Rex) and found.kind == "instances"


def test_only_valid_replaces_the_current_values_so_max_count_does_not_trip():
    shapes = SHAPES.replace("sh:disjoint ex:allergicTo", "sh:maxCount 1")
    data = DATA + "ex:Ann ex:pet ex:Rex ."
    assert values(shapes, data, only_valid=True, focus=EX.Ann).values == (EX.Happy, EX.Rex, EX.Tom)


def test_the_callers_data_is_not_changed():
    data = g(DATA + "ex:Ann ex:pet ex:Rex .")
    before = set(data.triples((None, None, None)))
    candidate_values(g(SHAPES), EX.PetShape, data, only_valid=True, focus=EX.Ann)
    assert set(data.triples((None, None, None))) == before


def test_subclass_triples_of_the_shapes_graph_are_read_only_on_request():
    shapes = SHAPES + "ex:Dog rdfs:subClassOf ex:Animal ."
    data = DATA.replace("ex:Dog rdfs:subClassOf ex:Animal .", "")
    assert values(shapes, data).values == (EX.Happy, EX.Tom)
    assert values(shapes, data, subclass_of_in_shapes_graph=True).values == (EX.Happy, EX.Rex, EX.Tom)


def test_sh_in_is_a_closed_list_in_a_stable_order():
    found = values("ex:P sh:path ex:p ; sh:in ( ex:b ex:a 2 1 ) .", "", EX.P)
    assert found.kind == "list" and found.closed and found.entry == ()
    assert found.values == (EX.a, EX.b, literal("1", XSD.integer), literal("2", XSD.integer))


def test_sh_in_is_intersected_with_sh_class():
    found = values("ex:P sh:path ex:p ; sh:in ( ex:Rex ex:Fern ex:Tom ) ; sh:class ex:Animal .", DATA, EX.P)
    assert found.kind == "list" and found.values == (EX.Rex, EX.Tom)


def test_has_value_is_a_closed_list_of_that_value():
    found = values("ex:P sh:path ex:p ; sh:hasValue ex:a .", "", EX.P)
    assert found == Candidates("list", (EX.a,), True, ())


def test_or_of_two_classes_is_the_union():
    shapes = "ex:P sh:path ex:p ; sh:or ( [ sh:class ex:Dog ] [ sh:class ex:Plant ] ) ."
    assert values(shapes, DATA, EX.P).values == (EX.Fern, EX.Rex)


def test_or_of_a_list_and_a_class_is_the_union_and_not_closed():
    shapes = "ex:P sh:path ex:p ; sh:or ( [ sh:in ( ex:z ) ] [ sh:class ex:Plant ] ) ."
    found = values(shapes, DATA, EX.P)
    assert found.values == (EX.Fern, EX.z) and found.kind == "instances" and not found.closed


def test_or_with_an_open_alternative_is_open_with_the_entries_of_the_alternatives():
    shapes = "ex:P sh:path ex:p ; sh:or ( [ sh:class ex:Dog ] [ sh:datatype xsd:string ] [ sh:datatype xsd:integer ] ) ."
    assert values(shapes, DATA, EX.P) == Candidates("open", (), False, (XSD.integer, XSD.string))


def test_a_datatype_only_is_open_with_that_entry():
    assert values("ex:P sh:path ex:p ; sh:datatype xsd:date .", "", EX.P) == Candidates("open", (), False, (XSD.date,))


def test_a_node_kind_only_is_open_with_that_entry():
    assert values("ex:P sh:path ex:p ; sh:nodeKind sh:IRI .", "", EX.P) == Candidates("open", (), False, (SH.IRI,))


def test_a_datatype_wins_over_a_node_kind_for_the_entry():
    found = values("ex:P sh:path ex:p ; sh:datatype xsd:date ; sh:nodeKind sh:Literal .", "", EX.P)
    assert found.entry == (XSD.date,)


def test_root_class_offers_the_root_and_its_subclasses_not_instances():
    found = values("ex:P sh:path ex:p ; sh:rootClass ex:Animal .", DATA, EX.P)
    assert found.kind == "instances" and found.values == (EX.Animal, EX.Cat, EX.Dog)


def test_literal_lists_are_tried_against_the_datatype():
    shapes = "ex:P sh:path ex:p ; sh:in ( 1 2 \"x\" ) ; sh:datatype xsd:integer ."
    found = values(shapes, "", EX.P, only_valid=True, focus=EX.Ann)
    assert found.values == (literal("1", XSD.integer), literal("2", XSD.integer))
    assert len(values(shapes, "", EX.P).values) == 3


def test_open_candidates_are_not_tried():
    assert values("ex:P sh:path ex:p ; sh:datatype xsd:date .", "", EX.P, only_valid=True, focus=EX.Ann).kind == "open"


def test_only_valid_needs_a_focus_node():
    with pytest.raises(ValueError, match="focus"):
        values(SHAPES, only_valid=True)


def test_a_node_that_is_not_a_property_shape_is_a_value_error():
    with pytest.raises(ValueError, match="property_shape"):
        values(SHAPES, shape=EX.PersonShape)
    with pytest.raises(ValueError, match="property_shape"):
        values(SHAPES, shape=EX.Missing)


def test_an_rdflib_graph_is_refused():
    rdflib = pytest.importorskip("rdflib")
    with pytest.raises(TypeError, match="from_rdflib"):
        candidate_values(rdflib.Graph(), EX.PetShape, g(DATA))


def test_the_method_form_matches_the_function_and_uses_the_constructor_default():
    shapes = g(SHAPES + "ex:Dog rdfs:subClassOf ex:Animal .")
    data = g(DATA.replace("ex:Dog rdfs:subClassOf ex:Animal .", ""))
    assert StarShaclProcessor(shacl_graph=shapes, data_graph=data).candidate_values(EX.PetShape) == candidate_values(shapes, EX.PetShape, data)
    on = StarShaclProcessor(shacl_graph=shapes, data_graph=data, subclass_of_in_shapes_graph=True)
    assert on.candidate_values(EX.PetShape) == candidate_values(shapes, EX.PetShape, data, subclass_of_in_shapes_graph=True)
    assert EX.Rex in on.candidate_values(EX.PetShape).values
    assert EX.Rex not in on.candidate_values(EX.PetShape, subclass_of_in_shapes_graph=False).values
    assert on.candidate_values(EX.PetShape, only_valid=True, focus=EX.Ann).values == (EX.Happy, EX.Rex)
