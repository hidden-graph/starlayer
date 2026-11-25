"""The clauses in ``srl_eval`` that turn an engine failure into "no value" or "use the slow path" do so only for the failure
they were written for; anything else reaches the caller."""

from __future__ import annotations

from types import SimpleNamespace

import pyoxigraph as ox
import pytest
from starlayer.graph import StarLayerGraph
from starlayer.sparql import srl_eval
from starlayer.sparql.srl import parse_ruleset
from tests.support.terms import NamedNode, lit

EX = "http://example.org/"
P = f"PREFIX ex: <{EX}>\n"
JOIN_MESSAGE = "a triple term that is not a valid RDF 1.2 term"


class _Raising:
    """A store whose update and query raise ``exc``."""

    def __init__(self, exc):
        self.exc = exc

    def update(self, *_a, **_k):
        raise self.exc

    def query(self, *_a, **_k):
        raise self.exc


def test_the_join_message_is_recognised_only_for_a_runtime_error():
    assert srl_eval._engine_cannot_join_triple_terms(RuntimeError(JOIN_MESSAGE))
    assert not srl_eval._engine_cannot_join_triple_terms(RuntimeError("the query ran out of memory"))
    assert not srl_eval._engine_cannot_join_triple_terms(ValueError(JOIN_MESSAGE))


def test_the_engine_refusing_to_join_a_literal_into_a_triple_term_still_falls_back_to_the_slow_path():
    g = StarLayerGraph()
    g.parse(
        data=f"@prefix ex: <{EX}> . ex:a ex:p \"lit\" . ex:w ex:q <<( ex:z ex:r ex:o )>> . ex:a ex:p ex:z .",
        format="turtle12",
    )
    rules = parse_ruleset(P + "RULE { ?w ex:found ?l } WHERE { ?a ex:p ?l . ?w ex:q <<( ?l ex:r ?o )>> }")
    assert {tuple(t) for t in rules.infer(g)} == {(NamedNode(EX + "w"), NamedNode(EX + "found"), NamedNode(EX + "z"))}


def _evaluation(store):
    return SimpleNamespace(store=store, ge=None, base=None)


def test_derive_into_candidates_falls_back_for_the_join_failure(monkeypatch):
    plan = SimpleNamespace(update=lambda position: "text")
    monkeypatch.setattr(srl_eval, "_eval_rule", lambda *a, **k: [])
    srl_eval._derive_into_candidates(object(), plan, None, _evaluation(_Raising(RuntimeError(JOIN_MESSAGE))))  # no raise


def test_derive_into_candidates_lets_another_runtime_error_through(monkeypatch):
    plan = SimpleNamespace(update=lambda position: "text")
    monkeypatch.setattr(srl_eval, "_eval_rule", lambda *a, **k: pytest.fail("the slow path must not run"))
    with pytest.raises(RuntimeError, match="out of memory"):
        srl_eval._derive_into_candidates(object(), plan, None, _evaluation(_Raising(RuntimeError("out of memory"))))


def _insert_target(store):
    target = object.__new__(srl_eval._Evaluation)
    target.store = store
    target.ge = SimpleNamespace(as_store=lambda: None)
    target._size = None
    return target


def test_insert_directly_says_no_for_the_join_failure_and_raises_for_another():
    plan = SimpleNamespace(direct=lambda: "INSERT DATA {}")
    assert _insert_target(_Raising(RuntimeError(JOIN_MESSAGE))).insert_directly(plan) is False
    with pytest.raises(RuntimeError, match="out of memory"):
        _insert_target(_Raising(RuntimeError("out of memory"))).insert_directly(plan)


def _sum_over(values):
    agg = srl_eval.srl_ast._Aggregation("SUM", ox.Variable("v"), False) if False else None
    return agg


def _aggregation(function="SUM"):
    return SimpleNamespace(argument=ox.Variable("v"), distinct=False, function=function)


def _solutions(*terms):
    return [{ox.Variable("v"): t} for t in terms]


def test_an_aggregate_over_a_value_the_engine_refuses_is_an_error_value(monkeypatch):
    # (pyoxigraph cannot build a triple term with a literal subject, so the refusal is stood in by a store that raises it)
    monkeypatch.setattr(srl_eval, "_EVAL_STORE", _Raising(SyntaxError("Literals are not allowed in subject position")))
    assert srl_eval._aggregate(_aggregation(), _solutions(lit(1))) is None


def test_an_aggregate_over_numbers_still_gives_their_sum():
    assert srl_eval._aggregate(_aggregation(), _solutions(lit(1), lit(2))).value == "3"


def test_an_aggregate_does_not_hide_an_engine_failure(monkeypatch):
    monkeypatch.setattr(srl_eval, "_EVAL_STORE", _Raising(RuntimeError("out of memory")))
    with pytest.raises(RuntimeError, match="out of memory"):
        srl_eval._aggregate(_aggregation(), _solutions(lit(1)))


def test_an_aggregate_does_not_hide_a_bug_in_writing_a_term(monkeypatch):
    def broken(term):
        raise KeyError("bug")

    monkeypatch.setattr(srl_eval, "_pattern_term_text", broken)
    with pytest.raises(KeyError):
        srl_eval._aggregate(_aggregation(), _solutions(lit(1)))


def test_an_aggregate_over_a_term_with_no_text_is_an_error_value(monkeypatch):
    def unwritable(term):
        raise ValueError("no text")

    monkeypatch.setattr(srl_eval, "_pattern_term_text", unwritable)
    assert srl_eval._aggregate(_aggregation(), _solutions(lit(1))) is None
