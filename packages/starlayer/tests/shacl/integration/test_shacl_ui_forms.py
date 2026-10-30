"""The form shapes in ``shacl_shacl_ui`` (GitHub issues #12, #25): a node shape per kind of shape whose property shapes are the
form's fields, generated at build time from the overlay and checked for completeness against ``shacl_shacl``.

The build is a build-time tool, not part of the library: it lives in scripts/, which pytest puts on sys.path.
"""

import pytest
from build_meta_shapes import build_meta_shapes_graph
from build_shacl_ui import (
    EXCLUDED,
    FORMS,
    STSH,
    build_shacl_ui_graph,
    form_fields,
    is_excluded,
    missing_fields,
)
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
    # the two well-formedness shapes moved here from shacl_shacl (GitHub issue #23) and do have targets; no form shape does
    well_formedness = {STSH.ShuiPredicateShapes, STSH.WidgetScoreShape, STSH.ConfigurationShape, STSH.DataGraphLinksShape}
    for target in ("targetClass", "targetNode", "targetSubjectsOf", "targetObjectsOf"):
        applied = {s for s, _, _ in ui.triples((None, sh(target), None))} - well_formedness
        assert not applied, f"a form is applied to nothing, so loading it never changes what validates: {applied}"


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


def test_sh_expression_is_a_field_of_both_shape_forms_with_the_details_editor(ui) -> None:
    """Node Expressions 7.1: expression constraints can be used in any shape, so the node shape form has the field too, and a
    shape may carry several (no maximum)."""
    scoring = Graph()
    for name in ("shacl_ui_baseline", "shacl_shacl_ui_scores"):
        for triple in starontology.get_ontology_graph(name):
            scoring.add(triple)
    for form in (STSH.NodeShapeForm, STSH.PropertyShapeForm):
        field = fields_of(ui, form)[sh("expression")]
        assert (field, sh("maxCount"), None) not in ui
        assert (field, sh("group"), STSH.CompositionGroup) in ui
        widgets = select_widgets(shape_node=form, shapes_graph=ui, scoring_graph=scoring, role="editor")
        assert str(widgets[field]).rsplit("#", 1)[-1] == "DetailsEditor"


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


def test_uncommon_predicates_are_marked_secondary_on_the_node_shape_form_only(ui) -> None:
    """stsh:nodePrimary false in the overlay (a predicate allowed on a node shape but not commonly expected) becomes
    stsh:secondary true on that field of the node shape form; the property shape form has no such mark."""
    node_fields, prop_fields = fields_of(ui, STSH.NodeShapeForm), fields_of(ui, STSH.PropertyShapeForm)
    flagged = {p for p in node_fields if (p, STSH.nodePrimary, Literal(False)) in ui}
    assert len(flagged) == 14 and sh("datatype") in flagged and sh("pattern") in flagged
    assert {p for p, f in node_fields.items() if (f, STSH.secondary, Literal(True)) in ui} == flagged
    assert not list(ui.triples((None, STSH.secondary, None)) ) or all(f in node_fields.values() for f, _, _ in ui.triples((None, STSH.secondary, None)))
    assert not any((f, STSH.secondary, None) in ui for f in prop_fields.values())


# --------------------------------------------------------------------------- honesty: the forms cannot make an invalid shapes graph
#
# A tool that builds a shapes graph only from the fields of these forms, with values the form allows, must get a graph that
# validates against shacl_shacl. Two checks keep the hand-curated flags honest: what shacl_shacl forbids on a kind of shape is
# not a field of that kind's form, and every single field set to a value its own constraints allow validates.

EX = "http://example.org/"
_NODE_BASE = "ex:S a sh:NodeShape ."
_PROPERTY_BASE = "ex:S a sh:NodeShape ; sh:property ex:P . ex:P a sh:PropertyShape ; sh:path ex:p ."
_PREFIXES = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "

# Fields whose values are structures (a list of shapes, a node expression, a property path) a single sample cannot stand for.
# They are the fields not checked here, named so that adding one to a form is a visible decision.
NOT_SAMPLED = {sh(x) for x in ("and", "or", "xone", "not", "node", "property", "qualifiedValueShape", "someValue", "memberShape",
                              "reifierShape", "expression", "sparql", "rule", "ignoredProperties", "languageIn", "in", "path", "values")}

# What a user would reasonably enter, for the fields whose own constraints do not say (shacl_shacl gives them no datatype or node kind).
SAMPLES = {
    **{sh(x): ['"x"'] for x in ("name", "description", "message", "flags", "defaultValue", "pattern")},
    sh("order"): ["1"], sh("group"): ["ex:G"], URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"): ["ex:T"], sh("datatype"): ["xsd:string"], sh("class"): ["ex:C"], sh("rootClass"): ["ex:C"],
    sh("closed"): ["true"], sh("hasValue"): ["ex:x"], sh("uniqueValuesFor"): ["ex:p"], sh("targetClass"): ["ex:C"], sh("targetNode"): ["ex:x"],
    sh("targetSubjectsOf"): ["ex:p"], sh("targetObjectsOf"): ["ex:p"], sh("subsetOf"): ["ex:p"],
    URIRef("http://www.w3.org/2000/01/rdf-schema#isDefinedBy"): ["ex:G"],
}

# Triples a sample needs besides the value: a sh:group must name an sh:PropertyGroup, so the form offers the groups that exist.
EXTRA = {sh("group"): "ex:G a sh:PropertyGroup ."}


def forbidden_on_node_shapes(shacl_shacl: Graph) -> set[URIRef]:
    """What shacl_shacl says a node shape must not have: the paths of NodeShapeShape's property shapes with sh:maxCount 0."""
    node_shape_shape = URIRef("http://www.w3.org/ns/shacl-shacl#NodeShapeShape")
    return {
        next(shacl_shacl.objects(prop, sh("path")))
        for prop in shacl_shacl.objects(node_shape_shape, sh("property"))
        if (prop, sh("maxCount"), Literal(0)) in shacl_shacl
    }


def test_what_shacl_shacl_forbids_on_a_node_shape_is_not_a_field_of_the_node_shape_form(ui, shacl_shacl) -> None:
    forbidden = forbidden_on_node_shapes(shacl_shacl)
    assert sh("path") in forbidden and len(forbidden) >= 5, "the Working Group's NodeShapeShape bans path, cardinality and others"
    assert not (set(fields_of(ui, STSH.NodeShapeForm)) & forbidden)


def test_the_property_shape_form_requires_the_path_the_validation_requires(ui) -> None:
    path = fields_of(ui, STSH.PropertyShapeForm)[sh("path")]
    assert (path, sh("minCount"), Literal(1)) in ui and (path, sh("maxCount"), Literal(1)) in ui


def test_a_form_never_allows_more_values_than_shacl_shacl_does(ui, shacl_shacl) -> None:
    for name in ("NodeShapeForm", "PropertyShapeForm"):
        for predicate, field in fields_of(ui, STSH[name]).items():
            limits = [int(o) for owner in shacl_shacl.subjects(sh("path"), predicate) for o in shacl_shacl.objects(owner, sh("maxCount"))]
            if limits and min(limits) > 0:
                allowed = [int(o) for o in ui.objects(field, sh("maxCount"))]
                assert allowed and min(allowed) <= min(limits), (name, predicate, limits, allowed)


def _samples(ui: Graph, field) -> list[str]:
    """Turtle values the field's own constraints allow (empty when a single sample cannot stand for it)."""
    in_lists = list(ui.objects(field, sh("in")))
    if in_lists:
        return [o.n3() if isinstance(o, URIRef) and False else (f"<{o}>" if isinstance(o, URIRef) else o.n3()) for o in ui.items(in_lists[0])]
    datatype = next(ui.objects(field, sh("datatype")), None)
    node_kind = next(ui.objects(field, sh("nodeKind")), None)
    if datatype == XSD.integer:
        return ["1"]
    if datatype == XSD.boolean:
        return ["true"]
    if datatype == XSD.string:
        return ['"x"']
    if datatype == XSD.decimal:
        return ["1.5"]
    if node_kind in (sh("IRI"), sh("BlankNodeOrIRI"), sh("IRIOrLiteral")):
        return ["ex:x"]
    if node_kind == sh("Literal"):
        return ['"x"']
    return []


@pytest.mark.parametrize("form,base,subject", [("NodeShapeForm", _NODE_BASE, "ex:S"), ("PropertyShapeForm", _PROPERTY_BASE, "ex:P")])
def test_every_field_set_to_a_value_its_constraints_allow_still_validates(ui, form, base, subject) -> None:
    """The honesty check: one field at a time, on a minimal valid shape of that kind. A field that makes the graph invalid is a
    predicate that should not be on that form (or a constraint the form is missing)."""
    from pyshacl.errors import ReportableRuntimeError
    from starlayer.shacl.meta_shapes import meta_validate

    checked, bad = 0, []
    for predicate, field in fields_of(ui, STSH[form]).items():
        if predicate in NOT_SAMPLED:
            continue
        samples = SAMPLES.get(predicate) or _samples(ui, field)
        if not samples:
            bad.append((predicate, "no sample value from the field's constraints; add it to NOT_SAMPLED with a reason, or give the field a datatype / node kind"))
            continue
        for value in samples:
            graph = Graph()
            graph.parse(data=_PREFIXES + f"{base} {EXTRA.get(predicate, '')} {subject} <{predicate}> {value} .", format="turtle")
            try:
                meta_validate(graph)
            except ReportableRuntimeError as error:
                bad.append((predicate, value, str(error).splitlines()[0][:100]))
        checked += 1
    assert not bad, f"{form}: " + "; ".join(str(b) for b in bad[:6])
    assert checked > 25


def test_the_group_field_offers_only_property_groups(ui) -> None:
    """shacl_shacl requires a sh:group value to be a sh:PropertyGroup, so the field says so: a tool lists the groups that exist
    and a graph cannot get a group that is not one."""
    group = fields_of(ui, STSH.PropertyShapeForm)[sh("group")]
    assert (group, sh("class"), sh("PropertyGroup")) in ui


def test_rdf_type_is_a_simple_multi_valued_iri_field_of_both_forms_in_its_own_first_group(ui) -> None:
    rdf_type = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
    for name in ("NodeShapeForm", "PropertyShapeForm"):
        field = fields_of(ui, STSH[name])[rdf_type]
        assert (field, sh("nodeKind"), sh("IRI")) in ui and not list(ui.objects(field, sh("maxCount"))), "an IRI, many allowed"
        assert (field, sh("group"), STSH.TypeGroup) in ui
    assert (STSH.TypeGroup, sh("order"), Literal(0)) in ui, "the type comes first"


class TestWhatAFieldsValuesCanBe:
    """The forms say, by sh:nodeKind, whether a field's values can be blank nodes: a tool shows those as branches of a tree and the rest in a panel."""

    @staticmethod
    def _node_kind(form, predicate):
        from rdflib import Namespace

        SH = Namespace("http://www.w3.org/ns/shacl#")
        ui = starontology.get_ontology_graph("shacl_shacl_ui")
        for field in ui.objects(form, SH.property):
            if (field, SH.path, predicate) in ui:
                return set(ui.objects(field, SH.nodeKind))
        raise AssertionError(f"no field for {predicate}")

    def test_shapes_and_rules_take_blank_nodes_and_classes_names_and_groups_do_not(self):
        from rdflib import Namespace

        SH = Namespace("http://www.w3.org/ns/shacl#")
        STSH = Namespace("https://github.com/hidden-graph/starlayer/ns/shacl#")
        for predicate in (SH.property, SH.node, SH["not"], SH.rule, SH.sparql, SH.qualifiedValueShape):
            form = STSH.PropertyShapeForm if predicate in (SH.qualifiedValueShape,) else STSH.NodeShapeForm
            assert self._node_kind(form, predicate) == {SH.BlankNodeOrIRI}, predicate
        for predicate in (SH["class"], SH.datatype, SH.nodeKind, SH.targetClass):
            assert SH.BlankNodeOrIRI not in self._node_kind(STSH.NodeShapeForm, predicate), predicate
        assert self._node_kind(STSH.PropertyShapeForm, SH.group) == {SH.IRI}
        assert self._node_kind(STSH.NodeShapeForm, SH.name) == {SH.Literal}
