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
        shape_node=EX.BirthDateProp, focus_node=EX.alice,
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
        shape_node=EX.BirthDateProp, focus_node=EX.alice,
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
        shape_node=EX.BirthDateProp, focus_node=EX.alice,
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
        shape_node=EX.BirthDateProp, focus_node=EX.alice,
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
        shape_node=EX.BirthDateProp, focus_node=EX.alice,
        data_graph=data, shapes_graph=shapes, scoring_graph=scoring, role="editor",
    )
    assert widget == SHUI.TextFieldEditor


def test_no_candidates_returns_none() -> None:
    data = _graph(_DATA)
    shapes = _graph(_SHAPES_NO_EXPLICIT_WIDGET)
    empty_scoring = _graph("@prefix ex: <http://example.org/> . ex:nothing ex:here ex:atAll .")

    widget = select_widget(
        shape_node=EX.BirthDateProp, focus_node=EX.alice,
        data_graph=data, shapes_graph=shapes, scoring_graph=empty_scoring, role="editor",
    )
    assert widget is None


# select_widgets() - the batch sibling: walks a NodeShape's own sh:property
# list and runs select_widget() once per property, returning one
# {property_shape: widget} dict rather than one call per property.

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


def test_select_widgets_returns_dict_of_property_to_widget() -> None:
    data = _graph(_PERSON_DATA)
    shapes = _graph(_PERSON_SHAPES_TWO_PROPS)
    scoring = _graph("""
        @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
        [] a shui:WidgetScore ; shui:widget shui:DatePickerEditor ; shui:score 9.0 .
    """)

    result = select_widgets(
        shape_node=EX.PersonShape, focus_node=EX.alice,
        data_graph=data, shapes_graph=shapes, scoring_graph=scoring, role="editor",
    )
    assert result.get(EX.NameProp) == SHUI.TextFieldEditor
    assert result.get(EX.BirthDateProp) == SHUI.DatePickerEditor
    assert len(result) == 2


def test_select_widgets_maps_properties_with_no_widget_to_none() -> None:
    data = _graph(_PERSON_DATA)
    shapes = _graph(_PERSON_SHAPES_TWO_PROPS)
    empty_scoring = _graph("@prefix ex: <http://example.org/> . ex:nothing ex:here ex:atAll .")

    result = select_widgets(
        shape_node=EX.PersonShape, focus_node=EX.alice,
        data_graph=data, shapes_graph=shapes, scoring_graph=empty_scoring, role="editor",
    )
    # ex:NameProp still resolves (explicit shui:editor, no matcher to reject
    # it); ex:BirthDateProp has nothing scored and no explicit widget, so it
    # maps to None, so the dict still lists every property of the shape.
    assert result == {EX.NameProp: SHUI.TextFieldEditor, EX.BirthDateProp: None}


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
        shape_node=EX.PersonShape, focus_node=EX.alice,
        data_graph=data, shapes_graph=shapes, scoring_graph=empty_scoring, role="editor",
    )
    viewer_result = select_widgets(
        shape_node=EX.PersonShape, focus_node=EX.alice,
        data_graph=data, shapes_graph=shapes, scoring_graph=empty_scoring, role="viewer",
    )
    assert editor_result.get(EX.NameProp) == SHUI.TextFieldEditor
    assert viewer_result.get(EX.NameProp) == SHUI.LabelViewer


def test_select_widgets_on_shape_with_no_properties_returns_empty_dict() -> None:
    data = _graph(_PERSON_DATA)
    shapes = _graph("""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:EmptyShape a sh:NodeShape ; sh:targetClass ex:Person .
    """)
    empty_scoring = _graph("@prefix ex: <http://example.org/> . ex:nothing ex:here ex:atAll .")

    result = select_widgets(
        shape_node=EX.EmptyShape, focus_node=EX.alice,
        data_graph=data, shapes_graph=shapes, scoring_graph=empty_scoring, role="editor",
    )
    assert result == {}


def test_scoring_graph_is_optional_when_widgets_are_fixed() -> None:
    data = StarLayerGraph()
    data.parse(data=_DATA, format="turtle")
    shapes = StarLayerGraph()
    shapes.parse(data=_SHAPES_EXPLICIT_WIDGET, format="turtle")
    widget = select_widget(
        shape_node=EX.BirthDateProp, focus_node=EX.alice, data_graph=data, shapes_graph=shapes, role="editor",
    )
    assert widget == SHUI.DatePickerEditor
    assignments = select_widgets(
        shape_node=EX.PersonShape, focus_node=EX.alice, data_graph=data, shapes_graph=shapes, role="editor",
    )
    assert assignments.get(EX.BirthDateProp) == SHUI.DatePickerEditor


def test_without_a_scoring_graph_a_property_with_no_explicit_widget_gets_none() -> None:
    data = StarLayerGraph()
    data.parse(data=_DATA, format="turtle")
    shapes = StarLayerGraph()
    shapes.parse(data=_SHAPES_NO_EXPLICIT_WIDGET, format="turtle")
    assert select_widget(
        shape_node=EX.BirthDateProp, focus_node=EX.alice, data_graph=data, shapes_graph=shapes, role="editor",
    ) is None
    assert select_widgets(
        shape_node=EX.PersonShape, focus_node=EX.alice, data_graph=data, shapes_graph=shapes, role="editor",
    ) == {EX.BirthDateProp: None}



def test_focus_node_and_data_graph_are_optional() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=_SHAPES_EXPLICIT_WIDGET, format="turtle")
    assert select_widget(shape_node=EX.BirthDateProp, shapes_graph=shapes, role="editor") == SHUI.DatePickerEditor
    assert select_widgets(shape_node=EX.PersonShape, shapes_graph=shapes, role="editor") == {
        EX.BirthDateProp: SHUI.DatePickerEditor
    }


def test_focus_node_without_data_graph_is_rejected() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=_SHAPES_EXPLICIT_WIDGET, format="turtle")
    with pytest.raises(ValueError):
        select_widget(shape_node=EX.BirthDateProp, focus_node=EX.alice, shapes_graph=shapes, role="editor")


def test_without_a_focus_node_a_data_only_matcher_rejects_its_widget() -> None:
    """Section 3.4 step 1: no focus node, a dataGraphShape and no shapesGraphShape -> false."""
    shapes = _graph(_SHAPES_NO_EXPLICIT_WIDGET)
    scoring = _graph("""
        @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://example.org/> .
        [] a shui:WidgetScore ; shui:widget shui:DatePickerEditor ; shui:score 9.0 .
        [] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 3.0 .
        [] a shui:WidgetAcceptMatcher ; shui:widget shui:DatePickerEditor ;
            shui:dataGraphShape ex:AlwaysConforms .
        ex:AlwaysConforms a sh:NodeShape .
    """)
    assert select_widget(
        shape_node=EX.BirthDateProp, shapes_graph=shapes, scoring_graph=scoring, role="editor",
    ) == SHUI.TextFieldEditor
    # with a focus node the same matcher accepts
    assert select_widget(
        shape_node=EX.BirthDateProp, focus_node=EX.alice, data_graph=_graph(_DATA), shapes_graph=shapes, scoring_graph=scoring, role="editor",
    ) == SHUI.DatePickerEditor


def test_shapes_graph_shape_checks_the_property_shape_in_the_shapes_graph() -> None:
    """The shape node is validated in the shapes graph; the shape itself is read from the scoring graph."""
    shapes = _graph("""
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
        ex:EventShape a sh:NodeShape ; sh:property ex:StartProp, ex:TitleProp .
        ex:StartProp a sh:PropertyShape ; sh:path ex:start ; sh:datatype xsd:date .
        ex:TitleProp a sh:PropertyShape ; sh:path ex:title ; sh:datatype xsd:string .
    """)
    scoring = _graph("""
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
        [] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1.0 .
        [] a shui:WidgetScore ; shui:widget shui:DatePickerEditor ; shui:score 9.0 .
        [] a shui:WidgetAcceptMatcher ; shui:widget shui:DatePickerEditor ; shui:shapesGraphShape ex:DateProperty .
        ex:DateProperty a sh:NodeShape ; sh:property [ sh:path sh:datatype ; sh:hasValue xsd:date ] .
    """)
    assert select_widgets(shape_node=EX.EventShape, shapes_graph=shapes, scoring_graph=scoring, role="editor") == {
        EX.StartProp: SHUI.DatePickerEditor,
        EX.TitleProp: SHUI.TextFieldEditor,
    }


def test_equal_scores_are_ordered_by_widget_iri() -> None:
    shapes = _graph(_SHAPES_NO_EXPLICIT_WIDGET)
    scoring = _graph("""
        @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
        [] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 5.0 .
        [] a shui:WidgetScore ; shui:widget shui:DatePickerEditor ; shui:score 5.0 .
    """)
    assert select_widget(
        shape_node=EX.BirthDateProp, shapes_graph=shapes, scoring_graph=scoring, role="editor",
    ) == SHUI.DatePickerEditor


def test_schema_method_uses_the_bound_shapes_graph() -> None:
    from starlayer.shacl import StarShaclSchema

    shapes = _graph(_PERSON_SHAPES_TWO_PROPS)
    scoring = _graph("""
        @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
        [] a shui:WidgetScore ; shui:widget shui:DatePickerEditor ; shui:score 9.0 .
    """)
    schema = StarShaclSchema(shapes)
    assert schema.select_widgets(shape_node=EX.PersonShape, role="editor", scoring_graph=scoring) == {
        EX.NameProp: SHUI.TextFieldEditor,
        EX.BirthDateProp: SHUI.DatePickerEditor,
    }
    assert schema.select_widgets(shape_node=EX.PersonShape, role="editor") == {
        EX.NameProp: SHUI.TextFieldEditor,
        EX.BirthDateProp: None,
    }


def test_schema_method_falls_back_to_the_bound_data_graph_for_a_focus_node() -> None:
    from starlayer.shacl import StarShaclSchema

    data = _graph(_PERSON_DATA)
    shapes = _graph(_PERSON_SHAPES_TWO_PROPS)
    with_data = StarShaclSchema(shapes, data_graph=data)
    assert with_data.select_widgets(shape_node=EX.PersonShape, focus_node=EX.alice, role="editor")[EX.NameProp] == SHUI.TextFieldEditor
    with pytest.raises(ValueError):
        StarShaclSchema(shapes).select_widgets(shape_node=EX.PersonShape, focus_node=EX.alice, role="editor")
    with pytest.raises(ValueError):
        StarShaclSchema().select_widgets(shape_node=EX.PersonShape, role="editor")


def test_schema_scoring_graph_can_be_bound_and_overridden_per_call() -> None:
    from starlayer.shacl import StarShaclSchema

    shapes = _graph(_PERSON_SHAPES_TWO_PROPS)
    bound = _graph("""
        @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
        [] a shui:WidgetScore ; shui:widget shui:DatePickerEditor ; shui:score 9.0 .
    """)
    other = _graph("""
        @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
        [] a shui:WidgetScore ; shui:widget shui:TextAreaEditor ; shui:score 9.0 .
    """)
    schema = StarShaclSchema(shapes, scoring_graph=bound)
    # bound catalog used when the call gives none
    assert schema.select_widgets(shape_node=EX.PersonShape, role="editor")[EX.BirthDateProp] == SHUI.DatePickerEditor
    # a per-call catalog overrides it
    assert schema.select_widgets(
        shape_node=EX.PersonShape, role="editor", scoring_graph=other
    )[EX.BirthDateProp] == SHUI.TextAreaEditor
    # an empty graph switches the bound catalog off for one call
    assert schema.select_widgets(
        shape_node=EX.PersonShape, role="editor", scoring_graph=StarLayerGraph()
    )[EX.BirthDateProp] is None


def test_schema_data_graph_can_be_overridden_per_call() -> None:
    from starlayer.shacl import StarShaclSchema

    shapes = _graph("""
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
        ex:PersonShape a sh:NodeShape ; sh:property ex:NameProp .
        ex:NameProp a sh:PropertyShape ; sh:path ex:name .
        ex:LongName a sh:NodeShape ; sh:property [ sh:path ex:name ; sh:minLength 10 ] .
    """)
    catalog = _graph("""
        @prefix ex: <http://example.org/> . @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
        [] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1.0 .
        [] a shui:WidgetScore ; shui:widget shui:TextAreaEditor ; shui:score 9.0 .
        [] a shui:WidgetAcceptMatcher ; shui:widget shui:TextAreaEditor ; shui:dataGraphShape ex:LongName .
    """)
    short = _graph('@prefix ex: <http://example.org/> . ex:p ex:name "Al" .')
    long = _graph('@prefix ex: <http://example.org/> . ex:p ex:name "Alexander the Great" .')
    schema = StarShaclSchema(shapes, data_graph=short, scoring_graph=catalog)
    call = dict(shape_node=EX.PersonShape, focus_node=EX.p, role="editor")
    assert schema.select_widgets(**call)[EX.NameProp] == SHUI.TextFieldEditor
    assert schema.select_widgets(**call, data_graph=long)[EX.NameProp] == SHUI.TextAreaEditor
