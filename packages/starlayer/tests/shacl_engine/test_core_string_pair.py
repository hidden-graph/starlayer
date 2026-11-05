"""String, property-pair and list components of the native SHACL engine."""

from __future__ import annotations

import pytest
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.shacl_engine import validate
from starlayer.shacl_engine.plan import ShapeError
from starlayer.shacl_engine.terms import text

PRE = """@prefix ex: <http://example.com/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"""


def run(shape_body: str, data: str):
    """One property shape on ex:p targeting ex:a; ``shape_body`` holds its extra constraint triples."""
    sg, dg = StarLayerGraph(), StarLayerGraph()
    sg.parse(data=PRE + f"ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; {shape_body} ] .", format="turtle")
    dg.parse(data=PRE + data, format="turtle")
    return validate(dg, sg)


def values(shape_body: str, data: str) -> list[str]:
    """Sorted n3 of the sh:value of each result ('-' when none)."""
    return sorted("-" if not r.has_value else text(r.value) for r in run(shape_body, data).results)


@pytest.mark.parametrize(
    ("body", "data", "expected"),
    [
        ("sh:minLength 3", 'ex:a ex:p "ab", "abc", ex:i .', ["ab"]),
        ("sh:minLength 3", "ex:a ex:p [ ex:q 1 ] .", None),
        ("sh:maxLength 3", 'ex:a ex:p "abcd", "abc" .', ["abcd"]),
        ("sh:maxLength 5", 'ex:a ex:p "x"@en--rtl, "x" .', []),
        ("sh:pattern '^a.c$'", 'ex:a ex:p "abc", "abd" .', ["abd"]),
        ("sh:pattern 'JOH' ; sh:flags 'i'", 'ex:a ex:p "john", "mary" .', ["mary"]),
        ("sh:pattern '^\\\\p{Lu}'", 'ex:a ex:p "Abc", "abc" .', ["abc"]),
        ("sh:languageIn ('en' 'mi')", 'ex:a ex:p "a"@en-NZ, "b"@MI, "c"@de, "d", ex:i .', ["c", "d", "http://example.com/i"]),
        ("sh:singleLine true", 'ex:a ex:p "a\\nb", "ab" .', ["a\nb"]),
        ("sh:singleLine false", 'ex:a ex:p "a\\nb" .', []),
        ("sh:uniqueLang true", 'ex:a ex:p "a"@en, "b"@en, "c"@fr, "d" , "e" .', ["-"]),
        ("sh:uniqueLang true", 'ex:a ex:p "a"@en--ltr, "a"@en--rtl, "a"@en .', []),
        ("sh:uniqueLang true", 'ex:a ex:p "a"@en--ltr, "b"@en--ltr .', ["-"]),
    ],
)
def test_string_components(body, data, expected):
    if expected is None:
        assert len(run(body, data).results) == 1  # blank node value
    else:
        assert values(body, data) == sorted(expected)


def test_pattern_with_two_patterns_reports_each_failure():
    assert values("sh:pattern 'a' , 'b'", 'ex:a ex:p "a" .') == ["a"]


@pytest.mark.parametrize(
    "body",
    ["sh:minLength 'x'", "sh:pattern '(' ", "sh:pattern 'a' ; sh:flags 'z'", "sh:uniqueLang 'yes'", "sh:languageIn ex:notAList"],
)
def test_malformed_parameters_raise(body):
    with pytest.raises(ShapeError):
        run(body, 'ex:a ex:p "a" .')


@pytest.mark.parametrize(
    ("body", "data", "expected"),
    [
        ("sh:equals ex:q", 'ex:a ex:p 1, 2 ; ex:q 2, 3 .', ["1", "3"]),
        ("sh:equals ex:q", 'ex:a ex:p 1 ; ex:q 1 .', []),
        ("sh:equals ex:q", 'ex:a ex:q "x" .', ["x"]),
        ("sh:disjoint ex:q", 'ex:a ex:p 1, 2 ; ex:q 2, 3 .', ["2"]),
        ("sh:lessThan ex:q", 'ex:a ex:p 1, 5 ; ex:q 3 .', ["5"]),
        ("sh:lessThan ex:q", 'ex:a ex:p 3 ; ex:q 3 .', ["3"]),
        ("sh:lessThanOrEquals ex:q", 'ex:a ex:p 3 ; ex:q 3 .', []),
        ("sh:lessThan ex:q", 'ex:a ex:p 1 ; ex:q "a" .', ["1"]),
        ("sh:lessThan ex:q", 'ex:a ex:p "a" ; ex:q "b" .', []),
        ("sh:lessThan ex:q", 'ex:a ex:p "2020-01-01"^^xsd:date ; ex:q "2021-01-01"^^xsd:date .', []),
        ("sh:lessThan ex:q", 'ex:a ex:p 1.5 ; ex:q 2e0 .', []),
        ("sh:lessThan ex:q", 'ex:a ex:p "a"@en ; ex:q "b"@en .', ["a"]),
        ("sh:lessThan ex:q", "ex:a ex:p ex:i ; ex:q ex:j .", ["http://example.com/i"]),
    ],
)
def test_property_pair_components(body, data, expected):
    assert values(body, data) == sorted(expected)


def test_pair_property_may_be_a_sequence_path():
    assert values("sh:equals ( ex:q ex:r )", "ex:a ex:p 1 ; ex:q [ ex:r 1 ] .") == []
    assert values("sh:equals ( ex:q ex:r )", "ex:a ex:p 1 ; ex:q [ ex:r 2 ] .") == ["1", "2"]


def test_subset_of():
    assert values("sh:subsetOf ex:q", "ex:a ex:p 1, 2 ; ex:q 2, 3 .") == ["1"]
    assert values("sh:subsetOf ex:q", "ex:a ex:p 1 ; ex:q 1, 2 .") == []


LISTS = "ex:a ex:p {} ."


@pytest.mark.parametrize(
    ("body", "obj", "bad"),
    [
        ("sh:minListLength 2", "( 1 2 )", False),
        ("sh:minListLength 2", "( 1 )", True),
        ("sh:minListLength 0", "rdf:nil", False),
        ("sh:minListLength 1", "ex:notAList", True),
        ("sh:maxListLength 1", "( 1 2 )", True),
        ("sh:maxListLength 2", "( 1 2 )", False),
        ("sh:maxListLength 2", '"literal"', True),
        ("sh:uniqueMembers true", "( 1 2 1 )", True),
        ("sh:uniqueMembers true", "( 1 2 )", False),
        ("sh:uniqueMembers true", "( 1 1.0 )", False),  # distinct terms
        ("sh:uniqueMembers false", "( 1 1 )", False),
        ("sh:uniqueMembers true", "ex:notAList", True),
    ],
)
def test_list_components(body, obj, bad):
    assert bool(run(body, LISTS.format(obj)).results) is bad


def test_cyclic_list_is_not_a_list():
    data = "ex:a ex:p ex:l1 . ex:l1 rdf:first 1 ; rdf:rest ex:l2 . ex:l2 rdf:first 2 ; rdf:rest ex:l1 ."
    assert len(run("sh:minListLength 0", data).results) == 1


def test_member_shape_reports_once_per_list():
    shapes = "sh:memberShape [ sh:nodeKind sh:IRI ]"
    assert run(shapes, LISTS.format("( ex:x ex:y )")).results == []
    assert len(run(shapes, LISTS.format('( "x" "y" )')).results) == 1
    assert len(run(shapes, LISTS.format("ex:notAList")).results) == 1


def test_some_value():
    shapes = "sh:someValue [ sh:nodeKind sh:IRI ]"
    assert run(shapes, 'ex:a ex:p "x", ex:y .').results == []
    out = run(shapes, 'ex:a ex:p "x" .').results
    assert len(out) == 1 and not out[0].has_value
    assert len(run(shapes, "ex:a ex:q 1 .").results) == 1  # no value nodes at all
