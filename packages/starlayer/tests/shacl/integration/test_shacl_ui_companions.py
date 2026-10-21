"""The two UI companions of shacl_shacl: ``shacl_shacl_ui`` (how to present the SHACL vocabulary in a form, GitHub issue
#12) and ``shacl_ui_baseline`` (a scoring catalog that picks a widget from a property shape, issue #10)."""

import warnings

import pytest
from pyshacl.errors import ReportableRuntimeError
from rdflib import RDF, Graph, Namespace
from starlayer import starontology
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl import StarShaclSchema
from starlayer.shacl import ui_widget_selection as uws
from starlayer.shacl.meta_shapes import meta_validate
from starlayer.shacl.ui_widget_selection import SHUI, select_widget, select_widgets

SH = Namespace("http://www.w3.org/ns/shacl#")
STSH = Namespace("https://github.com/hidden-graph/starlayer/ns/shacl#")
EX = Namespace("http://example.org/")


@pytest.fixture(scope="module")
def overlay() -> Graph:
    return starontology.get_ontology_graph("shacl_shacl_ui")


@pytest.fixture(scope="module")
def baseline() -> Graph:
    return starontology.get_ontology_graph("shacl_ui_baseline")


@pytest.fixture(scope="module")
def shacl_shacl() -> Graph:
    return starontology.get_ontology_graph("shacl_shacl")


# --------------------------------------------------------------------------- the overlay
def test_the_overlay_is_a_well_formed_shapes_graph_alone_and_with_shacl_shacl(overlay, shacl_shacl) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        meta_validate(overlay)
        merged = Graph()
        merged += shacl_shacl
        merged += overlay
        meta_validate(merged)


def test_loading_the_overlay_never_changes_what_validates(overlay) -> None:
    """It adds no constraints: the same shapes graphs are accepted and rejected with and without it."""
    good, bad = Graph(), Graph()
    prefixes = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    good.parse(data=prefixes + "ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .", format="turtle")
    bad.parse(data=prefixes + 'ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:minCount "x" ] .', format="turtle")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert meta_validate(good)[0] and meta_validate(good, extra_graphs=[overlay])[0]
        for extra in ((), (overlay,)):
            with pytest.raises(ReportableRuntimeError):
                meta_validate(bad, extra_graphs=extra)


def test_the_overlay_defines_its_property_groups(overlay) -> None:
    groups = set(overlay.subjects(RDF.type, SH.PropertyGroup))
    assert len(groups) == 18
    for group in groups:
        assert list(overlay.objects(group, SH.name)) and len(list(overlay.objects(group, SH.order))) == 1
    used = set(overlay.objects(None, SH.group))
    assert used <= groups, f"sh:group names a group the overlay does not define: {used - groups}"


def test_every_predicate_has_one_order(overlay) -> None:
    """SHACL gives sh:order a single value; sh:name and sh:description once had two (GitHub issue #12 work)."""
    for subject in set(overlay.subjects(SH.order, None)):
        assert len(list(overlay.objects(subject, SH.order))) == 1, subject


def test_the_overlay_hints_are_built_in_editors(overlay) -> None:
    editors = set(overlay.objects(None, SHUI.editor))
    assert editors and editors <= uws._BUILTIN_EDITORS, editors - uws._BUILTIN_EDITORS


def test_the_overlay_alone_gives_a_form_for_editing_a_shape(overlay) -> None:
    widgets = select_widgets(shape_node=STSH.ShapeEditorShape, shapes_graph=overlay, role="editor")
    by_path = {next(overlay.objects(prop, SH.path)): widget for prop, widget in widgets.items()}
    assert len(widgets) == 86 and sum(w is not None for w in widgets.values()) == 66
    assert by_path[SH.order] == SHUI.NumberFieldEditor
    assert by_path[SH.minCount] == SHUI.NumberFieldEditor
    assert by_path[SH.closed] == SHUI.BooleanEditor
    assert by_path[SH.nodeKind] == SHUI.EnumSelectEditor
    assert by_path[SH.name] == SHUI.TextFieldWithLangEditor
    # the rest need a widget the built-in set has no match for, and say so with stsh:widgetType
    unhinted = [prop for prop, widget in widgets.items() if widget is None]
    assert len(unhinted) == 20 and all(list(overlay.objects(prop, STSH.widgetType)) for prop in unhinted)


def test_the_overlays_preferences_win_with_the_baseline_catalog(overlay, baseline) -> None:
    """A widget a shape names itself wins. (The first baseline had a matcher per widget, which could reject a named
    widget and override it; the baseline now has none, so the overlay's preferences stand with it.)"""
    alone = select_widgets(shape_node=STSH.ShapeEditorShape, shapes_graph=overlay, role="editor")
    with_catalog = select_widgets(
        shape_node=STSH.ShapeEditorShape, shapes_graph=overlay, scoring_graph=baseline, role="editor"
    )
    by_path = {next(overlay.objects(prop, SH.path)): widget for prop, widget in with_catalog.items()}
    assert by_path[SH.order] == SHUI.NumberFieldEditor
    assert all(with_catalog[prop] == widget for prop, widget in alone.items() if widget is not None)


# --------------------------------------------------------------------------- the baseline catalog
def test_the_baseline_is_a_well_formed_shapes_graph(baseline) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        meta_validate(baseline)


def test_the_baseline_scores_are_well_formed_widget_scores(baseline, shacl_shacl) -> None:
    result = StarShaclSchema(shacl_graph=shacl_shacl).validate(data_graph=baseline, ignore_imports=True)
    assert result.conforms


def test_every_widget_in_the_baseline_has_a_known_role(baseline) -> None:
    widgets = {w for score in baseline.subjects(RDF.type, SHUI.WidgetScore) for w in baseline.objects(score, SHUI.widget)}
    assert len(widgets) == 12
    assert all(uws._widget_roles(w) for w in widgets), [w for w in widgets if not uws._widget_roles(w)]
    assert {w for w in widgets if "editor" in uws._widget_roles(w)} and {w for w in widgets if "viewer" in uws._widget_roles(w)}


def test_the_baseline_has_three_tiers_and_no_per_widget_matchers(baseline) -> None:
    """Tier 1 matches everything (no condition), tier 2 is by datatype, tier 3 by a constraint; the conditions sit on
    the scores, and there is no shui:WidgetAcceptMatcher (a shared gate a layer on top could not undo)."""
    assert not list(baseline.subjects(RDF.type, SHUI.WidgetAcceptMatcher))
    by_tier = {1: [], 2: [], 3: []}
    for score in baseline.subjects(RDF.type, SHUI.WidgetScore):
        by_tier[int(next(baseline.objects(score, SHUI.score)))].append(score)
    assert {tier: len(scores) for tier, scores in by_tier.items()} == {1: 2, 2: 6, 3: 4}
    assert all(not list(baseline.objects(score, SHUI.shapesGraphShape)) for score in by_tier[1])
    assert all(len(list(baseline.objects(score, SHUI.shapesGraphShape))) == 1 for score in by_tier[2] + by_tier[3])


SHAPES = """
@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
ex:S a sh:NodeShape ; sh:property ex:age, ex:active, ex:born, ex:stamp, ex:kind, ex:boss, ex:home, ex:note, ex:title, ex:pinned, ex:both .
ex:age sh:path ex:age ; sh:datatype xsd:integer . ex:active sh:path ex:active ; sh:datatype xsd:boolean .
ex:born sh:path ex:born ; sh:datatype xsd:date . ex:stamp sh:path ex:stamp ; sh:datatype xsd:dateTime .
ex:kind sh:path ex:kind ; sh:datatype xsd:string ; sh:in ( "a" "b" ) .
ex:boss sh:path ex:boss ; sh:class ex:Person . ex:home sh:path ex:home ; sh:nodeKind sh:IRI .
ex:both sh:path ex:both ; sh:nodeKind sh:IRI ; sh:class ex:Person .
ex:note sh:path ex:note . ex:title sh:path ex:title ; sh:datatype rdf:langString .
ex:pinned sh:path ex:pinned ; shui:editor shui:TextAreaEditor ."""

# one catalog, both roles: editors for role="editor", viewers for role="viewer"
EDITORS = {
    EX.age: SHUI.NumberFieldEditor, EX.active: SHUI.BooleanEditor, EX.born: SHUI.DatePickerEditor,
    EX.stamp: SHUI.DateTimePickerEditor, EX.kind: SHUI.EnumSelectEditor, EX.boss: SHUI.InstancesSelectEditor,
    EX.home: SHUI.IRIEditor, EX.both: SHUI.InstancesSelectEditor, EX.note: SHUI.TextFieldEditor,
    EX.title: SHUI.TextFieldWithLangEditor, EX.pinned: SHUI.TextAreaEditor,
}
VIEWERS = {
    EX.age: SHUI.LiteralViewer, EX.active: SHUI.LiteralViewer, EX.born: SHUI.LiteralViewer,
    EX.stamp: SHUI.LiteralViewer, EX.kind: SHUI.LiteralViewer, EX.boss: SHUI.LabelViewer,
    EX.home: SHUI.LabelViewer, EX.both: SHUI.LabelViewer, EX.note: SHUI.LiteralViewer,
    EX.title: SHUI.LangStringViewer, EX.pinned: SHUI.LiteralViewer,
}


@pytest.fixture(scope="module")
def shapes() -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=SHAPES, format="turtle12")
    return g


def test_one_baseline_catalog_serves_both_roles(shapes, baseline) -> None:
    for role, expected in (("editor", EDITORS), ("viewer", VIEWERS)):
        got = select_widgets(shape_node=EX.S, shapes_graph=shapes, scoring_graph=baseline, role=role)
        assert got == expected, role


def test_a_widget_a_shape_names_wins_over_the_baseline(shapes, baseline) -> None:
    assert select_widget(shape_node=EX.pinned, shapes_graph=shapes, scoring_graph=baseline, role="editor") == SHUI.TextAreaEditor


def test_without_the_baseline_a_property_that_names_no_widget_gets_none(shapes) -> None:
    assert select_widgets(shape_node=EX.S, shapes_graph=shapes, role="editor")[EX.age] is None
