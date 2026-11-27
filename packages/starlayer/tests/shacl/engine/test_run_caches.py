"""What the shapes graph says is read once for a run, not once for each node: the members of the lists of ``sh:and`` / ``sh:or`` / ``sh:xone``, and the
object that words terms for messages."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlayer.errors import ShapeError
from starlayer.graph import StarLayerGraph
from starlayer.shacl.engine.api import validate
from starlayer.shacl.engine.components import core_shape_based
from starlayer.shacl.engine.components.registry import words

PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
SHAPES = (
    "ex:A a sh:NodeShape ; sh:property [ sh:path ex:a ; sh:minCount 1 ] . ex:B a sh:NodeShape ; sh:property [ sh:path ex:b ; sh:minCount 1 ] . "
    "ex:Or a sh:NodeShape ; sh:targetClass ex:C ; sh:or ( ex:A ex:B ) . ex:Xone a sh:NodeShape ; sh:targetClass ex:C ; sh:xone ( ex:A ex:B ) . "
    "ex:And a sh:NodeShape ; sh:targetClass ex:C ; sh:and ( ex:A ex:B ) ."
)


def graph(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PFX + ttl, format="turtle")
    return g


def nodes(n: int) -> StarLayerGraph:
    return graph(" ".join(f"ex:n{i} a ex:C" + (" ; ex:a 1" if i % 2 else "") + (" ; ex:b 1" if i % 3 == 0 else "") + " ." for i in range(n)))


@pytest.fixture
def lists_read(monkeypatch) -> list:
    seen: list = []
    original = core_shape_based.shacl_list
    monkeypatch.setattr(core_shape_based, "shacl_list", lambda g, head: seen.append(head) or original(g, head))
    return seen


def test_a_list_is_read_from_the_shapes_graph_once_for_a_run_whatever_the_number_of_nodes(lists_read) -> None:
    s = graph(SHAPES)
    validate(nodes(4), s)
    few = len(lists_read)
    lists_read.clear()
    validate(nodes(60), s)
    assert len(lists_read) == few and few > 0
    assert few == 3  # (one read for each of the three lists, whatever the nodes)


def test_the_results_with_the_lists_cached_are_the_same_for_each_node() -> None:
    results = validate(nodes(30), graph(SHAPES)).results
    by_shape = {}
    for r in results:
        by_shape.setdefault(r.shape.value.rsplit("/", 1)[-1], set()).add(r.focus.value.rsplit("/", 1)[-1])
    # n_i has ex:a when i is odd and ex:b when i is a multiple of 3
    has_a = {f"n{i}" for i in range(30) if i % 2}
    has_b = {f"n{i}" for i in range(30) if i % 3 == 0}
    everyone = {f"n{i}" for i in range(30)}
    assert by_shape["Or"] == everyone - (has_a | has_b)
    assert by_shape["Xone"] == everyone - (has_a ^ has_b)
    assert by_shape["And"] == everyone - (has_a & has_b)


def test_a_malformed_list_still_fails_as_it_did() -> None:
    s = graph("ex:A a sh:NodeShape . ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:or _:l . _:l <http://www.w3.org/1999/02/22-rdf-syntax-ns#first> ex:A .")
    with pytest.raises(ShapeError) as error:
        validate(nodes(3), s)
    assert error.value.kind == "compile" and "malformed list" in str(error.value)


def test_the_words_of_a_run_are_made_once() -> None:
    g = graph("")
    ctx = SimpleNamespace(cache={}, data=g, shapes=g)
    assert words(ctx) is words(ctx)
    other = SimpleNamespace(cache={}, data=g, shapes=g)
    assert words(other) is not words(ctx)
