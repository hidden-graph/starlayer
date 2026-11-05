"""Bug-hunt reproducers for ``oxgraph/pretty.py``. Each test is a minimal case of a bug that was confirmed and fixed; they stay as regression tests."""

from __future__ import annotations

import random

import pyoxigraph as ox
import pytest
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.graph.oxgraph.pretty import pretty_trig

D = ox.DefaultGraph()
N = ox.NamedNode


@pytest.mark.parametrize("rest", [":a", "a_b:c", "é:x"])
def test_relative_iri_with_colon_in_first_segment_reparses(rest: str) -> None:
    iri = N("http://e/" + rest)
    quads = [ox.Quad(iri, N("http://e/p"), iri, D)]
    out = pretty_trig(quads, base_iri="http://e/")
    back = list(ox.parse(out.encode(), format=ox.RdfFormat.TRIG))
    assert set(back) == set(quads)


def test_pretty_honours_rdf_version_1_1() -> None:
    g = StarLayerGraph()
    g.add((N("http://e/s"), N("http://e/p"), ox.Triple(N("http://e/a"), N("http://e/b"), N("http://e/c"))))
    out = g.serialize(format="turtle", pretty=True, rdf_version="1.1")
    assert "<<" not in out and "@version" not in out


def test_output_independent_of_input_order_for_long_shared_chains() -> None:
    p, q, s = N("http://e/p"), N("http://e/q"), N("http://e/s")
    quads = []
    for k, tail in enumerate(["x", "y"]):  # two chains of 4 shared blank nodes, told apart only at the far end
        ids = [ox.BlankNode(f"c{k}_{i}") for i in range(4)]
        for a, b in zip(ids, ids[1:], strict=False):
            quads += [ox.Quad(a, p, b, D), ox.Quad(a, q, b, D)]
        quads += [ox.Quad(ids[-1], p, ox.Literal(tail), D), ox.Quad(s, p, ids[0], D)]
    outs = set()
    for seed in range(20):
        shuffled = list(quads)
        random.Random(seed).shuffle(shuffled)
        outs.add(pretty_trig(shuffled))
    assert len(outs) == 1
