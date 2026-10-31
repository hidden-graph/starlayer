"""Issue 43: a group FILTER whose expression is a falsy literal (false, 0, "") was dropped by rdflib's group translation,
so the group matched as if it had no filter (docs/upstream-issues/rdflib-upstream-issues.md)."""

from __future__ import annotations

import pytest
from rdflib import Graph
from starlayer.graph.graph.starlayer_graph import StarLayerGraph

DATA = "<http://e/a> <http://e/p> <http://e/b> ."


def _graph(cls):
    g = cls()
    g.parse(data=DATA, format="turtle")
    return g


@pytest.mark.parametrize("cls", [Graph, StarLayerGraph])
@pytest.mark.parametrize(
    ("query", "rows"),
    [
        ("SELECT * { ?s ?p ?o FILTER(false) }", 0),
        ("SELECT * { ?s ?p ?o FILTER(0) }", 0),
        ('SELECT * { ?s ?p ?o FILTER("") }', 0),
        ("SELECT * { ?s ?p ?o FILTER(true) }", 1),
        ("SELECT * { ?s ?p ?o FILTER(1) }", 1),
        ("SELECT * { { FILTER(false) } UNION { ?s ?p ?o } }", 1),
        ("SELECT * { ?s ?p ?o FILTER(false) FILTER(true) }", 0),
        ("SELECT * { ?s ?p ?o OPTIONAL { ?o ?q ?r FILTER(false) } }", 1),
    ],
)
def test_select_with_a_literal_filter(cls, query: str, rows: int) -> None:
    assert len(list(_graph(cls).query(query))) == rows


@pytest.mark.parametrize("cls", [Graph, StarLayerGraph])
def test_ask_with_filter_false_is_false(cls) -> None:
    assert _graph(cls).query("ASK { FILTER(false) }").askAnswer is False
    assert _graph(cls).query("ASK { FILTER(true) }").askAnswer is True


def test_the_patch_is_idempotent() -> None:
    from starlayer.graph.query.algebra_translator_patches import (
        patch_group_filter_falsy_literal,
    )

    assert patch_group_filter_falsy_literal() is True
    assert patch_group_filter_falsy_literal() is True
