"""A rule is not run again when nothing it can read has changed since it last ran, and the fixpoint is the one that running it every iteration reaches."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl.engine import rules as rules_module
from starlayer.shacl.engine.rules import InferredView, apply_rules
from starlayer.shacl.engine.sparql_support import query_reads

PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . "
DECLARE = 'sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.org/"^^xsd:anyURI ]'


def graph(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PFX + ttl, format="turtle")
    return g


def rule(construct: str, target: str = "sh:targetClass ex:Person", name: str = "S", extra: str = "") -> str:
    return f'ex:{name} a sh:NodeShape ; {target} ; sh:rule [ a sh:SPARQLRule ; sh:prefixes ex:P ; sh:construct """{construct}""" {extra} ] . '


def shapes(*rules: str) -> StarLayerGraph:
    return graph(f"ex:P a sh:NodeShape ; {DECLARE} . " + "".join(rules))


def people(n: int = 12) -> StarLayerGraph:
    return graph(" ".join(f"ex:p{i} a ex:Person ; ex:age {10 + i * 3} ." for i in range(n)))


ADULT = "CONSTRUCT { $this ex:isAdult true } WHERE { $this ex:age ?a FILTER (?a >= 18) }"
VOTER = "CONSTRUCT { $this ex:canVote true } WHERE { $this ex:isAdult true }"


@pytest.fixture
def runs(monkeypatch) -> list:
    """The text of each CONSTRUCT run (one entry per run, whether for one node or many)."""
    seen: list = []
    single, batch = InferredView.construct, InferredView.construct_batch
    monkeypatch.setattr(InferredView, "construct", lambda self, text, b: seen.append(text) or single(self, text, b))
    monkeypatch.setattr(InferredView, "construct_batch", lambda self, text, name, nodes, *a, **k: seen.append(text) or batch(self, text, name, nodes, *a, **k))
    return seen


def without_skipping(monkeypatch) -> None:
    monkeypatch.setattr(rules_module._Run, "skip_unchanged", False)


def same(left, right) -> None:
    assert left.inferred == right.inferred and left.iterations == right.iterations and set(left.source_rules) == set(right.source_rules)


# --- what a query reads -------------------------------------------------------------------------------------------------------------------

READS = {
    "a triple": ("CONSTRUCT { $this <http://e/q> ?o } WHERE { $this <http://e/p> ?o }", {"p"}),
    "what a CONSTRUCT writes is not read": ("CONSTRUCT { $this <http://e/q> 1 } WHERE { $this <http://e/p> ?o }", {"p"}),
    "the short form reads its pattern": ("CONSTRUCT WHERE { $this <http://e/p> ?o }", {"p"}),
    "a class": ("CONSTRUCT { $this <http://e/q> 1 } WHERE { $this a <http://e/C> }", {"type"}),
    "paths, a union and a not exists": (
        "CONSTRUCT { $this <http://e/r> ?z } WHERE { { $this <http://e/p>+ ?z } UNION { $this ^<http://e/s> ?z } FILTER NOT EXISTS { $this <http://e/t> ?z } }",
        {"p", "s", "t"},
    ),
    "a sub-select": ("CONSTRUCT { $this <http://e/r> ?o } WHERE { { SELECT ?o WHERE { ?x <http://e/u> ?o } } $this <http://e/p> ?o }", {"p", "u"}),
    "a builtin function": ("CONSTRUCT { $this <http://e/r> ?n } WHERE { $this <http://e/p> ?o BIND(STRLEN(STR(?o)) AS ?n) }", {"p"}),
}
ANYTHING = {
    "a variable predicate": "CONSTRUCT { $this <http://e/r> ?z } WHERE { $this ?p ?z }",
    "a path that can be of length zero": "CONSTRUCT { $this <http://e/r> ?z } WHERE { $this <http://e/p>* ?z }",
    "an optional path": "CONSTRUCT { $this <http://e/r> ?z } WHERE { $this <http://e/p>? ?z }",
    "a negated property set": "CONSTRUCT { $this <http://e/r> ?z } WHERE { $this !<http://e/p> ?z }",
    "a function of the shapes graph": "CONSTRUCT { $this <http://e/r> ?f } WHERE { $this <http://e/p> ?o BIND(<http://e/fn>(?o) AS ?f) }",
    "a triple term": "CONSTRUCT { $this <http://e/r> ?r } WHERE { ?r <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> <<( ?a ?b ?c )>> }",
}


@pytest.mark.parametrize("name", sorted(READS))
def test_the_predicates_a_query_reads(name: str) -> None:
    text, expected = READS[name]
    reads, volatile = query_reads(text)
    assert {p.value.rsplit("/", 1)[-1].rsplit("#", 1)[-1] for p in reads} == expected and not volatile


@pytest.mark.parametrize("name", sorted(ANYTHING))
def test_a_query_that_can_read_any_predicate_says_so(name: str) -> None:
    assert query_reads(ANYTHING[name]) == (None, False)


@pytest.mark.parametrize("function", ["BNODE()", "RAND()", "UUID()", "STRUUID()"])
def test_a_query_that_gives_other_answers_to_the_same_data_is_volatile(function: str) -> None:
    assert query_reads(f"CONSTRUCT {{ $this <http://e/r> ?b }} WHERE {{ $this <http://e/p> ?o BIND({function} AS ?b) }}")[1] is True


def test_a_blank_node_in_the_construct_template_is_a_new_node_in_every_run() -> None:
    assert query_reads("CONSTRUCT { $this <http://e/p> _:fresh } WHERE { $this <http://e/q> ?o }")[1] is True
    assert query_reads("CONSTRUCT { $this <http://e/p> [ <http://e/r> 1 ] } WHERE { $this <http://e/q> ?o }")[1] is True
    assert query_reads("CONSTRUCT { $this <http://e/p> ?o } WHERE { $this <http://e/q> _:b . _:b <http://e/s> ?o }")[1] is False  # (in the pattern it is a variable)


def test_a_rule_that_never_reaches_a_fixpoint_is_still_refused() -> None:
    s = shapes(rule("CONSTRUCT { $this ex:p _:fresh } WHERE { $this ex:age ?a }"))
    with pytest.raises(Exception, match="iterations"):
        apply_rules(people(4), s, max_iterations=5)


# --- the rules -----------------------------------------------------------------------------------------------------------------------------


def test_a_rule_whose_inputs_did_not_change_is_run_once(runs) -> None:
    result = apply_rules(people(), shapes(rule(ADULT)))
    assert result.iterations == 2 and len(runs) == 1 and len(result.inferred) == 9  # (nine of the twelve are adults)


def test_without_skipping_it_is_run_in_each_iteration(runs, monkeypatch) -> None:
    without_skipping(monkeypatch)
    result = apply_rules(people(), shapes(rule(ADULT)))
    assert result.iterations == 2 and len(runs) == 2


def test_a_rule_that_reads_what_another_infers_is_run_again_when_it_is_inferred(runs, monkeypatch) -> None:
    s, d = shapes(rule(ADULT), rule(VOTER, name="T")), people()
    result = apply_rules(d, s)
    assert len(result.inferred) == 18 and result.iterations == 3
    assert len(runs) == 3  # (the adult rule once; the voter rule when it starts, and again when the adults are in)
    without_skipping(monkeypatch)
    same(result, apply_rules(d, s))


def test_a_rule_over_a_class_is_run_again_when_another_rule_makes_new_members_of_it(monkeypatch) -> None:
    """The focus nodes of a rule are part of what it reads: a rule that types nodes as ex:Person adds focus nodes to the rule over ex:Person."""
    s = shapes(
        rule("CONSTRUCT { $this a ex:Person } WHERE { $this ex:worksAt ?c }", target="sh:targetClass ex:Employee", name="Hire"),
        rule("CONSTRUCT { $this ex:greeted true } WHERE { $this ex:age ?a }", name="Greet"),
    )
    d = graph(" ".join(f"ex:e{i} a ex:Employee ; ex:worksAt ex:acme ; ex:age {20 + i} ." for i in range(6)))
    skipped = apply_rules(d, s)
    assert sum(1 for t in skipped.inferred if t[1].value.endswith("greeted")) == 6
    without_skipping(monkeypatch)
    same(skipped, apply_rules(d, s))


def test_a_rule_over_the_subjects_of_a_predicate_is_run_again_when_that_predicate_is_inferred(monkeypatch) -> None:
    s = shapes(
        rule("CONSTRUCT { $this ex:knows ex:everyone } WHERE { $this ex:age ?a }", name="Know"),
        rule("CONSTRUCT { $this ex:social true } WHERE { $this ex:age ?a }", target="sh:targetSubjectsOf ex:knows", name="Social"),  # (its query does not read ex:knows, its target does)
    )
    d = people(8)
    skipped = apply_rules(d, s)
    assert sum(1 for t in skipped.inferred if t[1].value.endswith("social")) == 8
    without_skipping(monkeypatch)
    same(skipped, apply_rules(d, s))


def test_a_recursive_rule_reaches_the_same_fixpoint(monkeypatch) -> None:
    chain = "CONSTRUCT { $this ex:reach ?z } WHERE { { $this ex:next ?z } UNION { $this ex:reach ?y . ?y ex:next ?z } }"
    s = shapes(rule(chain, target="sh:targetClass ex:Node"))
    d = graph(" ".join(f"ex:n{i} a ex:Node ; ex:next ex:n{i + 1} ." for i in range(12)) + " ex:n12 a ex:Node .")
    skipped = apply_rules(d, s)
    assert len(skipped.inferred) == 78 and skipped.iterations == 13
    without_skipping(monkeypatch)
    same(skipped, apply_rules(d, s))


def test_a_rule_that_can_read_any_predicate_is_run_again_when_anything_changes(runs) -> None:
    s = shapes(rule(ADULT), rule("CONSTRUCT { $this ex:count ?n } WHERE { $this ?p ?o BIND(1 AS ?n) }", name="Any"))
    apply_rules(people(), s)
    assert sum("?p" in t for t in runs) == 2  # (it runs, the adults are inferred, and it runs again)


def test_a_rule_with_a_condition_is_run_again_when_anything_changes(runs) -> None:
    s = shapes(rule(ADULT), rule(VOTER, name="T", extra="; sh:condition ex:IsAdult"), "ex:IsAdult a sh:NodeShape ; sh:property [ sh:path ex:isAdult ; sh:hasValue true ] . ")
    apply_rules(people(), s)
    assert sum("canVote" in t for t in runs) == 2


def test_a_rule_that_makes_a_new_blank_node_each_time_is_never_skipped(runs) -> None:
    s = shapes(rule("CONSTRUCT { $this ex:ref ?b } WHERE { $this ex:age ?a BIND(BNODE() AS ?b) }", extra="; sh:runOnce false"))
    with pytest.raises(Exception, match="iterations"):
        apply_rules(people(3), s, max_iterations=4)
    assert len(runs) >= 4  # (it never reaches a fixpoint, as before)


def test_a_rule_that_could_give_other_answers_to_the_same_data_is_run_in_every_iteration(runs) -> None:
    """Its answer may differ from run to run, so nothing about the data says it need not run: the last iteration, in which nothing changes, runs it too."""
    s = shapes(rule(ADULT), rule(VOTER, name="T"), rule("CONSTRUCT { $this ex:lucky true } WHERE { $this ex:age ?a BIND(RAND() AS ?x) FILTER (?x >= 0) }", name="Dice"))
    result = apply_rules(people(), s)
    assert result.iterations == 3 and sum("RAND" in t for t in runs) == 3


def test_a_run_once_rule_is_run_once() -> None:
    s = shapes(rule(ADULT, extra="; sh:runOnce true"))
    assert len(apply_rules(people(), s).inferred) == 9


def test_the_record_of_which_rule_gave_a_triple_is_the_same(monkeypatch) -> None:
    s, d = shapes(rule(ADULT), rule(VOTER, name="T")), people()
    skipped = apply_rules(d, s, source_rules=True)
    without_skipping(monkeypatch)
    same(skipped, apply_rules(d, s, source_rules=True))
    assert skipped.source_rules
