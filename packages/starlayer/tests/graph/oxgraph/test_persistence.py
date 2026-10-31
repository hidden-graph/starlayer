"""Persistence round trip on a temporary RocksDB path."""

from __future__ import annotations

import pyoxigraph as ox
from starlayer.graph.oxgraph import OxDataset, OxGraph

TTL = "@prefix ex: <http://example.org/> . ex:a ex:p ex:b , 'x'@en , 42 ; ex:q <<( ex:a ex:p ex:b )>> ."


def test_round_trip_through_a_reopened_store(tmp_path):
    path = tmp_path / "rocks"
    ds = OxDataset(path=str(path))
    ds.parse(data=TTL)
    ds.graph("http://example.org/g").parse(data=TTL)
    ds.update("INSERT DATA { <http://example.org/z> <http://example.org/p> 1 }")
    want = set(ds.quads())
    n = len(want)
    assert n > 0
    ds.store.flush()
    del ds  # RocksDB allows one writer per path: release before reopening

    again = OxDataset(path=str(path))
    assert set(again.quads()) == want
    assert len(again.graph("http://example.org/g")) == 4
    assert again.query("ASK { <http://example.org/z> ?p ?o }").askAnswer is True
    again.graph("http://example.org/g").clear()
    again.store.flush()
    del again

    third = OxGraph(path=str(path))
    assert len(third) == 5  # the default graph only: four from TTL plus z
    assert list(OxDataset(store=third.store).graph_names()) in ([], [ox.NamedNode("http://example.org/g")])


def test_path_accepts_pathlike(tmp_path):
    ds = OxDataset(path=tmp_path / "x")
    ds.parse(data=TTL)
    assert len(ds) > 0
