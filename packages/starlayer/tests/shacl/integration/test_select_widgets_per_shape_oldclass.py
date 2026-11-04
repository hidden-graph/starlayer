"""``select_widgets(per="shape")``: one answer per property shape, finished per node (GitHub issue #14).

A UI shows many nodes of the same shape. ``select_widgets`` used to redo, for every node, the checks that depend only on
the shape. With ``per="shape"`` those are done once; ``choice.resolve(node, data)`` validates only the conditions that read
a node's data. The answer must not change, so each is checked against ``select_widget`` for the same node."""

import pytest
from rdflib import Namespace
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl import ui_widget_selection as uws
from starlayer.shacl.ui_widget_selection import (
    SHUI,
    select_widget,
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












def test_the_default_score_is_the_configured_one_and_a_higher_catalog_score_then_wins(shapes) -> None:
    catalog = _graph(PREFIXES + "[] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 50 . [] a shui:WidgetScore ; shui:widget shui:NumberFieldEditor ; shui:score 5 .")
    assert select_widget(shape_node=EX.Pinned, shapes_graph=shapes, scoring_graph=catalog, role="editor") == SHUI.TextFieldEditor, "50 beats the default 40"
    configured = _graph(SHAPES + "\nex:config a shui:Configuration ; shui:defaultWidgetScore 60 .")
    assert uws.default_widget_score(configured) == 60.0 and uws.default_widget_score(shapes) == 40.0
    assert select_widget(shape_node=EX.Pinned, shapes_graph=configured, scoring_graph=catalog, role="editor") == SHUI.TextAreaEditor, "60 beats 50"
    negative = _graph(SHAPES + "\nex:config a shui:Configuration ; shui:defaultWidgetScore -1 .")
    assert select_widget(shape_node=EX.Pinned, shapes_graph=negative, scoring_graph=catalog, role="editor") == SHUI.TextFieldEditor, "a negative score ranks below the rest"








