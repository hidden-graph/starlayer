"""The default validation-result message of every constraint component the engine implements.

Each case is a shapes graph and a data graph that fail one component. The test asserts the key substrings of the default
message (the path, the focus node or value, the limit or expected shape), that no blank-node label is printed, and that a
shape's own ``sh:message`` replaces the default. The message text is not part of SHACL conformance; this pins that it
says something useful."""

from __future__ import annotations

import re

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl import validate

_HEADER = """
@prefix ex: <http://example.org/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
"""


def _prop(constraints: str, extra: str = "") -> str:
    return f"ex:S a sh:PropertyShape ; sh:targetNode ex:a ; sh:path ex:p ; {constraints} .\n{extra}"


def _node(constraints: str, extra: str = "") -> str:
    return f"ex:S a sh:NodeShape ; sh:targetNode ex:a ; {constraints} .\n{extra}"


_DUCK = "ex:DuckShape a sh:NodeShape ; sh:class ex:Duck .\n"
_SELECT_P = '"SELECT $this ?value WHERE { $this <http://example.org/p> ?value }"'

# id: (shapes, data, substrings every message of the result must contain together; checked on the whole Message lines)
CASES: dict[str, tuple[str, str, list[str]]] = {
    "class": (_prop("sh:class ex:Animal"), "ex:a ex:p ex:Plant .", ["ex:Plant", "ex:Animal"]),
    "class-list": (_prop("sh:class ( ex:Animal ex:Robot )"), "ex:a ex:p ex:Plant .", ["ex:Plant", "one of ex:Animal, ex:Robot"]),
    "datatype": (_prop("sh:datatype xsd:integer"), 'ex:a ex:p "x" .', ['"x"', "xsd:integer"]),
    "datatype-list": (_prop("sh:datatype ( xsd:integer xsd:date )"), 'ex:a ex:p "x" .', ['"x"', "one of the datatypes xsd:integer, xsd:date"]),
    "nodeKind": (_prop("sh:nodeKind sh:IRI"), 'ex:a ex:p "x" .', ['"x"', "an IRI"]),
    "nodeKind-list": (_prop("sh:nodeKind ( sh:IRI sh:BlankNode )"), 'ex:a ex:p "x" .', ['"x"', "an IRI or a blank node"]),
    "nodeKind-triple-term": (_prop("sh:nodeKind sh:TripleTerm"), 'ex:a ex:p "x" .', ["a triple term"]),
    "nodeKind-blank-value": (_prop("sh:nodeKind sh:IRI"), "ex:a ex:p [ ex:q 1 ] .", ["A blank node value", "an IRI"]),
    "minCount": (_prop("sh:minCount 1"), "ex:a ex:q 1 .", ["at least 1 value for ex:p"]),
    "minCount-2": (_prop("sh:minCount 2"), "ex:a ex:p 1 .", ["at least 2 values for ex:p"]),
    "maxCount": (_prop("sh:maxCount 1"), "ex:a ex:p 1, 2 .", ["at most 1 value for ex:p"]),
    "minExclusive": (_prop("sh:minExclusive 5"), "ex:a ex:p 3 .", ["3", "greater than 5"]),
    "minInclusive": (_prop("sh:minInclusive 5"), "ex:a ex:p 3 .", ["3", "at least 5"]),
    "maxExclusive": (_prop("sh:maxExclusive 5"), "ex:a ex:p 7 .", ["7", "less than 5"]),
    "maxInclusive": (_prop("sh:maxInclusive 5"), "ex:a ex:p 7 .", ["7", "at most 5"]),
    "minLength": (_prop("sh:minLength 5"), 'ex:a ex:p "ab" .', ['"ab"', "at least 5 characters"]),
    "maxLength": (_prop("sh:maxLength 2"), 'ex:a ex:p "abcd" .', ['"abcd"', "at most 2 characters"]),
    "pattern": (_prop('sh:pattern "^a"'), 'ex:a ex:p "bcd" .', ['"bcd"', "'^a'"]),
    "pattern-flags": (_prop('sh:pattern "^a" ; sh:flags "i"'), 'ex:a ex:p "bcd" .', ['"bcd"', "'^a' (flags i)"]),
    "languageIn": (_prop('sh:languageIn ( "en" "fr" )'), 'ex:a ex:p "x"@de .', ['"x"@de', '"en", "fr"']),
    "languageIn-untagged": (_prop('sh:languageIn ( "en" "fr" )'), 'ex:a ex:p "x" .', ['"x"', '"en", "fr"']),
    "uniqueLang": (_prop("sh:uniqueLang true"), 'ex:a ex:p "a"@en, "b"@en .', ["ex:p", "language tag en", "found 2"]),
    "singleLine": (_prop("sh:singleLine true"), 'ex:a ex:p "one\\ntwo" .', ["one\\ntwo", "line break"]),
    "equals": (_prop("sh:equals ex:q"), "ex:a ex:p 1 ; ex:q 2 .", ["Value 1 for ex:p", "a value of ex:q", "Value 2 for ex:q", "a value of ex:p"]),
    "equals-sequence-path": (_prop("sh:equals ( ex:q ex:r )"), "ex:a ex:p 1 .\nex:a ex:q ex:m . ex:m ex:r 2 .", ["ex:q/ex:r"]),
    "equals-inverse-path": (_prop("sh:equals [ sh:inversePath ex:q ]"), "ex:a ex:p ex:b .", ["^ex:q"]),
    "disjoint": (_prop("sh:disjoint ex:q"), "ex:a ex:p 1 ; ex:q 1 .", ["Value 1", "ex:q"]),
    "lessThan": (_prop("sh:lessThan ex:q"), "ex:a ex:p 5 ; ex:q 3 .", ["Value 5", "less than the value 3 of ex:q"]),
    "lessThanOrEquals": (_prop("sh:lessThanOrEquals ex:q"), "ex:a ex:p 5 ; ex:q 3 .", ["Value 5", "at most the value 3 of ex:q"]),
    "subsetOf": (_prop("sh:subsetOf ex:q"), "ex:a ex:p ex:x, ex:y ; ex:q ex:x .", ["Value ex:y for ex:p", "not reachable by ex:q"]),
    "hasValue": (_prop("sh:hasValue ex:v"), "ex:a ex:p ex:w .", ["ex:v", "ex:p"]),
    "hasValue-literal": (_prop('sh:hasValue "v"'), 'ex:a ex:p "w" .', ['"v"', "ex:p"]),
    "in": (_prop("sh:in ( 1 2 )"), "ex:a ex:p 3 .", ["Value 3", "one of 1, 2"]),
    "minListLength": (_prop("sh:minListLength 2"), "ex:a ex:p ( ex:x ) .", ["ex:p", "1 member", "at least 2 are needed"]),
    "minListLength-empty": (_prop("sh:minListLength 1"), "ex:a ex:p () .", ["0 members", "at least 1 is needed"]),
    "minListLength-not-list": (_prop("sh:minListLength 2"), "ex:a ex:p ex:x .", ["ex:x", "ex:p", "should be a list"]),
    "maxListLength": (_prop("sh:maxListLength 3"), "ex:a ex:p ( 1 2 3 4 ) .", ["ex:p", "4 members", "at most 3 are allowed"]),
    "maxListLength-not-list": (_prop("sh:maxListLength 3"), "ex:a ex:p ex:x .", ["ex:x", "should be a list"]),
    "uniqueMembers": (_prop("sh:uniqueMembers true"), "ex:a ex:p ( ex:alice ex:bob ex:alice ) .", ["ex:alice more than once"]),
    "uniqueMembers-not-list": (_prop("sh:uniqueMembers true"), "ex:a ex:p ex:x .", ["ex:x", "should be a list"]),
    "memberShape": (_prop("sh:memberShape ex:StrShape", "ex:StrShape a sh:NodeShape ; sh:datatype xsd:string .\n"), 'ex:a ex:p ( "ok" 5 ) .', ["member 5", "ex:p", "ex:StrShape"]),
    "memberShape-not-list": (_prop("sh:memberShape ex:StrShape", "ex:StrShape a sh:NodeShape ; sh:datatype xsd:string .\n"), "ex:a ex:p ex:x .", ["ex:x", "should be a list"]),
    "someValue": (_prop("sh:someValue ex:DuckShape", _DUCK), "ex:a ex:p ex:cat .", ["No value of ex:p conforms to ex:DuckShape"]),
    "someValue-no-values": (_prop("sh:someValue ex:DuckShape", _DUCK), "ex:a ex:q 1 .", ["No value of ex:p conforms to ex:DuckShape"]),
    "not": (_prop("sh:not ex:DuckShape", _DUCK), "ex:a ex:p ex:d . ex:d a ex:Duck .", ["ex:d", "not conform to the shape ex:DuckShape"]),
    "and": (_prop("sh:and ( ex:DuckShape ex:SwimShape )", _DUCK + "ex:SwimShape a sh:NodeShape ; sh:class ex:Swimmer .\n"), "ex:a ex:p ex:d . ex:d a ex:Duck .", ["ex:d", "all of the shapes ex:DuckShape, ex:SwimShape"]),
    "or": (_prop("sh:or ( ex:DuckShape ex:SwimShape )", _DUCK + "ex:SwimShape a sh:NodeShape ; sh:class ex:Swimmer .\n"), "ex:a ex:p ex:d .", ["ex:d", "at least one of the shapes ex:DuckShape, ex:SwimShape"]),
    "xone": (_prop("sh:xone ( ex:DuckShape ex:SwimShape )", _DUCK + "ex:SwimShape a sh:NodeShape ; sh:class ex:Swimmer .\n"), "ex:a ex:p ex:d . ex:d a ex:Duck, ex:Swimmer .", ["ex:d", "exactly one of the shapes ex:DuckShape, ex:SwimShape"]),
    "node": (_prop("sh:node ex:DuckShape", _DUCK), "ex:a ex:p ex:d .", ["ex:d", "ex:DuckShape", "ex:Duck"]),
    "node-on-node-shape": (_node("sh:node ex:DuckShape", _DUCK), "ex:a a ex:Cat .", ["ex:a", "ex:DuckShape", "ex:Duck"]),
    "qualifiedMinCount": (_prop("sh:qualifiedValueShape ex:DuckShape ; sh:qualifiedMinCount 2", _DUCK), "ex:a ex:p ex:d . ex:d a ex:Duck .", ["at least 2 values for ex:p", "ex:DuckShape", "found 1"]),
    "qualifiedMaxCount": (_prop("sh:qualifiedValueShape ex:DuckShape ; sh:qualifiedMaxCount 1", _DUCK), "ex:a ex:p ex:d, ex:e . ex:d a ex:Duck . ex:e a ex:Duck .", ["at most 1 value for ex:p", "ex:DuckShape", "found 2"]),
    "closed": (_node("sh:closed true ; sh:property [ sh:path ex:p ]"), "ex:a ex:p 1 ; ex:z 2 .", ["ex:a", "ex:z", "closed"]),
    "closed-ignored": (_node("sh:closed true ; sh:ignoredProperties ( rdf:type ) ; sh:property [ sh:path ex:p ]"), "ex:a ex:p 1 ; ex:z 2 .", ["ex:a", "ex:z", "closed"]),
    "closed-ByTypes": (_node("sh:closed sh:ByTypes", "ex:C a rdfs:Class, sh:NodeShape ; sh:property [ sh:path ex:p ] .\n"), "ex:a a ex:C ; ex:p 1 ; ex:z 2 .", ["ex:a", "ex:z", "its types"]),
    "reifierShape": (_prop("sh:reifierShape ex:ClaimShape", "ex:ClaimShape a sh:NodeShape ; sh:property [ sh:path ex:author ; sh:minCount 1 ] .\n"), 'ex:a ex:p 23 {| ex:date "d" |} .', ["(ex:a ex:p 23)", "reifier", "ex:ClaimShape"]),
    "reificationRequired": (_prop("sh:reificationRequired true"), "ex:a ex:p 23 .", ["(ex:a ex:p 23)", "no reifier"]),
    "rootClass": (_prop("sh:rootClass ex:Animal"), "ex:a ex:p ex:Plant .", ["ex:Plant", "ex:Animal or a subclass"]),
    "rootClass-list": (_prop("sh:rootClass ( ex:Animal ex:Fungus )"), "ex:a ex:p ex:Plant .", ["ex:Plant", "ex:Animal, ex:Fungus"]),
    "uniqueValuesFor": (
        "ex:S a sh:NodeShape ; sh:targetNode ex:a, ex:b ; sh:uniqueValuesFor ex:name .",
        'ex:a ex:name "Bob" . ex:b ex:name "Bob" .',
        ["ex:a", "ex:b", "ex:name"],
    ),
    "expression-node": (_node("sh:expression false"), "ex:a ex:p 1 .", ["ex:a", "expression false"]),
    "expression-property": (_prop("sh:expression false"), "ex:a ex:p 1 .", ["Value 1", "expression false"]),
    "nodeByExpression": (_prop("sh:nodeByExpression ex:DuckShape", _DUCK), "ex:a ex:p ex:d .", ["ex:d", "ex:DuckShape"]),
    "sparql": (_node(f"sh:sparql [ sh:select {_SELECT_P} ]"), "ex:a ex:p 1 .", ["ex:a", "SPARQL constraint"]),
    "sparql-property": (_prop(f"sh:sparql [ sh:select {_SELECT_P} ]"), "ex:a ex:p 1 .", ["Value 1", "ex:p", "SPARQL constraint"]),
    "sparql-ask-component": (
        _prop(
            "ex:minScore 50",
            "ex:MinScoreConstraintComponent a sh:ConstraintComponent ; sh:parameter [ sh:path ex:minScore ] ;"
            ' sh:validator [ a sh:SPARQLAskValidator ; sh:ask "ASK { FILTER (?value >= ?minScore) }" ] .\n',
        ),
        "ex:a ex:p 20 .",
        ["Value 20", "MinScoreConstraintComponent", "ex:minScore 50"],
    ),
    "sparql-select-component": (
        _prop(
            "ex:minScore 50",
            "ex:MinScoreConstraintComponent a sh:ConstraintComponent ; sh:parameter [ sh:path ex:minScore ] ;"
            ' sh:propertyValidator [ a sh:SPARQLSelectValidator ; sh:select "SELECT $this ?value WHERE { $this $PATH ?value . FILTER (?value < $minScore) }" ] .\n',
        ),
        "ex:a ex:p 20 .",
        ["Value 20", "MinScoreConstraintComponent", "ex:minScore 50"],
    ),
}


def _run(shapes: str, data: str):
    s, d = StarLayerGraph(), StarLayerGraph()
    s.parse(data=_HEADER + shapes, format="turtle")
    d.parse(data=_HEADER + data, format="turtle12")
    return validate(d, s)


def _messages(result) -> list[str]:
    return [line.split("Message: ", 1)[1] for line in result.report_text.splitlines() if "Message: " in line]


_BNODE = re.compile(r"_:|\bn[0-9a-f]{8,}\b|\bb[0-9]+\b")


@pytest.mark.parametrize("case", sorted(CASES))
def test_default_message_names_what_matters(case: str) -> None:
    shapes, data, expected = CASES[case]
    result = _run(shapes, data)
    assert not result.conforms
    messages = _messages(result)
    assert messages, "a failing result has a default message"
    for message in messages:
        assert message.strip()
        assert not _BNODE.search(message), message
    joined = " | ".join(messages)
    for part in expected:
        assert part in joined, f"{part!r} missing from {joined!r}"


@pytest.mark.parametrize("case", sorted(CASES))
def test_shapes_own_message_replaces_the_default(case: str) -> None:
    shapes, data, _ = CASES[case]
    result = _run(shapes.replace("ex:S a ", 'ex:S sh:message "custom" ; a ', 1), data)
    assert not result.conforms
    top = [line for line in result.report_text.splitlines() if line.startswith("\tMessage: ")]
    assert top, "the shape's message is reported"
    assert all(line == "\tMessage: custom" for line in top), top


def test_conjoined_classes_name_only_the_missing_class() -> None:
    shapes = _prop("sh:class ex:Dog, ex:Trained")
    result = _run(shapes, "ex:a ex:p ex:buddy . ex:buddy a ex:Dog .")
    assert _messages(result) == ["Value ex:buddy should be an instance of ex:Trained"]
    both = _messages(_run(shapes, "ex:a ex:p ex:buddy ."))
    assert sorted(both) == [
        "Value ex:buddy should be an instance of ex:Dog",
        "Value ex:buddy should be an instance of ex:Trained",
    ]


def test_conjoined_datatypes_name_only_the_failed_datatype() -> None:
    result = _run(_prop("sh:datatype xsd:string, xsd:date"), 'ex:a ex:p "x" .')
    assert _messages(result) == ['Value "x" should have the datatype xsd:date']


def test_inline_shape_is_worded_without_a_blank_node_label() -> None:
    result = _run(_prop("sh:not [ sh:class ex:Duck ]"), "ex:a ex:p ex:d . ex:d a ex:Duck .")
    (message,) = _messages(result)
    assert "ex:Duck" in message and not _BNODE.search(message)


def test_a_sequence_path_in_a_count_message_reads_as_a_path() -> None:
    shapes = "ex:S a sh:PropertyShape ; sh:targetNode ex:a ; sh:path ( ex:p ex:q ) ; sh:minCount 1 ."
    assert _messages(_run(shapes, "ex:a ex:r 1 ."))[0].endswith("for ex:p/ex:q")
