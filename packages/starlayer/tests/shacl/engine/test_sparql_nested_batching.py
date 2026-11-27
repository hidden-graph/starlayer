"""A SPARQL constraint on a shape reached through ``sh:node``, ``sh:not``, ``sh:and``, ``sh:xone`` or ``sh:qualifiedValueShape`` is run once for all the value nodes the shape is asked about."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl.engine import executor
from starlayer.shacl.engine.api import validate
from starlayer.shacl.engine.executor import Context
from starlayer.shacl.engine.oxigraph_view import OxigraphGraph

PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
NO_STREET = 'sh:sparql [ sh:select "SELECT $this WHERE { FILTER NOT EXISTS { $this <http://example.org/street> ?s } }" ]'


def graph(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PFX + ttl, format="turtle")
    return g


def addresses(n: int = 12, tag: str = "a") -> str:
    return " ".join(f"ex:{tag}{i} a ex:Address" + (f" ; ex:street 'x{i}' ." if i % 4 else " .") for i in range(n))


def people(n: int = 12) -> str:
    return " ".join(f"ex:p{i} a ex:Person ; ex:address ex:a{i} ." for i in range(n))


def shapes(reference: str, extra: str = "") -> StarLayerGraph:
    return graph(f"ex:Person a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:address ; {reference} ] . ex:Addr a sh:NodeShape ; {NO_STREET} . {extra}")


@pytest.fixture
def calls(monkeypatch) -> dict:
    seen = {"single": 0, "batch": 0, "sizes": []}
    single, batch = OxigraphGraph.sparql_query, OxigraphGraph.sparql_query_batch

    def count_single(self, *args, **kwargs):
        seen["single"] += 1
        return single(self, *args, **kwargs)

    def count_batch(self, text, name, nodes, *args, **kwargs):
        seen["batch"] += 1
        seen["sizes"].append(len(nodes))
        return batch(self, text, name, nodes, *args, **kwargs)

    monkeypatch.setattr(OxigraphGraph, "sparql_query", count_single)
    monkeypatch.setattr(OxigraphGraph, "sparql_query_batch", count_batch)
    return seen


def one_by_one(monkeypatch) -> None:
    monkeypatch.setattr(executor, "_prefetch", lambda *args, **kwargs: None)


def run(reference: str, extra: str = "", n: int = 12):
    return validate(graph(people(n) + addresses(n)), shapes(reference, extra))


@pytest.mark.parametrize("reference", ["sh:node ex:Addr", "sh:qualifiedValueShape ex:Addr ; sh:qualifiedMinCount 1", "sh:and ( ex:Addr )", "sh:xone ( ex:Addr ex:Never )"])
def test_a_constraint_on_a_shape_a_value_must_conform_to_is_run_once_for_all_the_value_nodes(reference: str, calls) -> None:
    run(reference, "ex:Never a sh:NodeShape ; sh:class ex:NoSuchClass .")
    assert calls["single"] == 0 and calls["batch"] == 1 and calls["sizes"] == [12]


def test_sh_not_follows_too(calls) -> None:
    run("sh:not ex:Addr")
    assert calls["single"] == 0 and calls["sizes"] == [12]


def test_sh_or_is_not_followed_because_its_members_may_never_be_asked(calls) -> None:
    run("sh:or ( ex:Addr ex:Other )", "ex:Other a sh:NodeShape ; sh:class ex:Address .")
    assert calls["batch"] == 0


@pytest.mark.parametrize("reference", ["sh:node ex:Addr", "sh:not ex:Addr", "sh:and ( ex:Addr )", "sh:xone ( ex:Addr ex:Never )", "sh:or ( ex:Addr ex:Other )"])
def test_the_results_are_those_of_the_one_by_one_run(reference: str, monkeypatch) -> None:
    extra = "ex:Never a sh:NodeShape ; sh:class ex:NoSuchClass . ex:Other a sh:NodeShape ; sh:class ex:Address ."
    d, s = graph(people(12) + addresses(12)), shapes(reference, extra)
    batched = validate(d, s).results
    one_by_one(monkeypatch)
    assert validate(d, s).results == batched


def test_a_shape_reached_from_two_places_is_told_all_its_nodes_together(calls) -> None:
    d = graph(
        people(8) + addresses(8) + " " + " ".join(f"ex:c{i} a ex:Company ; ex:site ex:b{i} ." for i in range(5)) + " " + addresses(5, "b")
    )
    s = graph(
        f"ex:Person a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:address ; sh:node ex:Addr ] . "
        f"ex:Company a sh:NodeShape ; sh:targetClass ex:Company ; sh:property [ sh:path ex:site ; sh:node ex:Addr ] . ex:Addr a sh:NodeShape ; {NO_STREET} ."
    )
    validate(d, s)
    assert calls["single"] == 0 and calls["batch"] == 1 and calls["sizes"] == [13]


def test_a_value_shared_by_several_nodes_is_asked_about_once(calls) -> None:
    d = graph(" ".join(f"ex:p{i} a ex:Person ; ex:address ex:shared ." for i in range(6)) + " ex:shared a ex:Address ; ex:street 'x' . ex:other a ex:Address .")
    s = shapes("sh:node ex:Addr")
    validate(d, s)
    assert calls["single"] == 1 and calls["batch"] == 0  # (one distinct address: there is nothing to batch)


def test_a_shape_that_refers_to_itself_is_followed_once(calls, monkeypatch) -> None:
    d = graph(" ".join(f"ex:n{i} a ex:Tree ; ex:child ex:n{i + 1} ." for i in range(10)) + " ex:n10 a ex:Tree .")
    s = graph(f"ex:Tree a sh:NodeShape ; sh:targetClass ex:Tree ; sh:property [ sh:path ex:child ; sh:node ex:Tree ] ; {NO_STREET} .")
    batched = validate(d, s).results
    assert calls["batch"] == 1 and calls["single"] == 0
    one_by_one(monkeypatch)
    assert validate(d, s).results == batched


def test_nothing_is_read_ahead_when_no_shape_it_leads_to_can_use_it(monkeypatch) -> None:
    """The value nodes are not worked out for a reference to shapes that have nothing to batch."""
    s = graph("ex:Person a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:address ; sh:node ex:Addr ] . ex:Addr a sh:NodeShape ; sh:class ex:Address .")
    d = graph(people(12) + addresses(12))
    counted = []
    original = Context.value_nodes
    monkeypatch.setattr(Context, "value_nodes", lambda self, shape, focus: counted.append(1) or original(self, shape, focus))
    validate(d, s)
    with_read_ahead = len(counted)
    counted.clear()
    one_by_one(monkeypatch)
    validate(d, s)
    assert with_read_ahead == len(counted)


def test_a_deactivated_shape_is_not_read_ahead(calls) -> None:
    s = shapes("sh:node ex:Addr", "ex:Addr sh:deactivated true .")
    validate(graph(people(8) + addresses(8)), s)
    assert calls["batch"] == 0 and calls["single"] == 0


def test_blank_node_value_nodes_are_run_one_by_one(calls, monkeypatch) -> None:
    d = graph("ex:p1 a ex:Person ; ex:address [ a ex:Address ] . ex:p2 a ex:Person ; ex:address [ a ex:Address ; ex:street 'x' ] . ex:p3 a ex:Person ; ex:address ex:a3 . ex:p4 a ex:Person ; ex:address ex:a4 . ex:a3 a ex:Address . ex:a4 a ex:Address .")
    s = shapes("sh:node ex:Addr")
    batched = validate(d, s).results
    # (the two IRIs in a batch; each blank node alone, and the one that fails is asked a second time for the details of its failure, as before)
    assert calls["batch"] == 1 and calls["sizes"] == [2] and calls["single"] == 3
    one_by_one(monkeypatch)
    assert len(validate(d, s).results) == len(batched)
