"""Extended checks of SRL's stratification (SRL §4.3.2 dependency
graph, §4.4.2 stratification) beyond the spec's one worked example in
``test_srl_eval.py``: indirect negation cycles, long chains, edge cases of
the dependency graph, and the deliberately loose pattern match.

Opt-in, like the store matrix - left out of an ordinary run, see
``tests/conftest.py``:

    pytest --srl-stratification
"""

from __future__ import annotations

import pytest
from rdflib import Graph
from starlayer.sparql.srl import parse_ruleset
from starlayer.sparql.srl_eval import StratificationError

pytestmark = pytest.mark.srl_stratification

PREFIX = "PREFIX : <http://example.org/>\n"


def _ruleset(*rules: str):
    return parse_ruleset(PREFIX + "\n".join(rules))


def _strata(plan):
    """[[rule indexes in stratum 0], [... stratum 1], ...] - run-once and general rules together."""
    return [sorted(r.index for r in s.run_once + s.general) for s in plan.strata]


def _labels(plan):
    return {(e.source, e.target): e.label for e in plan.edges}


def _two_rules(producer_head, consumer_body):
    """Rule 0 produces ``producer_head`` from a body that binds every variable
    it might use; rule 1 matches ``consumer_body`` and has a constant head."""
    return _ruleset(
        f"RULE {{ {producer_head} }} WHERE {{ ?x ?pp ?y . ?v ?pp2 ?w }}",
        f"RULE {{ :r :out :done }} WHERE {{ {consumer_body} }}",
    ).plan()


# --- cycles -----------------------------------------------------------------


def test_negation_cycle_through_two_rules_is_rejected():
    ruleset = _ruleset(
        "RULE { ?x :p ?y } WHERE { ?x :q ?y . NOT { ?x :r ?y } }",
        "RULE { ?x :r ?y } WHERE { ?x :p ?y }",
    )
    with pytest.raises(StratificationError):
        ruleset.plan()


def test_negation_cycle_through_three_rules_is_rejected():
    ruleset = _ruleset(
        "RULE { ?x :a ?y } WHERE { ?x :q ?y . NOT { ?x :c ?y } }",
        "RULE { ?x :b ?y } WHERE { ?x :a ?y }",
        "RULE { ?x :c ?y } WHERE { ?x :b ?y }",
    )
    with pytest.raises(StratificationError):
        ruleset.plan()


def test_positive_mutual_recursion_stays_in_one_stratum():
    ruleset = _ruleset(
        "RULE { ?x :a ?y } WHERE { ?x :b ?y }",
        "RULE { ?x :b ?y } WHERE { ?x :a ?y }",
    )
    plan = ruleset.plan()
    assert _strata(plan) == [[0, 1]]
    assert set(_labels(plan).values()) == {"open"}


def test_negation_of_something_nothing_produces_is_not_a_cycle():
    ruleset = _ruleset("RULE { ?x :p ?y } WHERE { ?x :q ?y . NOT { ?x :never ?y } }")
    assert _strata(ruleset.plan()) == [[0]]


# --- chains -----------------------------------------------------------------

CHAIN = [
    "RULE { ?x :a ?y } WHERE { ?x :base ?y }",
    "RULE { ?x :b ?y } WHERE { ?x :c ?y . NOT { ?x :a ?y } }",
    "RULE { ?x :d ?y } WHERE { ?x :c ?y . NOT { ?x :b ?y } }",
]


def test_chain_of_negations_gives_one_stratum_per_link():
    plan = _ruleset(*CHAIN).plan()
    assert _strata(plan) == [[0], [1], [2]]
    labels = _labels(plan)
    assert labels[(1, 0)] == "closed" and labels[(2, 1)] == "closed"


def test_chain_result_depends_on_evaluating_in_stratum_order():
    """If rule 2 ran before rule 1, ``y`` would wrongly get :d."""
    base = Graph()
    base.parse(
        data="@prefix : <http://example.org/> . :x :base 1 ; :c 1 . :y :c 1 .",
        format="turtle",
    )
    inferred = {(str(s).rsplit("/", 1)[-1], str(p).rsplit("/", 1)[-1]) for s, p, _ in _ruleset(*CHAIN).infer(base)}
    assert inferred == {("x", "a"), ("y", "b"), ("x", "d")}


@pytest.mark.parametrize("length", [10, 40])
def test_long_negation_chain_gets_one_stratum_per_rule(length):
    rules = ["RULE { ?x :p0 ?y } WHERE { ?x :base ?y }"]
    rules += [f"RULE {{ ?x :p{i} ?y }} WHERE {{ ?x :c ?y . NOT {{ ?x :p{i - 1} ?y }} }}" for i in range(1, length)]
    plan = _ruleset(*rules).plan()
    assert _strata(plan) == [[i] for i in range(length)]


def test_many_independent_rules_share_one_stratum_with_no_edges():
    ruleset = _ruleset(*[f"RULE {{ ?x :out{i} ?y }} WHERE {{ ?x :in{i} ?y }}" for i in range(150)])
    plan = ruleset.plan()
    assert _strata(plan) == [list(range(150))]
    assert plan.edges == []


# --- shape of the dependency graph -------------------------------------------


def test_not_with_several_patterns_depends_on_every_rule_that_could_feed_it():
    plan = _ruleset(
        "RULE { ?x :a ?y } WHERE { ?x :base ?y }",
        "RULE { ?x :b ?y } WHERE { ?x :base2 ?y }",
        "RULE { ?x :s ?y } WHERE { ?x :c ?y . NOT { ?x :a ?y . ?y :b ?z } }",
    ).plan()
    labels = _labels(plan)
    assert labels[(2, 0)] == "closed" and labels[(2, 1)] == "closed"
    assert _strata(plan) == [[0, 1], [2]]


def test_two_rules_producing_the_same_predicate_both_feed_a_consumer():
    plan = _ruleset(
        "RULE { ?x :a ?y } WHERE { ?x :base ?y }",
        "RULE { ?x :a ?y } WHERE { ?x :base2 ?y }",
        "RULE { ?x :s ?y } WHERE { ?x :a ?y }",
        "RULE { ?x :t ?y } WHERE { ?x :c ?y . NOT { ?x :a ?y } }",
    ).plan()
    labels = _labels(plan)
    assert labels[(2, 0)] == labels[(2, 1)] == "open"
    assert labels[(3, 0)] == labels[(3, 1)] == "closed"
    assert _strata(plan) == [[0, 1, 2], [3]]


def test_open_and_closed_dependency_on_the_same_rule_is_closed():
    plan = _ruleset(
        "RULE { ?x :a ?y } WHERE { ?x :base ?y }",
        "RULE { ?x :s ?y } WHERE { ?x :a ?y . NOT { ?x :a ?z } }",
    ).plan()
    assert _labels(plan)[(1, 0)] == "closed"


def test_every_dependency_of_a_run_once_rule_is_closed():
    """A blank node in the head makes a rule run-once; it must see its inputs complete."""
    plan = _ruleset(
        "RULE { ?x :a ?y } WHERE { ?x :base ?y }",
        "RULE { [] :n ?x } WHERE { ?x :a ?y }",
    ).plan()
    assert _labels(plan)[(1, 0)] == "closed"
    assert [r.index for r in plan.strata[1].run_once] == [1]


# --- the deliberately loose match ---------------------------------------------


@pytest.mark.parametrize(
    "head, body",
    [
        ("?x :p ?y", "?a :p ?b"),  # variables everywhere
        ("?x :p :o", "?a :p ?b"),  # constant in the head, variable in the body
        (":s :p ?y", ":s :p ?b"),  # same constant subject
        ("?x ?pp ?y", "?a :p ?b"),  # variable predicate in the head
        ("?x :p ?y", "?a ?pred ?b"),  # variable predicate in the body
    ],
)
def test_a_real_dependency_is_never_missed(head, body):
    plan = _two_rules(head, body)
    assert (1, 0) in _labels(plan)


@pytest.mark.parametrize(
    "head, body",
    [
        ("?x :p ?y", "?a :q ?b"),  # different predicate
        (":s :p ?y", ":other :p ?b"),  # different constant subject
        ("?x :p :o1", "?a :p :o2"),  # different constant object
    ],
)
def test_clearly_unrelated_patterns_give_no_edge(head, body):
    plan = _two_rules(head, body)
    assert (1, 0) not in _labels(plan)


def test_a_repeated_variable_does_not_narrow_the_match():
    """The head ?v :p ?v can only produce triples whose subject equals its
    object, so a stricter reading than the spec's procedure would find no
    dependency on the body :a :p :b. This implementation checks each position
    on its own and reports one: a coarser plan, never a wrong result."""
    plan = _two_rules("?v :p ?v", ":a :p :b")
    assert (1, 0) in _labels(plan)


# --- plan() itself --------------------------------------------------------------


def test_plan_is_repeatable_and_does_not_change_the_rule_set():
    ruleset = _ruleset(*CHAIN)
    before = list(ruleset.rules)
    assert ruleset.plan() == ruleset.plan()
    assert ruleset.rules == before
