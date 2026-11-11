"""``select_widget(s)(implemented=, on_report=)``: a widget the application does not implement is never selected, and the application is
told (SHACL UI, Scoring System: "An implementation MUST NOT select or offer a widget that it does not implement. When a widget that the
implementation does not implement matches, or when no widget matches, the implementation MUST report this to the application.")"""

import pytest
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.shacl.ui_widget_selection import (
    SHUI,
    WidgetReport,
    select_widget,
    select_widgets,
)
from starlayer.shacl_engine.terms import NS

EX = NS("http://example.org/")
PREFIXES = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix shui: <http://www.w3.org/ns/shacl-ui/> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
)
SHAPES = PREFIXES + "ex:S a sh:NodeShape ; sh:property ex:Note . ex:Note sh:path ex:note ; sh:datatype xsd:string ."
DATA = PREFIXES + 'ex:a ex:note "a note that is a good deal longer than twenty characters" . ex:b ex:note "short" .'
SCORES = PREFIXES + """
    [] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1 .
    [] a shui:WidgetScore ; shui:widget shui:TextAreaEditor ; shui:score 5 .
    [] a shui:WidgetScore ; shui:widget shui:RichTextEditor ; shui:score 9 ."""
SCORES_DATA_DEPENDENT = PREFIXES + """
    [] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1 .
    [] a shui:WidgetScore ; shui:widget shui:TextAreaEditor ; shui:score 5 ; shui:dataGraphShape ex:Long .
    ex:Long a sh:NodeShape ; sh:property [ sh:path ex:note ; sh:minLength 20 ] ."""

TEXT_FIELD = SHUI.TextFieldEditor
TEXT_AREA = SHUI.TextAreaEditor
RICH_TEXT = SHUI.RichTextEditor


def _g(ttl):
    g = StarLayerGraph()
    g.parse(data=ttl, format="turtle")
    return g


@pytest.fixture
def graphs():
    return {"shapes_graph": _g(SHAPES), "scoring_graph": _g(SCORES)}


def test_without_implemented_nothing_changes_and_nothing_is_reported(graphs):
    reports: list = []
    got = select_widget(shape_node=EX.Note, role="editor", on_report=reports.append, **graphs)
    assert got == RICH_TEXT
    assert reports == []


def test_an_unimplemented_widget_is_not_selected_and_the_next_ranked_one_is(graphs):
    got = select_widget(shape_node=EX.Note, role="editor", implemented=[TEXT_FIELD, TEXT_AREA], **graphs)
    assert got == TEXT_AREA


def test_each_unimplemented_widget_that_matched_is_reported(graphs):
    reports: list[WidgetReport] = []
    got = select_widget(shape_node=EX.Note, role="editor", implemented=[TEXT_FIELD], on_report=reports.append, **graphs)
    assert got == TEXT_FIELD
    assert [(r.kind, r.widget, r.score) for r in reports] == [("unimplemented", RICH_TEXT, 9.0), ("unimplemented", TEXT_AREA, 5.0)]
    assert all(r.shape_node == EX.Note and r.role == "editor" for r in reports)


def test_nothing_implemented_selects_nothing_and_reports_none(graphs):
    reports: list[WidgetReport] = []
    got = select_widget(shape_node=EX.Note, role="editor", implemented=[], on_report=reports.append, **graphs)
    assert got is None
    assert [r.kind for r in reports] == ["unimplemented", "unimplemented", "unimplemented", "none"]
    assert reports[-1].widget is None


def test_no_matching_widget_is_reported_even_when_every_widget_is_implemented():
    reports: list[WidgetReport] = []
    got = select_widget(shape_node=EX.Note, role="editor", shapes_graph=_g(SHAPES), scoring_graph=_g(PREFIXES), on_report=reports.append)
    assert got is None
    assert [r.kind for r in reports] == ["none"]


def test_a_widget_the_shape_names_is_not_exempt():
    shapes = _g(SHAPES + " ex:Note shui:editor shui:TextAreaEditor .")
    reports: list[WidgetReport] = []
    got = select_widget(shape_node=EX.Note, role="editor", shapes_graph=shapes, scoring_graph=_g(SCORES), implemented=[TEXT_FIELD],
                        on_report=reports.append)
    assert got == TEXT_FIELD
    assert TEXT_AREA in [r.widget for r in reports]


def test_iris_may_be_given_as_strings(graphs):
    got = select_widget(shape_node=EX.Note, role="editor", implemented=[TEXT_FIELD.value], **graphs)
    assert got == TEXT_FIELD


def test_select_widgets_applies_it_to_every_property(graphs):
    reports: list[WidgetReport] = []
    got = select_widgets(shape_node=EX.S, role="editor", implemented=[TEXT_AREA], on_report=reports.append, **graphs)
    assert got == {EX.Note: TEXT_AREA}
    assert [(r.kind, r.widget) for r in reports] == [("unimplemented", RICH_TEXT)]


def test_per_shape_reports_a_widget_that_matches_every_node_when_the_choice_is_made():
    reports: list[WidgetReport] = []
    choices = select_widgets(shape_node=EX.S, role="editor", per="shape", shapes_graph=_g(SHAPES), scoring_graph=_g(SCORES),
                             implemented=[TEXT_FIELD], on_report=reports.append)
    assert choices[EX.Note].widget_without_data == TEXT_FIELD
    assert [(r.kind, r.widget) for r in reports] == [("unimplemented", RICH_TEXT), ("unimplemented", TEXT_AREA)]


def test_per_shape_decides_a_data_dependent_widget_per_node():
    reports: list[WidgetReport] = []
    data = _g(DATA)
    choice = select_widgets(shape_node=EX.S, role="editor", per="shape", shapes_graph=_g(SHAPES), scoring_graph=_g(SCORES_DATA_DEPENDENT),
                            implemented=[TEXT_FIELD], on_report=reports.append)[EX.Note]
    assert reports == []  # whether the text area matches depends on the node
    assert choice.resolve(EX.b, data) == TEXT_FIELD  # short note: the text area does not match, nothing to report
    assert reports == []
    assert choice.resolve(EX.a, data) == TEXT_FIELD  # long note: the text area matches but is not implemented
    assert [(r.kind, r.widget, r.focus_node) for r in reports] == [("unimplemented", TEXT_AREA, EX.a)]


def test_per_shape_resolve_reports_none_when_nothing_implemented_matches():
    reports: list[WidgetReport] = []
    choice = select_widgets(shape_node=EX.S, role="editor", per="shape", shapes_graph=_g(SHAPES), scoring_graph=_g(SCORES_DATA_DEPENDENT),
                            implemented=[], on_report=reports.append)[EX.Note]
    assert choice.resolve(EX.a, _g(DATA)) is None
    assert reports[-1].kind == "none" and reports[-1].focus_node == EX.a
