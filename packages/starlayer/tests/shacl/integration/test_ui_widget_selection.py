import pytest
from rdflib import Namespace

from starlayer.graph import StarLayerGraph
from starlayer.shacl.ui_widget_selection import select_widget, select_widgets

pyshacl = pytest.importorskip("pyshacl")

EX = Namespace("http://example.org/")
SHUI = Namespace("http://www.w3.org/ns/shacl-ui#")

# SHACL 1.2 User Interfaces (https://www.w3.org/TR/shacl12-ui/) Section 3
# "Scoring System" - the widget *selection* algorithm, built entirely on
# the public starlayer.shacl.validate() (see ui_widget_selection.py's own
# module docstring). shui:WidgetAcceptMatcher has no formal upstream
# shape and is actively contested (w3c/data-shapes#1249) as of the
# 2026-10-16 re-check - these tests deliberately exercise matchers with
# unusual/unconventional cardinality too, not just the conventional
# "exactly one shui:widget" reading.

_DATA = """
    @prefix ex: <http://example.org/> .
    ex:alice a ex:Person ; ex:birthDate "1990-01-01"^^<http://www.w3.org/2001/XMLSchema#date> .
"""

_SHAPES_EXPLICIT_WIDGET = """
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
    ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:property ex:BirthDateProp .
    ex:BirthDateProp a sh:PropertyShape ; sh:path ex:birthDate ; shui:editor shui:DatePickerEditor .
"""

_SHAPES_NO_EXPLICIT_WIDGET = """
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:property ex:BirthDateProp .
    ex:BirthDateProp a sh:PropertyShape ; sh:path ex:birthDate .
"""


def _graph(turtle: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=turtle, format="turtle")
    return g


def test_explicit_widget_with_no_matcher_is_accepted_unconditionally() -> None:
    data = _graph(_DATA)
    shapes = _graph(_SHAPES_EXPLICIT_WIDGET)

    widget = select_widget(
        EX.BirthDateProp, EX.alice,
        data_graph=data, shapes_graph=shapes, scoring_graph=shapes, role="editor",
    )
    assert widget == SHUI.DatePickerEditor


def test_explicit_widget_rejected_by_matcher_falls_back_to_scoring() -> None:
    data = _graph(_DATA)
    shapes = _graph(_SHAPES_EXPLICIT_WIDGET)
    scoring = _graph("""
        @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://example.org/> .

        [] a shui:WidgetAcceptMatcher ;
            shui:widget shui:DatePickerEditor ;
            shui:dataGraphShape ex:NeverConforms .
        ex:NeverConforms a sh:NodeShape ;
            sh:property [ sh:path ex:thisPropertyDoesNotExist ; sh:minCount 1 ] .

        [] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 5.0 .
    """)

    widget = select_widget(
        EX.BirthDateProp, EX.alice,
        data_graph=data, shapes_graph=shapes, scoring_graph=scoring, role="editor",
    )
    assert widget == SHUI.TextFieldEditor


def test_score_ranking_with_multiple_candidates_picks_the_highest() -> None:
    data = _graph(_DATA)
    shapes = _graph(_SHAPES_NO_EXPLICIT_WIDGET)
    scoring = _graph("""
        @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
        [] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 3.0 .
        [] a shui:WidgetScore ; shui:widget shui:DatePickerEditor ; shui:score 9.0 .
        [] a shui:WidgetScore ; shui:widget shui:NumberFieldEditor ; shui:score 1 .
    """)

    widget = select_widget(
        EX.BirthDateProp, EX.alice,
        data_graph=data, shapes_graph=shapes, scoring_graph=scoring, role="editor",
    )
    assert widget == SHUI.DatePickerEditor


def test_lower_ranked_candidate_wins_when_higher_ranked_is_rejected() -> None:
    data = _graph(_DATA)
    shapes = _graph(_SHAPES_NO_EXPLICIT_WIDGET)
    scoring = _graph("""
        @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://example.org/> .

        [] a shui:WidgetScore ; shui:widget shui:DatePickerEditor ; shui:score 9.0 .
        [] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 3.0 .

        [] a shui:WidgetAcceptMatcher ;
            shui:widget shui:DatePickerEditor ;
            shui:dataGraphShape ex:NeverConforms .
        ex:NeverConforms a sh:NodeShape ;
            sh:property [ sh:path ex:thisPropertyDoesNotExist ; sh:minCount 1 ] .
    """)

    widget = select_widget(
        EX.BirthDateProp, EX.alice,
        data_graph=data, shapes_graph=shapes, scoring_graph=scoring, role="editor",
    )
    assert widget == SHUI.TextFieldEditor


def test_matcher_with_more_than_one_shui_widget_value_still_resolves() -> None:
    """PR #1249 (open, unmerged) proposes shui:WidgetAcceptMatcher allow
    *at least one* shui:widget rather than exactly one, specifically so
    one matcher can serve several widgets - confirm select_widget() does
    not assume either cardinality."""
    data = _graph(_DATA)
    shapes = _graph(_SHAPES_NO_EXPLICIT_WIDGET)
    scoring = _graph("""
        @prefix ex: <http://example.org/> .
        @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
        ex:SharedMatcher a shui:WidgetAcceptMatcher ;
            shui:widget shui:DatePickerEditor, shui:TextFieldEditor .
        [] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1.0 .
    """)

    widget = select_widget(
        EX.BirthDateProp, EX.alice,
        data_graph=data, shapes_graph=shapes, scoring_graph=scoring, role="editor",
    )
    assert widget == SHUI.TextFieldEditor


def test_no_candidates_returns_none() -> None:
    data = _graph(_DATA)
    shapes = _graph(_SHAPES_NO_EXPLICIT_WIDGET)
    empty_scoring = _graph("@prefix ex: <http://example.org/> . ex:nothing ex:here ex:atAll .")

    widget = select_widget(
        EX.BirthDateProp, EX.alice,
        data_graph=data, shapes_graph=shapes, scoring_graph=empty_scoring, role="editor",
    )
    assert widget is None


# select_widgets() - the batch sibling: walks a NodeShape's own sh:property
# list and runs select_widget() once per property, returning one assembled
# graph of (property_shape, shui:editor|shui:viewer, widget) triples -
# mirrors this package's own evaluate() precedent (per-property-shape
# computation assembled into one graph) rather than one call per property.

_PERSON_DATA = """
    @prefix ex: <http://example.org/> .
    ex:alice a ex:Person ; ex:name "Alice" ;
        ex:birthDate "1990-01-01"^^<http://www.w3.org/2001/XMLSchema#date> .
"""

_PERSON_SHAPES_TWO_PROPS = """
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
    ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ;
        sh:property ex:NameProp, ex:BirthDateProp .
    ex:NameProp a sh:PropertyShape ; sh:path ex:name ; shui:editor shui:TextFieldEditor .
    ex:BirthDateProp a sh:PropertyShape ; sh:path ex:birthDate .
"""


def test_select_widgets_returns_graph_of_property_to_widget_assignments() -> None:
    data = _graph(_PERSON_DATA)
    shapes = _graph(_PERSON_SHAPES_TWO_PROPS)
    scoring = _graph("""
        @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
        [] a shui:WidgetScore ; shui:widget shui:DatePickerEditor ; shui:score 9.0 .
    """)

    result = select_widgets(
        EX.PersonShape, EX.alice,
        data_graph=data, shapes_graph=shapes, scoring_graph=scoring, role="editor",
    )
    assert (EX.NameProp, SHUI.editor, SHUI.TextFieldEditor) in result
    assert (EX.BirthDateProp, SHUI.editor, SHUI.DatePickerEditor) in result
    assert len(result) == 2


def test_select_widgets_omits_properties_with_no_widget() -> None:
    data = _graph(_PERSON_DATA)
    shapes = _graph(_PERSON_SHAPES_TWO_PROPS)
    empty_scoring = _graph("@prefix ex: <http://example.org/> . ex:nothing ex:here ex:atAll .")

    result = select_widgets(
        EX.PersonShape, EX.alice,
        data_graph=data, shapes_graph=shapes, scoring_graph=empty_scoring, role="editor",
    )
    # ex:NameProp still resolves (explicit shui:editor, no matcher to reject
    # it); ex:BirthDateProp has nothing scored and no explicit widget, so it
    # contributes no triple at all - absence, not an asserted null.
    assert (EX.NameProp, SHUI.editor, SHUI.TextFieldEditor) in result
    assert len(result) == 1


def test_select_widgets_respects_role() -> None:
    data = _graph(_PERSON_DATA)
    shapes = _graph("""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
        ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:property ex:NameProp .
        ex:NameProp a sh:PropertyShape ; sh:path ex:name ;
            shui:editor shui:TextFieldEditor ; shui:viewer shui:LabelViewer .
    """)
    empty_scoring = _graph("@prefix ex: <http://example.org/> . ex:nothing ex:here ex:atAll .")

    editor_result = select_widgets(
        EX.PersonShape, EX.alice,
        data_graph=data, shapes_graph=shapes, scoring_graph=empty_scoring, role="editor",
    )
    viewer_result = select_widgets(
        EX.PersonShape, EX.alice,
        data_graph=data, shapes_graph=shapes, scoring_graph=empty_scoring, role="viewer",
    )
    assert (EX.NameProp, SHUI.editor, SHUI.TextFieldEditor) in editor_result
    assert (EX.NameProp, SHUI.viewer, SHUI.LabelViewer) in viewer_result


def test_select_widgets_on_shape_with_no_properties_returns_empty_graph() -> None:
    data = _graph(_PERSON_DATA)
    shapes = _graph("""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:EmptyShape a sh:NodeShape ; sh:targetClass ex:Person .
    """)
    empty_scoring = _graph("@prefix ex: <http://example.org/> . ex:nothing ex:here ex:atAll .")

    result = select_widgets(
        EX.EmptyShape, EX.alice,
        data_graph=data, shapes_graph=shapes, scoring_graph=empty_scoring, role="editor",
    )
    assert len(result) == 0
