"""SHACL 1.2 SPARQL Appendix A: a VALUES clause is forbidden only when it mentions a potentially pre-bound variable."""

from __future__ import annotations

import pytest
from rdflib import Graph
from starlayer.shacl_engine import validate
from starlayer.shacl_engine.plan import ShapeError

DATA = "@prefix ex: <http://example.org/> . ex:a ex:p 1 . ex:a ex:q 2 ."


def _run(select: str):
    shapes = f'''@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
    ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:select """{select}""" ] .'''
    return validate(Graph().parse(data=DATA, format="turtle"), Graph().parse(data=shapes, format="turtle"))


def test_values_over_an_unrelated_variable_is_allowed() -> None:
    outcome = _run("SELECT $this WHERE { VALUES ?any { true } }")
    assert not outcome.conforms and len(outcome.results) == 1


def test_values_over_another_variable_joins_normally() -> None:
    outcome = _run("SELECT $this ?value WHERE { $this <http://example.org/p> ?value VALUES ?value { 1 3 } }")
    assert len(outcome.results) == 1


@pytest.mark.parametrize(
    "select",
    [
        "SELECT $this WHERE { VALUES $this { <http://example.org/a> } }",
        "SELECT $this WHERE { VALUES ($this ?x) { (<http://example.org/a> 1) } }",
    ],
)
def test_values_mentioning_the_pre_bound_variable_is_a_failure(select: str) -> None:
    with pytest.raises(ShapeError, match="pre-bound variable"):
        _run(select)


def test_minus_is_still_forbidden() -> None:
    with pytest.raises(ShapeError, match="MINUS"):
        _run("SELECT $this WHERE { $this ?p ?o MINUS { $this <http://example.org/q> ?o } }")
