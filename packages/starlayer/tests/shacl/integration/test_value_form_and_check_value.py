"""``value_form`` (how a field's value is held) and ``check_value`` (would a value be accepted for a field of a node)."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer import starontology
from starlayer.graph import StarLayerGraph
from starlayer.shacl import (
    ReportResult,
    StarShaclProcessor,
    ValueCheck,
    check_value,
    value_form,
)
from starlayer.shacl.engine.terms import NS, literal
from starlayer.shacl.meta_shapes import load_meta_shapes_graph

EX = NS("http://example.org/")
XSD = NS("http://www.w3.org/2001/XMLSchema#")
SH = NS("http://www.w3.org/ns/shacl#")
SHUI = NS("http://www.w3.org/ns/shacl-ui/")
STSH = NS("https://github.com/hidden-graph/starlayer/ns/shacl#")
SHSH = NS("http://www.w3.org/ns/shacl-shacl#")
PFX = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . "
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
)

# A shape that describes a list, as shsh:ListShape does (a path of rdf:rest steps that must reach rdf:nil).
LIST_SHAPE = "ex:L a sh:NodeShape ; sh:property [ sh:path [ sh:zeroOrMorePath rdf:rest ] ; sh:hasValue rdf:nil ] ."


def g(turtle: str) -> StarLayerGraph:
    return StarLayerGraph().parse(data=PFX + turtle, format="turtle")


def form(turtle: str, shape=EX.P) -> str:
    return value_form(g(turtle), shape)


# ---- value_form --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("body", ["", "sh:nodeKind sh:IRI", "sh:datatype xsd:string ; sh:maxCount 1", "sh:class ex:Animal"])
def test_a_property_shape_that_says_nothing_about_lists_is_single(body):
    assert form(f"ex:P sh:path ex:p ; {body} .") == "single"


def test_a_value_that_must_conform_to_a_list_shape_is_a_list():
    assert form(f"ex:P sh:path ex:p ; sh:node ex:L . {LIST_SHAPE}") == "list"


def test_the_list_shape_is_known_by_its_pattern_not_by_its_name():
    assert form("ex:P sh:path ex:p ; sh:node ex:Other . ex:Other sh:property [ sh:path [ sh:zeroOrMorePath rdf:rest ] ; sh:hasValue rdf:nil ] .") == "list"
    # the same path without the requirement that it reaches rdf:nil does not require a list
    assert form("ex:P sh:path ex:p ; sh:node ex:Other . ex:Other sh:property [ sh:path [ sh:zeroOrMorePath rdf:rest ] ; sh:nodeKind sh:IRI ] .") == "single"


def test_the_shsh_list_shape_is_known_even_when_the_graph_does_not_hold_it():
    assert form("ex:P sh:path ex:p ; sh:node <http://www.w3.org/ns/shacl-shacl#ListShape> .") == "list"


def test_the_member_path_needs_a_min_count_to_require_a_list():
    member = "ex:Other sh:property [ sh:path ( [ sh:zeroOrMorePath rdf:rest ] rdf:first ) ; sh:nodeKind sh:IRI {more} ] ."
    assert form("ex:P sh:path ex:p ; sh:node ex:Other . " + member.format(more="; sh:minCount 1")) == "list"
    assert form("ex:P sh:path ex:p ; sh:node ex:Other . " + member.format(more="")) == "single"


@pytest.mark.parametrize("body", ["sh:minListLength 1", "sh:maxListLength 3", "sh:uniqueMembers true", "sh:memberShape [ sh:nodeKind sh:IRI ]", "sh:class rdf:List"])
def test_the_list_constraints_and_rdf_list_class_require_a_list(body):
    assert form(f"ex:P sh:path ex:p ; {body} .") == "list"


def test_unique_members_false_is_not_a_requirement():
    assert form("ex:P sh:path ex:p ; sh:uniqueMembers false .") == "single"


def test_a_list_shape_inside_sh_and_is_a_list():
    assert form(f"ex:P sh:path ex:p ; sh:and ( [ sh:nodeKind sh:BlankNodeOrIRI ] [ sh:node ex:L ] ) . {LIST_SHAPE}") == "list"


def test_sh_or_with_a_list_alternative_and_one_that_is_not_is_single_or_list():
    assert form(f"ex:P sh:path ex:p ; sh:or ( [ sh:nodeKind sh:IRI ] [ sh:node ex:L ] ) . {LIST_SHAPE}") == "single-or-list"
    assert form(f"ex:P sh:path ex:p ; sh:xone ( [ sh:nodeKind sh:IRI ] [ sh:node ex:L ] ) . {LIST_SHAPE}") == "single-or-list"


def test_sh_or_of_only_lists_is_a_list_and_of_no_list_is_single():
    assert form(f"ex:P sh:path ex:p ; sh:or ( [ sh:node ex:L ] [ sh:minListLength 1 ] ) . {LIST_SHAPE}") == "list"
    assert form("ex:P sh:path ex:p ; sh:or ( [ sh:nodeKind sh:IRI ] [ sh:datatype xsd:string ] ) .") == "single"


def test_a_list_requirement_next_to_an_sh_or_wins():
    shapes = f"ex:P sh:path ex:p ; sh:minListLength 1 ; sh:or ( [ sh:nodeKind sh:IRI ] [ sh:node ex:L ] ) . {LIST_SHAPE}"
    assert form(shapes) == "list"


def test_sh_in_as_a_parameter_of_the_shape_is_not_a_list_field():
    """``sh:in`` lists the allowed values of the field; whether the value of the field is a list is another question."""
    assert form("ex:P sh:path ex:p ; sh:in ( ex:a ex:b ) .") == "single"


def test_a_property_shape_for_sh_in_itself_is_a_list_only_when_its_shape_says_so():
    assert form("ex:P sh:path sh:in ; sh:maxCount 1 .") == "single"
    assert form("ex:P sh:path sh:in ; sh:minListLength 1 .") == "list"


def test_a_deactivated_list_shape_requires_nothing():
    assert form("ex:P sh:path ex:p ; sh:node ex:L . ex:L sh:deactivated true ; sh:minListLength 1 .") == "single"


def test_shapes_that_refer_to_each_other_terminate():
    assert form("ex:P sh:path ex:p ; sh:node ex:A . ex:A sh:node ex:B . ex:B sh:node ex:A .") == "single"
    assert form("ex:P sh:path ex:p ; sh:node ex:A . ex:A sh:node ex:B . ex:B sh:node ex:A ; sh:minListLength 1 .") == "list"
    assert form("ex:P sh:path ex:p ; sh:node ex:P .") == "single"
    assert form("ex:P sh:path ex:p ; sh:or ( ex:P [ sh:minListLength 1 ] ) .") == "single-or-list"


def test_an_unknown_or_non_property_shape_is_a_value_error_naming_the_argument():
    with pytest.raises(ValueError, match="property_shape"):
        form("ex:P sh:path ex:p .", EX.Missing)
    with pytest.raises(ValueError, match="property_shape"):
        form("ex:N a sh:NodeShape ; sh:targetClass ex:C .", EX.N)
    with pytest.raises(ValueError, match="property_shape"):
        value_form(g(""), None)


def test_an_rdflib_graph_is_refused_by_value_form():
    rdflib = pytest.importorskip("rdflib")
    with pytest.raises(TypeError, match="from_rdflib"):
        value_form(rdflib.Graph(), EX.P)


# ---- value_form on the shapes about shapes ------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def meta():
    graph = load_meta_shapes_graph()
    graph.extend(list(starontology.get_ontology_graph("shacl_shacl_ui").triples((None, None, None))))
    return graph


def _field(meta, owner, path):
    """The property shape of the shape ``owner`` for the property ``path``."""
    found = [
        p
        for p in meta.objects(to_term(owner), SH.property)
        if (p, SH.path, to_term(path)) in meta
    ]
    assert len(found) == 1, (owner, path, found)
    return found[0]


def to_term(iri):
    return ox.NamedNode(iri.value if hasattr(iri, "value") else str(iri))


# (the shape that owns the property shape, the property, what value_form says, what the workbench's editors.ttl flag says)
# shsh:ShapeShape is the Working Group's and is never edited: its property shape for sh:in has only a maxCount, so the list
# requirement for sh:in is on stsh:InIsListShape (same target, sh:targetSubjectsOf sh:in).
AGREE = [
    (STSH.NewPredicateShapes, SH.uniqueValuesFor, "single-or-list", "singleOrList"),
    (STSH.ShapeShapeOverrides, SH.nodeKind, "single-or-list", "singleOrList"),
    (SHSH.inSubjectsShape, SH["in"], "list", "isList"),
    (STSH.InIsListShape, SH["in"], "list", "isList"),
    (STSH.InXoneSatisfiabilityShapes, SH["in"], "list", "isList"),
    (SHSH.ShapeShape, SH.languageIn, "list", "isList"),
    (STSH.IgnoredPropertiesLanguageInMinListLengthShapes, SH.languageIn, "list", "isList"),
    (SHSH.ShapeShape, SH.ignoredProperties, "list", "isList"),
    (STSH.IgnoredPropertiesLanguageInMinListLengthShapes, SH.ignoredProperties, "list", "isList"),
    (STSH.ConfigurationShape, SHUI.languagePreference, "list", "isList"),
    (STSH.SuggestedValuesShape, SHUI.suggestedValues, "list", "isList"),
    (STSH.ConfigurationShape, SHUI.labelPreference, "list", "isList"),
]


@pytest.mark.parametrize(("owner", "path", "expected", "flag"), AGREE)
def test_value_form_of_the_shapes_about_shapes_agrees_with_the_workbench_flag(meta, owner, path, expected, flag):
    assert value_form(meta, _field(meta, owner, path)) == expected
    assert flag == ("singleOrList" if expected == "single-or-list" else "isList")


def test_the_working_groups_property_shape_for_sh_in_still_says_nothing_about_a_list(meta):
    """It is vendored and not edited; the list requirement is the added shape's."""
    assert value_form(meta, _field(meta, SHSH.ShapeShape, SH["in"])) == "single"


SHAPES_PFX = "@prefix shui: <http://www.w3.org/ns/shacl-ui/> .\n"


@pytest.mark.parametrize(
    ("turtle", "problem"),
    [
        ("ex:S a sh:PropertyShape ; sh:path ex:p ; sh:in ex:a .", "sh:in: The value ex:a of sh:in should be a list"),
        ("ex:S a sh:PropertyShape ; sh:path ex:p ; shui:suggestedValues ex:a .", "shui:suggestedValues: The value ex:a of shui:suggestedValues should be a list"),
        ("ex:C a shui:Configuration ; shui:labelPreference ex:a .", "shui:labelPreference: The value ex:a of shui:labelPreference should be a list"),
        ('ex:C a shui:Configuration ; shui:labelPreference ( ex:a "x" ) .', "does not conform to the shape shsh:PathShape"),
    ],
)
def test_meta_validate_rejects_a_value_that_is_not_a_list(turtle, problem):
    from starlayer.shacl import MetaShaclError, meta_validate

    shapes = g(SHAPES_PFX + turtle)
    with pytest.raises(MetaShaclError) as raised:
        meta_validate(shapes, extra_graphs=[starontology.get_ontology_graph("shacl_shacl_ui")])
    assert problem in str(raised.value)


@pytest.mark.parametrize(
    "turtle",
    [
        "ex:S a sh:PropertyShape ; sh:path ex:p ; sh:in ( ex:a ex:b ) .",
        "ex:S a sh:PropertyShape ; sh:path ex:p ; shui:suggestedValues ( ex:a 1 ) .",
        "ex:S a sh:PropertyShape ; sh:path ex:p ; shui:suggestedValues () .",
        "ex:C a shui:Configuration ; shui:labelPreference ( ex:a [ sh:inversePath ex:b ] ) .",
        "ex:C a shui:Configuration ; shui:labelPreference () .",
    ],
)
def test_meta_validate_accepts_a_list(turtle):
    from starlayer.shacl import meta_validate

    conforms, _, _ = meta_validate(g(SHAPES_PFX + turtle), extra_graphs=[starontology.get_ontology_graph("shacl_shacl_ui")])
    assert conforms


@pytest.mark.parametrize("value", ['"http://example.com/ns#"', '"urn:x:y"'])
def test_default_namespace_accepts_a_literal_that_is_an_absolute_iri(value):
    from starlayer.shacl import meta_validate

    shapes = g(SHAPES_PFX + f"ex:C a shui:Configuration ; shui:defaultNamespace {value} .")
    assert meta_validate(shapes, extra_graphs=[starontology.get_ontology_graph("shacl_shacl_ui")])[0]


@pytest.mark.parametrize("value", ['"not an iri"', '"http://a b/"', '""', "ex:ns"])
def test_default_namespace_refuses_what_is_not_an_absolute_iri_literal(value):
    from starlayer.shacl import MetaShaclError, meta_validate

    shapes = g(SHAPES_PFX + f"ex:C a shui:Configuration ; shui:defaultNamespace {value} .")
    with pytest.raises(MetaShaclError) as raised:
        meta_validate(shapes, extra_graphs=[starontology.get_ontology_graph("shacl_shacl_ui")])
    assert "shui:defaultNamespace" in str(raised.value)


# ---- check_value -------------------------------------------------------------------------------------------------------


SHAPES = """
ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:property ex:PetShape , ex:AgeShape .
ex:PetShape sh:path ex:pet ; sh:class ex:Animal ; sh:disjoint ex:allergicTo ; sh:maxCount 1 .
ex:AgeShape sh:path ex:age ; sh:datatype xsd:integer ; sh:minCount 1 .
"""
DATA = """
ex:Rex a ex:Animal . ex:Tom a ex:Animal . ex:Fern a ex:Plant .
ex:Ann a ex:Person ; ex:allergicTo ex:Tom ; ex:pet ex:Rex ; ex:age 4 .
"""


def check(value, shape=EX.PetShape, focus=EX.Ann, shapes=SHAPES, data=DATA) -> ValueCheck:
    return check_value(g(shapes), shape, focus, value, g(data))


def test_a_value_that_fits_conforms():
    found = check(EX.Rex)
    assert isinstance(found, ValueCheck) and found.conforms and found.results == ()


def test_a_value_that_breaks_the_datatype_does_not_conform_and_the_result_says_where():
    found = check(literal("old", XSD.string), shape=EX.AgeShape)
    assert not found.conforms and len(found.results) == 1
    (result,) = found.results
    assert isinstance(result, ReportResult)
    assert (result.focus, result.path, result.component) == (EX.Ann, EX.age, SH.DatatypeConstraintComponent)
    assert result.value == literal("old", XSD.string) and result.source_shape == EX.AgeShape
    assert result.messages


def test_a_value_that_breaks_sh_disjoint_against_another_property_of_the_focus_is_refused():
    found = check(EX.Tom)
    assert not found.conforms
    assert [(r.component, r.focus, r.path) for r in found.results] == [(SH.DisjointConstraintComponent, EX.Ann, EX.pet)]


def test_a_value_replaces_the_current_ones_so_max_count_is_not_tripped():
    assert check(EX.Rex).conforms  # ex:Ann has ex:Rex as a pet already
    assert check(EX.Fern).conforms is False  # the class, not the count
    found = check(EX.Tom, data=DATA.replace("ex:pet ex:Rex ;", "ex:pet ex:Rex , ex:Fern ;"))
    assert [r.component for r in found.results] == [SH.DisjointConstraintComponent]  # no sh:maxCount result either


def test_only_the_given_property_shape_is_checked():
    found = check(EX.Rex, data=DATA.replace("ex:age 4", ""))
    assert found.conforms  # ex:AgeShape would say sh:minCount, but that is another field


def test_the_callers_graph_is_unchanged():
    data = g(DATA)
    before = set(data.triples((None, None, None)))
    check_value(g(SHAPES), EX.PetShape, EX.Ann, EX.Tom, data)
    assert set(data.triples((None, None, None))) == before


def test_an_inverse_path_is_written_the_other_way_round():
    shapes = "ex:OwnerShape sh:path [ sh:inversePath ex:pet ] ; sh:class ex:Person ; sh:maxCount 1 ."
    data = "ex:Ann a ex:Person . ex:Bob a ex:Person . ex:Rex ex:pet ex:Ann . ex:Fern a ex:Plant ."
    assert check_value(g(shapes), EX.OwnerShape, EX.Rex, EX.Bob, g(data)).conforms
    assert not check_value(g(shapes), EX.OwnerShape, EX.Rex, EX.Fern, g(data)).conforms


@pytest.mark.parametrize("path", ["( ex:pet ex:name )", "[ sh:zeroOrMorePath ex:pet ]"])
def test_a_path_that_cannot_be_written_is_a_value_error(path):
    with pytest.raises(ValueError, match="predicate"):
        check_value(g(f"ex:S sh:path {path} ; sh:minCount 1 ."), EX.S, EX.Ann, EX.Rex, g(DATA))


def test_an_unknown_property_shape_is_a_value_error_naming_the_argument():
    with pytest.raises(ValueError, match="property_shape"):
        check(EX.Rex, shape=EX.Missing)


def test_a_literal_cannot_be_the_value_of_an_inverse_path():
    shapes = "ex:OwnerShape sh:path [ sh:inversePath ex:pet ] ."
    with pytest.raises(ValueError, match="literal"):
        check_value(g(shapes), EX.OwnerShape, EX.Rex, literal("x", XSD.string), g(DATA))


def test_a_list_value_is_a_term_the_caller_built():
    shapes = "ex:LangShape sh:path ex:langs ; sh:memberShape [ sh:datatype xsd:string ] ; sh:minListLength 1 ."
    data = 'ex:Ann ex:langs ex:old . ex:good ex:x 1 .'
    good = g(data + ' _:l1 rdf:first "en" ; rdf:rest rdf:nil .')
    head = next(iter(good.subjects(ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#first"), None)))
    assert check_value(g(shapes), EX.LangShape, EX.Ann, head, good).conforms
    bad = g(data + " _:l1 rdf:first 5 ; rdf:rest rdf:nil .")
    head = next(iter(bad.subjects(ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#first"), None)))
    result = check_value(g(shapes), EX.LangShape, EX.Ann, head, bad)
    assert not result.conforms and result.results[0].component == SH.MemberShapeConstraintComponent


def test_what_is_checked_is_the_property_shape_only_not_the_text_checks_of_the_meta_layer(meta):
    """A pattern that is not a regular expression is accepted by the property shape for ``sh:pattern``; ``meta_validate`` has its own shape."""
    field = _field(meta, SHSH.ShapeShape, SH.pattern)
    data = g("ex:S sh:pattern \"(\" .")
    assert check_value(meta, field, EX.S, literal("(", XSD.string), data).conforms
    assert not check_value(meta, field, EX.S, literal("5", XSD.integer), data).conforms


def test_an_rdflib_graph_or_term_is_refused_by_check_value():
    rdflib = pytest.importorskip("rdflib")
    with pytest.raises(TypeError, match="from_rdflib"):
        check_value(rdflib.Graph(), EX.PetShape, EX.Ann, EX.Rex, g(DATA))
    with pytest.raises(TypeError):
        check_value(g(SHAPES), EX.PetShape, EX.Ann, rdflib.URIRef("http://example.org/Rex"), g(DATA))


def test_the_methods_match_the_functions_and_use_the_bound_graphs():
    shapes, data = g(SHAPES + f"ex:Q sh:path ex:q ; sh:node ex:L . {LIST_SHAPE}"), g(DATA)
    processor = StarShaclProcessor(shacl_graph=shapes, data_graph=data)
    from_method, from_function = processor.check_value(EX.PetShape, EX.Ann, EX.Tom), check_value(shapes, EX.PetShape, EX.Ann, EX.Tom, data)
    assert from_method.conforms is from_function.conforms is False
    # the result nodes are blank nodes of each call's own report; everything else is the same
    assert [(r.identity(), r.messages) for r in from_method.results] == [(r.identity(), r.messages) for r in from_function.results]
    assert processor.check_value(EX.PetShape, EX.Ann, EX.Rex).conforms
    other = g(DATA.replace("ex:allergicTo ex:Tom", "ex:allergicTo ex:Rex"))
    assert not processor.check_value(EX.PetShape, EX.Ann, EX.Rex, data_graph=other).conforms
    assert processor.value_form(EX.Q) == value_form(shapes, EX.Q) == "list"
    assert processor.value_form(EX.PetShape) == "single"


def test_the_method_applies_the_processors_severity_floor():
    shapes = "ex:AgeShape sh:path ex:age ; sh:datatype xsd:integer ; sh:severity sh:Warning ."
    data = "ex:Ann ex:age 4 ."
    value = literal("old", XSD.string)
    strict = StarShaclProcessor(shacl_graph=g(shapes), data_graph=g(data))
    lenient = StarShaclProcessor(shacl_graph=g(shapes), data_graph=g(data), allow_warnings=True)
    assert not strict.check_value(EX.AgeShape, EX.Ann, value).conforms
    found = lenient.check_value(EX.AgeShape, EX.Ann, value)
    assert found.conforms and [r.severity_name for r in found.results] == ["Warning"]
