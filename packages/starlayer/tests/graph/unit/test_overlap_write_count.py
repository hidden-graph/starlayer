"""The deduplicated union copy of a dataset (``union.Overlap``) follows the write count of its own store: a write to another store
does not make it scan again, a write to the same store (through any wrapper of it) does, and so does a write that names no store."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph import StarLayerDataset, StarLayerGraph
from starlayer.graph.execution import union

EX = "http://example.org/"


def _n(name: str) -> ox.NamedNode:
    return ox.NamedNode(EX + name)


@pytest.fixture
def scans(monkeypatch) -> list:
    calls: list = []
    real = union.has_overlap

    def counting(store):
        calls.append(1)
        return real(store)

    monkeypatch.setattr(union, "has_overlap", counting)
    return calls


def _overlapping_dataset() -> StarLayerDataset:
    ds = StarLayerDataset(default_union=True)
    for g in ("g1", "g2"):
        ds.add((_n("s"), _n("p"), _n("o"), _n(g)))
    return ds


def test_a_write_to_another_store_does_not_scan_again(scans):
    ds = _overlapping_dataset()
    overlap = union.Overlap()
    assert overlap.overlapping(ds.store)
    copy = overlap.store(ds.store)
    assert len(scans) == 1
    StarLayerDataset().add((_n("a"), _n("b"), _n("c"), _n("g")))
    StarLayerGraph().add((_n("a"), _n("b"), _n("c")))
    assert overlap.overlapping(ds.store)
    assert overlap.store(ds.store) is copy
    assert len(scans) == 1


def test_a_write_through_another_wrapper_of_the_same_store_scans_again(scans):
    ds = _overlapping_dataset()
    overlap = union.Overlap()
    assert overlap.overlapping(ds.store)
    copy = overlap.store(ds.store)
    StarLayerGraph(ds.as_store(), identifier=_n("g1")).remove((_n("s"), _n("p"), _n("o")))
    assert not overlap.overlapping(ds.store)
    assert len(scans) == 2
    assert overlap.store(ds.store) is ds.store
    assert copy is not ds.store


def test_a_write_that_names_no_store_scans_again(scans):
    ds = _overlapping_dataset()
    overlap = union.Overlap()
    assert overlap.overlapping(ds.store)
    ds.store.remove_graph(_n("g2"))  # a raw store reference
    union.touch()
    assert not overlap.overlapping(ds.store)
    assert len(scans) == 2
