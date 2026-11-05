"""A ``default_union`` dataset's SPARQL sees the union as a set: a triple held by several graphs counts once.

Oxigraph itself counts it once per graph (docs/working/oxigraph-upstream-issues.md section 5); ``oxgraph/union.py`` fixes that.
"""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph.oxgraph import StarLayerDataset

EX = "http://example.org/"
P, Q = f"<{EX}p>", f"<{EX}q>"


def _ds(copies: int, union: bool = True) -> StarLayerDataset:
    """One triple ``a p 5`` in ``copies`` places (0: absent; the default graph, then named graphs), plus ``b p 7`` once and ``a q b``."""
    ds = StarLayerDataset(default_union=union)
    places = [None, f"{EX}g1", f"{EX}g2"][:copies]
    for g in places:
        ds.store.add(ox.Quad(ox.NamedNode(f"{EX}a"), ox.NamedNode(f"{EX}p"), ox.Literal("5", datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer")),
                             ox.DefaultGraph() if g is None else ox.NamedNode(g)))
    ds.graph(f"{EX}g3").add((ox.NamedNode(f"{EX}b"), ox.NamedNode(f"{EX}p"), ox.Literal("7", datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer"))))
    ds.graph(f"{EX}g3").add((ox.NamedNode(f"{EX}a"), ox.NamedNode(f"{EX}q"), ox.NamedNode(f"{EX}b")))
    return ds


def _one(ds: StarLayerDataset, text: str) -> int:
    return int(next(iter(ds.query(text)))[0].value)


@pytest.mark.parametrize("copies", [0, 1, 2, 3])
class TestCountsOverTheUnion:
    def test_count_star(self, copies):
        assert _one(_ds(copies), "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }") == 2 + (copies > 0)

    def test_sum(self, copies):
        assert _one(_ds(copies), f"SELECT (SUM(?o) AS ?n) WHERE {{ ?s {P} ?o }}") == 7 + 5 * (copies > 0)

    def test_group_by(self, copies):
        rows = {str(r[0].value): int(r[1].value) for r in _ds(copies).query(f"SELECT ?s (COUNT(*) AS ?n) WHERE {{ ?s {P} ?o }} GROUP BY ?s")}
        assert rows == ({f"{EX}b": 1, f"{EX}a": 1} if copies else {f"{EX}b": 1})

    def test_select_without_distinct_has_one_row_per_triple(self, copies):
        rows = list(_ds(copies).query("SELECT ?s ?p ?o WHERE { ?s ?p ?o }"))
        assert len(rows) == 2 + (copies > 0)

    def test_ask(self, copies):
        assert _ds(copies).query(f"ASK {{ <{EX}a> {P} 5 }}").askAnswer is bool(copies)

    def test_property_path(self, copies):
        # a q b / p: reaches b's value; (p|q)+ from a reaches each node once per distinct route
        assert _one(_ds(copies), f"SELECT (COUNT(*) AS ?n) WHERE {{ <{EX}a> {Q}/{P} ?o }}") == 1
        assert _one(_ds(copies), f"SELECT (COUNT(*) AS ?n) WHERE {{ <{EX}a> ({P}|{Q}) ?o }}") == 1 + (copies > 0)
        assert _one(_ds(copies), f"SELECT (COUNT(*) AS ?n) WHERE {{ ?s ^{P} ?o }}") == 1 + (copies > 0)

    def test_sub_select(self, copies):
        text = f"SELECT (SUM(?c) AS ?n) WHERE {{ {{ SELECT ?s (COUNT(*) AS ?c) WHERE {{ ?s {P} ?o }} GROUP BY ?s }} }}"
        assert _one(_ds(copies), text) == 1 + (copies > 0)

    def test_count_graphs_are_still_the_named_graphs(self, copies):
        n = _one(_ds(copies), "SELECT (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } }")
        assert n == 2 + max(copies - 1, 0)

    def test_having(self, copies):
        rows = list(_ds(copies).query(f"SELECT ?s WHERE {{ ?s {P} ?o }} GROUP BY ?s HAVING (COUNT(*) > 1)"))
        assert rows == []


@pytest.mark.parametrize("copies", [0, 1, 2, 3])
class TestUpdateThenQuery:
    def test_insert_where_aggregate_reads_the_union_as_a_set(self, copies):
        ds = _ds(copies)
        ds.update(f"INSERT {{ <{EX}stats> <{EX}n> ?n }} WHERE {{ SELECT (COUNT(*) AS ?n) WHERE {{ ?s {P} ?o }} }}")
        want = 1 + (copies > 0)
        assert _one(ds, f"SELECT ?n WHERE {{ <{EX}stats> <{EX}n> ?n }}") == want
        assert _one(ds, "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }") == 3 + (copies > 0)  # the stats triple joins the union

    def test_a_write_after_a_query_is_seen_by_the_next_query(self, copies):
        ds = _ds(copies)
        assert _one(ds, f"SELECT (COUNT(*) AS ?n) WHERE {{ ?s {P} ?o }}") == 1 + (copies > 0)
        ds.graph(f"{EX}g1").add((ox.NamedNode(f"{EX}c"), ox.NamedNode(f"{EX}p"), ox.Literal("1")))
        ds.graph(f"{EX}g2").add((ox.NamedNode(f"{EX}c"), ox.NamedNode(f"{EX}p"), ox.Literal("1")))
        assert _one(ds, f"SELECT (COUNT(*) AS ?n) WHERE {{ ?s {P} ?o }}") == 2 + (copies > 0)
        ds.update(f"DELETE WHERE {{ GRAPH <{EX}g2> {{ <{EX}c> {P} ?o }} }}")
        assert _one(ds, f"SELECT (COUNT(*) AS ?n) WHERE {{ ?s {P} ?o }}") == 2 + (copies > 0)  # still in g1
        ds.remove((ox.NamedNode(f"{EX}c"), None, None))
        assert _one(ds, f"SELECT (COUNT(*) AS ?n) WHERE {{ ?s {P} ?o }}") == 1 + (copies > 0)

    def test_insert_with_aggregate_over_a_join(self, copies):
        ds = _ds(copies)
        ds.update(f"INSERT {{ <{EX}b> <{EX}m> ?n }} WHERE {{ <{EX}b> {P} ?o . {{ SELECT (COUNT(*) AS ?n) WHERE {{ ?s {P} ?x }} }} }}")
        assert _one(ds, f"SELECT ?o WHERE {{ <{EX}b> <{EX}m> ?o }}") == 1 + (copies > 0)


def test_the_copy_is_dropped_when_a_write_goes_through_another_wrapper():
    ds = _ds(2)
    assert _one(ds, "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }") == 3
    other = StarLayerDataset(store=ds.store)  # a second wrapper over the same store
    other.graph(f"{EX}g1").add((ox.NamedNode(f"{EX}z"), ox.NamedNode(f"{EX}p"), ox.Literal("z")))
    assert _one(ds, "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }") == 4


def test_a_write_on_the_store_handed_out_by_as_store_is_seen():
    ds = _ds(2)
    assert _one(ds, "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }") == 3
    ds.as_store().add(ox.Quad(ox.NamedNode(f"{EX}z"), ox.NamedNode(f"{EX}p"), ox.Literal("z"), ox.NamedNode(f"{EX}g1")))
    assert _one(ds, "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }") == 4


def test_sparql_query_hook_also_sees_a_set():
    ds = _ds(2)
    sol = ds.sparql_query("SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }")
    assert sol.rows[0]["n"].value == "3"


def test_the_store_itself_is_not_changed_by_queries_or_updates():
    ds = _ds(3)
    before = set(ds.store)
    ds.query("SELECT * WHERE { ?s ?p ?o }")
    ds.update(f"INSERT {{ <{EX}n> <{EX}n> ?n }} WHERE {{ SELECT (COUNT(*) AS ?n) WHERE {{ ?s ?p ?o }} }}")
    after = set(ds.store)
    assert before <= after and len(after - before) == 1
    assert not any(str(g).startswith("<urn:x-starlayer") for g in ds.store.named_graphs())


class TestDefaultUnionFalseIsUnchanged:
    def test_default_graph_only(self):
        ds = _ds(2, union=False)
        # the default graph holds the copy once, the named graphs are not in the default graph
        assert _one(ds, "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }") == 1
        assert _one(ds, "SELECT (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } }") == 3
        assert ds._overlap._stamp is None  # the deduplication is never consulted
