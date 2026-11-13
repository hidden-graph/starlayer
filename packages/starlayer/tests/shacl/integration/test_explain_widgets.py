"""``explain_widgets``: every candidate widget of a property shape with the conditions behind it, consistent with ``select_widget``."""

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl import WidgetTrace, explain_widgets, select_widget
from starlayer.shacl.engine.terms import NS

EX = NS("http://example.org/")
SHUI = NS("http://www.w3.org/ns/shacl-ui/")
PREFIXES = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix shui: <http://www.w3.org/ns/shacl-ui/> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
)
SHAPES = PREFIXES + """
ex:S a sh:NodeShape ; sh:property ex:Note, ex:Age, ex:Pinned .
ex:Note sh:path ex:note ; sh:datatype xsd:string .
ex:Age sh:path ex:age ; sh:datatype xsd:integer .
ex:Pinned sh:path ex:pinned ; shui:editor shui:TextAreaEditor ."""
DATA = PREFIXES + """
ex:a ex:note "a note that is a good deal longer than twenty characters" ; ex:age 3 .
ex:b ex:note "short" ; ex:age 4 ."""
SCORING = PREFIXES + """
[] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1 .
[] a shui:WidgetScore ; shui:widget shui:NumberFieldEditor ; shui:score 2 ; shui:shapesGraphShape ex:Num .
[] a shui:WidgetScore ; shui:widget shui:TextAreaEditor ; shui:score 5 ; shui:dataGraphShape ex:Long .
ex:Num a sh:NodeShape ; sh:property [ sh:path sh:datatype ; sh:hasValue xsd:integer ] .
ex:Long a sh:NodeShape ; sh:property [ sh:path ex:note ; sh:minLength 20 ] ."""


def _graph(ttl):
    g = StarLayerGraph()
    g.parse(data=ttl, format="turtle12")
    return g


@pytest.fixture(scope="module")
def graphs():
    return _graph(SHAPES), _graph(SCORING), _graph(DATA)


def _trace(graphs, shape, **kw):
    shapes, scoring, data = graphs
    return explain_widgets(shape_node=shape, shapes_graph=shapes, scoring_graph=scoring, role="editor", **kw)


def test_candidates_are_in_rank_order_with_their_scores(graphs):
    trace = _trace(graphs, EX.Age)
    assert isinstance(trace, WidgetTrace) and trace.shape_node == EX.Age and trace.role == "editor"
    assert [c.widget for c in trace.candidates] == [SHUI.TextAreaEditor, SHUI.NumberFieldEditor, SHUI.TextFieldEditor]
    assert [c.score for c in trace.candidates] == [5, 2, 1] and all(c.scored for c in trace.candidates)


def test_a_shape_condition_that_fails_rejects_the_candidate(graphs):
    note = {c.widget: c for c in _trace(graphs, EX.Note).candidates}
    number = note[SHUI.NumberFieldEditor]
    assert number.outcome == "rejected"
    (condition,) = number.conditions
    assert condition.kind == "score" and condition.shape == EX.Num and condition.shape_holds is False and condition.blocks == "shape"
    age = {c.widget: c for c in _trace(graphs, EX.Age).candidates}
    assert age[SHUI.NumberFieldEditor].outcome == "accepted" and age[SHUI.NumberFieldEditor].conditions[0].shape_holds is True


def test_a_data_condition_alone_is_decided_per_node_or_blocks_without_one(graphs):
    area = {c.widget: c for c in _trace(graphs, EX.Age).candidates}[SHUI.TextAreaEditor]
    (condition,) = area.conditions
    assert condition.data_shape == EX.Long and condition.shape is None and condition.blocks == "data" and area.outcome == "rejected"


def test_data_conditions_are_tried_on_the_sampled_focus_nodes(graphs):
    shapes, scoring, data = graphs
    trace = _trace(graphs, EX.Note, data_graph=data, focus_nodes=[EX.a, EX.b])
    area = {c.widget: c for c in trace.candidates}[SHUI.TextAreaEditor]
    assert area.conditions[0].data_holds == (1, 2)
    assert _trace(graphs, EX.Note, data_graph=data, focus_nodes=[EX.a, EX.b], sample=1).candidates[0].conditions[0].data_holds == (1, 1)
    assert _trace(graphs, EX.Note).candidates[0].conditions[0].data_holds is None  # no data given: nothing counted


def test_a_widget_the_shape_names_ranks_with_the_default_score(graphs):
    trace = _trace(graphs, EX.Pinned)
    assert trace.named == (SHUI.TextAreaEditor,)
    assert trace.default_score == 40.0
    scored = {c.widget: c for c in trace.candidates}[SHUI.TextAreaEditor]
    assert scored.scored is True  # the scoring graph scores it too, so its own score ranks
    shapes, scoring, _ = graphs
    bare = explain_widgets(shape_node=EX.Pinned, shapes_graph=shapes, scoring_graph=_graph(PREFIXES), role="editor")
    assert [(c.widget, c.score, c.scored) for c in bare.candidates] == [(SHUI.TextAreaEditor, 40.0, False)]


@pytest.mark.parametrize("shape", [EX.Note, EX.Age, EX.Pinned])
def test_the_first_candidate_that_stands_is_what_select_widget_picks_without_data(graphs, shape):
    shapes, scoring, _ = graphs
    chosen = select_widget(shape_node=shape, shapes_graph=shapes, scoring_graph=scoring, role="editor")
    first = next((c.widget for c in _trace(graphs, shape).candidates if c.outcome != "rejected"), None)
    assert first == chosen


def test_the_viewer_role_and_errors(graphs):
    shapes, scoring, _ = graphs
    assert explain_widgets(shape_node=EX.Age, shapes_graph=shapes, scoring_graph=scoring, role="viewer").role == "viewer"
    with pytest.raises(ValueError, match="role"):
        explain_widgets(shape_node=EX.Age, shapes_graph=shapes, scoring_graph=scoring, role="reader")
    with pytest.raises(ValueError, match="not a subject"):
        explain_widgets(shape_node=EX.Missing, shapes_graph=shapes, scoring_graph=scoring, role="editor")
