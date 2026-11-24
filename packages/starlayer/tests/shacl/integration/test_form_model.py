"""``form_model``: the fields of a node's form, joined from what StarLayer already answers (shapes, widgets, values, a report)."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl import (
    FormModel,
    StarShaclProcessor,
    check_value,
    form_model,
    select_widgets,
    validate,
    value_form,
)
from starlayer.shacl.engine.terms import NS, literal

EX = NS("http://example.org/")
SH = NS("http://www.w3.org/ns/shacl#")
XSD_STRING = NS("http://www.w3.org/2001/XMLSchema#").string
SHUI = NS("http://www.w3.org/ns/shacl-ui/")
STSH = NS("https://github.com/hidden-graph/starlayer/ns/shacl#")
PFX = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix shui: <http://www.w3.org/ns/shacl-ui/> . "
    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "
    "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . @prefix stsh: <https://github.com/hidden-graph/starlayer/ns/shacl#> .\n"
)


def g(turtle: str) -> StarLayerGraph:
    return StarLayerGraph().parse(data=PFX + turtle, format="turtle")


SHAPES = """
ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:property ex:Name, ex:Age .
ex:Name sh:path ex:name ; sh:name "Name"@en, "Nom"@fr ; sh:order 1 ; sh:minCount 1 ; sh:maxCount 3 ; sh:datatype xsd:string .
ex:Age sh:path ex:age ; sh:name "Age" ; sh:order 2 ; sh:datatype xsd:integer .
ex:AgentShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:property ex:AgentName .
ex:AgentName sh:path ex:name ; sh:name "Agent name" ; sh:order 0 ; sh:maxCount 2 ; sh:minLength 2 .
"""
DATA = 'ex:alice a ex:Person ; ex:name "Alice" ; ex:age 30 ; ex:nick "Al" .'


def model(ttl=SHAPES, data=DATA, node=EX.alice, **options) -> FormModel:
    return form_model(g(ttl), g(data), node, **options)


def paths(m: FormModel) -> list:
    return [f.path for f in m.fields]


def test_two_target_shapes_with_one_path_merge_into_one_field_that_keeps_every_property_shape():
    m = model()
    name = m.field(EX.name)
    assert paths(m).count(EX.name) == 1
    assert set(name.property_shapes) == {EX.Name, EX.AgentName}
    assert name.property_shapes[0] == EX.AgentName  # sh:order 0 comes before sh:order 1
    assert name.required and name.max_count == 2  # any minCount above 0; the smallest maxCount
    assert name.constraints.min_length == 2 and name.constraints.datatypes == (XSD_STRING,)
    assert [lit.value for lit in name.name] == ["Agent name"]  # the first contributing shape that has a name
    assert set(m.shapes) == {EX.PersonShape, EX.AgentShape}


def test_a_shape_lens_gives_the_per_shape_view():
    m = model(shapes=[EX.PersonShape])
    name = m.field(EX.name)
    assert name.property_shapes == (EX.Name,) and name.max_count == 3
    assert {lit.language for lit in name.name} == {"en", "fr"}  # every language-tagged name is kept
    assert EX.nick not in paths(m) and m.shapes == (EX.PersonShape,)
    assert model(shapes=EX.PersonShape) == m  # a single term is allowed


def test_a_deactivated_shape_is_ignored():
    shapes = SHAPES + "ex:AgentShape sh:deactivated true ."
    m = model(shapes)
    assert m.shapes == (EX.PersonShape,) and m.field(EX.name).property_shapes == (EX.Name,)
    asked = model(shapes, shapes=[EX.AgentShape])
    assert asked.fields == () and "deactivated" in asked.notes[0]


GROUPED = """
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:A, ex:B, ex:C, ex:D, ex:E, ex:F .
ex:A sh:path ex:a ; sh:order 9 .
ex:B sh:path ex:b ; sh:order 1 ; sh:group ex:G2 .
ex:C sh:path ex:c ; sh:order 2 ; sh:group ex:G1 .
ex:D sh:path ex:d ; sh:order 1 ; sh:group ex:G1 .
ex:E sh:path ex:e ; sh:group ex:G3 .
ex:F sh:path ex:f ; sh:order 1 ; sh:group ex:G1 ; sh:name "F" .
ex:G1 a sh:PropertyGroup ; sh:order 5 ; rdfs:label "One" .
ex:G2 a sh:PropertyGroup ; sh:order 1 ; sh:name "Two" .
ex:G3 a sh:PropertyGroup .
"""
GDATA = 'ex:x a ex:T ; ex:a 1 ; ex:b 1 ; ex:c 1 ; ex:d 1 ; ex:e 1 ; ex:f 1 .'


def test_ungrouped_first_then_groups_by_order_then_fields_by_order_with_stable_ties():
    m = model(GROUPED, GDATA, EX.x)
    assert [s.group for s in m.sections] == [None, EX.G2, EX.G1, EX.G3]
    assert [f.path for f in m.sections[2].fields] == [EX.d, EX.f, EX.c]  # order 1 tie: no name before "F", then order 2
    assert [lit.value for lit in m.sections[2].label] == ["One"]  # rdfs:label when there is no sh:name
    assert m.sections[1].order == 1.0 and m.sections[3].order is None  # a group with no order comes last


def test_the_default_order_stands_in_for_a_missing_order():
    m = model(GROUPED + "ex:Config shui:defaultOrder 3 .", GDATA, EX.x)
    assert [s.group for s in m.sections] == [None, EX.G2, EX.G3, EX.G1] and m.sections[2].order == 3.0
    assert m.sections[0].fields[0].order == 9.0
    assert m.field(EX.e).order == 3.0


def test_a_placement_callable_replaces_the_core_rule():
    by_text = lambda f: f.path.value  # noqa: E731
    m = model(GROUPED, GDATA, EX.x, placement=by_text)
    # the section holding the first field in key order comes first: ex:a (ungrouped) is first, ex:b next
    assert [f.path for f in m.sections[0].fields] == [EX.a]
    assert [s.group for s in m.sections] == [None, EX.G2, EX.G1, EX.G3]
    reverse = model(GROUPED, GDATA, EX.x, placement=lambda f: -ord(f.path.value[-1]))
    assert [s.group for s in reverse.sections] == [EX.G1, EX.G3, EX.G2, None]
    assert [f.path for f in reverse.sections[0].fields] == [EX.f, EX.d, EX.c]


WIDGETS = """
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:A, ex:B .
ex:A sh:path ex:a ; shui:editor shui:TextAreaEditor ; shui:viewer shui:HTMLViewer .
ex:B sh:path ex:b ; shui:editor shui:NumberFieldEditor .
"""


@pytest.mark.parametrize("role", ["editor", "viewer"])
def test_widgets_equal_select_widgets_for_the_same_shape(role):
    shapes = g(WIDGETS)
    m = form_model(shapes, g("ex:x a ex:T ; ex:a 1 ; ex:b 2 ."), EX.x, role=role)
    expected = {p: c.widget_without_data for p, c in select_widgets(shape_node=EX.S, shapes_graph=shapes, role=role, per="shape").items()}
    assert {EX.A: m.field(EX.a).widget, EX.B: m.field(EX.b).widget} == expected
    assert m.field(EX.a).widget == (SHUI.TextAreaEditor if role == "editor" else SHUI.HTMLViewer)


def test_a_precomputed_widgets_mapping_is_used_and_implemented_is_passed_on():
    shapes = g(WIDGETS)
    given = {EX.A: SHUI.IRIEditor}
    m = form_model(shapes, g("ex:x a ex:T ; ex:a 1 ; ex:b 2 ."), EX.x, widgets=given)
    assert m.field(EX.a).widget == SHUI.IRIEditor and m.field(EX.b).widget is None
    only = form_model(shapes, g("ex:x a ex:T ; ex:a 1 ; ex:b 2 ."), EX.x, implemented=[SHUI.NumberFieldEditor.value])
    assert only.field(EX.a).widget is None and only.field(EX.b).widget == SHUI.NumberFieldEditor


VALUES = """
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:Name, ex:Full, ex:Mail .
ex:Name sh:path ex:name ; sh:order 1 .
ex:Full sh:path ex:fullName ; sh:order 2 ; sh:values [ <http://www.w3.org/ns/shacl-node-expr#pathValues> ex:name ] .
ex:Mail sh:path ex:mail ; sh:order 3 ; sh:defaultValue "none@example.org" .
"""
VDATA = 'ex:x a ex:T ; ex:name "Al" .'


def test_stored_inferred_computed_and_default_values_have_their_source_editability_and_reason():
    m = model(VALUES, VDATA, EX.x, inferred_graph=g('ex:x ex:name "Ally" .'))
    seen = {f.path: [(v.term.value, v.source, v.editable, v.reason) for v in f.values] for f in m.fields}
    assert seen[EX.name] == [("Al", "stored", True, None), ("Ally", "inferred", False, "inferred")]
    assert seen[EX.fullName] == [("Al", "computed", False, "computed")]
    assert seen[EX.mail] == [("none@example.org", "default", False, "default")]
    assert m.field(EX.name).editable and m.field(EX.fullName).editable  # the stored values of the field could be edited


def test_a_default_is_not_shown_when_a_value_is_stored_and_sh_values_beats_it():
    m = model(VALUES, VDATA + ' ex:x ex:mail "a@b" .', EX.x)
    assert [(v.term.value, v.source) for v in m.field(EX.mail).values] == [("a@b", "stored")]
    both = VALUES.replace('ex:Mail sh:path ex:mail ;', 'ex:Mail sh:path ex:mail ; sh:values [ <http://www.w3.org/ns/shacl-node-expr#pathValues> ex:name ] ;')
    sources = {(v.term.value, v.source) for v in model(both, VDATA, EX.x).field(EX.mail).values}
    assert sources == {("Al", "computed")}  # the default applies only when sh:values gave nothing
    none = model(both, "ex:x a ex:T .", EX.x).field(EX.mail)
    assert [(v.term.value, v.source) for v in none.values] == [("none@example.org", "default")]


def test_a_viewer_has_no_editable_value():
    m = model(VALUES, VDATA, EX.x, role="viewer", inferred_graph=g('ex:x ex:name "Ally" .'))
    assert not m.field(EX.name).editable
    assert {v.reason for f in (*m.fields, *m.others) for v in f.values} == {"role"}
    assert not any(v.editable for f in m.fields for v in f.values)


COMPLEX = """
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:Seq, ex:Inv, ex:Plain .
ex:Seq sh:path ( ex:knows ex:name ) .
ex:Inv sh:path [ sh:inversePath ex:knows ] .
ex:Plain sh:path ex:name .
"""
CDATA = 'ex:x a ex:T ; ex:knows ex:y ; ex:name "X" . ex:y ex:name "Y" . ex:z ex:knows ex:x .'


def test_a_complex_path_is_read_and_read_only_and_an_inverse_predicate_is_editable():
    m = model(COMPLEX, CDATA, EX.x)
    seq = next(f for f in m.fields if f.property_shapes == (EX.Seq,))
    inv = next(f for f in m.fields if f.property_shapes == (EX.Inv,))
    assert not seq.editable and [(v.term.value, v.editable, v.reason) for v in seq.values] == [("Y", False, "path")]
    assert inv.editable and [(v.term, v.editable) for v in inv.values] == [(EX.z, True)]
    assert m.field(EX.name).editable


def test_others_lists_a_predicate_no_shape_covers_and_not_a_covered_one_or_an_ignored_one():
    m = model()
    assert [f.path for f in m.others if f.path == EX.nick] and EX.name not in [f.path for f in m.others]
    nick = m.field(EX.nick)
    assert nick.property_shapes == () and nick.widget is None and not nick.editable
    assert [(v.editable, v.reason) for v in nick.values] == [(False, "no shape")]
    # rdf:type is a field like any other when nothing covers it
    assert EX.nick in [f.path for f in m.others] and any(f.path.value.endswith("#type") for f in m.others)
    closed = SHAPES.replace("ex:PersonShape a sh:NodeShape ;", "ex:PersonShape a sh:NodeShape ; sh:closed true ; sh:ignoredProperties ( rdf:type ex:nick ) ;")
    kept = model(closed).others
    assert kept == ()


def test_a_node_no_shape_targets_has_no_sections_and_everything_is_in_others():
    m = model(node=EX.nobody, data=DATA + " ex:nobody ex:p 1 .")
    assert m.shapes == () and m.sections == () and [f.path for f in m.others] == [EX.p]


EMPTY = """
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:Req, ex:Opt, ex:Have .
ex:Req sh:path ex:req ; sh:minCount 1 . ex:Opt sh:path ex:opt . ex:Have sh:path ex:have .
"""
EDATA = 'ex:x a ex:T ; ex:have 1 .'


@pytest.mark.parametrize(
    ("role", "empty", "kept", "hidden"),
    [
        ("editor", "auto", {EX.req, EX.have}, 1),
        ("viewer", "auto", {EX.have}, 2),
        ("editor", "all", {EX.req, EX.opt, EX.have}, 0),
        ("editor", "none", {EX.have}, 2),
    ],
)
def test_the_empty_setting_keeps_and_counts_fields(role, empty, kept, hidden):
    m = model(EMPTY, EDATA, EX.x, role=role, empty=empty)
    assert set(paths(m)) == kept and m.hidden_empty == hidden


def test_a_section_left_empty_is_dropped():
    m = model(EMPTY.replace("ex:Opt sh:path ex:opt .", "ex:Opt sh:path ex:opt ; sh:group ex:G ."), EDATA, EX.x)
    assert all(s.fields for s in m.sections) and EX.G not in [s.group for s in m.sections]


def test_a_bad_role_or_empty_setting_is_a_value_error():
    with pytest.raises(ValueError, match="role"):
        model(role="admin")
    with pytest.raises(ValueError, match="empty"):
        model(empty="some")


def test_errors_come_only_from_the_report_passed_in_and_nothing_validates_without_one(monkeypatch):
    shapes, data = g(SHAPES), g('ex:alice a ex:Person ; ex:name "A" ; ex:age "old" ; ex:nick "n" .')
    import starlayer.shacl.engine.api as api

    def boom(*a, **k):
        raise AssertionError("form_model must not validate")

    monkeypatch.setattr(api, "validate", boom)
    plain = form_model(shapes, data, EX.alice)
    assert all(f.errors == () for f in plain.fields) and plain.node_errors == ()
    monkeypatch.undo()
    report = validate(data, shapes)
    assert not report.conforms
    m = form_model(shapes, data, EX.alice, report=report)
    assert m.field(EX.age).errors and all(r.path == EX.age for r in m.field(EX.age).errors)
    assert m.field(EX.name).errors  # minLength 2
    by_graph = form_model(shapes, data, EX.alice, report=report.report_graph)
    assert by_graph.field(EX.age).errors == m.field(EX.age).errors
    assert form_model(shapes, g('ex:alice a ex:Person .'), EX.alice, report=validate(g('ex:alice a ex:Person .'), shapes)).node_errors == ()


def test_node_level_results_are_the_node_errors():
    shapes = g(SHAPES + "ex:PersonShape sh:nodeKind sh:Literal .")
    data = g(DATA)
    m = form_model(shapes, data, EX.alice, report=validate(data, shapes))
    assert m.node_errors and all(r.path is None for r in m.node_errors)


def test_suggestions_are_off_by_default_and_suggested_values_are_separate():
    shapes = """
    ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:Pet, ex:Colour .
    ex:Pet sh:path ex:pet ; sh:class ex:Animal .
    ex:Colour sh:path ex:colour ; shui:suggestedValues ( ex:red ex:green ) ; sh:in ( ex:red ex:green ex:blue ) .
    """
    data = "ex:x a ex:T . ex:rex a ex:Animal ."
    off = model(shapes, data, EX.x, empty="all")
    assert off.field(EX.pet).candidates is None and off.field(EX.colour).candidates is None
    assert off.field(EX.colour).suggested == (EX.red, EX.green) and off.field(EX.pet).suggested == ()
    on = model(shapes, data, EX.x, suggestions=True, empty="all")
    assert on.field(EX.pet).candidates.values == (EX.rex,)
    assert on.field(EX.colour).candidates.values == (EX.blue, EX.green, EX.red) and on.field(EX.colour).candidates.closed
    assert on.field(EX.colour).constraints.in_values == (EX.red, EX.green, EX.blue)


def test_only_valid_is_passed_through_to_the_candidates():
    shapes = "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:Pet . ex:Pet sh:path ex:pet ; sh:in ( ex:a ex:b ) ; sh:not [ sh:hasValue ex:a ] ."
    m = model(shapes, "ex:x a ex:T .", EX.x, suggestions=True, only_valid=True, empty="all")
    assert m.field(EX.pet).candidates.values == (EX.b,)
    assert model(shapes, "ex:x a ex:T .", EX.x, suggestions=True, empty="all").field(EX.pet).candidates.values == (EX.a, EX.b)


def test_field_check_equals_check_value():
    shapes, data = g(SHAPES), g(DATA)
    field = form_model(shapes, data, EX.alice).field(EX.age)
    for value in (literal(31), literal("old")):
        expected = check_value(shapes, EX.Age, EX.alice, value, data)
        got = field.check(value)
        assert got.conforms == expected.conforms and [r.identity() for r in got.results] == [r.identity() for r in expected.results]
    assert not field.check(literal("old")).conforms
    with pytest.raises(ValueError, match="no property shape"):
        form_model(shapes, data, EX.alice).field(EX.nick).check(literal("x"))


def test_value_form_and_members_of_a_list_field():
    shapes = "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:Tags . ex:Tags sh:path ex:tags ; sh:minListLength 1 ."
    data = 'ex:x a ex:T ; ex:tags ( "b" "a" ) .'
    m = model(shapes, data, EX.x)
    field = m.field(EX.tags)
    assert field.value_form == value_form(g(shapes), EX.Tags) == "list"
    (value,) = field.values
    assert [t.value for t in value.members] == ["b", "a"]  # the list's own order
    assert model(SHAPES, DATA).field(EX.age).values[0].members is None


def test_the_callers_graphs_are_unchanged_and_two_calls_are_equal():
    shapes, data, inferred = g(VALUES), g(VDATA), g('ex:x ex:name "Ally" .')
    before = [set(x.triples((None, None, None))) for x in (shapes, data, inferred)]
    one = form_model(shapes, data, EX.x, inferred_graph=inferred, suggestions=True)
    two = form_model(shapes, data, EX.x, inferred_graph=inferred, suggestions=True)
    assert one == two and hash(one.field(EX.name).constraints) == hash(two.field(EX.name).constraints)
    assert before == [set(x.triples((None, None, None))) for x in (shapes, data, inferred)]


def test_an_rdflib_graph_or_term_is_refused():
    rdflib = pytest.importorskip("rdflib")
    with pytest.raises(TypeError, match="from_rdflib"):
        form_model(rdflib.Graph(), g(DATA), EX.alice)
    with pytest.raises(TypeError, match="from_rdflib"):
        form_model(g(SHAPES), rdflib.Graph(), EX.alice)
    with pytest.raises(TypeError, match="from_rdflib"):
        form_model(g(SHAPES), g(DATA), rdflib.URIRef("http://example.org/alice"))


def test_form_held_by_and_form_only_for_hide_a_field_that_is_not_for_the_node():
    shapes = """
    ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:Only, ex:Held, ex:All .
    ex:Only sh:path ex:only ; stsh:formOnlyFor ex:Special . ex:Held sh:path ex:held ; stsh:formHeldBy ex:Holder . ex:All sh:path ex:all .
    """
    base = "ex:x a ex:T ; ex:only 1 ; ex:held 1 ; ex:all 1 ."
    assert set(paths(model(shapes, base, EX.x))) == {EX.all, EX.held}  # held: nothing holds it yet
    assert set(paths(model(shapes, base + " ex:x a ex:Special .", EX.x))) == {EX.all, EX.held, EX.only}
    assert set(paths(model(shapes, base + " ex:h sh:parameter ex:x . ex:h a ex:Other .", EX.x))) == {EX.all}
    assert set(paths(model(shapes, base + " ex:h sh:parameter ex:x . ex:h a ex:Holder .", EX.x))) == {EX.all, EX.held}
    typed = model(shapes, base, EX.x, inferred_graph=g("ex:x a ex:Special ."))
    assert EX.only in paths(typed)


def test_secondary_fields_go_to_one_collapsed_section_last():
    shapes = "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:A, ex:B . ex:A sh:path ex:a ; sh:order 5 ; stsh:secondary true . ex:B sh:path ex:b ; sh:order 9 ."
    m = model(shapes, "ex:x a ex:T ; ex:a 1 ; ex:b 1 .", EX.x)
    assert [s.collapsed for s in m.sections] == [False, True] and m.sections[1].fields[0].secondary and m.sections[1].group is None


def test_the_method_matches_the_function_and_uses_the_bound_graphs():
    shapes, data = g(SHAPES), g(DATA)
    expected = form_model(shapes, data, EX.alice)
    assert StarShaclProcessor(shacl_graph=shapes, data_graph=data).form_model(EX.alice) == expected
    assert StarShaclProcessor(shacl_graph=shapes).form_model(EX.alice, data_graph=data, role="viewer") == form_model(shapes, data, EX.alice, role="viewer")
