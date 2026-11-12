"""extract_subgraph() and logical shapes: ``sh:and``, ``sh:or``, ``sh:xone``, ``sh:not`` (design rule 3, restated 2026-11-11).

A fragment says "this is the state of the graph when it validated", so it must not depend on list order: ``sh:or`` keeps every
disjunct that holds, ``sh:xone`` the holding disjunct plus the full trace of the others, ``sh:not`` the full trace of the negated
shape, ``sh:and`` every conjunct. Reordering a list gives the same fragment and the same canonical hash.
"""

from __future__ import annotations

import pyoxigraph as ox
from starlayer.graph import StarLayerGraph
from starlayer.graph.rdfc import rdfc10_hash
from starlayer.shacl import extract_subgraph, validate


class _Namespace:
    def __getattr__(self, name: str) -> ox.NamedNode:
        return ox.NamedNode(f"http://example.org/{name}")


EX = _Namespace()
PREFIXES = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .\n"
DATA = """
ex:a a ex:Person ; ex:name "A" ; ex:pet ex:rex .
ex:rex a ex:Dog ; ex:name "Rex" ; ex:colour "black" .
"""
BLACK = "[ sh:property [ sh:path ex:colour ; sh:hasValue \"black\" ] ]"
REX = "[ sh:property [ sh:path ex:name ; sh:hasValue \"Rex\" ] ]"
RED = "[ sh:property [ sh:path ex:colour ; sh:hasValue \"red\" ] ]"


def _graph(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PREFIXES + ttl, format="turtle12")
    return g


def _shapes(constraint: str) -> StarLayerGraph:
    return _graph(f"ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:pet ; {constraint} ] .")


def _fragment(constraint: str) -> set:
    shapes, data = _shapes(constraint), _graph(DATA)
    assert validate(shapes, data).conforms
    return {(s.value.rsplit("/", 1)[-1], p.value.rsplit("/", 1)[-1].rsplit("#", 1)[-1], o.value.rsplit("/", 1)[-1]) for s, p, o in extract_subgraph(data, shapes, shape=EX.S, focus_node=EX.a)}


def test_or_keeps_every_disjunct_that_holds() -> None:
    triples = _fragment(f"sh:or ( {BLACK} {REX} )")
    assert ("rex", "colour", "black") in triples and ("rex", "name", "Rex") in triples


def test_or_leaves_out_a_disjunct_that_fails() -> None:
    triples = _fragment(f"sh:or ( {RED} {REX} )")
    assert ("rex", "name", "Rex") in triples and ("rex", "colour", "black") not in triples


def test_or_gives_the_same_fragment_and_hash_in_either_order() -> None:
    shapes_a, shapes_b, data = _shapes(f"sh:or ( {BLACK} {REX} )"), _shapes(f"sh:or ( {REX} {BLACK} )"), _graph(DATA)
    a = extract_subgraph(data, shapes_a, shape=EX.S, focus_node=EX.a)
    b = extract_subgraph(data, shapes_b, shape=EX.S, focus_node=EX.a)
    assert set(a) == set(b) and rdfc10_hash(a) == rdfc10_hash(b)


def test_xone_keeps_the_holding_disjunct_and_the_full_trace_of_the_others() -> None:
    triples = _fragment(f"sh:xone ( {RED} {REX} )")
    assert ("rex", "name", "Rex") in triples, "the disjunct that holds"
    assert ("rex", "colour", "black") in triples, "what the failing disjunct read: changing it could make two hold"


def test_not_keeps_the_full_trace_of_the_negated_shape() -> None:
    triples = _fragment(f"sh:not {RED}")
    assert ("rex", "colour", "black") in triples


def test_and_keeps_every_conjunct() -> None:
    triples = _fragment(f"sh:and ( {BLACK} {REX} )")
    assert ("rex", "colour", "black") in triples and ("rex", "name", "Rex") in triples
