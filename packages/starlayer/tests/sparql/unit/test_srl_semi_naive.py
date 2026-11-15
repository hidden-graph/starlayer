"""The fixpoint of a stratum is computed from each round's new triples (``srl_eval._run_to_fixpoint``), with the rounds' work done in
the store for the rules ``_store_plan`` accepts. It must give exactly what re-evaluating every rule in full each round gives, so
every rule set here runs both ways on random graphs and the results are compared. ``_naive`` is the loop the evaluator used before."""

import random

import pyoxigraph as ox
import pytest
from starlayer.graph import StarLayerGraph
from starlayer.sparql import srl, srl_eval

EX = "http://example.org/"
PRELUDE = f"PREFIX : <{EX}>\n"

RULE_SETS = {
    "transitive closure": "RULE { ?a :reach ?b } WHERE { ?a :edge ?b }\nRULE { ?a :reach ?c } WHERE { ?a :edge ?b . ?b :reach ?c }",
    "non-linear closure (the delta on either side)": "RULE { ?a :r ?b } WHERE { ?a :edge ?b }\nRULE { ?a :r ?c } WHERE { ?a :r ?b . ?b :r ?c }",
    "mutual recursion": "RULE { ?a :even ?b } WHERE { ?a :edge ?x . ?x :odd ?b }\nRULE { ?a :odd ?b } WHERE { ?a :edge ?b }\n"
    "RULE { ?a :odd ?b } WHERE { ?a :edge ?x . ?x :even ?b }",
    "symmetric and transitive": "RULE { ?b :same ?a } WHERE { ?a :same ?b }\nRULE { ?a :same ?c } WHERE { ?a :same ?b . ?b :same ?c }\n"
    "RULE { ?a :same ?b } WHERE { ?a :edge ?b }",
    "same generation": "RULE { ?a :sg ?b } WHERE { ?p :edge ?a . ?p :edge ?b }\nRULE { ?a :sg ?b } WHERE { ?p :edge ?a . ?q :edge ?b . ?p :sg ?q }",
    "a variable predicate matches what the rules derive": "RULE { ?a :t ?b } WHERE { ?a :edge ?b }\nRULE { ?b :inv ?a } WHERE { ?a ?p ?b . FILTER(?p != :inv) }\n"
    "RULE { ?a :t ?c } WHERE { ?a ?p ?b . ?b :t ?c . FILTER(?p = :edge) }",
    "a filter in a recursive rule": "RULE { ?a :reach ?b } WHERE { ?a :edge ?b }\n"
    "RULE { ?a :reach ?c } WHERE { ?a :reach ?b . ?b :edge ?c . FILTER(?a != ?c) }",
    "negation of a lower stratum": "RULE { ?a :reach ?b } WHERE { ?a :edge ?b }\nRULE { ?a :reach ?c } WHERE { ?a :reach ?b . ?b :edge ?c }\n"
    "RULE { ?a :lonely :yes } WHERE { ?a :edge ?x . NOT { ?a :reach ?a } }",
    "a rule that reads the base graph only (WHERE DATA)": "RULE { ?a :reach ?b } WHERE { ?a :edge ?b }\n"
    "RULE { ?a :reach ?c } WHERE { ?a :reach ?b . ?b :edge ?c }\nRULE { ?a :seen :base } WHERE DATA { ?a :edge ?b }",
    "two strata": "RULE { ?a :reach ?b } WHERE { ?a :edge ?b }\nRULE { ?a :reach ?c } WHERE { ?a :reach ?b . ?b :edge ?c }\n"
    "RULE { ?a :far ?c } WHERE { ?a :reach ?b . ?b :reach ?c . NOT { ?a :edge ?c } }",
}


def _naive(rules, ge, base_graph, gi):
    finished = False
    while not finished:
        finished = True
        for rule in rules:
            for t in srl_eval._eval_rule(rule, ge, base_graph):
                if t not in ge:
                    finished = False
                    gi.add(t)
                    ge.add(t)


def _graph(seed: int, nodes: int = 7, edges: int = 12) -> StarLayerGraph:
    rng = random.Random(seed)
    g = StarLayerGraph()
    names = [ox.NamedNode(f"{EX}n{i}") for i in range(nodes)]
    for _ in range(edges):
        g.add((rng.choice(names), ox.NamedNode(EX + "edge"), rng.choice(names)))
    return g


def _inferred(ruleset, graph) -> set:
    return {tuple(t) for t in ruleset.infer(graph)}


@pytest.mark.parametrize("name", RULE_SETS)
def test_each_round_from_the_new_triples_gives_what_full_rounds_give(name, monkeypatch):
    ruleset = srl.parse_ruleset(PRELUDE + RULE_SETS[name])
    for seed in range(25):
        graph = _graph(seed)
        fast = _inferred(ruleset, graph)
        monkeypatch.setattr(srl_eval, "_run_to_fixpoint", _naive)
        slow = _inferred(ruleset, graph)
        monkeypatch.undo()
        assert fast == slow, f"seed {seed}: {len(fast ^ slow)} triples differ"


def test_the_comparison_notices_a_missed_derivation(monkeypatch):
    """Mutation check: a round that ignores the delta (here, one that derives nothing after the first round) must not pass."""
    ruleset = srl.parse_ruleset(PRELUDE + RULE_SETS["transitive closure"])
    graph = _graph(3)
    real = srl_eval._StorePlan.update

    def first_round_only(self, delta_index):
        return "CLEAR SILENT GRAPH <urn:x:none>" if delta_index is not None else real(self, delta_index)

    monkeypatch.setattr(srl_eval._StorePlan, "update", first_round_only)
    broken = _inferred(ruleset, graph)
    monkeypatch.undo()
    assert broken != _inferred(ruleset, graph)


@pytest.mark.parametrize("name", RULE_SETS)
def test_the_element_by_element_path_gives_the_same(name, monkeypatch):
    """Every rule the store takes can also be evaluated element by element (the path for what the store cannot take)."""
    ruleset = srl.parse_ruleset(PRELUDE + RULE_SETS[name])
    for seed in range(10):
        graph = _graph(seed)
        in_store = _inferred(ruleset, graph)
        monkeypatch.setattr(srl_eval, "_store_plan", lambda rule: None)
        by_element = _inferred(ruleset, graph)
        monkeypatch.undo()
        assert in_store == by_element, f"seed {seed}: {len(in_store ^ by_element)} triples differ"


@pytest.mark.parametrize("name", RULE_SETS)
@pytest.mark.parametrize("threshold", [0, 10**9], ids=["every round checked in Python", "every round by MINUS"])
def test_both_ways_of_finding_the_new_triples_agree(name, threshold, monkeypatch):
    """A round keeps the candidates the graph does not have either one by one in Python or by a MINUS update, by size; each must
    give the answer of the loop that re-evaluates every rule in full."""
    ruleset = srl.parse_ruleset(PRELUDE + RULE_SETS[name])
    for seed in range(10):
        graph = _graph(seed)
        monkeypatch.setattr(srl_eval, "_MINUS_FROM", threshold)
        chosen = _inferred(ruleset, graph)
        monkeypatch.setattr(srl_eval, "_run_to_fixpoint", _naive)
        slow = _inferred(ruleset, graph)
        monkeypatch.undo()
        assert chosen == slow, f"seed {seed}: {len(chosen ^ slow)} triples differ"


def _rule(rule_text: str, filter_first: bool = False):
    """The one rule of ``rule_text``; with ``filter_first`` its last body element moves to second place (the parser refuses a rule
    written that way, so this is the only way to get one)."""
    ruleset = srl.parse_ruleset(PRELUDE + rule_text)
    (rule,) = ruleset.rules
    if filter_first:
        rule.body.insert(1, rule.body.pop())
    return ruleset, rule


def _plan(rule_text: str, filter_first: bool = False):
    return srl_eval._store_plan(_rule(rule_text, filter_first)[1])


def test_which_rules_the_store_takes():
    assert _plan("RULE { ?a :q ?b } WHERE { ?a :p ?b . FILTER(?a != ?b) }") is not None
    assert _plan("RULE { ?a :q ?b } WHERE { ?a :p ?b . NOT { ?b :p ?a } }") is not None
    # an element that reads a variable a later pattern binds: in order it sees it unbound, in a SPARQL group it would see the value
    assert _plan("RULE { ?a :q ?b } WHERE { ?a :p ?x . ?a :r ?b . FILTER(?x != ?b) }", filter_first=True) is None
    assert _plan("RULE { ?a :q ?b } WHERE { ?a :p ?x . ?a :s ?b . NOT { ?a :r ?b } }", filter_first=True) is None
    assert _plan("RULE { ?a :q ?b } WHERE DATA { ?a :p ?b }") is None
    assert _plan("RULE { ?a :q ?b } WHERE { ?a :p ?b . NOT DATA { ?a :r ?b } }") is None
    assert _plan("RULE { ?a :q ?b } WHERE { ?a :p ?x . SET (?b := ?x + 1) }") is None
    assert _plan("RULE { ?a :q [] } WHERE { ?a :p ?b }") is None


def test_a_filter_before_its_variable_is_bound_keeps_the_in_order_meaning():
    """The store would answer with the group-scoped filter; the evaluator must answer as the spec's element order does (an error
    is false, so the row is dropped), and does, because such a rule is not given to the store."""
    ruleset, _ = _rule("RULE { ?a :q ?b } WHERE { ?a :p ?x . ?a :r ?b . FILTER(?x != ?b) }", filter_first=True)
    g = StarLayerGraph()
    g.parse(data=f"@prefix : <{EX}> . :a :p :x ; :r :y .", format="turtle")
    assert _inferred(ruleset, g) == set()
    ruleset, _ = _rule("RULE { ?a :q ?b } WHERE { ?a :p ?x . ?a :r ?b . FILTER(?x != ?b) }")
    assert len(_inferred(ruleset, g)) == 1  # in its written order the same rule derives the triple


def test_the_delta_graph_is_gone_afterwards():
    ruleset = srl.parse_ruleset(PRELUDE + RULE_SETS["transitive closure"])
    graph = _graph(1)
    ge_stores = []
    real = srl_eval._run_to_fixpoint

    def spy(rules, ge, base_graph, gi):
        real(rules, ge, base_graph, gi)
        ge_stores.append(ge.as_store())

    srl_eval._run_to_fixpoint = spy
    try:
        ruleset.infer(graph)
    finally:
        srl_eval._run_to_fixpoint = real
    scratch = (srl_eval._DELTA_GRAPH, srl_eval._CANDIDATE_GRAPH, srl_eval._NEW_GRAPH, srl_eval._INFERRED_GRAPH)
    assert ge_stores and all(not list(s.quads_for_pattern(None, None, None, g)) for s in ge_stores for g in scratch)
    assert not any(list(graph.as_store().quads_for_pattern(None, None, None, g)) for g in scratch)


def test_a_long_chain_is_not_cubic():
    """Chain of 120: 7,260 derived facts. Re-evaluating every rule each round took tens of seconds; the new triples of each round
    take under a second. The bound is loose; it exists to catch a return to full rounds."""
    import time

    ruleset = srl.parse_ruleset(PRELUDE + RULE_SETS["transitive closure"])
    g = StarLayerGraph()
    g.extend((ox.NamedNode(f"{EX}n{i}"), ox.NamedNode(EX + "edge"), ox.NamedNode(f"{EX}n{i + 1}")) for i in range(120))
    start = time.perf_counter()
    inferred = ruleset.infer(g)
    assert len(inferred) == 120 * 121 // 2  # every reach pair
    assert time.perf_counter() - start < 10
