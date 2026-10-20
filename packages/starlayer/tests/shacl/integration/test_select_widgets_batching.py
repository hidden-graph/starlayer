"""``select_widgets()`` checks the catalog's matchers for all of a shape's properties in one pass per matcher shape
(GitHub issue #14: one ``validate()`` per (property, matcher) pair re-encoded the whole shapes graph each time and took
seconds for a shape with a few dozen properties). The answers must not change, so each is checked against the
one-property-at-a-time ``select_widget()`` and against the widget expected by hand."""

import pytest
from rdflib import Namespace
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl import ui_widget_selection
from starlayer.shacl.ui_widget_selection import SHUI, select_widget, select_widgets

EX = Namespace("http://example.org/")

SHAPES = """
@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:property ex:age, ex:active, ex:born, ex:kind, ex:boss, ex:home, ex:note .
ex:age a sh:PropertyShape ; sh:path ex:age ; sh:datatype xsd:integer .
ex:active a sh:PropertyShape ; sh:path ex:active ; sh:datatype xsd:boolean .
ex:born a sh:PropertyShape ; sh:path ex:born ; sh:datatype xsd:date .
ex:kind a sh:PropertyShape ; sh:path ex:kind ; sh:in ( "a" "b" ) .
ex:boss a sh:PropertyShape ; sh:path ex:boss ; sh:class ex:Person .
ex:home a sh:PropertyShape ; sh:path ex:home ; sh:nodeKind sh:IRI .
ex:note a sh:PropertyShape ; sh:path ex:note .
"""

# An editors-only catalog (the role does not filter the catalog, issue #9), reduced from the issue #10 baseline.
CATALOG = """
@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> . @prefix uib: <http://example.org/ui-baseline#> .
[] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1.0 .
[] a shui:WidgetScore ; shui:widget shui:NumberFieldEditor ; shui:score 5.0 .
[] a shui:WidgetScore ; shui:widget shui:BooleanEditor ; shui:score 5.0 .
[] a shui:WidgetScore ; shui:widget shui:DatePickerEditor ; shui:score 5.0 .
[] a shui:WidgetScore ; shui:widget shui:EnumSelectEditor ; shui:score 6.0 .
[] a shui:WidgetScore ; shui:widget shui:InstancesSelectEditor ; shui:score 4.0 .
[] a shui:WidgetScore ; shui:widget shui:IRIEditor ; shui:score 3.0 .
[] a shui:WidgetAcceptMatcher ; shui:widget shui:NumberFieldEditor ; shui:shapesGraphShape uib:Numeric .
[] a shui:WidgetAcceptMatcher ; shui:widget shui:BooleanEditor ; shui:shapesGraphShape uib:Boolean .
[] a shui:WidgetAcceptMatcher ; shui:widget shui:DatePickerEditor ; shui:shapesGraphShape uib:Date .
[] a shui:WidgetAcceptMatcher ; shui:widget shui:EnumSelectEditor ; shui:shapesGraphShape uib:Enumerated .
[] a shui:WidgetAcceptMatcher ; shui:widget shui:InstancesSelectEditor ; shui:shapesGraphShape uib:Classed .
[] a shui:WidgetAcceptMatcher ; shui:widget shui:IRIEditor ; shui:shapesGraphShape uib:IRI .
uib:Numeric a sh:NodeShape ; sh:property [ sh:path sh:datatype ; sh:minCount 1 ; sh:in ( xsd:integer xsd:decimal ) ] .
uib:Boolean a sh:NodeShape ; sh:property [ sh:path sh:datatype ; sh:hasValue xsd:boolean ] .
uib:Date a sh:NodeShape ; sh:property [ sh:path sh:datatype ; sh:hasValue xsd:date ] .
uib:Enumerated a sh:NodeShape ; sh:property [ sh:path sh:in ; sh:minCount 1 ] .
uib:Classed a sh:NodeShape ; sh:property [ sh:path sh:class ; sh:minCount 1 ] .
uib:IRI a sh:NodeShape ; sh:property [ sh:path sh:nodeKind ; sh:hasValue sh:IRI ] .
"""

EXPECTED = {
    EX.age: SHUI.NumberFieldEditor,
    EX.active: SHUI.BooleanEditor,
    EX.born: SHUI.DatePickerEditor,
    EX.kind: SHUI.EnumSelectEditor,
    EX.boss: SHUI.InstancesSelectEditor,
    EX.home: SHUI.IRIEditor,
    EX.note: SHUI.TextFieldEditor,
}


@pytest.fixture(scope="module")
def graphs():
    shapes, catalog = StarLayerGraph(), StarLayerGraph()
    shapes.parse(data=SHAPES, format="turtle12")
    catalog.parse(data=CATALOG, format="turtle12")
    return shapes, catalog


def test_each_property_gets_the_widget_expected_by_hand(graphs):
    shapes, catalog = graphs
    assert select_widgets(shape_node=EX.S, shapes_graph=shapes, scoring_graph=catalog, role="editor") == EXPECTED


def test_batched_answers_equal_one_property_at_a_time(graphs):
    shapes, catalog = graphs
    batched = select_widgets(shape_node=EX.S, shapes_graph=shapes, scoring_graph=catalog, role="editor")
    single = {
        prop: select_widget(shape_node=prop, shapes_graph=shapes, scoring_graph=catalog, role="editor")
        for prop in EXPECTED
    }
    assert batched == single


def test_validation_runs_once_per_matcher_shape_not_once_per_property(graphs, monkeypatch):
    shapes, catalog = graphs
    calls = []
    real_validate = ui_widget_selection.validate

    def counting(*args, **kwargs):
        calls.append(1)
        return real_validate(*args, **kwargs)

    monkeypatch.setattr(ui_widget_selection, "validate", counting)
    select_widgets(shape_node=EX.S, shapes_graph=shapes, scoring_graph=catalog, role="editor")
    matcher_shapes = 6
    assert len(calls) <= matcher_shapes  # was one per (property, matcher) check: 7 properties x up to 6 matchers


def test_a_wrong_batch_answer_would_be_noticed(graphs, monkeypatch):
    """Mutation check: if every node were reported as conforming, the expected widgets above would not come out."""
    shapes, catalog = graphs
    monkeypatch.setattr(
        ui_widget_selection._ConformanceBatch, "_check", lambda self, shape: frozenset(self._nodes)
    )
    wrong = select_widgets(shape_node=EX.S, shapes_graph=shapes, scoring_graph=catalog, role="editor")
    assert wrong != EXPECTED


def test_a_data_matcher_with_a_focus_node_still_works(graphs):
    shapes, catalog = graphs
    data = StarLayerGraph()
    data.parse(data="@prefix ex: <http://example.org/> . ex:alice ex:age 3 .", format="turtle12")
    result = select_widgets(
        shape_node=EX.S, focus_node=EX.alice, data_graph=data, shapes_graph=shapes, scoring_graph=catalog, role="editor"
    )
    assert result == EXPECTED
