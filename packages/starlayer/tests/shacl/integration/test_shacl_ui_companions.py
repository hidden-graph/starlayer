"""The two UI companions of shacl_shacl: ``shacl_shacl_ui`` (how to present the SHACL vocabulary in a form, GitHub issue
#12) and ``shacl_ui_baseline`` (a scoring catalog that picks a widget from a property shape, issue #10)."""

import warnings

import pytest
from pyshacl.errors import ReportableRuntimeError
from rdflib import RDF, Graph, Namespace, URIRef
from rdflib.collection import Collection
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
    assert len(groups) == 21
    for group in groups:
        assert list(overlay.objects(group, SH.name)) and len(list(overlay.objects(group, SH.order))) == 1
    used = set(overlay.objects(None, SH.group))
    assert used <= groups, f"sh:group names a group the overlay does not define: {used - groups}"


def test_every_predicate_has_one_order(overlay) -> None:
    """SHACL gives sh:order a single value; sh:name and sh:description once had two (GitHub issue #12 work)."""
    for subject in set(overlay.subjects(SH.order, None)):
        assert len(list(overlay.objects(subject, SH.order))) == 1, subject


def test_the_overlay_contains_no_widget(overlay) -> None:
    """Widget choice is scoring, in shacl_shacl_ui_scores; the overlay holds sections, order and form flags only. The 20
    stsh:widgetType fields (no built-in widget fits) were dropped: an application layer can bring them back."""
    assert not list(overlay.triples((None, SHUI.editor, None)))
    assert not list(overlay.triples((None, SHUI.viewer, None)))
    assert not list(overlay.triples((None, STSH.widgetType, None)))
    assert (STSH.ShapeEditorShape, RDF.type, SH.NodeShape) not in overlay


# --------------------------------------------------------------------------- the shacl_shacl scoring layer
@pytest.fixture(scope="module")
def scores() -> Graph:
    return starontology.get_ontology_graph("shacl_shacl_ui_scores")


@pytest.fixture(scope="module")
def stacked(baseline, scores) -> Graph:
    """The generic catalog plus the SHACL layer: the caller combines scoring graphs, and higher scores win."""
    graph = Graph()
    graph += baseline
    graph += scores
    return graph


def test_the_scores_layer_is_well_formed(scores, shacl_shacl) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        meta_validate(scores)
    assert StarShaclSchema(shacl_graph=shacl_shacl).validate(data_graph=scores, ignore_imports=True).conforms


def _paths_by_widget(scores) -> dict:
    out = {}
    for score in scores.subjects(RDF.type, SHUI.WidgetScore):
        widget = next(scores.objects(score, SHUI.widget))
        condition = next(scores.objects(score, SHUI.shapesGraphShape))
        listed = next(scores.objects(next(scores.objects(condition, SH.property)), SH["in"]))
        out[widget] = set(Collection(scores, listed))
    return out


def test_the_scores_layer_is_nine_editor_scores_at_forty(scores) -> None:
    entries = list(scores.subjects(RDF.type, SHUI.WidgetScore))
    assert len(entries) == 9
    assert {int(next(scores.objects(score, SHUI.score))) for score in entries} == {40}
    widgets = {next(scores.objects(score, SHUI.widget)) for score in entries}
    assert widgets <= uws._BUILTIN_EDITORS and len(widgets) == 9, "an application layer uses standard shui widgets only"
    assert not list(scores.subjects(RDF.type, SHUI.WidgetAcceptMatcher))


def test_no_predicate_is_scored_by_two_widgets(scores) -> None:
    """Two scores of the same value for one predicate would tie, and a tie goes to the widget IRI."""
    by_widget = _paths_by_widget(scores)
    all_paths = [path for paths in by_widget.values() for path in paths]
    assert len(all_paths) == 75 and len(set(all_paths)) == 75  # 66, plus the 8 paths of the new fields (issues #91, #105), plus sh:expression


def test_the_layer_gives_a_form_for_editing_a_shape(shacl_shacl, baseline, stacked) -> None:
    shape = URIRef("http://www.w3.org/ns/shacl-shacl#ShapeShape")

    def by_path(scoring):
        widgets = select_widgets(shape_node=shape, shapes_graph=shacl_shacl, scoring_graph=scoring, role="editor")
        return {next(shacl_shacl.objects(prop, SH.path)): widget for prop, widget in widgets.items()}

    generic, with_layer = by_path(baseline), by_path(stacked)
    assert with_layer[SH.closed] == SHUI.BooleanEditor
    assert with_layer[SH.minInclusive] == SHUI.NumberFieldEditor
    assert with_layer[SH.severity] == SHUI.EnumSelectEditor
    assert with_layer[SH["class"]] == SHUI.InstancesSelectEditor
    assert with_layer[SH.memberShape] == SHUI.DetailsEditor
    # IRI-valued targets get the IRI editor; sh:targetNode may hold a literal (SHACL 1.0 section 2.1.3), so a text field
    for iri_only in (SH.targetClass, SH.targetSubjectsOf, SH.targetObjectsOf):
        assert with_layer[iri_only] == SHUI.IRIEditor, iri_only
    assert with_layer[SH.targetNode] == SHUI.TextFieldEditor
    assert generic[SH.closed] == SHUI.TextFieldEditor  # the layer is what makes the difference
    assert sum(generic[p] != with_layer[p] for p in generic) >= 10


def test_the_layer_does_not_touch_other_shapes_or_viewers(shapes, baseline, stacked) -> None:
    for role in ("editor", "viewer"):
        assert select_widgets(shape_node=EX.S, shapes_graph=shapes, scoring_graph=stacked, role=role) == select_widgets(
            shape_node=EX.S, shapes_graph=shapes, scoring_graph=baseline, role=role
        )
    shacl_shape = URIRef("http://www.w3.org/ns/shacl-shacl#ShapeShape")
    viewers = select_widgets(shape_node=shacl_shape, shapes_graph=starontology.get_ontology_graph("shacl_shacl"), scoring_graph=stacked, role="viewer")
    assert all(widget in uws._BUILTIN_VIEWERS or widget is None for widget in viewers.values())


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
