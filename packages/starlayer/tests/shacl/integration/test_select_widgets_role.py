"""``select_widgets(role=...)`` only considers widgets of that role from the scoring catalog (GitHub issue #9).

The draft's Select Function takes a widget predicate and its Score Function lists every ``shui:WidgetScore``, but its
Sections 4.1 and 4.2 pick an editor for ``shui:editor`` and a viewer for ``shui:viewer``, and the built-in scores are
written per role."""

import pytest
from rdflib import Namespace, URIRef
from starlayer import starontology
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl import ui_widget_selection as uws
from starlayer.shacl.ui_widget_selection import SHUI, select_widget, select_widgets

EX = Namespace("http://example.org/")
SHAPES = """
@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:property ex:P . ex:P a sh:PropertyShape ; sh:path ex:nick ."""
PREFIX = "@prefix shui: <http://www.w3.org/ns/shacl-ui#> . @prefix ex: <http://example.org/> .\n"


def _graph(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PREFIX + ttl, format="turtle12")
    return g


@pytest.fixture(scope="module")
def shapes():
    return _graph(SHAPES)


def _pick(shapes, catalog_ttl, role):
    return select_widgets(shape_node=EX.S, shapes_graph=shapes, scoring_graph=_graph(catalog_ttl), role=role)[EX.P]


# --- the three cases from the issue
def test_a_viewer_only_catalog_gives_no_editor(shapes):
    assert _pick(shapes, "[] a shui:WidgetScore ; shui:widget shui:LabelViewer ; shui:score 1.0 .", "editor") is None


def test_an_editor_only_catalog_gives_no_viewer(shapes):
    assert _pick(shapes, "[] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1.0 .", "viewer") is None


def test_a_higher_scoring_widget_of_the_other_role_does_not_win(shapes):
    catalog = (
        "[] a shui:WidgetScore ; shui:widget shui:LabelViewer ; shui:score 9.0 .\n"
        "[] a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1.0 ."
    )
    assert _pick(shapes, catalog, "editor") == SHUI.TextFieldEditor
    assert _pick(shapes, catalog, "viewer") == SHUI.LabelViewer


# --- what counts as an editor or a viewer
def test_one_catalog_serves_both_roles(shapes):
    catalog = (
        "[] a shui:WidgetScore ; shui:widget shui:IRIEditor ; shui:score 3.0 .\n"
        "[] a shui:WidgetScore ; shui:widget shui:IRIViewer ; shui:score 2.0 ."
    )
    assert (_pick(shapes, catalog, "editor"), _pick(shapes, catalog, "viewer")) == (SHUI.IRIEditor, SHUI.IRIViewer)


def test_a_widget_the_catalog_types_as_an_editor_is_an_editor(shapes):
    catalog = "ex:MyPicker a shui:Editor . [] a shui:WidgetScore ; shui:widget ex:MyPicker ; shui:score 1.0 ."
    assert _pick(shapes, catalog, "editor") == EX.MyPicker
    assert _pick(shapes, catalog, "viewer") is None


@pytest.mark.parametrize(
    ("declared", "role"),
    [("shui:SingleEditor", "editor"), ("shui:MultiEditor", "editor"), ("shui:SingleViewer", "viewer"), ("shui:MultiViewer", "viewer")],
)
def test_single_and_multi_classes_count(shapes, declared, role):
    catalog = f"ex:W a {declared} . [] a shui:WidgetScore ; shui:widget ex:W ; shui:score 1.0 ."
    other = "viewer" if role == "editor" else "editor"
    assert _pick(shapes, catalog, role) == EX.W
    assert _pick(shapes, catalog, other) is None


def test_a_widget_with_no_known_role_is_a_candidate_for_both(shapes):
    catalog = "[] a shui:WidgetScore ; shui:widget ex:CustomWidget ; shui:score 1.0 ."
    assert _pick(shapes, catalog, "editor") == EX.CustomWidget
    assert _pick(shapes, catalog, "viewer") == EX.CustomWidget


def test_the_type_may_be_declared_in_the_shapes_graph_instead():
    shapes = _graph(SHAPES + " ex:W a shui:Viewer .")
    catalog = "[] a shui:WidgetScore ; shui:widget ex:W ; shui:score 1.0 ."
    assert _pick(shapes, catalog, "viewer") == EX.W
    assert _pick(shapes, catalog, "editor") is None


def test_a_widget_the_shape_names_itself_is_not_checked_against_the_role():
    shapes = _graph(SHAPES + " ex:P shui:editor shui:LabelViewer .")
    assert select_widget(shape_node=EX.P, shapes_graph=shapes, role="editor") == SHUI.LabelViewer


def test_select_widget_single_applies_the_same_filter(shapes):
    catalog = _graph("[] a shui:WidgetScore ; shui:widget shui:LabelViewer ; shui:score 1.0 .")
    assert select_widget(shape_node=EX.P, shapes_graph=shapes, scoring_graph=catalog, role="editor") is None


# --- the built-in lists
def test_builtin_lists_match_the_widgets_the_shipped_shapes_document():
    graph = starontology.get_ontology_graph("shacl_shacl")
    documented = {
        s for s in set(graph.subjects()) if isinstance(s, URIRef) and str(s).startswith(str(SHUI))
        and str(s).endswith(("Editor", "Viewer")) and (s, URIRef("http://www.w3.org/ns/shacl#name"), None) in graph
    }
    # shui:editor/shui:viewer are properties, not widgets
    documented -= {SHUI.editor, SHUI.viewer}
    assert len(documented) == 26
    assert uws._BUILTIN_EDITORS | uws._BUILTIN_VIEWERS == documented
    assert not uws._BUILTIN_EDITORS & uws._BUILTIN_VIEWERS
    assert all(str(w).endswith("Editor") for w in uws._BUILTIN_EDITORS)
    assert all(str(w).endswith("Viewer") for w in uws._BUILTIN_VIEWERS)


def test_every_builtin_widget_is_only_a_candidate_for_its_own_role(shapes):
    for widget in uws._BUILTIN_EDITORS | uws._BUILTIN_VIEWERS:
        catalog = f"[] a shui:WidgetScore ; shui:widget <{widget}> ; shui:score 1.0 ."
        own = "editor" if widget in uws._BUILTIN_EDITORS else "viewer"
        other = "viewer" if own == "editor" else "editor"
        assert (_pick(shapes, catalog, own), _pick(shapes, catalog, other)) == (widget, None), widget


