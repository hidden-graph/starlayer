"""Every operation that has a function form and a method form gives the same answer in both (the method uses the processor's bound graphs)."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl import (
    StarShaclProcessor,
    candidate_values,
    check_value,
    close_shape,
    explain_widgets,
    extract_shapes_graph,
    extract_subgraph,
    select_widget,
    value_form,
)
from starlayer.shacl.engine.terms import NS

EX = NS("http://example.org/")
PFX = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "
    "@prefix shui: <http://www.w3.org/ns/shacl-ui/> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
)


def _graph(turtle: str) -> StarLayerGraph:
    return StarLayerGraph().parse(data=PFX + turtle, format="turtle")


def _triples(graph) -> set:
    return set(graph.triples((None, None, None)))


def _named(graph) -> set:
    """The triples without a blank node: a copy that adds a list (as ``close_shape`` does) gets new blank node labels each time."""
    return {t for t in graph.triples((None, None, None)) if not any(type(term).__name__ == "BlankNode" for term in t)}


SHAPES = "ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:property ex:NameShape . ex:NameShape sh:path ex:name ; sh:minCount 1 ."
DATA = 'ex:alice a ex:Person ; ex:name "Alice" ; ex:age 30 .'


def test_extract_subgraph_method_matches_the_function():
    shapes, data = _graph(SHAPES), _graph(DATA)
    by_function = extract_subgraph(data, shapes)
    by_method = StarShaclProcessor(shacl_graph=shapes, data_graph=data).extract_subgraph()
    assert _triples(by_method) == _triples(by_function)
    assert any(p == EX.name for _, p, _ in by_method.triples((None, None, None)))
    assert not any(p == EX.age for _, p, _ in by_method.triples((None, None, None)))  # the fragment holds only what the shape covers


def test_extract_subgraph_method_takes_a_data_graph_for_the_call():
    shapes, other = _graph(SHAPES), _graph('ex:bob a ex:Person ; ex:name "Bob" .')
    fragment = StarShaclProcessor(shacl_graph=shapes).extract_subgraph(other)
    assert any(o.value == "Bob" for _, _, o in fragment.triples((None, EX.name, None)))


def test_close_shape_function_matches_the_method():
    shapes = _graph(SHAPES)
    closed = close_shape(shapes, EX.PersonShape)
    by_method = StarShaclProcessor(shacl_graph=shapes).close_shape(EX.PersonShape)
    assert _named(closed) == _named(by_method) and len(closed) == len(by_method)
    assert any(p.value.endswith("#closed") for _, p, _ in closed.triples((EX.PersonShape, None, None)))
    assert not any(p.value.endswith("#closed") for _, p, _ in shapes.triples((EX.PersonShape, None, None)))  # the input is not changed


MODULES = SHAPES + " ex:Module a sh:ShapesGraph ; rdfs:member ex:PersonShape ."


def test_extract_shapes_graph_function_matches_the_method():
    shapes = _graph(MODULES)
    module = extract_shapes_graph(shapes, EX.Module)
    assert module is not None and _triples(module) == _triples(StarShaclProcessor(shacl_graph=shapes).extract_shapes_graph(EX.Module))
    assert extract_shapes_graph(shapes, EX.NoSuchModule) is None


WIDGET_SHAPES = "ex:S a sh:NodeShape ; sh:property ex:Note, ex:Pinned . ex:Note sh:path ex:note ; sh:datatype xsd:string . ex:Pinned sh:path ex:pinned ; shui:editor shui:TextAreaEditor ."
SCORING = "[] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1 ."


@pytest.mark.parametrize("shape_node", [EX.Note, EX.Pinned])
def test_select_widget_method_matches_the_function(shape_node):
    shapes, scoring = _graph(WIDGET_SHAPES), _graph(SCORING)
    expected = select_widget(shape_node=shape_node, shapes_graph=shapes, scoring_graph=scoring, role="editor")
    assert StarShaclProcessor(shacl_graph=shapes, scoring_graph=scoring).select_widget(shape_node=shape_node, role="editor") == expected
    assert expected is not None


def test_explain_widgets_method_matches_the_function():
    shapes, scoring = _graph(WIDGET_SHAPES), _graph(SCORING)
    expected = explain_widgets(shape_node=EX.Note, shapes_graph=shapes, scoring_graph=scoring, role="editor")
    assert StarShaclProcessor(shacl_graph=shapes, scoring_graph=scoring).explain_widgets(shape_node=EX.Note, role="editor") == expected


@pytest.mark.parametrize("call", ["select_widget", "explain_widgets"])
def test_the_widget_methods_need_a_bound_shapes_graph(call):
    with pytest.raises(ValueError, match="shacl_graph"):
        getattr(StarShaclProcessor(), call)(shape_node=EX.Note, role="editor")


def test_candidate_values_method_matches_the_function_and_takes_a_data_graph_for_the_call():
    shapes = _graph("ex:Pet sh:path ex:pet ; sh:class ex:Animal .")
    data, other = _graph("ex:Rex a ex:Animal ."), _graph("ex:Tom a ex:Animal . ex:Fern a ex:Plant .")
    expected = candidate_values(shapes, EX.Pet, data)
    assert StarShaclProcessor(shacl_graph=shapes, data_graph=data).candidate_values(EX.Pet) == expected
    assert expected.values == (EX.Rex,)
    assert StarShaclProcessor(shacl_graph=shapes).candidate_values(EX.Pet, data_graph=other).values == (EX.Tom,)


def test_value_form_and_check_value_methods_match_the_functions_and_take_a_data_graph_for_the_call():
    shapes = _graph("ex:Pet sh:path ex:pet ; sh:class ex:Animal ; sh:maxCount 1 . ex:Tags sh:path ex:tags ; sh:minListLength 1 .")
    data, other = _graph("ex:Ann ex:pet ex:Rex . ex:Rex a ex:Animal . ex:Fern a ex:Plant ."), _graph("ex:Fern a ex:Animal .")
    processor = StarShaclProcessor(shacl_graph=shapes, data_graph=data)
    assert processor.value_form(EX.Tags) == value_form(shapes, EX.Tags) == "list"
    assert processor.value_form(EX.Pet) == value_form(shapes, EX.Pet) == "single"
    expected = check_value(shapes, EX.Pet, EX.Ann, EX.Fern, data)
    assert not expected.conforms
    assert [r.identity() for r in processor.check_value(EX.Pet, EX.Ann, EX.Fern).results] == [r.identity() for r in expected.results]
    assert StarShaclProcessor(shacl_graph=shapes).check_value(EX.Pet, EX.Ann, EX.Fern, data_graph=other).conforms
