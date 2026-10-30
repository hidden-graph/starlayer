"""Unit tests for the Core value components of the native SHACL engine (``components/core_value.py``)."""

from __future__ import annotations

import pytest
from rdflib import Graph
from rdflib.namespace import Namespace
from starlayer.shacl_engine import validate
from starlayer.shacl_engine.plan import ShapeError

SH = Namespace("http://www.w3.org/ns/shacl#")
EX = Namespace("http://example.com/")
PREFIXES = """
@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.com/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
"""


def run(shape_body: str, data: str):
    """Validate ``ex:a`` against a property shape on ex:p with the given constraint body."""
    shapes = Graph().parse(
        data=PREFIXES + f"ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; {shape_body} ] .",
        format="turtle",
    )
    data_g = Graph().parse(data=PREFIXES + data, format="turtle")
    return validate(data_g, shapes)


def values(outcome):
    return {r.value for r in outcome.results}


def components(outcome):
    return {r.component for r in outcome.results}


def test_class_uses_subclass_closure_in_data_graph():
    out = run(
        "sh:class ex:Animal",
        "ex:Dog rdfs:subClassOf ex:Animal . ex:a ex:p ex:rex, ex:tree . ex:rex a ex:Dog . ex:tree a ex:Plant .",
    )
    assert values(out) == {EX.tree}
    assert components(out) == {SH.ClassConstraintComponent}


def test_class_literal_value_violates():
    assert not run("sh:class ex:Animal", 'ex:a ex:p "x" .').conforms


def test_class_list_is_a_union():
    out = run("sh:class ( ex:A ex:B )", "ex:a ex:p ex:x, ex:y . ex:x a ex:B .")
    assert values(out) == {EX.y}


def test_datatype_checks_datatype_and_well_formedness():
    out = run(
        "sh:datatype xsd:integer",
        'ex:a ex:p 1, "abc"^^xsd:integer, "s", "2"^^xsd:decimal .',
    )
    assert {str(v) for v in values(out)} == {"abc", "s", "2"}


def test_datatype_langstring_and_plain_string():
    assert run("sh:datatype rdf:langString", 'ex:a ex:p "hi"@en .').conforms
    assert not run("sh:datatype rdf:langString", 'ex:a ex:p "hi" .').conforms
    assert not run("sh:datatype xsd:string", 'ex:a ex:p "hi"@en .').conforms
    assert run("sh:datatype xsd:string", 'ex:a ex:p "hi" .').conforms


def test_datatype_iri_value_violates():
    assert not run("sh:datatype xsd:string", "ex:a ex:p ex:b .").conforms


@pytest.mark.parametrize(
    ("kind", "bad"),
    [
        ("sh:IRI", {"bnode", "lit"}),
        ("sh:BlankNode", {"iri", "lit"}),
        ("sh:Literal", {"iri", "bnode"}),
        ("sh:BlankNodeOrIRI", {"lit"}),
        ("sh:BlankNodeOrLiteral", {"iri"}),
        ("sh:IRIOrLiteral", {"bnode"}),
    ],
)
def test_node_kind(kind, bad):
    out = run(f"sh:nodeKind {kind}", 'ex:a ex:p ex:i, _:b, "l" .')
    seen = set()
    for v in values(out):
        seen.add("iri" if v == EX.i else "lit" if str(v) == "l" else "bnode")
    assert seen == bad


def test_node_kind_rejects_unknown_kind():
    with pytest.raises(ShapeError):
        run("sh:nodeKind ex:Nope", "ex:a ex:p ex:b .")


def test_count_reports_no_value():
    out = run("sh:minCount 2", "ex:a ex:p 1 .")
    assert [r.has_value for r in out.results] == [False]
    assert components(out) == {SH.MinCountConstraintComponent}
    out = run("sh:maxCount 1", "ex:a ex:p 1, 2 .")
    assert [r.has_value for r in out.results] == [False]
    assert components(out) == {SH.MaxCountConstraintComponent}
    assert run("sh:minCount 1 ; sh:maxCount 2", "ex:a ex:p 1, 2 .").conforms


def test_count_malformed_raises():
    with pytest.raises(ShapeError):
        run('sh:minCount "x"', "ex:a ex:p 1 .")
    with pytest.raises(ShapeError):
        run("sh:maxCount -1", "ex:a ex:p 1 .")


@pytest.mark.parametrize(
    ("param", "bad"),
    [
        ("sh:minExclusive 5", {"5", "4"}),
        ("sh:minInclusive 5", {"4"}),
        ("sh:maxExclusive 5", {"5", "6"}),
        ("sh:maxInclusive 5", {"6"}),
    ],
)
def test_ranges(param, bad):
    out = run(param, "ex:a ex:p 4, 5, 6 .")
    got = {str(v) for v in values(out)}
    assert got == bad


def test_range_mixed_numeric_types_and_incomparable():
    out = run("sh:minInclusive 1.5", 'ex:a ex:p 2, 1.0e0, "x", ex:i, "3"^^xsd:integer .')
    assert {str(v) for v in values(out)} == {"1.0", "x", "http://example.com/i"}


def test_range_dates_and_strings():
    assert run('sh:maxInclusive "2020-01-02"^^xsd:date', 'ex:a ex:p "2020-01-01"^^xsd:date .').conforms
    assert not run('sh:maxInclusive "2020-01-02"^^xsd:date', 'ex:a ex:p "2020-01-03"^^xsd:date .').conforms
    # dateTime against date is incomparable
    assert not run(
        'sh:maxInclusive "2020-01-02"^^xsd:date', 'ex:a ex:p "2020-01-01T00:00:00"^^xsd:dateTime .'
    ).conforms
    assert run('sh:minInclusive "b"', 'ex:a ex:p "c" .').conforms
    assert not run('sh:minInclusive "b"', 'ex:a ex:p "a" .').conforms


def test_range_ill_typed_is_incomparable():
    assert not run("sh:minInclusive 0", 'ex:a ex:p "zz"^^xsd:integer .').conforms


def test_has_value():
    assert run("sh:hasValue 1", "ex:a ex:p 1, 2 .").conforms
    out = run("sh:hasValue 3", "ex:a ex:p 1, 2 .")
    assert [r.has_value for r in out.results] == [False]
    assert components(out) == {SH.HasValueConstraintComponent}


def test_in():
    out = run('sh:in ( 1 "a" ex:i )', 'ex:a ex:p 1, "a", ex:i, 2, "b" .')
    assert {str(v) for v in values(out)} == {"2", "b"}
    assert components(out) == {SH.InConstraintComponent}


def test_in_malformed_raises():
    with pytest.raises(ShapeError):
        run("sh:in 1", "ex:a ex:p 1 .")
