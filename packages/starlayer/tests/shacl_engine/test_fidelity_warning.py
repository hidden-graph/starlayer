"""The lexical-fidelity warning (starlayer issue #190): one ``StarLayerFidelityWarning`` per validate() call when the data
graph does not preserve lexical forms, the shapes use form-dependent constraints and the data has an affected literal."""

from __future__ import annotations

import warnings

import pytest

pytest.importorskip("pyoxigraph")

from rdflib import Graph  # noqa: E402
from starlayer.graph.graph import StarLayerGraph  # noqa: E402
from starlayer.shacl_engine import api  # noqa: E402
from starlayer.shacl_engine.oxigraph_view import OxigraphGraph  # noqa: E402
from starlayer.shacl_engine.terms import StarLayerFidelityWarning  # noqa: E402

PFX = "@prefix ex: <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
INT_DATA = PFX + "ex:a ex:p 4 . ex:a ex:q 'x' .\n"
STR_DATA = PFX + "ex:a ex:p 'hello' .\n"


def _shape(body: str) -> str:
    return PFX + f"ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; {body} ] .\n"


def _validate(data, shapes):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        outcome = api.validate(data, shapes)
    return outcome, [w for w in caught if issubclass(w.category, StarLayerFidelityWarning)]


@pytest.mark.parametrize(
    "body, kind",
    [
        ("sh:pattern '^[0-9]+$'", "sh:pattern"),
        ("sh:minLength 1", "sh:minLength"),
        ("sh:maxLength 3", "sh:maxLength"),
        ("sh:datatype xsd:integer", "sh:datatype"),
        ("sh:in (1 2 4)", "sh:in"),
        ("sh:hasValue 4", "sh:hasValue"),
        ("sh:equals ex:q", "sh:equals"),
        ("sh:disjoint ex:q", "sh:disjoint"),
        ("sh:uniqueLang true", "sh:uniqueLang"),
    ],
)
def test_warns_once_for_a_form_dependent_constraint_over_an_oxigraph_graph(body, kind):
    data = OxigraphGraph.from_text(INT_DATA)
    outcome, caught = _validate(data, OxigraphGraph.from_text(_shape(body)))
    assert len(caught) == 1
    text = str(caught[0].message)
    assert kind in text and "#190" in text and "oxigraph#526" in text and "oxigraph#1989" in text and "PR #2010" in text
    assert outcome.warnings == (text,)


def test_one_warning_names_every_kind_involved():
    shapes = OxigraphGraph.from_text(_shape("sh:pattern '4' ; sh:minLength 1 ; sh:in (4)"))
    _, caught = _validate(OxigraphGraph.from_text(INT_DATA), shapes)
    assert len(caught) == 1
    assert all(k in str(caught[0].message) for k in ("sh:pattern", "sh:minLength", "sh:in"))


@pytest.mark.parametrize("make", [lambda t: Graph().parse(data=t, format="turtle"), lambda t: StarLayerGraph().parse(data=t, format="turtle")])
def test_no_warning_for_rdflib_or_starlayergraph_input(make):
    outcome, caught = _validate(make(INT_DATA), make(_shape("sh:pattern '^[0-9]+$' ; sh:in (4)")))
    assert caught == [] and outcome.warnings == ()


def test_no_warning_for_string_only_data():
    outcome, caught = _validate(OxigraphGraph.from_text(STR_DATA), OxigraphGraph.from_text(_shape("sh:pattern 'h' ; sh:minLength 1")))
    assert caught == [] and outcome.warnings == ()


def test_no_warning_when_the_constraints_do_not_depend_on_the_form():
    outcome, caught = _validate(OxigraphGraph.from_text(INT_DATA), OxigraphGraph.from_text(_shape("sh:minCount 1 ; sh:nodeKind sh:Literal")))
    assert caught == [] and outcome.warnings == ()


def test_sh_in_with_only_string_values_does_not_warn():
    _, caught = _validate(OxigraphGraph.from_text(INT_DATA), OxigraphGraph.from_text(_shape("sh:in ('a' 'b')")))
    assert caught == []


def test_the_warning_is_filterable():
    data, shapes = OxigraphGraph.from_text(INT_DATA), OxigraphGraph.from_text(_shape("sh:pattern '4'"))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("ignore", StarLayerFidelityWarning)
        outcome = api.validate(data, shapes)
    assert caught == [] and len(outcome.warnings) == 1  # still recorded on the outcome


def test_the_warning_is_a_userwarning():
    assert issubclass(StarLayerFidelityWarning, UserWarning)
