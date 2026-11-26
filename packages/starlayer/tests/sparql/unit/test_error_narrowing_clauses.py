"""Catch clauses that turn a failure into a fallback or a reported problem do so for the failures they were written for;
a bug (KeyError, TypeError, AttributeError) or a SHACL error is not turned into a slower query, an unsupported query or
"the query has a problem"."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.errors import FormatError
from starlayer.shacl.errors import ExecutionError, ShapeError
from starlayer.sparql import check
from starlayer.sparql.sqe import entailment, rewrite
from starlayer.sparql.sqe.entailment import rewrite_for_entailment

EXISTS_QUERY = "SELECT ?p WHERE { ?p <urn:a> ?a . FILTER EXISTS { ?p <urn:b> ?q . ?q <urn:a> ?b . FILTER(?b > ?a) } }"
RDFS = "http://www.w3.org/ns/entailment/RDFS"
ENTAIL_QUERY = "SELECT ?x WHERE { ?x a <urn:C> }"


# --- sqe/rewrite.py ---------------------------------------------------------------------------------------------------

def test_the_exists_rewrite_changes_the_text_when_it_can():
    assert rewrite.rewrite_exists_text(EXISTS_QUERY) != EXISTS_QUERY


@pytest.mark.parametrize("exc", [ExecutionError("no text for this node", kind="unsupported"), ExecutionError("deep", kind="nesting"), ValueError("bad tree"), RecursionError()])
def test_the_exists_rewrite_keeps_the_text_when_the_tree_cannot_be_rewritten(monkeypatch, exc):
    def fail(*_a, **_k):
        raise exc

    monkeypatch.setattr(rewrite, "_rewrite_node", fail)
    assert rewrite.rewrite_exists_text(EXISTS_QUERY) == EXISTS_QUERY


@pytest.mark.parametrize("exc", [KeyError("x"), TypeError("x"), AttributeError("x"), ImportError("x")])
def test_the_exists_rewrite_does_not_hide_a_bug(monkeypatch, exc):
    def fail(*_a, **_k):
        raise exc

    monkeypatch.setattr(rewrite, "_rewrite_node", fail)
    with pytest.raises(type(exc)):
        rewrite.rewrite_exists_text(EXISTS_QUERY)


# --- sqe/entailment.py ------------------------------------------------------------------------------------------------

def _break_writing_out(monkeypatch, exc):
    from starlayer.sparql.sqe import to_text

    def fail(*_a, **_k):
        raise exc

    entailment._rewrite_cached.cache_clear()
    monkeypatch.setattr(to_text, "sqe_tree_to_text", fail)


def test_the_entailment_rewrite_reports_a_tree_it_cannot_write_out(monkeypatch):
    _break_writing_out(monkeypatch, ExecutionError("no text for this node", kind="unsupported"))
    with pytest.raises(ExecutionError, match="could not be written out") as caught:
        rewrite_for_entailment(ENTAIL_QUERY, RDFS)
    assert caught.value.kind == "unsupported"
    entailment._rewrite_cached.cache_clear()


@pytest.mark.parametrize("exc", [KeyError("x"), TypeError("x"), AttributeError("x")])
def test_the_entailment_rewrite_does_not_report_a_bug_as_an_unsupported_query(monkeypatch, exc):
    _break_writing_out(monkeypatch, exc)
    with pytest.raises(type(exc)):
        rewrite_for_entailment(ENTAIL_QUERY, RDFS)
    entailment._rewrite_cached.cache_clear()


# --- sparql/check.py --------------------------------------------------------------------------------------------------

def test_check_query_reports_what_the_engine_refuses():
    result = check.check_query("SELECT ?x WHERE { ?x <urn:p> ?y } ORDER BY <urn:nope>(?y)")
    assert [(p.kind, p.message) for p in result.problems] == [("engine", "The custom function <urn:nope> is not supported")]


def _query_raises(monkeypatch, exc):
    def fail(self, *_a, **_k):
        raise exc

    monkeypatch.setattr(StarLayerGraph, "query", fail)


@pytest.mark.parametrize("exc", [ExecutionError("evaluation failed", kind="query"), FormatError("bad", kind="sparql"), NotImplementedError("no")])
def test_the_engine_problem_is_reported_for_the_engines_own_failures(monkeypatch, exc):
    _query_raises(monkeypatch, exc)
    problem = check._engine_problem("SELECT * WHERE {}", None, {})
    assert problem is not None and problem.message


@pytest.mark.parametrize("exc", [KeyError("x"), AttributeError("x"), RuntimeError("raw"), SyntaxError("raw"), ExecutionError("a user function failed", kind="expression"), ShapeError("bad shapes")])
def test_the_engine_problem_does_not_turn_a_bug_or_a_shacl_error_into_a_query_problem(monkeypatch, exc):
    _query_raises(monkeypatch, exc)
    with pytest.raises(type(exc)):
        check._engine_problem("SELECT * WHERE {}", None, {})
