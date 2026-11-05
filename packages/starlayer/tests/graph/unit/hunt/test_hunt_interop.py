"""Bug-hunt reproducers for interop.py, rdfc_native.py, setops.py and the StarLayerGraph operators.

Each test was a confirmed bug; they stay as regression tests.
"""

from __future__ import annotations

import pyoxigraph as ox
from starlayer.graph import interop
from starlayer.graph.rdfc_native import canonical_hash, isomorphic

P = ox.NamedNode("http://e/p")
G = ox.DefaultGraph()


def _b(label):
    return ox.BlankNode(label)


def _three_cycle_of_triple_terms(a, b, c):
    """_:a p <<( _:b p _:c )>> . _:b p <<( _:c p _:a )>> . _:c p <<( _:a p _:b )>> ."""
    return [
        ox.Quad(_b(a), P, ox.Triple(_b(b), P, _b(c)), G),
        ox.Quad(_b(b), P, ox.Triple(_b(c), P, _b(a)), G),
        ox.Quad(_b(c), P, ox.Triple(_b(a), P, _b(b)), G),
    ]


def test_native_isomorphic_is_reflexive_on_triple_term_cycle():
    g = _three_cycle_of_triple_terms("b0", "b1", "b2")
    assert all(isomorphic(g, g) for _ in range(60))


def test_native_isomorphic_relabelled_triple_term_cycle():
    a = _three_cycle_of_triple_terms("b0", "b1", "b2")
    b = _three_cycle_of_triple_terms("z7", "z3", "z9")
    assert all(isomorphic(a, b) for _ in range(60))


def test_native_canonical_hash_without_basic_is_stable():
    g = _three_cycle_of_triple_terms("b0", "b1", "b2")
    assert len({canonical_hash(g, basic=False) for _ in range(60)}) == 1


def test_basic_encoding_path_is_stable_on_the_same_cycle():
    """Control: with the basic encoding the verdict is stable (this passes)."""
    a = _three_cycle_of_triple_terms("b0", "b1", "b2")
    b = _three_cycle_of_triple_terms("z7", "z3", "z9")
    assert all(isomorphic(a, b, basic=True) for _ in range(20))
    assert len({canonical_hash(a) for _ in range(20)} | {canonical_hash(b)}) == 1


def _nested(depth):
    o = ox.NamedNode("http://e/leaf")
    for i in range(depth):
        o = ox.Triple(ox.NamedNode(f"http://e/s{i % 3}"), P, o)
    return [ox.Quad(ox.NamedNode("http://e/a"), P, o, G)]


def test_to_basic_deeply_nested_triple_term():
    quads = _nested(1000)
    assert interop.has_triple_terms(quads)
    out = interop.to_basic(quads)
    assert not interop.has_triple_terms(out)
