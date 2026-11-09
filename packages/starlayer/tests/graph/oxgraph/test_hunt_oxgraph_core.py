"""Regression tests for the oxgraph-core bug hunt (StarLayerGraph / StarLayerDataset wrapper)."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph import StarLayerDataset, StarLayerGraph  # noqa: F401

N = ox.NamedNode


def ex(x: str) -> ox.NamedNode:
    return N("http://ex/" + x)


def _out(ds, name="out"):
    return len(list(ds.store.quads_for_pattern(None, None, None, ex(name))))


# ---- default_union update(): prologue must not switch off the union rewrite ---------------------------------------------
@pytest.mark.parametrize(
    "prologue",
    ["PREFIX e: <http://ex/> ", 'VERSION "1.2" ', 'VERSION "1.2"\nPREFIX e: <http://ex/>\nBASE <http://ex/> ', "BASE <http://ex/> "],
)
def test_union_update_with_prologue_reads_union(prologue):
    ds = StarLayerDataset(default_union=True)
    ds.graph(ex("g1")).add((ex("a"), ex("p"), ex("b")))
    ds.update(prologue + "INSERT { GRAPH <http://ex/out> { ?s ?p ?o } } WHERE { ?s ?p ?o }")
    assert _out(ds) == 1


def test_union_update_second_operation_after_prologue():
    ds = StarLayerDataset(default_union=True)
    ds.graph(ex("g1")).add((ex("a"), ex("p"), ex("b")))
    ds.update(
        "PREFIX e: <http://ex/> INSERT { GRAPH e:out { ?s ?p ?o } } WHERE { ?s ?p ?o } ; "
        "INSERT { GRAPH <http://ex/out2> { ?s ?p ?o } } WHERE { ?s ?p ?o }"
    )
    assert _out(ds) == 1
    assert _out(ds, "out2") == 1


# ---- blank-node-named graphs are part of the union ----------------------------------------------------------------------
def test_union_update_sees_blank_node_graph():
    ds = StarLayerDataset(default_union=True)
    ds.store.add(ox.Quad(ex("a"), ex("p"), ex("b"), ox.BlankNode("g")))
    ds.update("INSERT { GRAPH <http://ex/out> { ?s ?p ?o } } WHERE { ?s ?p ?o }")
    assert _out(ds) == 1


def test_union_update_blank_graph_into_default():
    ds = StarLayerDataset(default_union=True)
    ds.graph(ox.BlankNode("g")).add((ex("a"), ex("p"), ex("b")))
    ds.update("INSERT { ?s <http://ex/q> ?o } WHERE { ?s <http://ex/p> ?o }")
    assert len(list(ds.store.quads_for_pattern(None, ex("q"), None, ox.DefaultGraph()))) == 1
    assert not [q for q in ds.store if "union-default" in str(q.graph_name)]


# ---- malformed DELETE WHERE ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["DELETE WHERE", "DELETE WHERE ?x"])
def test_union_update_malformed_delete_where_is_syntax_error(text):
    for union in (False, True):
        ds = StarLayerDataset(default_union=union)
        ds.graph(ex("g1")).add((ex("a"), ex("b"), ex("c")))
        with pytest.raises(SyntaxError):
            ds.update(text)


# ---- a query own FROM clause is honoured on a default_union dataset ----
@pytest.mark.parametrize("overlap", [False, True])
def test_query_from_clause_on_union_dataset(overlap):
    ds = StarLayerDataset()
    ds.graph("urn:g1").add((N("urn:a"), N("urn:p"), N("urn:b")))
    ds.add((N("urn:a"), N("urn:p"), N("urn:c")))
    if overlap:
        ds.graph("urn:g2").add((N("urn:a"), N("urn:p"), N("urn:b")))
    got = sorted(r[0].value for r in ds.query("SELECT ?o FROM <urn:g1> WHERE { ?s <urn:p> ?o }"))
    assert got == ["urn:b"]
    got = sorted(r[0].value for r in ds.query("PREFIX from: <urn:> SELECT ?o WHERE { ?s <urn:p> ?o }"))
    assert got == ["urn:b", "urn:c"]
