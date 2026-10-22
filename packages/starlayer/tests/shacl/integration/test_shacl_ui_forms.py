"""The form shapes in ``shacl_shacl_ui`` (GitHub issues #12, #25): a node shape per kind of shape whose property shapes are the
form's fields, generated at build time from the overlay and checked for completeness against ``shacl_shacl``.

The build is a build-time tool, not part of the library: it lives in scripts/, which pytest puts on sys.path.
"""

import pytest
from build_meta_shapes import build_meta_shapes_graph
from build_shacl_ui import EXCLUDED, FORMS, STSH, build_shacl_ui_graph, form_fields, is_excluded, missing_fields, validated_predicates
from rdflib import RDF, Graph, Literal, URIRef
from rdflib.compare import to_isomorphic
from rdflib.namespace import XSD

from starlayer import starontology
from starlayer.shacl.ui_widget_selection import select_widgets

_SH = "http://www.w3.org/ns/shacl#"
SHUI = "http://www.w3.org/ns/shacl-ui#"


def sh(local: str) -> URIRef:
    return URIRef(_SH + local)


@pytest.fixture(scope="module")
def ui() -> Graph:
    return starontology.get_ontology_graph("shacl_shacl_ui")


@pytest.fixture(scope="module")
def shacl_shacl() -> Graph:
    return starontology.get_ontology_graph("shacl_shacl")


def fields_of(ui: Graph, form: URIRef) -> dict[URIRef, URIRef]:
    return {next(ui.objects(prop, sh("path"))): prop for prop in ui.objects(form, sh("property"))}


@pytest.mark.deferred
def test_the_stored_file_matches_a_fresh_build() -> None:
    """The library reads the stored shacl12-shacl-ui.ttl, so it must equal what the build produces. On failure run
    scripts/build_starontology.py (the overlay source or shacl_shacl changed)."""
    assert to_isomorphic(starontology.get_ontology_graph("shacl_shacl_ui")) == to_isomorphic(build_shacl_ui_graph())


def test_every_predicate_shacl_shacl_validates_is_a_field_of_a_form_or_excluded_with_a_reason(ui) -> None:
    """The completeness check: the forms cannot fall behind the validation shapes."""
    assert missing_fields(ui, build_meta_shapes_graph()) == set()
    assert all(reason for reason in EXCLUDED.values())


def test_an_exclusion_is_not_also_a_field(ui) -> None:
    """A predicate that is excluded because it belongs to another kind of node must not be a field of a shape's form."""
    fields = form_fields(ui)
    assert not [p for p in fields if is_excluded(p)], "an excluded predicate is a field: drop it from EXCLUDED or from the form"


def test_the_two_forms_exist_and_are_for_node_shapes_and_property_shapes(ui) -> None:
    for name, kind, _flag in FORMS:
        form = STSH[name]
        assert (form, RDF.type, sh("NodeShape")) in ui and (form, STSH.formFor, kind) in ui
    assert not list(ui.triples((None, sh("targetClass"), None))), "a form is applied to nothing, so loading it never changes what validates"
    assert not list(ui.triples((None, sh("targetNode"), None)))


def test_each_field_has_a_group_and_an_order_from_the_overlay(ui) -> None:
    for name, _kind, flag in FORMS:
        fields = fields_of(ui, STSH[name])
        assert len(fields) > 30, name
        for predicate, field in fields.items():
            assert (predicate, flag, Literal(True)) in ui, (name, predicate)
            if predicate not in (sh("path"),):
                assert list(ui.objects(field, sh("group"))) and len(list(ui.objects(field, sh("order")))) == 1, (name, predicate)


def test_a_property_shape_form_has_the_fields_a_form_was_missing(ui) -> None:
    """sh:path, sh:name, sh:order and sh:group sit in shacl_shacl in shapes that apply only when the node already has them, and
    sh:property in no property shape at all; a form needs all of them from the start."""
    prop_form, node_form = fields_of(ui, STSH.PropertyShapeForm), fields_of(ui, STSH.NodeShapeForm)
    for local in ("path", "name", "order", "group", "minCount", "maxCount", "datatype", "property"):
        assert sh(local) in prop_form, local
    assert URIRef(SHUI + "editor") in prop_form and URIRef(SHUI + "viewer") in prop_form, "a property shape's own widget fields"
    assert sh("path") not in node_form and sh("minCount") not in node_form, "path and cardinality belong to property shapes"
    assert sh("closed") in node_form and sh("property") in node_form


def test_a_field_takes_the_datatype_and_the_values_its_predicate_has_in_shacl_shacl(ui) -> None:
    fields = fields_of(ui, STSH.PropertyShapeForm)
    assert (fields[sh("minCount")], sh("datatype"), XSD.integer) in ui, "a minimum count is stored as an integer"
    node_kind = fields[sh("nodeKind")]
    listed = {str(o) for lst in ui.objects(node_kind, sh("in")) for o in ui.items(lst)}
    assert {_SH + "IRI", _SH + "Literal", _SH + "BlankNode"} <= listed, "an enumeration lists its values"
    assert (fields[sh("order")], sh("maxCount"), Literal(1)) in ui, "the form allows one value where the overlay says so"


def test_the_hand_written_forms_for_a_group_and_a_shapes_graph_are_there(ui) -> None:
    group, graph = fields_of(ui, STSH.PropertyGroupForm), fields_of(ui, STSH.ShapesGraphForm)
    assert {sh("name"), URIRef("http://www.w3.org/2000/01/rdf-schema#label"), sh("order")} <= set(group)
    assert {URIRef("http://www.w3.org/2000/01/rdf-schema#member"), URIRef("http://www.w3.org/2002/07/owl#imports")} <= set(graph)
    assert (STSH.PropertyGroupForm, STSH.formFor, sh("PropertyGroup")) in ui and (STSH.ShapesGraphForm, STSH.formFor, sh("ShapesGraph")) in ui


def test_select_widgets_gives_a_property_shape_form_its_widgets(ui) -> None:
    """The point of the forms: a tool passes one to select_widgets as shape_node, with the scoring layers."""
    scoring = Graph()
    for name in ("shacl_ui_baseline", "shacl_shacl_ui_scores"):
        for triple in starontology.get_ontology_graph(name):
            scoring.add(triple)
    widgets = select_widgets(shape_node=STSH.PropertyShapeForm, shapes_graph=ui, scoring_graph=scoring, role="editor")
    by_path = {next(ui.objects(prop, sh("path"))): str(widget).rsplit("#", 1)[-1] for prop, widget in widgets.items()}
    assert by_path[sh("minCount")] == "NumberFieldEditor"
    assert by_path[sh("nodeKind")] == "EnumSelectEditor"
    assert by_path[sh("deactivated")] == "BooleanEditor"
    assert by_path[sh("name")] == "TextFieldWithLangEditor"


def test_the_forms_change_nothing_about_what_validates(ui, shacl_shacl) -> None:
    from pyshacl.errors import ReportableRuntimeError

    from starlayer.shacl.meta_shapes import meta_validate

    bad, good = Graph(), Graph()
    prefixes = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    good.parse(data=prefixes + "ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .", format="turtle")
    bad.parse(data=prefixes + 'ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:minCount "x" ] .', format="turtle")
    assert meta_validate(good, extra_graphs=[ui])[0]
    with pytest.raises(ReportableRuntimeError):
        meta_validate(bad, extra_graphs=[ui])
