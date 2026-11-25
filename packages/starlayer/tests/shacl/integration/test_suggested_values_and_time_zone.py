"""What the shapes-about-shapes forms offer (``shui:suggestedValues``, an open set that never constrains), the closed set of ``sh:nodeKind``,
and the checks on ``shui:timeZone`` (its form, in ``shacl_shacl_ui``, and whether the platform knows it, in the private layer)."""

import zoneinfo

import pyoxigraph as ox
import pytest
from starlayer import starontology
from starlayer.graph import StarLayerGraph as Graph
from starlayer.shacl import MetaShaclError, form_model
from starlayer.shacl.engine.builtin_functions import (
    BUILTIN_FUNCTIONS,
    TIME_ZONE_PROBLEM,
)
from starlayer.shacl.engine.terms import NS
from starlayer.shacl.meta_shapes import meta_validate

EX = NS("http://example.org/")
SH = NS("http://www.w3.org/ns/shacl#")
XSD = NS("http://www.w3.org/2001/XMLSchema#")
STSH = NS("https://github.com/hidden-graph/starlayer/ns/shacl#")
PRE = ("@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix shui: <http://www.w3.org/ns/shacl-ui/> . "
       "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n")
DATATYPES = ["string", "boolean", "integer", "decimal", "double", "float", "date", "dateTime", "time", "anyURI", "gYear", "long", "int",
             "nonNegativeInteger", "positiveInteger"]


def graph(body: str) -> Graph:
    return Graph().parse(data=PRE + body, format="turtle")


def ui_check(body: str):
    return meta_validate(graph(body), extra_graphs=[starontology.get_ontology_graph("shacl_shacl_ui")])


def problems(body: str) -> str:
    """The report text of the strict meta check (a warning or info result counts), "" when the graph is valid."""
    try:
        ui_check(body)
    except MetaShaclError as error:
        return error.report_text
    return ""


def local(terms) -> list[str]:
    return [t.value.rsplit("#", 1)[-1] for t in terms]


# --- form_model offers the suggestions ---------------------------------------------------------------------------------------

def _model(node, form):
    shapes = Graph()
    for name in ("shacl_shacl_ui", "shacl_shacl"):
        shapes.extend(list(starontology.get_ontology_graph(name).triples((None, None, None))))
    data = graph("ex:P a sh:PropertyShape ; sh:path ex:p ; sh:severity sh:Warning ; sh:datatype xsd:string . ex:F a sh:Function ; sh:returnType xsd:string .")
    return form_model(shapes, data, node, shapes=form)


def test_form_model_offers_the_five_severities_and_the_datatypes():
    model = _model(EX.P, STSH.PropertyShapeForm)
    assert local(model.field(SH.severity).suggested) == ["Violation", "Warning", "Info", "Debug", "Trace"]
    assert local(model.field(SH.datatype).suggested) == DATATYPES + ["langString"]
    assert local(_model(EX.F, STSH.FunctionForm).field(SH.returnType).suggested) == DATATYPES + ["langString"]


def test_the_node_shape_form_offers_them_too():
    shapes = Graph()
    shapes.extend(list(starontology.get_ontology_graph("shacl_shacl_ui").triples((None, None, None))))
    model = form_model(shapes, graph("ex:N a sh:NodeShape ; sh:severity sh:Info ."), EX.N, shapes=STSH.NodeShapeForm)
    assert local(model.field(SH.severity).suggested) == ["Violation", "Warning", "Info", "Debug", "Trace"]


def test_the_suggestions_do_not_constrain():
    conforms, _report, _text = meta_validate(graph("ex:S a sh:NodeShape ; sh:severity ex:Loud . ex:T a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:datatype ex:MyType ] ."),
                                              extra_graphs=[starontology.get_ontology_graph("shacl_shacl_ui")])
    assert conforms


# --- sh:nodeKind is a closed set -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["sh:BlankNode", "sh:IRI", "sh:Literal", "sh:BlankNodeOrIRI", "sh:BlankNodeOrLiteral", "sh:IRIOrLiteral", "sh:TripleTerm",
                                   "( sh:IRI sh:Literal )"])
def test_a_node_kind_of_the_set_passes(value):
    assert meta_validate(graph("ex:S a sh:NodeShape ; sh:nodeKind " + value + " ."))[0]


@pytest.mark.parametrize("value", ["ex:Weird", "sh:Violation", "'IRI'", "( sh:IRI ex:Weird )"])
def test_a_node_kind_outside_the_set_is_reported(value):
    with pytest.raises(MetaShaclError):
        meta_validate(graph("ex:S a sh:NodeShape ; sh:nodeKind " + value + " ."))


def test_the_form_lists_the_seven_node_kinds():
    ui = starontology.get_ontology_graph("shacl_shacl_ui")
    for field in (STSH.PropertyShapeForm_sh_nodeKind, STSH.NodeShapeForm_sh_nodeKind):
        head = next(iter(ui.objects(field, SH["in"])))
        members = []
        while head != ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#nil"):
            members.append(next(iter(ui.objects(head, ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#first")))))
            head = next(iter(ui.objects(head, ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#rest"))))
        assert sorted(local(members)) == sorted(["BlankNode", "IRI", "Literal", "BlankNodeOrIRI", "BlankNodeOrLiteral", "IRIOrLiteral", "TripleTerm"])


# --- shui:timeZone ----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("zone", ["Europe/Vienna", "America/Argentina/Buenos_Aires", "Etc/GMT+5", "UTC"])
def test_a_well_formed_known_zone_passes_both_checks(zone):
    assert problems('ex:G shui:timeZone "' + zone + '" .') == ""


@pytest.mark.parametrize("zone", ["Europe Vienna", "", "/Vienna", "Europe/", "Europe//Vienna", "Europe/Vi enna"])
def test_a_malformed_zone_is_reported_by_the_pattern(zone):
    text = problems('ex:G shui:timeZone "' + zone + '" .')
    assert "IANA time-zone identifier" in text


def test_a_malformed_zone_is_a_warning_and_a_warning_makes_the_shapes_graph_invalid():
    with pytest.raises(MetaShaclError) as error:
        ui_check('ex:G shui:timeZone "Europe Vienna" .')
    assert "Europe Vienna" in error.value.report_text
    assert (None, SH.resultSeverity, SH.Warning) in error.value.report_graph


def test_an_unknown_zone_is_reported_by_the_existence_check_only():
    text = problems('ex:G shui:timeZone "Mars/Olympus" .')
    assert "platform's time-zone database" in text
    assert "IANA time-zone identifier" not in text  # it is well formed
    assert "Warning" in text  # advice, and advice makes the shapes graph invalid


def test_the_existence_check_is_in_the_layer_not_in_shacl_shacl_ui():
    layer = starontology._load_private("shacl_shacl_starlayer")
    assert list(layer.triples((STSH.TimeZoneShape, None, None)))
    for name in ("shacl_shacl", "shacl_shacl_ui"):
        assert not list(starontology.get_ontology_graph(name).triples((STSH.TimeZoneShape, None, None)))
    # without the layer the unknown zone is not noticed, the form is
    from starlayer.shacl.engine.api import validate as engine_validate

    base = Graph()
    for name in ("shacl_shacl", "shacl_shacl_ui"):
        base.extend(list(starontology.get_ontology_graph(name).triples((None, None, None))))
    shapes = graph('ex:G shui:timeZone "Mars/Olympus" . ex:H shui:timeZone "Europe Vienna" .')
    report = engine_validate(shapes, base, rules=False, meta_shacl=False, ignore_imports=True).report_graph
    messages = [m.value for m in report.objects(None, ox.NamedNode(SH.resultMessage.value))]
    assert len(messages) == 1 and "IANA time-zone identifier" in messages[0]  # Europe Vienna, by the pattern; Mars/Olympus is not noticed


def test_the_function_gives_no_value_for_a_known_zone_and_a_message_for_an_unknown_one():
    function = BUILTIN_FUNCTIONS[TIME_ZONE_PROBLEM]
    assert function(ox.Literal("Europe/Vienna")) is None
    assert "platform's time-zone database" in function(ox.Literal("Mars/Olympus")).value
    assert function(ox.NamedNode("http://example.org/x")) is None
    assert function(ox.Literal("7", datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer"))) is None


def test_a_machine_without_a_time_zone_database_reports_nothing(monkeypatch):
    monkeypatch.setattr(zoneinfo, "available_timezones", lambda: set())
    assert BUILTIN_FUNCTIONS[TIME_ZONE_PROBLEM](ox.Literal("Mars/Olympus")) is None
    assert problems('ex:G shui:timeZone "Mars/Olympus" .') == ""


# --- shui:defaultOrder: the draft says "is of datatype xsd:decimal or xsd:integer" (a Violation) -----------------------------

@pytest.mark.parametrize("value", ["0", "-10", "2.5"])
def test_default_order_of_a_number_passes(value):
    assert problems("ex:G shui:defaultOrder " + value + " .") == ""


@pytest.mark.parametrize("value", ["'first'", "'3'", "1e3"])
def test_default_order_that_is_not_decimal_or_integer_is_a_violation(value):
    assert "Violation" in problems("ex:G shui:defaultOrder " + value + " .")
