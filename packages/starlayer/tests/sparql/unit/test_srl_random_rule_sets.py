"""Random rule sets, run with every fast path (rules in the store, writing straight into the evaluation graph, closures by property
path, rounds from the delta) and with none of them (every rule element by element, every round in full). The two must give the same
graph up to blank-node names. ``SRL_FUZZ_SEEDS=5000`` runs a longer hunt; the default is a short one."""

import os
import random

import pyoxigraph as ox
import pytest
from starlayer.graph import StarLayerGraph
from starlayer.graph.compare import isomorphic
from starlayer.sparql import srl, srl_eval

EX = "http://e/"
PREDICATES = ["a", "b", "c", "d"]
NODES = [f"n{i}" for i in range(5)]
INTEGER = ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer")
SEEDS = int(os.environ.get("SRL_FUZZ_SEEDS", "600"))


def _closure_rule(rng: random.Random) -> str:
    q, p = rng.choice(PREDICATES), rng.choice(PREDICATES)
    body = rng.choice(
        [f"?x :{q} ?y . ?y :{q} ?z .", f"?x :{q} ?y . ?y :{p} ?z .", f"?x :{p} ?y . ?y :{q} ?z .", f"?y :{q} ?z . ?x :{q} ?y ."]
    )
    return f"RULE {{ ?x :{q} ?z . }} WHERE {{ {body} }}"


def _rule(rng: random.Random) -> str:
    if rng.random() < 0.3:
        return _closure_rule(rng)
    variables = ("x", "y", "z", "w")
    body: list[str] = []
    bound: set[str] = set()
    for _ in range(rng.choice([1, 1, 2, 2, 3])):
        s = rng.choice(variables) if rng.random() < 0.85 else f":{rng.choice(NODES)}"
        o = rng.choice(variables) if rng.random() < 0.85 else (f":{rng.choice(NODES)}" if rng.random() < 0.7 else str(rng.randrange(1, 4)))
        p = f":{rng.choice(PREDICATES)}" if rng.random() < 0.92 else "?q"
        parts = []
        for term in (s, p, o):
            if term.startswith("?"):
                bound.add(term[1:])
                parts.append(term)
            elif term in variables:
                bound.add(term)
                parts.append("?" + term)
            else:
                parts.append(term)
        body.append(" ".join(parts) + " .")
    names = sorted(bound)
    for _ in range(rng.choice([0, 0, 1, 2])):
        if not names:
            break
        kind = rng.choice(["filter", "not", "set", "set"])
        a = rng.choice(names)
        if kind == "filter":
            b = rng.choice([*names, "2"])
            body.append(f"FILTER (?{a} {rng.choice(['!=', '=', '<', '>'])} {'?' + b if b in names else b})")
        elif kind == "not":
            body.append(f"NOT {{ ?{a} :{rng.choice(PREDICATES)} ?{rng.choice(names)} }}")
        else:
            new = f"v{len(body)}"
            expression = rng.choice([f"?{a} + 1", f"?{a} * 2", f"STR(?{a})", f"?{a}", "1/0" if rng.random() < 0.2 else "7"])
            body.append(f"SET (?{new} := {expression})")
            names.append(new)
    head = []
    for _ in range(rng.choice([1, 1, 1, 2])):
        s = rng.choice(names) if rng.random() < 0.9 else f":{rng.choice(NODES)}"
        o = rng.choice(names) if rng.random() < 0.85 else (f":{rng.choice(NODES)}" if rng.random() < 0.5 else "[]")
        head.append(f"{'?' + s if s in names else s} :{rng.choice([*PREDICATES, 'h', 'h'])} {'?' + o if o in names else o} .")
    return "RULE { " + " ".join(head) + " } WHERE { " + " ".join(body) + " }"


def _graph(rng: random.Random) -> StarLayerGraph:
    g = StarLayerGraph()
    for _ in range(rng.randrange(4, 14)):
        o = ox.NamedNode(EX + rng.choice(NODES)) if rng.random() < 0.65 else ox.Literal(str(rng.randrange(1, 4)), datatype=INTEGER)
        g.add((ox.NamedNode(EX + rng.choice(NODES)), ox.NamedNode(EX + rng.choice(PREDICATES)), o))
    return g


def _run(ruleset, graph, monkeypatch, plain: bool):
    with monkeypatch.context() as m:
        if plain:
            m.setattr(srl_eval, "_store_plan", lambda rule: None)
            m.setattr(srl_eval, "_closure_of", lambda rules, positions: None)
        try:
            return ruleset.infer(graph)
        except Exception as error:  # noqa: BLE001  (the two ways must fail the same way too)
            return type(error).__name__


@pytest.mark.parametrize("seed", range(SEEDS))
def test_the_fast_paths_give_what_the_plain_evaluation_gives(seed, monkeypatch):
    rng = random.Random(seed)
    try:
        text = "PREFIX : <http://e/>\n" + "\n".join(_rule(rng) for _ in range(rng.choice([1, 2, 2, 3])))
        ruleset = srl.parse_ruleset(text)
        ruleset.plan()
    except Exception:  # noqa: BLE001  (not a well-formed or stratifiable rule set: nothing to compare)
        pytest.skip("not a valid rule set")
    for k in range(3):
        graph = _graph(random.Random(seed * 3 + k))
        fast, plain = _run(ruleset, graph, monkeypatch, False), _run(ruleset, graph, monkeypatch, True)
        if isinstance(fast, str) or isinstance(plain, str):
            assert fast == plain, text
        else:
            assert len(fast) == len(plain) and isomorphic(fast, plain), f"{text}\n{sorted(map(str, fast))}\n{sorted(map(str, plain))}"
