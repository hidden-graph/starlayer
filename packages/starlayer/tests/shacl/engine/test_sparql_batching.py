"""``sh:sparql`` queries run once for all the focus nodes of a shape when the query allows it, and give the results the node-by-node run gives."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl.engine import sparql_support
from starlayer.shacl.engine.api import validate
from starlayer.shacl.engine.oxigraph_view import OxigraphGraph, inject_everywhere
from starlayer.shacl.engine.sparql_support import BATCH_FALLBACKS, batch_blocker

PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
NO_OWNER = "SELECT $this WHERE { FILTER NOT EXISTS { $this <http://example.org/owner> ?o } }"


def graph(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PFX + ttl, format="turtle")
    return g


def shapes(select: str, on: str = "node") -> StarLayerGraph:
    constraint = f'sh:sparql [ sh:select """{select}""" ; sh:message "no owner" ]'
    if on == "node":
        return graph(f"ex:S a sh:NodeShape ; sh:targetClass ex:C ; {constraint} .")
    return graph(f"ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:owner ; {constraint} ] .")


def dogs(n: int = 10) -> StarLayerGraph:
    return graph(" ".join(f"ex:n{i} a ex:C" + (f" ; ex:owner ex:o{i % 3} ." if i % 2 else " .") for i in range(n)))


@pytest.fixture
def calls(monkeypatch) -> dict:
    """How many queries the data graph was asked to run: ``single`` (one node) and ``batch`` (many nodes, one query), and the size of each batch."""
    seen = {"single": 0, "batch": 0, "sizes": []}
    single, batch = OxigraphGraph.sparql_query, OxigraphGraph.sparql_query_batch

    def count_single(self, *args, **kwargs):
        seen["single"] += 1
        return single(self, *args, **kwargs)

    def count_batch(self, text, name, nodes, *args, **kwargs):
        seen["batch"] += 1
        seen["sizes"].append(len(nodes))
        return batch(self, text, name, nodes, *args, **kwargs)

    monkeypatch.setattr(OxigraphGraph, "sparql_query", count_single)
    monkeypatch.setattr(OxigraphGraph, "sparql_query_batch", count_batch)
    return seen


def node_by_node(monkeypatch) -> None:
    monkeypatch.setattr(sparql_support, "prefetch_select", lambda ctx, text, foci: None)
    from starlayer.shacl.engine.components import sparql_constraints

    monkeypatch.setattr(sparql_constraints, "prefetch_select", lambda ctx, text, foci: None)


# --- the rule -------------------------------------------------------------------------------------------------------------------------------

BATCHABLE = {
    "plain": "SELECT $this WHERE { $this <http://example.org/p> ?o }",
    "more variables": "SELECT $this ?o ?message WHERE { $this <http://example.org/p> ?o BIND('m' AS ?message) }",
    "not exists": NO_OWNER,
    "exists": "SELECT $this WHERE { $this <http://example.org/p> ?o FILTER EXISTS { ?x <http://example.org/q> $this } }",
    "union and optional": "SELECT $this ?o WHERE { { $this <http://example.org/p> ?o } UNION { $this <http://example.org/q> ?o } OPTIONAL { $this <http://example.org/r> ?x } }",
    "distinct and order": "SELECT DISTINCT $this ?o WHERE { $this <http://example.org/p> ?o } ORDER BY ?o",
    "graph": "SELECT $this WHERE { GRAPH ?g { $this <http://example.org/p> ?o } }",
    "filter": "SELECT $this WHERE { $this <http://example.org/p> ?o FILTER (?o > 1) }",
    "a trailing values over other variables": "SELECT $this WHERE { $this <http://example.org/p> ?o } VALUES ?o { 1 2 }",
}
BLOCKED = {
    "limit": ("SELECT $this WHERE { $this <http://example.org/p> ?o } LIMIT 1", "LIMIT"),
    "offset": ("SELECT $this WHERE { $this <http://example.org/p> ?o } OFFSET 1", "OFFSET"),
    "group by": ("SELECT $this WHERE { $this <http://example.org/p> ?o } GROUP BY $this", "GROUP BY"),
    "having": ("SELECT $this WHERE { $this <http://example.org/p> ?o } GROUP BY $this HAVING (COUNT(?o) > 1)", "GROUP BY"),
    "an aggregate": ("SELECT $this (COUNT(?o) AS ?n) WHERE { $this <http://example.org/p> ?o } GROUP BY $this", "GROUP BY"),
    "a sub-select": ("SELECT $this WHERE { { SELECT ?o WHERE { ?x <http://example.org/p> ?o } LIMIT 1 } $this <http://example.org/q> ?o }", "SubSelect"),
    "an aggregate in a sub-select": ("SELECT $this WHERE { { SELECT ?o (MAX(?z) AS ?m) WHERE { ?x <http://example.org/p> ?o . ?x <http://example.org/z> ?z } GROUP BY ?o } $this <http://example.org/q> ?o }", "MAX"),
    "a sub-select in an EXISTS": ("SELECT $this WHERE { $this <http://example.org/p> ?o FILTER EXISTS { SELECT (COUNT(*) AS ?c) WHERE { ?s <http://example.org/q> ?o } } }", "COUNT"),
    "no ?this projected": ("SELECT ?o WHERE { $this <http://example.org/p> ?o }", "project"),
    "an ASK": ("ASK { $this <http://example.org/p> ?o }", "SELECT"),
    "a CONSTRUCT": ("CONSTRUCT { $this <http://example.org/p> ?o } WHERE { $this <http://example.org/p> ?o }", "SELECT"),
    "not a query": ("SELECT $this WHERE {", "parse"),
}


@pytest.mark.parametrize("name", sorted(BATCHABLE))
def test_a_query_whose_rows_for_a_node_depend_on_that_node_alone_is_batchable(name: str) -> None:
    assert batch_blocker(BATCHABLE[name]) is None


@pytest.mark.parametrize("name", sorted(BLOCKED))
def test_a_query_that_combines_rows_across_nodes_is_not(name: str) -> None:
    text, why = BLOCKED[name]
    assert why in (batch_blocker(text) or "")


# --- the scanner ----------------------------------------------------------------------------------------------------------------------------


def test_the_clause_is_left_out_of_an_exists_group_when_asked() -> None:
    values = "VALUES (?this) { (<a>) (<b>) }"
    assert inject_everywhere(NO_OWNER, values).count("VALUES") == 2
    skipped = inject_everywhere(NO_OWNER, values, skip_exists=True)
    assert skipped.count("VALUES") == 1 and "EXISTS { $this" in skipped
    after = "SELECT $this WHERE { FILTER EXISTS { $this <p> ?o } { $this <q> 1 } }"
    assert inject_everywhere(after, values, skip_exists=True).count("VALUES") == 2  # the outer group, and the group after the EXISTS
    nested = "SELECT $this WHERE { FILTER NOT EXISTS { { $this <p> 1 } UNION { OPTIONAL { $this <q> 2 } } } }"
    assert inject_everywhere(nested, values, skip_exists=True).count("VALUES") == 1
    assert inject_everywhere("SELECT $this WHERE { $this <p> ?o }", values) == inject_everywhere("SELECT $this WHERE { $this <p> ?o }", values, skip_exists=True)


# --- the engine -----------------------------------------------------------------------------------------------------------------------------


def test_a_query_is_run_once_for_all_the_focus_nodes(calls) -> None:
    outcome = validate(dogs(10), shapes(NO_OWNER))
    assert calls["single"] == 0 and calls["batch"] == 1 and calls["sizes"] == [10]
    assert len(outcome.results) == 5


@pytest.mark.parametrize("on", ["node", "property"])
def test_the_results_are_those_of_the_node_by_node_run(on: str, monkeypatch) -> None:
    select = NO_OWNER if on == "node" else "SELECT $this WHERE { FILTER NOT EXISTS { $this $PATH ?o } }"
    data, shape = dogs(12), shapes(select, on)  # (one shapes graph: a result names the constraint's blank node, which is new in each parse)
    batched = validate(data, shape).results
    node_by_node(monkeypatch)
    assert validate(data, shape).results == batched and len(batched) == 6


def test_a_property_shape_is_batched_at_the_focus_nodes_of_its_node_shape(calls) -> None:
    validate(dogs(10), shapes("SELECT $this WHERE { FILTER NOT EXISTS { $this $PATH ?o } }", "property"))
    assert calls["single"] == 0 and calls["batch"] == 1 and calls["sizes"] == [10]


def test_rows_of_a_node_keep_the_order_and_content_of_the_node_by_node_run(monkeypatch) -> None:
    select = "SELECT $this ?o WHERE { $this <http://example.org/tag> ?o }"
    data, shape = graph(" ".join(f'ex:n{i} a ex:C ; ex:tag "a{i}", "b{i}", "c{i}" .' for i in range(6))), shapes(select)
    batched = validate(data, shape).results
    node_by_node(monkeypatch)
    assert validate(data, shape).results == batched and len(batched) == 18


def test_a_query_that_cannot_be_batched_is_run_for_each_node(calls) -> None:
    validate(dogs(6), shapes("SELECT $this WHERE { FILTER NOT EXISTS { $this <http://example.org/owner> ?o } } LIMIT 1"))
    assert calls["batch"] == 0 and calls["single"] == 6


def test_one_focus_node_is_run_by_itself(calls) -> None:
    validate(dogs(1), shapes(NO_OWNER))
    assert calls["batch"] == 0 and calls["single"] == 1


def test_blank_node_focus_nodes_are_run_one_by_one_and_the_rest_in_a_batch(calls) -> None:
    data = graph("ex:a a ex:C . ex:b a ex:C . [ a ex:C ] . [ a ex:C ] .")
    outcome = validate(data, shapes(NO_OWNER))
    assert calls["batch"] == 1 and calls["sizes"] == [2] and calls["single"] == 2
    assert len(outcome.results) == 4


def test_a_batch_is_made_of_chunks(calls, monkeypatch) -> None:
    monkeypatch.setattr(sparql_support, "_BATCH_SIZE", 3)
    data, shape = dogs(7), shapes(NO_OWNER)
    batched = validate(data, shape).results
    assert calls["sizes"] == [3, 3, 1] and calls["single"] == 0
    node_by_node(monkeypatch)
    assert validate(data, shape).results == batched


def test_a_batch_that_fails_leaves_the_node_by_node_run_to_do_it(calls, monkeypatch) -> None:
    def refuse(self, *args, **kwargs):
        raise RuntimeError("the batch failed")

    monkeypatch.setattr(OxigraphGraph, "sparql_query_batch", refuse)
    expected = validate(dogs(8), shapes(NO_OWNER)).results
    assert calls["single"] == 8 and len(expected) == 4


def test_a_graph_that_says_it_cannot_gives_the_node_by_node_run(calls, monkeypatch) -> None:
    monkeypatch.setattr(OxigraphGraph, "sparql_query_batch", lambda self, *a, **k: None)
    assert len(validate(dogs(8), shapes(NO_OWNER)).results) == 4 and calls["single"] == 8


def test_a_refused_batch_is_counted(monkeypatch) -> None:
    from starlayer.shacl.engine import executor

    seen: list = []
    original = executor.Context.__post_init__
    monkeypatch.setattr(OxigraphGraph, "sparql_query_batch", lambda self, *a, **k: None)
    monkeypatch.setattr(executor.Context, "__post_init__", lambda self: (original(self), seen.append(self))[0])
    validate(dogs(8), shapes(NO_OWNER))
    assert seen[0].cache[BATCH_FALLBACKS] == 1


def test_nothing_is_read_ahead_when_the_run_stops_at_the_first_result(calls) -> None:
    outcome = validate(dogs(10), shapes(NO_OWNER), abort_on_first=True)
    assert calls["batch"] == 0 and len(outcome.results) == 1


def test_only_the_nodes_a_filter_keeps_are_asked_about(calls) -> None:
    nodes = sorted(set(dogs(10).subjects(None, None)), key=str)
    validate(dogs(10), shapes(NO_OWNER), focus_filter=frozenset(nodes[:4]))
    assert calls["sizes"] == [4]
