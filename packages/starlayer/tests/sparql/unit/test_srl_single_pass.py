"""Rules with nothing to repeat (the run-once rules, and the general rules of a stratum that no rule of the stratum feeds) are
evaluated in the store as well (``srl_eval._derive_once``): a rule with an assignment or a blank node in its head, and a rule
that can write its new triples straight into the evaluation graph (``_StorePlan.direct``). Each way must give what the
element-by-element evaluation gives; ``RuleSet.query`` reads the evaluation graph itself, so it must give the answer of
``infer`` followed by a match over the base graph and the inferred triples."""

import random

import pyoxigraph as ox
import pytest
from starlayer.graph import StarLayerGraph
from starlayer.graph.compare import isomorphic
from starlayer.sparql import srl, srl_eval

EX = "http://example.org/"
PRELUDE = f"PREFIX : <{EX}>\n"

RULE_SETS = {
    "an assignment": "RULE { ?a :double ?d } WHERE { ?a :val ?v . SET (?d := ?v * 2) }",
    "an assignment that is an error for some values drops the solution": "RULE { ?a :next ?d } WHERE { ?a :label ?v . SET (?d := ?v + 1) }\n"
    "RULE { ?a :next ?d } WHERE { ?a :val ?v . SET (?d := ?v + 1) }",
    "an assignment that is an error drops the solution though the head does not use it": "RULE { ?a :flag :yes } WHERE { ?a :label ?v . SET (?d := ?v + 1) }\n"
    "RULE { ?a :flag :yes } WHERE { ?a :val ?v . SET (?d := ?v + 1) }",
    "a blank node inside a triple term of the head": "RULE { ?a :says <<( ?a :edge [] )>> } WHERE { ?a :edge ?b . SET (?z := 1) }",
    "an assignment that is an error, before a pattern that would bind its variable": "RULE { ?a :hit :yes } WHERE { SET (?x := 1 / 0) ?a :val ?x }",
    "an assignment before a pattern that binds its variable": "RULE { ?a :hit :yes } WHERE { SET (?x := 2) ?a :val ?x }",
    "assignments in a chain, then a filter on the last": "RULE { ?a :big ?w } WHERE { ?a :val ?v . SET (?z := ?v + 1) SET (?w := ?z * 2) FILTER (?w > 6) }",
    "an assignment after a negation": "RULE { ?a :free ?d } WHERE { ?a :val ?v . NOT { ?a :edge ?a } SET (?d := ?v - 1) }",
    "a blank node in the head, shared by the head's triples": "RULE { [] :from ?a ; :to ?b } WHERE { ?a :edge ?b }",
    "a blank node in one head triple and a triple the graph may have": "RULE { ?a :copy ?v . ?a :tag [] } WHERE { ?a :val ?v . SET (?z := 1) }",
    "a blank node in one head triple of a general rule": "RULE { ?a :copy ?v . [] :for ?a } WHERE { ?a :val ?v }",
    "a blank node and an assignment": "RULE { [ :of ?a ; :twice ?d ] a :Twin } WHERE { ?a :val ?v . SET (?d := ?v * 2) }",
    "a run-once rule that feeds a general one of its stratum": "RULE { ?a :link ?d } WHERE { ?a :val ?v . SET (?d := IRI(CONCAT(\"http://example.org/n\", STR(?v)))) }\n"
    "RULE { ?a :reach ?b } WHERE { ?a :link ?b }\nRULE { ?a :reach ?c } WHERE { ?a :reach ?b . ?b :link ?c }",
    "a run-once rule that reads what an earlier one derived": "RULE { ?a :double ?d } WHERE { ?a :val ?v . SET (?d := ?v * 2) }\n"
    "RULE { ?a :triple ?e } WHERE { ?a :double ?d . SET (?e := ?d + ?d) }",
    "a run-once rule that derives a base triple": "RULE { ?a :copy ?v } WHERE { ?a :val ?v . SET (?z := 1) }",
    "a run-once rule with two head triples, one of them in the graph": "RULE { ?a :copy ?v . ?a :twin ?v } WHERE { ?a :val ?v . SET (?z := ?v) }",
    "a head with no variable": "RULE { :x :seen :yes } WHERE { ?a :edge ?b . SET (?z := 1) }\nRULE { :x :seen :base } WHERE { ?a :edge ?b }",
    "a general rule with nothing to repeat": "RULE { ?a :q ?b } WHERE { ?a :edge ?b . NOT { ?b :edge ?a } }",
    "a general rule with nothing to repeat, deriving a base triple": "RULE { ?a :copy ?v } WHERE { ?a :val ?v }",
    "a general rule with two head triples": "RULE { ?a :q ?b . ?b :q ?a } WHERE { ?a :edge ?b }",
    "two strata, the second a single pass": "RULE { ?a :reach ?b } WHERE { ?a :edge ?b }\nRULE { ?a :reach ?c } WHERE { ?a :reach ?b . ?b :edge ?c }\n"
    "RULE { ?a :far ?c } WHERE { ?a :reach ?c . NOT { ?a :edge ?c } }",
}


def _has_blank_node(term) -> bool:
    if isinstance(term, ox.Triple):
        return any(_has_blank_node(x) for x in (term.subject, term.predicate, term.object))
    return isinstance(term, ox.BlankNode)


def _graph(seed: int, nodes: int = 6, edges: int = 9) -> StarLayerGraph:
    rng = random.Random(seed)
    g = StarLayerGraph()
    names = [ox.NamedNode(f"{EX}n{i}") for i in range(nodes)]
    integer = ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer")
    for _ in range(edges):
        g.add((rng.choice(names), ox.NamedNode(EX + "edge"), rng.choice(names)))
    for name in names:
        if rng.random() < 0.7:
            g.add((name, ox.NamedNode(EX + "val"), ox.Literal(str(rng.randrange(1, 6)), datatype=integer)))
        if rng.random() < 0.3:
            g.add((name, ox.NamedNode(EX + "label"), ox.Literal("text")))
        if rng.random() < 0.3:  # some of what the :copy rules derive is in the graph already
            g.add((name, ox.NamedNode(EX + "copy"), ox.Literal("1", datatype=integer)))
            g.add((name, ox.NamedNode(EX + "val"), ox.Literal("1", datatype=integer)))
    return g


@pytest.mark.parametrize("name", RULE_SETS)
def test_the_store_gives_what_the_element_by_element_evaluation_gives(name, monkeypatch):
    ruleset = srl.parse_ruleset(PRELUDE + RULE_SETS[name])
    for seed in range(12):
        graph = _graph(seed)
        in_store = ruleset.infer(graph)
        monkeypatch.setattr(srl_eval, "_store_plan", lambda rule: None)
        by_element = ruleset.infer(graph)
        monkeypatch.undo()
        assert len(in_store) == len(by_element) and isomorphic(in_store, by_element), f"seed {seed}: {len(in_store)} against {len(by_element)}"


@pytest.mark.parametrize("name", RULE_SETS)
def test_writing_straight_into_the_graph_and_going_through_the_candidates_agree(name, monkeypatch):
    ruleset = srl.parse_ruleset(PRELUDE + RULE_SETS[name])
    for seed in range(12):
        graph = _graph(seed)
        direct = ruleset.infer(graph)
        monkeypatch.setattr(srl_eval._StorePlan, "direct", lambda self: None)
        through_candidates = ruleset.infer(graph)
        monkeypatch.undo()
        assert len(direct) == len(through_candidates) and isomorphic(direct, through_candidates), f"seed {seed}"


@pytest.mark.parametrize("threshold", [0, 10**9], ids=["every round checked in Python", "every round by MINUS"])
@pytest.mark.parametrize("name", RULE_SETS)
def test_the_candidates_are_kept_either_way(name, threshold, monkeypatch):
    """With no rule writing straight into the graph, the candidates are kept either one by one in Python or by a MINUS update."""
    ruleset = srl.parse_ruleset(PRELUDE + RULE_SETS[name])
    for seed in range(6):
        graph = _graph(seed)
        with monkeypatch.context() as m:
            m.setattr(srl_eval._StorePlan, "direct", lambda self: None)
            m.setattr(srl_eval, "_MINUS_FROM", threshold)
            chosen = ruleset.infer(graph)
        with monkeypatch.context() as m:
            m.setattr(srl_eval, "_store_plan", lambda rule: None)
            by_element = ruleset.infer(graph)
        assert len(chosen) == len(by_element) and isomorphic(chosen, by_element), f"seed {seed}"


@pytest.mark.parametrize("name", ["an assignment", "a blank node in the head, shared by the head's triples", "a general rule with nothing to repeat"])
def test_these_rules_never_leave_the_store(name, monkeypatch):
    """Mutation check on the tests above: the rule sets they compare really run in the store (the other way is not used)."""

    def refuse(*args, **kwargs):
        raise AssertionError("the rule was evaluated element by element")

    monkeypatch.setattr(srl_eval, "_eval_rule", refuse)
    ruleset = srl.parse_ruleset(PRELUDE + RULE_SETS[name])
    assert len(ruleset.infer(_graph(2))) > 0


def test_which_rules_can_write_straight_into_the_graph():
    def direct(rule_text):
        (rule,) = srl.parse_ruleset(PRELUDE + rule_text).rules
        return srl_eval._store_plan(rule).direct()

    assert "MINUS" in direct("RULE { ?a :q ?b } WHERE { ?a :p ?b }")
    assert "MINUS" not in direct("RULE { [] :from ?a } WHERE { ?a :p ?b }")  # a new node in every solution: nothing to take away
    assert direct("RULE { ?a :q ?b . ?b :q ?a } WHERE { ?a :p ?b }") is None  # one MINUS cannot compare two triples
    assert direct("RULE { ?a :q ?b . ?a :r [] } WHERE { ?a :p ?b }") is None  # the first triple may be in the graph already
    assert "MINUS" not in direct("RULE { [] :from ?a . [] :to ?b } WHERE { ?a :p ?b }")
    assert direct("RULE { :x :seen :yes } WHERE { ?a :p ?b }") is None  # a MINUS with no variable in common takes nothing away


def test_a_blank_node_inside_a_triple_term_is_left_to_the_element_by_element_evaluation():
    (rule,) = srl.parse_ruleset(PRELUDE + RULE_SETS["a blank node inside a triple term of the head"]).rules
    assert srl_eval._store_plan(rule) is None


def test_the_size_of_the_evaluation_graph_is_right_after_every_way_of_adding_to_it():
    """The size chooses between Python and MINUS for a round, so a stale one would only make a round slower: check it directly."""
    ruleset = srl.parse_ruleset(PRELUDE + "RULE { ?a :q ?b } WHERE { ?a :edge ?b }\nRULE { ?a :r ?b } WHERE { ?a :edge ?b . SET (?z := 1) }")
    graph = _graph(4)
    evaluation = srl_eval._Evaluation(graph, [])
    assert evaluation.size == len(graph)
    for rule in ruleset.rules:
        srl_eval._derive_once([rule], evaluation)
        assert evaluation.size == len(list(evaluation.store.quads_for_pattern(None, None, None, ox.DefaultGraph())))
    assert evaluation.size > len(graph)


def test_a_blank_node_is_new_for_each_solution_and_shared_within_one():
    ruleset = srl.parse_ruleset(PRELUDE + RULE_SETS["a blank node in the head, shared by the head's triples"])
    g = StarLayerGraph()
    g.parse(data=f"@prefix : <{EX}> . :a :edge :b , :c . :b :edge :c .", format="turtle")
    inferred = ruleset.infer(g)
    assert len(inferred) == 6
    subjects = {s for s, _p, _o in inferred}
    assert len(subjects) == 3 and all(isinstance(s, ox.BlankNode) for s in subjects)
    assert all(len(list(inferred.triples((s, None, None)))) == 2 for s in subjects)


def test_now_is_one_instant_for_every_solution():
    ruleset = srl.parse_ruleset(PRELUDE + "RULE { ?a :at ?t } WHERE { ?a :val ?v . SET (?t := NOW()) }")
    inferred = ruleset.infer(_graph(1, nodes=12))
    assert len(inferred) > 4
    assert len({o for _s, _p, o in inferred}) == 1


def test_an_expression_that_is_new_each_time_is_new_for_each_solution():
    ruleset = srl.parse_ruleset(PRELUDE + "RULE { ?a :id ?u } WHERE { ?a :val ?v . SET (?u := STRUUID()) }")
    inferred = ruleset.infer(_graph(1, nodes=12))
    assert len(inferred) > 4
    assert len({o for _s, _p, o in inferred}) == len(inferred)


def test_what_the_base_graph_has_is_not_inferred_by_a_direct_insert():
    ruleset = srl.parse_ruleset(PRELUDE + "RULE { ?a :q ?b } WHERE { ?a :p ?b }")
    g = StarLayerGraph()
    g.parse(data=f"@prefix : <{EX}> . :a :p :b , :c . :a :q :b .", format="turtle")
    inferred = ruleset.infer(g)
    assert set(inferred) == {(ox.NamedNode(EX + "a"), ox.NamedNode(EX + "q"), ox.NamedNode(EX + "c"))}


def test_the_rule_sets_own_data_is_inferred_only_when_the_graph_lacks_it():
    ruleset = srl.parse_ruleset(PRELUDE + "DATA { :a :p :b . :a :p :new }\nRULE { ?a :q ?b } WHERE { ?a :p ?b }")
    g = StarLayerGraph()
    g.parse(data=f"@prefix : <{EX}> . :a :p :b .", format="turtle")
    local = lambda triples: {tuple(term.value.removeprefix(EX) for term in t) for t in triples}  # noqa: E731
    assert local(ruleset.infer(g)) == {("a", "p", "new"), ("a", "q", "b"), ("a", "q", "new")}


@pytest.mark.parametrize("name", list(RULE_SETS))
def test_query_reads_the_evaluation_graph_and_agrees_with_infer(name):
    ruleset = srl.parse_ruleset(PRELUDE + RULE_SETS[name])
    goal = srl.parse_ruleset(PRELUDE + "RULE { ?s :goal ?o } WHERE { ?s ?p ?o }").rules[0].body[0]
    for seed in range(4):
        graph = _graph(seed)
        before = set(graph)
        rows = ruleset.query(graph, goal)
        inferred = ruleset.infer(graph)
        both = set(graph) | set(inferred)
        # blank nodes differ between two runs, so compare the rows without them
        plain = lambda triples: {t for t in triples if not any(_has_blank_node(x) for x in t)}  # noqa: E731
        got = {(r[ox.Variable("s")], r[ox.Variable("p")], r[ox.Variable("o")]) for r in rows}
        assert plain(got) == plain(both), f"seed {seed}"
        assert len(rows) == len(both)
        assert set(graph) == before  # the caller's graph is left as it was


def test_the_inferred_graph_has_nothing_but_the_inferred_triples():
    ruleset = srl.parse_ruleset(PRELUDE + RULE_SETS["two strata, the second a single pass"])
    inferred = ruleset.infer(_graph(3))
    assert not list(inferred.store.named_graphs())
    base = _graph(3)
    assert not (set(inferred) & set(base))
