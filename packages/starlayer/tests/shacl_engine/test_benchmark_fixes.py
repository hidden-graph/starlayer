"""Fixes found by docs/working/shacl-engine-benchmarks.md: sh:uniqueValuesFor was quadratic, and OxigraphGraph had no
sparql_query hook so any sh:sparql constraint crashed on it."""

from __future__ import annotations

import time

import pytest
from rdflib import Graph
from starlayer.shacl_engine import validate
from starlayer.shacl_engine.terms import text

ox = pytest.importorskip("pyoxigraph")
from starlayer.shacl_engine.oxigraph_view import OxigraphGraph  # noqa: E402

SHAPES = """@prefix ex: <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:uniqueValuesFor ex:id ."""


def test_unique_values_for_scales_linearly_enough_and_still_finds_duplicates() -> None:
    n = 3000
    lines = ["@prefix ex: <http://e/> ."] + [f'ex:n{i} a ex:T ; ex:id "{i}" .' for i in range(n)]
    lines.append('ex:dup1 a ex:T ; ex:id "7" .')  # shares a key with ex:n7
    data = Graph().parse(data="\n".join(lines), format="turtle")
    shapes = Graph().parse(data=SHAPES, format="turtle")
    start = time.perf_counter()
    outcome = validate(data, shapes)
    elapsed = time.perf_counter() - start
    assert not outcome.conforms
    assert sorted(text(r.focus).rsplit("/", 1)[1] for r in outcome.results) == ["dup1", "n7"]
    assert elapsed < 10, f"unique values took {elapsed:.1f}s for {n} focus nodes (was quadratic)"


def test_sh_sparql_runs_natively_on_an_oxigraph_view() -> None:
    data = OxigraphGraph.from_text("@prefix ex:<http://e/> . ex:a ex:p 1 . ex:b ex:p 2 .")
    shapes = OxigraphGraph.from_text(
        """@prefix ex:<http://e/> . @prefix sh:<http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:a ;
          sh:sparql [ sh:select "SELECT $this ?value WHERE { $this <http://e/p> ?value FILTER(?value = 1) }" ;
                      sh:message "bad" ] ."""
    )
    outcome = validate(data, shapes)
    assert not outcome.conforms
    assert len(outcome.results) == 1


def test_oxigraph_sparql_query_handles_an_unprojected_substitution() -> None:
    data = OxigraphGraph.from_text("@prefix ex:<http://e/> . ex:a ex:p 1 .")
    solutions = data.sparql_query("SELECT ?o WHERE { ?s <http://e/p> ?o }", {"s": ox.NamedNode("http://e/a")})
    assert len(solutions.rows) == 1
