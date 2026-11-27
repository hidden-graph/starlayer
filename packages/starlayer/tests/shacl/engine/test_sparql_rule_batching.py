"""A ``sh:SPARQLRule`` is run once for all the focus nodes of its shapes when its query allows it, and infers what the one-by-one run infers."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl.engine import rules as rules_module
from starlayer.shacl.engine import sparql_support
from starlayer.shacl.engine.rules import InferredView, apply_rules

PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . "
DECLARE = 'sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.org/"^^xsd:anyURI ]'
ADULT = "CONSTRUCT { $this ex:isAdult true } WHERE { $this ex:age ?a FILTER (?a >= 18) }"


def graph(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PFX + ttl, format="turtle")
    return g


def shapes(construct: str = ADULT, extra: str = "") -> StarLayerGraph:
    return graph(f'ex:S a sh:NodeShape ; sh:targetClass ex:Person ; {DECLARE} ; sh:rule [ a sh:SPARQLRule ; sh:prefixes ex:S ; sh:construct """{construct}""" ] . {extra}')


def people(n: int = 10) -> StarLayerGraph:
    return graph(" ".join(f"ex:p{i} a ex:Person ; ex:age {10 + i * 3} ." for i in range(n)))


@pytest.fixture
def calls(monkeypatch) -> dict:
    """How many CONSTRUCT queries the overlay was asked to run: ``single`` (one node) and ``batch`` (many nodes, one query), and the size of each batch."""
    seen = {"single": 0, "batch": 0, "sizes": []}
    single, batch = InferredView.construct, InferredView.construct_batch

    def count_single(self, *args, **kwargs):
        seen["single"] += 1
        return single(self, *args, **kwargs)

    def count_batch(self, text, name, nodes, *args, **kwargs):
        seen["batch"] += 1
        seen["sizes"].append(len(nodes))
        return batch(self, text, name, nodes, *args, **kwargs)

    monkeypatch.setattr(InferredView, "construct", count_single)
    monkeypatch.setattr(InferredView, "construct_batch", count_batch)
    return seen


def one_by_one(monkeypatch) -> None:
    monkeypatch.setattr(rules_module._Run, "_construct_batch", lambda self, rule, foci: ([], foci))


def test_a_rule_is_run_once_for_all_its_focus_nodes(calls) -> None:
    result = apply_rules(people(10), shapes())
    # (two iterations: the second finds nothing new)
    assert calls["single"] == 0 and calls["batch"] == 2 and calls["sizes"] == [10, 10]
    assert len(result.inferred) == 7


def test_what_it_infers_is_what_the_one_by_one_run_infers(monkeypatch) -> None:
    d, s = people(12), shapes()
    batched = apply_rules(d, s)
    one_by_one(monkeypatch)
    expected = apply_rules(d, s)
    assert batched.inferred == expected.inferred and batched.iterations == expected.iterations and len(batched.inferred) == 9


def test_a_recursive_rule_reaches_the_same_fixpoint_in_the_same_iterations(monkeypatch) -> None:
    chain = "CONSTRUCT { $this ex:reach ?z } WHERE { { $this ex:next ?z } UNION { $this ex:reach ?y . ?y ex:next ?z } }"
    s = graph(f'ex:S a sh:NodeShape ; sh:targetClass ex:Node ; {DECLARE} ; sh:rule [ a sh:SPARQLRule ; sh:prefixes ex:S ; sh:construct "{chain}" ] .')
    d = graph(" ".join(f"ex:n{i} a ex:Node ; ex:next ex:n{i + 1} ." for i in range(15)) + " ex:n15 a ex:Node .")
    batched = apply_rules(d, s)
    one_by_one(monkeypatch)
    expected = apply_rules(d, s)
    assert batched.inferred == expected.inferred and batched.iterations == expected.iterations and len(batched.inferred) == 120


def test_the_record_of_which_rule_produced_a_triple_is_the_same(monkeypatch) -> None:
    d, s = people(8), shapes()
    batched = apply_rules(d, s, source_rules=True)
    one_by_one(monkeypatch)
    expected = apply_rules(d, s, source_rules=True)
    assert set(batched.source_rules) == set(expected.source_rules) and batched.source_rules


def test_the_parameters_of_a_rule_template_are_pre_bound_in_the_batch(calls, monkeypatch) -> None:
    s = graph(
        f"ex:S a sh:NodeShape ; sh:targetClass ex:Person ; {DECLARE} ; sh:rule ex:Big . "
        'ex:Template rdfs:subClassOf sh:SPARQLRule ; sh:prefixes ex:S ; sh:parameter [ sh:path ex:threshold ] ; sh:construct "CONSTRUCT { $this ex:big true } WHERE { $this ex:age ?a FILTER (?a > $threshold) }" . '
        "ex:Big a ex:Template ; ex:threshold 20 ."
    )
    d = people(10)
    batched = apply_rules(d, s)
    assert calls["single"] == 0 and calls["batch"] >= 1 and len(batched.inferred) == 6  # (ages 22 to 37)
    one_by_one(monkeypatch)
    assert apply_rules(d, s).inferred == batched.inferred


def test_a_blank_node_focus_node_is_run_by_itself(calls, monkeypatch) -> None:
    d = graph("ex:a a ex:Person ; ex:age 30 . ex:b a ex:Person ; ex:age 40 . [ a ex:Person ; ex:age 50 ] . [ a ex:Person ; ex:age 60 ] .")
    s = shapes()
    batched = apply_rules(d, s)
    assert calls["batch"] == 2 and calls["sizes"] == [2, 2] and calls["single"] == 4  # (two iterations; the two blank nodes alone in each)
    assert len(batched.inferred) == 4


def test_one_focus_node_is_run_by_itself(calls) -> None:
    apply_rules(people(1), shapes())
    assert calls["batch"] == 0 and calls["single"] == 1  # (the one person is 10: nothing is inferred, so there is one iteration)


def test_a_query_that_cannot_be_batched_is_run_for_each_node(calls) -> None:
    limited = "CONSTRUCT { $this ex:isAdult true } WHERE { $this ex:age ?a FILTER (?a >= 18) } LIMIT 100"
    apply_rules(people(6), shapes(limited))
    assert calls["batch"] == 0 and calls["single"] == 12


def test_a_global_rule_has_no_focus_nodes_to_batch(calls) -> None:
    s = graph(f'ex:G a sh:RuleSet ; sh:hasRule ex:R . ex:R a sh:SPARQLRule ; sh:prefixes ex:P ; sh:construct "CONSTRUCT {{ ex:x ex:count 1 }} WHERE {{ ?s a ex:Person }}" . ex:P {DECLARE} .')
    assert apply_rules(people(5), s).inferred
    assert calls["batch"] == 0


def test_a_batch_is_made_of_chunks(calls, monkeypatch) -> None:
    monkeypatch.setattr(sparql_support, "_BATCH_SIZE", 3)
    d, s = people(7), shapes()
    batched = apply_rules(d, s)
    assert calls["sizes"][:3] == [3, 3, 1] and calls["single"] == 0
    one_by_one(monkeypatch)
    assert apply_rules(d, s).inferred == batched.inferred


def test_a_batch_that_fails_leaves_the_one_by_one_run_to_do_it(calls, monkeypatch) -> None:
    def refuse(self, *args, **kwargs):
        raise RuntimeError("the batch failed")

    monkeypatch.setattr(InferredView, "construct_batch", refuse)
    assert len(apply_rules(people(8), shapes()).inferred) == 5 and calls["single"] > 0


def test_a_rule_with_a_forbidden_construct_fails_as_it_always_did(monkeypatch) -> None:
    """MINUS in a rule query is refused when the node is run, and a batch must not make that go away or change its words."""
    minus = "CONSTRUCT { $this ex:isAdult true } WHERE { $this ex:age ?a MINUS { $this ex:blocked true } }"
    d, s = people(6), shapes(minus)
    with pytest.raises(Exception) as batched:
        apply_rules(d, s)
    one_by_one(monkeypatch)
    with pytest.raises(Exception) as expected:
        apply_rules(d, s)
    assert type(batched.value) is type(expected.value) and str(batched.value) == str(expected.value) and "MINUS" in str(batched.value)


def test_the_rule_for_a_construct() -> None:
    query = "PREFIX ex: <http://example.org/> " + ADULT
    assert sparql_support.batch_blocker(query, construct=True) is None
    assert sparql_support.batch_blocker("CONSTRUCT WHERE { $this <http://e/p> ?o }", construct=True) is None
    assert "LIMIT" in sparql_support.batch_blocker(query + " LIMIT 1", construct=True)
    assert "SubSelect" in sparql_support.batch_blocker(
        "CONSTRUCT { $this <http://e/q> ?n } WHERE { { SELECT $this (COUNT(*) AS ?n) WHERE { $this <http://e/p> ?o } GROUP BY $this } }", construct=True
    )
    assert "not a CONSTRUCT" in sparql_support.batch_blocker("SELECT $this WHERE { $this <http://e/p> ?o }", construct=True)
