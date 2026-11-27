"""The queries of a SPARQL-based constraint component's validators are run once for many focus nodes (a SELECT validator) or many (focus node,
value node) pairs (an ASK validator), and give the results the one-by-one run gives."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl.engine import executor, sparql_support
from starlayer.shacl.engine.api import validate
from starlayer.shacl.engine.oxigraph_view import OxigraphGraph
from starlayer.shacl.engine.sparql_support import BATCH_FALLBACKS, _ask_as_select, batch_blocker

PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . "
COMPONENTS = (
    "ex:MaxLen a sh:ConstraintComponent ; sh:parameter [ sh:path ex:maxLen ] ; "
    '  sh:validator [ a sh:SPARQLAskValidator ; sh:message "{$value} is too long" ; sh:ask "ASK { FILTER (STRLEN(STR($value)) <= $maxLen) }" ] . '
    "ex:MaxLenSel a sh:ConstraintComponent ; sh:parameter [ sh:path ex:maxLenSel ] ; "
    '  sh:validator [ a sh:SPARQLSelectValidator ; sh:message "too long" ; sh:select "SELECT $this ?value WHERE { $this $PATH ?value FILTER (STRLEN(STR(?value)) > $maxLenSel) }" ] . '
)


def graph(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PFX + ttl, format="turtle")
    return g


def shapes(constraint: str) -> StarLayerGraph:
    return graph(COMPONENTS + f"ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:name ; {constraint} ] .")


def data(n: int = 10, values: int = 3) -> StarLayerGraph:
    return graph(" ".join(
        f"ex:n{i} a ex:C ; ex:name " + ", ".join(f'"a-long-value-{i}-{j}"' if (i + j) % 4 == 0 else f'"v{j}"' for j in range(values)) + " ."
        for i in range(n)
    ))


@pytest.fixture
def calls(monkeypatch) -> dict:
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


def one_by_one(monkeypatch) -> None:
    monkeypatch.setattr(executor, "_prefetch", lambda *args, **kwargs: None)


ASK, SELECT = "ex:maxLen 8", "ex:maxLenSel 8"


def test_an_ask_validator_is_run_once_for_all_the_pairs(calls) -> None:
    outcome = validate(data(10, 3), shapes(ASK))
    assert calls["single"] == 0 and calls["batch"] == 1 and calls["sizes"] == [30]
    assert len(outcome.results) == 7  # (the values of (i + j) % 4 == 0 are the long ones)


def test_a_select_validator_is_run_once_for_all_the_focus_nodes(calls) -> None:
    outcome = validate(data(10, 3), shapes(SELECT))
    assert calls["single"] == 0 and calls["batch"] == 1 and calls["sizes"] == [10]
    assert len(outcome.results) == 7


@pytest.mark.parametrize("constraint", [ASK, SELECT])
def test_the_results_are_those_of_the_one_by_one_run(constraint: str, monkeypatch) -> None:
    d, s = data(12, 3), shapes(constraint)
    batched = validate(d, s).results
    one_by_one(monkeypatch)
    assert validate(d, s).results == batched and batched


def test_each_combination_of_parameter_values_is_run_apart(calls, monkeypatch) -> None:
    d, s = data(8, 2), shapes("ex:maxLen 3, 12")
    batched = validate(d, s).results
    assert calls["single"] == 0 and calls["batch"] == 2 and calls["sizes"] == [16, 16]
    one_by_one(monkeypatch)
    assert validate(d, s).results == batched


def test_the_messages_of_an_ask_validator_name_the_value(calls) -> None:
    said = {str(m.value) for r in validate(data(6, 2), shapes(ASK)).results for m in r.messages}
    assert said == {"a-long-value-0-0 is too long", "a-long-value-3-1 is too long", "a-long-value-4-0 is too long"}


def test_a_blank_node_focus_or_value_is_run_by_itself(calls, monkeypatch) -> None:
    d = graph('ex:a a ex:C ; ex:name "a-long-value-1", "x" . ex:b a ex:C ; ex:name "a-long-value-2", [ ex:z 1 ] . [ a ex:C ; ex:name "a-long-value-3" ] .')
    s = shapes(ASK)
    batched = validate(d, s).results
    assert calls["batch"] == 1 and calls["sizes"] == [3] and calls["single"] == 2  # (the pairs with a blank node: one value, and one focus node)
    one_by_one(monkeypatch)
    assert validate(d, s).results == batched


def test_a_validator_query_that_cannot_be_batched_is_run_one_by_one(calls) -> None:
    d = data(6, 2)
    s = graph(
        COMPONENTS.replace('"ASK { FILTER (STRLEN(STR($value)) <= $maxLen) }"', '"ASK { { SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o } } FILTER (STRLEN(STR($value)) <= $maxLen) }"')
        + "ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:name ; ex:maxLen 8 ] ."
    )
    validate(d, s)
    assert calls["batch"] == 0 and calls["single"] == 12


def test_a_parameter_that_is_a_blank_node_is_run_one_by_one_and_counted(calls, monkeypatch) -> None:
    seen: list = []
    original = executor.Context.__post_init__
    monkeypatch.setattr(executor.Context, "__post_init__", lambda self: (original(self), seen.append(self))[0])
    d, s = data(6, 2), shapes("ex:maxLen [ ex:x 8 ]")
    validate(d, s)
    assert calls["single"] == 12 and seen[0].cache.get(BATCH_FALLBACKS, 0) >= 1  # (the store is asked, says it cannot write the parameter, and each pair is run)


def test_a_batch_that_fails_leaves_the_one_by_one_run_to_do_it(calls, monkeypatch) -> None:
    def refuse(self, *args, **kwargs):
        raise RuntimeError("the batch failed")

    monkeypatch.setattr(OxigraphGraph, "sparql_query_batch", refuse)
    outcome = validate(data(6, 2), shapes(ASK))
    assert calls["single"] == 12 and outcome.results


def test_the_ask_as_a_select_and_the_rule_for_it() -> None:
    assert _ask_as_select("ASK { $this <p> $value }") == "SELECT DISTINCT $this $value { $this <p> $value }"
    assert _ask_as_select("# ASK\nask WHERE { FILTER (\"ASK\" != $value) }").startswith("# ASK\nSELECT DISTINCT $this $value WHERE")
    assert batch_blocker("ASK { $this <p> $value }", ask=True) is None
    assert batch_blocker("ASK { $this <p> $value FILTER NOT EXISTS { $value <q> $this } }", ask=True) is None
    assert "SubSelect" in batch_blocker("ASK { { SELECT ?x WHERE { ?x <p> ?y } LIMIT 1 } }", ask=True)
    assert "not an ASK" in batch_blocker("SELECT $this WHERE { $this <p> ?o }", ask=True)
    assert "not a SELECT" in batch_blocker("ASK { $this <p> ?o }")


def test_a_run_that_stops_at_the_first_result_reads_nothing_ahead(calls) -> None:
    outcome = validate(data(10, 3), shapes(ASK), abort_on_first=True)
    assert calls["batch"] == 0 and len(outcome.results) == 1


def test_the_text_of_a_validator_is_read_once_for_a_run(monkeypatch) -> None:
    prefixes = []
    original = sparql_support.with_prefixes
    monkeypatch.setattr("starlayer.shacl.engine.components.sparql_components.with_prefixes", lambda *a: prefixes.append(1) or original(*a))
    validate(data(20, 3), shapes(ASK))
    assert len(prefixes) == 1
