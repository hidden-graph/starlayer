"""``MessageMemo``: the messages and the fixed lines of a report are worded once per distinct result, and are the same as worded one by one."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl.engine import text
from starlayer.shacl.engine.api import validate
from starlayer.shacl.engine.executor import Result
from starlayer.shacl.engine.plan import Path
from starlayer.shacl.engine.terms import SH
from starlayer.shacl.engine.text import MessageMemo, report_text, result_messages

PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . "
SHAPES = (
    "ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:age ; sh:datatype xsd:integer ] ; "
    "sh:property [ sh:path ex:name ; sh:minCount 1 ] ; sh:sparql [ sh:select 'SELECT $this WHERE { $this ex:flag true }' ; sh:prefixes ex:P ] ."
    " ex:P sh:declare [ sh:prefix 'ex' ; sh:namespace 'http://example.org/'^^xsd:anyURI ] ."
)
DATA = " ".join(f'ex:n{i} a ex:C ; ex:age "x{i % 2}" ; ex:flag true .' for i in range(6))


def graph(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PFX + ttl, format="turtle")
    return g


def run():
    shapes, data = graph(SHAPES), graph(DATA)
    return validate(data, shapes), shapes, data


def test_a_memoised_message_is_the_one_worded_alone() -> None:
    outcome, shapes, data = run()
    memo = MessageMemo()
    assert len(outcome.results) > 6
    for r in outcome.results:
        assert memo(r, shapes, data) == result_messages(r, shapes, data)


def test_a_message_is_worded_once_for_results_that_differ_only_in_the_focus_node(monkeypatch) -> None:
    outcome, shapes, data = run()
    calls = []
    original = text.result_messages
    monkeypatch.setattr(text, "result_messages", lambda r, s, d: calls.append(r) or original(r, s, d))
    memo = MessageMemo()
    min_counts = [r for r in outcome.results if r.component.value.endswith("MinCountConstraintComponent")]
    assert len(min_counts) == 6
    for r in min_counts:
        memo(r, shapes, data)
    assert len(calls) == 1


def test_results_with_different_values_are_worded_apart() -> None:
    outcome, shapes, data = run()
    memo = MessageMemo()
    said = {m.value for r in outcome.results if r.component.value.endswith("DatatypeConstraintComponent") for m in memo(r, shapes, data)}
    assert said == {'Value "x0" should have the datatype xsd:integer', 'Value "x1" should have the datatype xsd:integer'}


def test_a_sparql_constraint_message_is_kept_for_each_focus_node() -> None:
    """The one message that names the focus node: a SPARQL constraint with no message of its own."""
    shapes, data = graph(SHAPES), graph("ex:a a ex:C ; ex:flag true . ex:b a ex:C ; ex:flag true .")
    outcome = validate(data, shapes)
    memo = MessageMemo()
    sparql = [r for r in outcome.results if r.component.value.endswith("SPARQLConstraintComponent")]
    assert len(sparql) == 2
    for r in sparql:
        assert memo(r, shapes, data) == result_messages(r, shapes, data)
    assert len({m.value for r in sparql for m in memo(r, shapes, data)}) == 2


def test_a_memo_does_not_answer_for_another_pair_of_graphs() -> None:
    outcome, shapes, data = run()
    memo = MessageMemo()
    r = outcome.results[0]
    memo(r, shapes, data)
    other = graph(SHAPES)
    assert memo(r, other, data) == result_messages(r, other, data)
    assert memo._same_graphs(shapes, data) and not memo._same_graphs(other, data)


def test_the_text_of_a_report_is_the_same_with_and_without_the_memo(monkeypatch) -> None:
    outcome, shapes, data = run()
    with_memo = report_text(outcome.results, outcome.conforms, shapes, data)

    class Direct(MessageMemo):
        def __call__(self, r, s, d):
            return result_messages(r, s, d)

        def shape_text(self, s, term):
            return text.stringify_node(s, term)

    monkeypatch.setattr(text, "MessageMemo", Direct)
    assert report_text(outcome.results, outcome.conforms, shapes, data) == with_memo


# Each field the memo keys on, tested alone: two results that differ in that field only, with no message of their own so the engine's
# wording is used. The wording must differ (else the test says nothing) and the memo must give each result its own.
EX = "http://example.org/"
WORDS_SHAPES = (
    "ex:IsInt a sh:PropertyShape ; sh:path ex:age ; sh:datatype xsd:integer . ex:Once a sh:PropertyShape ; sh:path ex:q ; sh:minCount 1 . "
    "ex:Twice a sh:PropertyShape ; sh:path ex:q ; sh:minCount 2 ; sh:maxCount 3 . ex:Q a sh:NodeShape ; sh:sparql ex:C1 . "
)


def node(name: str) -> ox.NamedNode:
    return ox.NamedNode(EX + name)


def result(**fields) -> Result:
    base = dict(focus=node("n"), path=None, value=None, has_value=False, component=SH.MinCountConstraintComponent, shape=node("Once"), severity=SH.Violation)
    return Result(**{**base, **fields})


def pred(name: str) -> Path:
    return Path(kind="pred", iri=node(name), node=node(name))


CASES = {
    "value": (
        dict(component=SH.DatatypeConstraintComponent, shape=node("IsInt"), path=pred("age"), has_value=True, value=ox.Literal("a")),
        dict(component=SH.DatatypeConstraintComponent, shape=node("IsInt"), path=pred("age"), has_value=True, value=ox.Literal("b")),
    ),
    "focus": (
        dict(component=SH.SPARQLConstraintComponent, shape=node("Q"), source_constraint=node("C1"), focus=node("a")),
        dict(component=SH.SPARQLConstraintComponent, shape=node("Q"), source_constraint=node("C1"), focus=node("b")),
    ),
    "path": (dict(path=pred("q")), dict(path=pred("r"))),
    "shape": (dict(shape=node("Once")), dict(shape=node("Twice"))),
    "component": (dict(shape=node("Twice")), dict(shape=node("Twice"), component=SH.MaxCountConstraintComponent)),
    "has_value": (
        dict(component=SH.DatatypeConstraintComponent, shape=node("IsInt"), path=pred("age"), has_value=True, value=ox.Literal("a")),
        dict(component=SH.DatatypeConstraintComponent, shape=node("IsInt"), path=pred("age"), has_value=False),
    ),
}


@pytest.mark.parametrize("field", sorted(CASES))
def test_each_field_the_wording_depends_on_is_part_of_the_memo_key(field: str) -> None:
    shapes, data = graph(WORDS_SHAPES), graph("ex:n a ex:C .")
    a, b = (result(**fields) for fields in CASES[field])
    assert result_messages(a, shapes, data) != result_messages(b, shapes, data), "the pair must be worded differently, or this tests nothing"
    memo = MessageMemo()
    assert memo(a, shapes, data) == result_messages(a, shapes, data)
    assert memo(b, shapes, data) == result_messages(b, shapes, data)
