"""``select_widgets(per="shape")``: one answer per property shape, finished per node (GitHub issue #14).

A UI shows many nodes of the same shape. ``select_widgets`` used to redo, for every node, the checks that depend only on
the shape. With ``per="shape"`` those are done once; ``choice.resolve(node, data)`` validates only the conditions that read
a node's data. The answer must not change, so each is checked against ``select_widget`` for the same node."""

import pytest
from rdflib import Namespace
from starlayer import StarShaclSchema, starontology
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl import ui_widget_selection as uws
from starlayer.shacl.ui_widget_selection import (
    SHUI,
    WidgetChoice,
    check_data_matchers,
    select_widget,
    select_widgets,
)

EX = Namespace("http://example.org/")
PREFIXES = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix shui: <http://www.w3.org/ns/shacl-ui#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
)
SHAPES = PREFIXES + """
ex:S a sh:NodeShape ; sh:property ex:Note, ex:Age, ex:Title, ex:Pinned .
ex:Note sh:path ex:note ; sh:datatype xsd:string .
ex:Age sh:path ex:age ; sh:datatype xsd:integer .
ex:Title sh:path ex:title ; sh:datatype xsd:string .
ex:Pinned sh:path ex:pinned ; shui:editor shui:TextAreaEditor ."""
DATA = PREFIXES + """
ex:a ex:note "a note that is a good deal longer than twenty characters" ; ex:age 3 ; ex:title "Hello" .
ex:b ex:note "short" ; ex:age 4 ; ex:title "A title that is also rather long indeed, longer than forty chars" .
ex:c ex:pinned "x" ."""

# conditions that read data, on the score or on the widget's matcher, with and without a shape condition beside them
CATALOGS = {
    "no data conditions": PREFIXES + """
        [] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1 .
        [] a shui:WidgetScore ; shui:widget shui:NumberFieldEditor ; shui:score 2 ; shui:shapesGraphShape ex:Num .
        ex:Num a sh:NodeShape ; sh:property [ sh:path sh:datatype ; sh:hasValue xsd:integer ] .""",
    "a data condition on a score": PREFIXES + """
        [] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1 .
        [] a shui:WidgetScore ; shui:widget shui:TextAreaEditor ; shui:score 5 ; shui:dataGraphShape ex:Long .
        ex:Long a sh:NodeShape ; sh:property [ sh:path ex:note ; sh:minLength 20 ] .""",
    "shape and data conditions together": PREFIXES + """
        [] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1 .
        [] a shui:WidgetScore ; shui:widget shui:TextAreaEditor ; shui:score 5 ;
           shui:shapesGraphShape ex:Strings ; shui:dataGraphShape ex:Long .
        ex:Strings a sh:NodeShape ; sh:property [ sh:path sh:datatype ; sh:hasValue xsd:string ] .
        ex:Long a sh:NodeShape ; sh:property [ sh:path ex:title ; sh:minLength 40 ] .""",
    "a data condition on a per-widget matcher": PREFIXES + """
        [] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1 .
        [] a shui:WidgetScore ; shui:widget shui:TextAreaEditor ; shui:score 5 .
        [] a shui:WidgetAcceptMatcher ; shui:widget shui:TextAreaEditor ; shui:dataGraphShape ex:Long .
        ex:Long a sh:NodeShape ; sh:property [ sh:path ex:note ; sh:minLength 20 ] .""",
    "several data conditions, ranked": PREFIXES + """
        [] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1 .
        [] a shui:WidgetScore ; shui:widget shui:TextAreaEditor ; shui:score 5 ; shui:dataGraphShape ex:Long .
        [] a shui:WidgetScore ; shui:widget shui:RichTextEditor ; shui:score 9 ; shui:dataGraphShape ex:VeryLong .
        ex:Long a sh:NodeShape ; sh:property [ sh:path ex:note ; sh:minLength 20 ] .
        ex:VeryLong a sh:NodeShape ; sh:property [ sh:path ex:title ; sh:minLength 40 ] .""",
}


def _graph(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=ttl, format="turtle12")
    return g


@pytest.fixture(scope="module")
def shapes() -> StarLayerGraph:
    return _graph(SHAPES)


@pytest.fixture(scope="module")
def data() -> StarLayerGraph:
    return _graph(DATA)


@pytest.mark.parametrize("catalog_name", list(CATALOGS))
@pytest.mark.parametrize("role", ["editor", "viewer"])
def test_resolving_gives_the_same_widget_as_choosing_per_node(shapes, data, catalog_name, role) -> None:
    catalog = _graph(CATALOGS[catalog_name])
    choices = select_widgets(shape_node=EX.S, shapes_graph=shapes, scoring_graph=catalog, role=role, per="shape")
    assert set(choices) == {EX.Note, EX.Age, EX.Title, EX.Pinned}
    for prop, choice in choices.items():
        assert isinstance(choice, WidgetChoice)
        for node in (EX.a, EX.b, EX.c):
            expected = select_widget(
                shape_node=prop, focus_node=node, data_graph=data, shapes_graph=shapes, scoring_graph=catalog, role=role
            )
            assert choice.resolve(node, data) == expected, (catalog_name, role, prop, node)
            assert check_data_matchers(choice, focus_node=node, data_graph=data) == expected
        without_data = select_widget(shape_node=prop, shapes_graph=shapes, scoring_graph=catalog, role=role)
        assert choice.widget_without_data == without_data, (catalog_name, role, prop)


def test_with_no_data_condition_one_answer_serves_every_node(shapes, data) -> None:
    catalog = _graph(CATALOGS["no data conditions"])
    choices = select_widgets(shape_node=EX.S, shapes_graph=shapes, scoring_graph=catalog, role="editor", per="shape")
    assert not any(choice.needs_data for choice in choices.values())
    assert choices[EX.Age].widget_without_data == SHUI.NumberFieldEditor
    assert choices[EX.Note].widget_without_data == SHUI.TextFieldEditor
    assert all(len(choice.candidates) >= 1 for choice in choices.values())


def test_the_candidates_stop_at_the_first_one_that_needs_no_data(shapes) -> None:
    catalog = _graph(CATALOGS["several data conditions, ranked"])
    choice = select_widgets(shape_node=EX.S, shapes_graph=shapes, scoring_graph=catalog, role="editor", per="shape")[EX.Note]
    assert [c.widget for c in choice.candidates] == [SHUI.RichTextEditor, SHUI.TextAreaEditor, SHUI.TextFieldEditor]
    assert [c.needs_data for c in choice.candidates] == [True, True, False]
    assert choice.needs_data


def test_a_preference_is_the_first_candidate(shapes, data) -> None:
    catalog = _graph(CATALOGS["a data condition on a score"])
    choice = select_widgets(shape_node=EX.S, shapes_graph=shapes, scoring_graph=catalog, role="editor", per="shape")[EX.Pinned]
    assert choice.candidates[0].widget == SHUI.TextAreaEditor and choice.candidates[0].score is None
    assert not choice.needs_data
    assert choice.resolve(EX.c, data) == SHUI.TextAreaEditor


def test_the_shape_conditions_are_checked_once_however_many_nodes_follow(shapes, data, monkeypatch) -> None:
    """The cost the issue was about: per node, every shape condition is validated again; per shape, once."""
    catalog = _graph(CATALOGS["shape and data conditions together"])
    calls = []
    real = uws.validate
    monkeypatch.setattr(uws, "validate", lambda *a, **k: (calls.append(1), real(*a, **k))[1])

    def per_shape(nodes):
        calls.clear()
        choices = select_widgets(shape_node=EX.S, shapes_graph=shapes, scoring_graph=catalog, role="editor", per="shape")
        after_shape_checks = len(calls)
        for node in nodes:
            for choice in choices.values():
                choice.resolve(node, data)
        return after_shape_checks, len(calls)

    def per_node(nodes):
        calls.clear()
        for node in nodes:
            select_widgets(shape_node=EX.S, focus_node=node, data_graph=data, shapes_graph=shapes, scoring_graph=catalog, role="editor")
        return len(calls)

    shape_checks_1, total_1 = per_shape([EX.a])
    shape_checks_3, total_3 = per_shape([EX.a, EX.b, EX.c])
    assert shape_checks_1 == shape_checks_3, "shape checks must not grow with the number of nodes"
    assert total_3 < per_node([EX.a, EX.b, EX.c])


def test_per_shape_takes_no_node(shapes, data) -> None:
    catalog = _graph(CATALOGS["no data conditions"])
    with pytest.raises(ValueError, match="resolve"):
        select_widgets(shape_node=EX.S, focus_node=EX.a, data_graph=data, shapes_graph=shapes, scoring_graph=catalog, role="editor", per="shape")
    with pytest.raises(ValueError, match="per must be"):
        select_widgets(shape_node=EX.S, shapes_graph=shapes, scoring_graph=catalog, role="editor", per="everything")


def test_the_schema_method_passes_per_through(shapes, data) -> None:
    catalog = _graph(CATALOGS["a data condition on a score"])
    schema = StarShaclSchema(shacl_graph=shapes, data_graph=data, scoring_graph=catalog)
    choices = schema.select_widgets(shape_node=EX.S, role="editor", per="shape")
    assert choices[EX.Note].resolve(EX.a, data) == SHUI.TextAreaEditor
    assert choices[EX.Note].resolve(EX.b, data) == SHUI.TextFieldEditor


def test_the_generic_catalog_never_needs_a_node(shapes) -> None:
    """The shipped baseline has no data condition, so a UI can keep one answer per (shape, role)."""
    baseline = starontology.get_ontology_graph("shacl_ui_baseline")
    for role in ("editor", "viewer"):
        choices = select_widgets(shape_node=EX.S, shapes_graph=shapes, scoring_graph=baseline, role=role, per="shape")
        assert not any(choice.needs_data for choice in choices.values())
