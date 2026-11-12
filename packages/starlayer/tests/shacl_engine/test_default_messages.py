"""Default ``sh:resultMessage`` wording of the engine (a shape without ``sh:message``): plain phrases that name the path,
the offending value and the limit, with correct singular and plural; ``sh:message`` still wins; the structured result
fields stay on the row."""

from __future__ import annotations

import pytest
from pyoxigraph import NamedNode as URIRef
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.shacl_engine.api import validate
from starlayer.shacl_engine.terms import SH

PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . "


def g(ttl: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=PFX + ttl, format="turtle")
    return graph


def messages(data: str, constraint: str, node_level: bool = False) -> list[str]:
    shape = f"ex:S a sh:NodeShape ; sh:targetNode ex:n ; {constraint} ." if node_level else (
        f"ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:property [ sh:path ex:p ; {constraint} ] ."
    )
    report = validate(g(data), g(shape)).report_graph
    return sorted(str(m.value) for m in report.objects(None, SH.resultMessage))


CASES = [
    ("ex:n ex:q 1 .", "sh:minCount 1", ["Needs at least 1 value for ex:p"]),
    ("ex:n ex:q 1 .", "sh:minCount 2", ["Needs at least 2 values for ex:p"]),
    ("ex:n ex:p 1, 2 .", "sh:maxCount 1", ["Allows at most 1 value for ex:p"]),
    ("ex:n ex:p 1, 2, 3 .", "sh:maxCount 2", ["Allows at most 2 values for ex:p"]),
    ("ex:n ex:p ex:x .", "sh:class ex:C", ["Value ex:x should be an instance of ex:C"]),
    ("ex:n ex:p 'a' .", "sh:datatype xsd:integer", ['Value "a" should have the datatype xsd:integer']),
    ("ex:n ex:p 'a' .", "sh:nodeKind sh:IRI", ['Value "a" should be an IRI']),
    ("ex:n ex:p 'a' .", "sh:minLength 3", ['Value "a" should have at least 3 characters']),
    ("ex:n ex:p 'abc' .", "sh:maxLength 1", ['Value "abc" should have at most 1 character']),
    ("ex:n ex:p 3 .", "sh:minInclusive 5", ["Value 3 should be at least 5"]),
    ("ex:n ex:p 3 .", "sh:minExclusive 3", ["Value 3 should be greater than 3"]),
    ("ex:n ex:p 7 .", "sh:maxExclusive 5", ["Value 7 should be less than 5"]),
    ("ex:n ex:p 7 .", "sh:maxInclusive 5", ["Value 7 should be at most 5"]),
    ("ex:n ex:p 'a' .", "sh:pattern '^b'", ["Value \"a\" should match the pattern '^b'"]),
    ("ex:n ex:p 'a'@fr .", "sh:languageIn ('en' 'de')", ['Value "a"@fr should have a language tag in "en", "de"']),
    ("ex:n ex:p 'a'@en, 'b'@en .", "sh:uniqueLang true", ["Values for ex:p should not share a language tag"]),
    ("ex:n ex:p 1 ; ex:q 2 .", "sh:equals ex:q", ["Value 1 should also be a value of ex:q", "Value 2 should also be a value of ex:q"]),
    ("ex:n ex:p 1 ; ex:q 1 .", "sh:disjoint ex:q", ["Value 1 should not also be a value of ex:q"]),
    ("ex:n ex:p 5 ; ex:q 1 .", "sh:lessThan ex:q", ["Value 5 should be less than every value of ex:q"]),
    ("ex:n ex:p 5 ; ex:q 1 .", "sh:lessThanOrEquals ex:q", ["Value 5 should be at most every value of ex:q"]),
    ("ex:n ex:p 9 .", "sh:in (1 2)", ["Value 9 should be one of 1, 2"]),
    ("ex:n ex:p 9 .", "sh:not [ sh:minInclusive 5 ]", [None]),
    ("ex:n ex:p 9 .", "sh:or ( [ sh:maxInclusive 5 ] [ sh:datatype xsd:string ] )", [None]),
]


@pytest.mark.parametrize(("data", "constraint", "want"), CASES)
def test_default_message(data, constraint, want):
    got = messages(data, constraint)
    if None in want:  # the nested shapes are blank nodes: only the sentence frame is fixed
        assert len(got) == 1 and got[0].startswith("Value 9 should ")
        return
    assert got == want


def test_closed_names_the_property():
    got = messages("ex:n ex:q 1 .", "sh:closed true ; sh:property [ sh:path ex:p ]", node_level=True)
    assert got == ["The property ex:q is not allowed here, because the shape is closed"]


def test_node_shape_value_message_has_no_path_phrase():
    assert messages("ex:n ex:p 1 .", "sh:nodeKind sh:Literal", node_level=True) == ["Value ex:n should be a literal"]


def test_no_arrow_notation_or_pyshacl_wording():
    for data, constraint, _ in CASES:
        for m in messages(data, constraint):
            assert "->" not in m and "Less than" not in m and "More than" not in m and "values on" not in m


def test_sh_message_wins():
    got = messages("ex:n ex:q 1 .", "sh:minCount 1 ; sh:message 'custom'")
    assert got == ["custom"]


def test_result_rows_keep_their_structured_fields():
    report = validate(g("ex:n ex:p 'a' ."), g("ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:property [ sh:path ex:p ; sh:datatype xsd:integer ] .")).report_graph
    row = next(report.subjects(SH.resultMessage))
    assert set(report.objects(row, SH.sourceConstraintComponent)) == {SH.DatatypeConstraintComponent}
    assert set(report.objects(row, SH.resultPath)) == {URIRef("http://example.org/p")}
    assert len(set(report.objects(row, SH.value))) == 1 and len(set(report.objects(row, SH.sourceShape))) == 1
    assert len(set(report.objects(row, SH.focusNode))) == 1
