"""A condition written on a shui:WidgetScore (shui:shapesGraphShape / shui:dataGraphShape) applies to that score only, as in
the Working Group's own widget files. A score with no condition applies to everything. Layers therefore stack: a score
added by a higher layer is never blocked by a condition in a lower one (which a per-widget shui:WidgetAcceptMatcher,
shared by every layer, would do)."""

import pytest
from rdflib import Namespace
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl.ui_widget_selection import SHUI, select_widget, select_widgets

EX = Namespace("http://example.org/")
PREFIXES = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix shui: <http://www.w3.org/ns/shacl-ui#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
)
SHAPES = PREFIXES + """
ex:S a sh:NodeShape ; sh:property ex:Age, ex:Note .
ex:Age sh:path ex:age ; sh:datatype xsd:integer .
ex:Note sh:path ex:note ; sh:datatype xsd:string ."""
BASE = PREFIXES + """
[] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1 .
[] a shui:WidgetScore ; shui:widget shui:NumberFieldEditor ; shui:score 2 ; shui:shapesGraphShape ex:Numeric .
ex:Numeric a sh:NodeShape ; sh:property [ sh:path sh:datatype ; sh:in ( xsd:integer ) ; sh:minCount 1 ] ."""


def _graph(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=ttl, format="turtle12")
    return g


@pytest.fixture(scope="module")
def shapes() -> StarLayerGraph:
    return _graph(SHAPES)


def _pick(shapes, catalog, prop, **kwargs):
    return select_widget(shape_node=prop, shapes_graph=shapes, scoring_graph=_graph(catalog), role="editor", **kwargs)


def test_a_condition_on_a_score_applies_to_that_score_only(shapes) -> None:
    assert _pick(shapes, BASE, EX.Age) == SHUI.NumberFieldEditor
    assert _pick(shapes, BASE, EX.Note) == SHUI.TextFieldEditor  # the number field's condition does not hold


def test_a_score_without_a_condition_applies_to_everything(shapes) -> None:
    only_default = PREFIXES + "[] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1 ."
    assert _pick(shapes, only_default, EX.Age) == SHUI.TextFieldEditor
    assert _pick(shapes, only_default, EX.Note) == SHUI.TextFieldEditor


def test_a_higher_layer_can_add_a_widget_a_lower_layer_conditioned(shapes) -> None:
    """The base layer only offers the number field for integers. A layer on top wants one for ex:note (a string that
    holds a number) and just adds a score with its own condition; nothing in the base layer has to be removed."""
    layer = PREFIXES + """
    [] a shui:WidgetScore ; shui:widget shui:NumberFieldEditor ; shui:score 40 ; shui:shapesGraphShape ex:IsNoteField .
    ex:IsNoteField a sh:NodeShape ; sh:property [ sh:path sh:path ; sh:hasValue ex:note ] ."""
    stacked = BASE + layer.replace(PREFIXES, "")
    assert _pick(shapes, BASE, EX.Note) == SHUI.TextFieldEditor
    assert _pick(shapes, stacked, EX.Note) == SHUI.NumberFieldEditor
    assert _pick(shapes, stacked, EX.Age) == SHUI.NumberFieldEditor  # unchanged elsewhere


def test_a_per_widget_matcher_is_a_gate_every_layer_shares(shapes) -> None:
    """For contrast (still supported, as the draft's text describes it): a shui:WidgetAcceptMatcher attached to a widget
    rejects it for everyone, including a score a higher layer adds for that widget."""
    gated = BASE.replace(
        "ex:Numeric a sh:NodeShape",
        "[] a shui:WidgetAcceptMatcher ; shui:widget shui:NumberFieldEditor ; shui:shapesGraphShape ex:Numeric .\n"
        "ex:Numeric a sh:NodeShape",
    ).replace(" ; shui:shapesGraphShape ex:Numeric .\n[] a shui:WidgetScore ; shui:widget shui:NumberFieldEditor", " .\n[] a shui:WidgetScore ; shui:widget shui:NumberFieldEditor")
    layer = """
    [] a shui:WidgetScore ; shui:widget shui:NumberFieldEditor ; shui:score 40 .
    """
    assert _pick(shapes, gated + layer, EX.Note) != SHUI.NumberFieldEditor


def test_a_condition_on_the_focus_node_needs_a_focus_node(shapes) -> None:
    catalog = PREFIXES + """
    [] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1 .
    [] a shui:WidgetScore ; shui:widget shui:TextAreaEditor ; shui:score 5 ; shui:dataGraphShape ex:LongText .
    ex:LongText a sh:NodeShape ; sh:property [ sh:path ex:note ; sh:minLength 20 ] ."""
    data_long = _graph(PREFIXES + 'ex:a ex:note "a note that is longer than twenty characters" .')
    data_short = _graph(PREFIXES + 'ex:b ex:note "short" .')
    assert _pick(shapes, catalog, EX.Note) == SHUI.TextFieldEditor  # no focus node: a data condition cannot hold
    assert _pick(shapes, catalog, EX.Note, focus_node=EX.a, data_graph=data_long) == SHUI.TextAreaEditor
    assert _pick(shapes, catalog, EX.Note, focus_node=EX.b, data_graph=data_short) == SHUI.TextFieldEditor


def test_select_widgets_applies_score_conditions_to_every_property(shapes) -> None:
    result = select_widgets(shape_node=EX.S, shapes_graph=shapes, scoring_graph=_graph(BASE), role="editor")
    assert result == {EX.Age: SHUI.NumberFieldEditor, EX.Note: SHUI.TextFieldEditor}
