"""Set operations on graphs and datasets, on both families (rdflib and pyoxigraph)."""

from __future__ import annotations

import time

import pyoxigraph as ox
import pytest
from rdflib import BNode, Graph, Literal, URIRef
from starlayer.graph import setops
from starlayer.graph.oxgraph import OxDataset, OxGraph

union, intersection, difference, symmetric_difference = (
    getattr(setops, n) for n in ("union", "intersection", "difference", "symmetric_difference")
)


def TripleTerm(s, p, o):  # noqa: N802
    return ox.Triple(s, p, o)

E = "http://example.org/"


def _u(n: str) -> URIRef:
    return URIRef(E + n)


def _triples(*names: str, cls=Graph):
    g = cls()
    for n in names:
        g.add((_u(n), _u("p"), Literal(n)))
    return g


def _ox(*names: str):
    s = ox.Store()
    for n in names:
        s.add(ox.Quad(ox.NamedNode(E + n), ox.NamedNode(E + "p"), ox.Literal(n), ox.DefaultGraph()))
    return s


def _subjects(g) -> set[str]:
    if isinstance(g, ox.Store):
        return {q.subject.value.removeprefix(E) for q in g}
    return {getattr(s, "value", str(s)).removeprefix(E) for s, _, _ in g}


@pytest.fixture(params=["rdflib", "starlayer", "oxigraph"])
def make(request):
    return {"rdflib": lambda *n: _triples(*n), "starlayer": lambda *n: _triples(*n, cls=OxGraph), "oxigraph": _ox}[
        request.param
    ]


def test_the_four_operations(make) -> None:
    a, b = make("1", "2", "3"), make("3", "4")
    assert _subjects(union(a, b)) == {"1", "2", "3", "4"}
    assert _subjects(intersection(a, b)) == {"3"}
    assert _subjects(difference(a, b)) == {"1", "2"}
    assert _subjects(difference(b, a)) == {"4"}
    assert _subjects(symmetric_difference(a, b)) == {"1", "2", "4"}


def test_the_algebraic_laws(make) -> None:
    a, b = make("1", "2", "3"), make("3", "4", "5")
    assert _subjects(union(a, a)) == _subjects(a)
    assert _subjects(difference(a, a)) == set()
    assert _subjects(intersection(a, b)) <= _subjects(a) & _subjects(b)
    assert _subjects(union(difference(a, b), intersection(a, b))) == _subjects(a)
    assert _subjects(symmetric_difference(a, b)) == _subjects(union(difference(a, b), difference(b, a)))
    assert _subjects(union(a, b)) == _subjects(union(b, a))


def test_empty_operands(make) -> None:
    a, empty = make("1", "2"), make()
    assert _subjects(union(a, empty)) == {"1", "2"}
    assert _subjects(intersection(a, empty)) == set()
    assert _subjects(difference(a, empty)) == {"1", "2"}
    assert _subjects(difference(empty, a)) == set()


def test_inputs_are_not_modified(make) -> None:
    a, b = make("1", "2"), make("2", "3")
    before = (_subjects(a), _subjects(b))
    for op in (union, intersection, difference, symmetric_difference):
        op(a, b)
    assert (_subjects(a), _subjects(b)) == before


def test_result_has_the_first_operands_type(make) -> None:
    a, b = make("1"), make("2")
    assert type(union(a, b)) is type(a)


def test_into_accumulates_and_may_be_an_operand(make) -> None:
    a, b = make("1"), make("2")
    out = union(a, b, into=a)
    assert out is a and _subjects(a) == {"1", "2"} and _subjects(b) == {"2"}
    target = make("9")
    difference(make("1", "2"), make("2"), into=target)
    assert _subjects(target) == {"9", "1"}


def test_blank_nodes_compare_by_label_not_by_isomorphism() -> None:
    def one(label: str) -> Graph:
        g = Graph()
        g.add((BNode(label), _u("p"), Literal("x")))
        return g

    same_label = one("b1")
    assert len(intersection(one("b1"), same_label)) == 1
    assert len(intersection(one("b1"), one("b2"))) == 0
    assert len(difference(one("b1"), one("b2"))) == 1


def test_triple_terms_compare_by_structure() -> None:
    def tt(o: str) -> OxGraph:
        g = OxGraph()
        g.add((_u("r"), URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies"), TripleTerm(ox.NamedNode(E + "s"), ox.NamedNode(E + "p"), ox.NamedNode(E + o))))
        return g

    assert len(intersection(tt("o"), tt("o"))) == 1
    assert len(intersection(tt("o"), tt("other"))) == 0
    assert len(union(tt("o"), tt("other"))) == 2

    def oxtt(o: str) -> ox.Store:
        s = ox.Store()
        triple = ox.Triple(ox.NamedNode(E + "s"), ox.NamedNode(E + "p"), ox.NamedNode(E + o))
        s.add(ox.Quad(ox.NamedNode(E + "r"), ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies"), triple, ox.DefaultGraph()))
        return s

    assert len(list(intersection(oxtt("o"), oxtt("o")))) == 1
    assert len(list(intersection(oxtt("o"), oxtt("other")))) == 0


def test_datasets_compare_quads_with_their_graph_names() -> None:
    def ds(*graphs: str) -> OxDataset:
        d = OxDataset()
        for g in graphs:
            d.graph(_u(g)).add((_u("s"), _u("p"), Literal("x")))
        return d

    a, b = ds("g1", "g2"), ds("g2", "g3")
    assert {g.identifier.value for g in intersection(a, b).graphs() if len(g)} == {E + "g2"}
    assert {g.identifier.value for g in difference(a, b).graphs() if len(g)} == {E + "g1"}
    assert {g.identifier.value for g in union(a, b).graphs() if len(g)} == {E + "g1", E + "g2", E + "g3"}
    # no graph was created in the operands by the comparison
    assert {str(g.identifier) for g in a.graphs()} == {str(g.identifier) for g in ds("g1", "g2").graphs()}

    def oxds(*graphs: str) -> ox.Store:
        s = ox.Store()
        for g in graphs:
            s.add(ox.Quad(ox.NamedNode(E + "s"), ox.NamedNode(E + "p"), ox.Literal("x"), ox.NamedNode(E + g)))
        return s

    got = {q.graph_name.value for q in difference(oxds("g1", "g2"), oxds("g2", "g3"))}
    assert got == {E + "g1"}


def test_prefixes_of_both_rdflib_operands_are_carried() -> None:
    a, b = Graph(), Graph()
    a.bind("aa", "http://a.example/")
    b.bind("bb", "http://b.example/")
    bound = dict(union(a, b).namespaces())
    assert bound["aa"].toPython() == "http://a.example/" and bound["bb"].toPython() == "http://b.example/"


def test_mixed_families_are_refused_with_a_clear_message() -> None:
    with pytest.raises(TypeError, match="different families"):
        union(_triples("1"), _ox("1"))
    with pytest.raises(TypeError, match="not in the same family"):
        union(_triples("1"), _triples("2"), into=_ox())
    with pytest.raises(TypeError, match="rdflib Graph/Dataset or a pyoxigraph"):
        union([1], [2])


def test_large_graphs_stream() -> None:
    n = 30_000
    a = ox.Store()
    a.bulk_extend(ox.Quad(ox.NamedNode(f"{E}s{i}"), ox.NamedNode(E + "p"), ox.Literal(str(i)), ox.DefaultGraph()) for i in range(n))
    b = ox.Store()
    b.bulk_extend(ox.Quad(ox.NamedNode(f"{E}s{i}"), ox.NamedNode(E + "p"), ox.Literal(str(i)), ox.DefaultGraph()) for i in range(n // 2, n + n // 2))
    start = time.perf_counter()
    assert len(difference(a, b)) == n // 2
    assert len(intersection(a, b)) == n - n // 2
    assert len(union(a, b)) == n + n // 2
    assert time.perf_counter() - start < 20
