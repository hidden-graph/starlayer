"""``p+``, ``p*`` and ``p?`` are evaluated with a visited-set search, not rdflib's recursive generators (slow parts hunt)."""

import itertools
import random

import pytest
from rdflib import Graph, URIRef
from rdflib.paths import MulPath
from starlayer import StarLayerGraph

E = "http://e/"


def _u(x):
    return URIRef(f"{E}{x}")


def _chain(n):
    g = StarLayerGraph()
    for i in range(n):
        g.add((_u(f"n{i}"), _u("next"), _u(f"n{i + 1}")))
    return g


def _count(g, where):
    return int(list(g.query(f"SELECT (COUNT(*) AS ?c) WHERE {{ {where} }}"))[0][0])


@pytest.mark.parametrize("hops", [3000])
def test_a_long_chain_does_not_overflow_the_stack(hops):
    g = _chain(hops)
    assert _count(g, f"<{E}n0> <{E}next>+ ?x") == hops
    assert _count(g, f"<{E}n0> <{E}next>* ?x") == hops + 1
    assert _count(g, f"?x <{E}next>+ <{E}n{hops}>") == hops
    assert _count(g, f"?x <{E}next>* <{E}n{hops}>") == hops + 1
    assert _count(g, f"<{E}n0> <{E}next>? ?x") == 2


def _closure(edges, nodes, more):
    """The reachable pairs by naive fixed point: one or more steps (``more``), or exactly one."""
    reach = set(edges)
    while more:
        grown = reach | {(a, d) for (a, b) in reach for (c, d) in edges if b == c}
        if grown == reach:
            break
        reach = grown
    return reach


@pytest.mark.parametrize("modifier", ["*", "+", "?"])
def test_pairs_match_a_naive_closure_on_random_graphs_with_cycles(modifier):
    rng = random.Random(11)
    for _ in range(40):
        n = rng.randint(2, 8)
        g = Graph()
        edges = {(rng.randrange(n), rng.randrange(n)) for _ in range(rng.randint(0, 2 * n))}
        for a, b in edges:
            g.add((_u(a), _u("p"), _u(b)))
        path = MulPath(_u("p"), modifier)
        pairs = _closure(edges, range(n), more=modifier != "?")
        nodes = {x for e in edges for x in e}
        if modifier != "+":
            pairs |= {(x, x) for x in nodes}
        for subj, obj in itertools.product([None, 0, n - 1], repeat=2):
            got = {(int(str(s)[len(E):]), int(str(o)[len(E):])) for s, o in path.eval(g, None if subj is None else _u(subj), None if obj is None else _u(obj))}
            want = {(a, b) for (a, b) in pairs if (subj is None or a == subj) and (obj is None or b == obj)}
            if modifier != "+" and subj is not None and (subj not in nodes) and (obj is None or obj == subj):
                want.add((subj, subj))  # a zero-length match for a bound node that is not in the graph
            if modifier != "+" and obj is not None and subj is None and obj not in nodes:
                want.add((obj, obj))
            assert got == want, (modifier, subj, obj, edges)
