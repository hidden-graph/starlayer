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
    "a closure with the edge on the right": "RULE { ?a :reach ?b } WHERE { ?a :edge ?b }\nRULE { ?a :reach ?c } WHERE { ?a :reach ?b . ?b :edge ?c }",
    "a closure with the patterns the other way round": "RULE { ?a :reach ?c } WHERE { ?b :edge ?c . ?a :reach ?b }\nRULE { ?a :reach ?b } WHERE { ?a :edge ?b }",
    "a closure fed by a rule of its own stratum": "RULE { ?a :r ?b } WHERE { ?a :edge ?b }\nRULE { ?b :r ?a } WHERE { ?a :edge ?b . ?b :edge ?c }\n"
    "RULE { ?a :r ?c } WHERE { ?a :r ?b . ?b :r ?c }",
    "a closure whose edge is derived by another rule of its stratum": "RULE { ?a :edge ?b } WHERE { ?a :same ?b }\nRULE { ?a :reach ?b } WHERE { ?a :sg ?b }\n"
    "RULE { ?a :reach ?c } WHERE { ?a :reach ?b . ?b :edge ?c }",
    "a closure whose edge is derived by the closure's own kind of rule": "RULE { ?a :reach ?b } WHERE { ?a :edge ?b }\nRULE { ?a :edge ?c } WHERE { ?a :reach ?b . ?b :edge ?c }\n"
    "RULE { ?a :reach ?c } WHERE { ?a :reach ?b . ?b :edge ?c }",
    "a closure that needs an edge from a node to itself": "RULE { ?a :reach ?b } WHERE { ?a :edge ?b }\nRULE { ?a :reach ?c } WHERE { ?a :edge ?a . ?a :reach ?c }",
    "a transitive rule whose ends are the same node": "RULE { ?a :r ?a } WHERE { ?a :r ?b . ?b :r ?a }\nRULE { ?a :r ?b } WHERE { ?a :edge ?b }",
    "a closure over a constant": "RULE { ?a :reach ?b } WHERE { ?a :edge ?b }\nRULE { :n0 :reach ?c } WHERE { :n0 :reach ?b . ?b :edge ?c }",
    "a closure with a variable predicate": "RULE { ?a :reach ?b } WHERE { ?a :edge ?b }\nRULE { ?a :reach ?c } WHERE { ?a :reach ?b . ?b ?p ?c }",
    "two strata": "RULE { ?a :reach ?b } WHERE { ?a :edge ?b }\nRULE { ?a :reach ?c } WHERE { ?a :reach ?b . ?b :edge ?c }\n"
    "RULE { ?a :far ?c } WHERE { ?a :reach ?b . ?b :reach ?c . NOT { ?a :edge ?c } }",
}


def _naive(rules, evaluation):
    finished = False
    while not finished:
        finished = True
        for rule in rules:
            for t in srl_eval._eval_rule(rule, evaluation.ge, evaluation.base):
                if t not in evaluation.ge:
                    finished = False
                    evaluation.ge.add(t)
                    evaluation.store.add(ox.Quad(*t, srl_eval._INFERRED_GRAPH))
    evaluation.forget_size()


def _graph(seed: int, nodes: int = 7, edges: int = 12) -> StarLayerGraph:
    rng = random.Random(seed)
    g = StarLayerGraph()
    names = [ox.NamedNode(f"{EX}n{i}") for i in range(nodes)]
    for _ in range(edges):
        g.add((rng.choice(names), ox.NamedNode(EX + "edge"), rng.choice(names)))
    for predicate in ("reach", "r", "same", "sg", "even", "odd"):  # a few of what the rules derive, in the graph already
        for _ in range(rng.randrange(3)):
            g.add((rng.choice(names), ox.NamedNode(EX + predicate), rng.choice(names)))
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
    ruleset = srl.parse_ruleset(PRELUDE + RULE_SETS["mutual recursion"])
    graph = _graph(3)
    real = srl_eval._StorePlan.update

    def first_round_only(self, delta_index):
        return "CLEAR SILENT GRAPH <urn:x:none>" if delta_index is not None else real(self, delta_index)

    monkeypatch.setattr(srl_eval._StorePlan, "update", first_round_only)
    broken = _inferred(ruleset, graph)
    monkeypatch.undo()
    assert broken != _inferred(ruleset, graph)


@pytest.mark.parametrize("name", RULE_SETS)
def test_the_rounds_give_what_full_rounds_give_when_no_closure_is_recognised(name, monkeypatch):
    """A closure of the shapes ``_closure_of`` knows is computed by one update, so the rounds would not run for those rule sets
    above: switch the recognition off and compare the rounds as well."""
    ruleset = srl.parse_ruleset(PRELUDE + RULE_SETS[name])
    for seed in range(25):
        graph = _graph(seed)
        with monkeypatch.context() as m:
            m.setattr(srl_eval, "_closure_of", lambda rules, positions: None)
            rounds = _inferred(ruleset, graph)
        with monkeypatch.context() as m:
            m.setattr(srl_eval, "_run_to_fixpoint", _naive)
            slow = _inferred(ruleset, graph)
        assert rounds == slow, f"seed {seed}: {len(rounds ^ slow)} triples differ"


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
    assert _plan("RULE { ?a :q ?b } WHERE { ?a :p ?x . SET (?b := ?x + 1) }") is not None
    assert _plan("RULE { ?a :q [] } WHERE { ?a :p ?b }") is not None
    assert _plan("RULE { ?a :q ?b } WHERE { ?a :p ?x . SET (?b := BNODE(STR(?x))) }") is None  # a node of its own on each call
    assert _plan("RULE { ?a :q ?b } WHERE { ?a :p ?x . SET (?b := ?x + 1) FILTER(?b > 1) }") is not None  # the assignment binds ?b first
    assert _plan("RULE { ?a :q ?s } WHERE { GROUP BY ?a { ?a :p ?v } [ ?s := SUM(?v) ] }") is None


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

    def spy(rules, evaluation):
        real(rules, evaluation)
        ge_stores.append(evaluation.store)

    srl_eval._run_to_fixpoint = spy
    try:
        ruleset.infer(graph)
    finally:
        srl_eval._run_to_fixpoint = real
    scratch = (srl_eval._DELTA_GRAPH, srl_eval._CANDIDATE_GRAPH)
    assert ge_stores and all(not list(s.quads_for_pattern(None, None, None, g)) for s in ge_stores for g in scratch)
    assert not any(list(graph.as_store().quads_for_pattern(None, None, None, g)) for g in (*scratch, srl_eval._INFERRED_GRAPH))


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


def _closure(rules_text: str):
    ruleset = srl.parse_ruleset(PRELUDE + rules_text)
    heads = [head for rule in ruleset.rules for head in rule.head]
    positions = {id(rule): srl_eval._delta_positions(rule, heads) for rule in ruleset.rules}
    found = srl_eval._closure_of(ruleset.rules, positions)
    return None if found is None else found[1].split("WHERE", 1)[1].strip()


@pytest.mark.parametrize(
    ("rules", "path"),
    [
        ("RULE { ?a :q ?b } WHERE { ?a :p ?b }\nRULE { ?a :q ?c } WHERE { ?a :q ?b . ?b :q ?c }", "{ ?a <http://example.org/q>+ ?c }"),
        ("RULE { ?a :q ?c } WHERE { ?b :q ?c . ?a :q ?b }", "{ ?a <http://example.org/q>+ ?c }"),
        ("RULE { ?a :q ?c } WHERE { ?a :q ?b . ?b :p ?c }", "{ ?a <http://example.org/q> ?b . ?b <http://example.org/p>* ?c }"),
        ("RULE { ?a :q ?c } WHERE { ?b :p ?c . ?a :q ?b }", "{ ?a <http://example.org/q> ?b . ?b <http://example.org/p>* ?c }"),
        ("RULE { ?a :q ?c } WHERE { ?a :p ?b . ?b :q ?c }", "{ ?b <http://example.org/q> ?c . ?a <http://example.org/p>* ?b }"),
        ("RULE { ?a :p ?b } WHERE { ?a :s ?b }\nRULE { ?a :q ?c } WHERE { ?a :q ?b . ?b :p ?c }", "{ ?a <http://example.org/q> ?b . ?b <http://example.org/p>* ?c }"),  # p derived by a rule that nothing feeds
        ("RULE { ?a :q ?b } WHERE { ?a :s ?b }\nRULE { ?a :q ?c } WHERE { ?a :q ?b . ?b :p ?c }", "{ ?a <http://example.org/q> ?b . ?b <http://example.org/p>* ?c }"),
    ],
)
def test_the_closures_oxigraph_computes_by_itself(rules, path):
    assert _closure(rules) == path


@pytest.mark.parametrize(
    "rules",
    [
        "RULE { ?a :q ?a } WHERE { ?a :q ?b . ?b :q ?a }",  # the ends are one node
        "RULE { ?a :q ?c } WHERE { ?a :q ?a . ?a :q ?c }",  # the middle is the start
        "RULE { ?a :q ?c } WHERE { ?a :p ?a . ?a :q ?c }",  # the same, with the edge first
        "RULE { :a :q ?c } WHERE { :a :q ?b . ?b :p ?c }",  # a constant end
        "RULE { ?a :q ?c } WHERE { ?a :q ?b . ?b ?p ?c }",  # a variable predicate
        "RULE { ?a :q ?c } WHERE { ?a :q ?b . ?b :p ?c . FILTER (?a != ?c) }",  # three elements
        "RULE { ?a :q ?c } WHERE { ?a :q ?b . ?c :p ?b }",  # the edge the wrong way
        "RULE { ?a :q ?c } WHERE { ?a :q ?b . ?b :p ?c }\nRULE { ?a :p ?c } WHERE { ?a :p ?b . ?b :q ?c }",  # p grows with q
        "RULE { ?a :q ?c } WHERE { ?a :q ?b . ?b :p ?c }\nRULE { ?a :s ?c } WHERE { ?a :s ?b . ?b :s ?c }",  # a second repeating rule
        "RULE { ?a :q ?c . ?a :t ?c } WHERE { ?a :q ?b . ?b :p ?c }",  # two head triples
        "RULE { ?a :q ?c } WHERE DATA { ?a :q ?b . ?b :p ?c }",  # reads the base graph only
    ],
)
def test_the_rules_that_are_not_such_closures(rules):
    assert _closure(rules) is None


def test_a_long_closure_is_computed_by_the_store_in_one_update():
    """The closure of a chain of 300 takes one update, not 300 rounds: the delta graph is never written."""
    ruleset = srl.parse_ruleset(PRELUDE + RULE_SETS["transitive closure"])
    g = StarLayerGraph()
    g.extend((ox.NamedNode(f"{EX}n{i}"), ox.NamedNode(EX + "edge"), ox.NamedNode(f"{EX}n{i + 1}")) for i in range(300))
    real = srl_eval._Evaluation.commit
    deltas = []

    def spy(self, delta):
        deltas.append(delta)
        return real(self, delta)

    srl_eval._Evaluation.commit = spy
    try:
        inferred = ruleset.infer(g)
    finally:
        srl_eval._Evaluation.commit = real
    assert len(inferred) == 300 * 301 // 2
    assert deltas and not any(deltas)
