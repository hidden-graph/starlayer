"""``query()`` and ``update()`` pass Oxigraph's ``custom_functions`` and ``custom_aggregate_functions`` through."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph import ENTAILMENT, StarLayerDataset, StarLayerGraph
from tests.support.errors import raises_kind

UP = "urn:fn:upper"
JOIN = "urn:fn:join"


def _upper(term):
    return ox.Literal(term.value.upper())


class _Join:
    def __init__(self):
        self.parts = []

    def accumulate(self, term):
        self.parts.append(term.value)

    def finish(self):
        return ox.Literal("|".join(sorted(self.parts)))


def _graph(cls=StarLayerGraph):
    g = cls()
    g.parse(data='<urn:a> <urn:p> "x", "y" . <urn:b> <urn:p> "z" .', format="turtle")
    return g


@pytest.mark.parametrize("cls", [StarLayerGraph, StarLayerDataset])
def test_a_custom_function_is_called_from_the_query(cls):
    rows = _graph(cls).query(f'SELECT (<{UP}>(?o) AS ?u) WHERE {{ <urn:a> <urn:p> ?o }}', custom_functions={UP: _upper})
    assert sorted(r.u.value for r in rows) == ["X", "Y"]


def test_the_function_may_be_named_by_a_named_node():
    rows = _graph().query(f'SELECT (<{UP}>("abc") AS ?u) WHERE {{}}', custom_functions={ox.NamedNode(UP): _upper})
    assert [r.u.value for r in rows] == ["ABC"]


def test_a_custom_aggregate_is_called_from_the_query():
    rows = _graph().query(f'SELECT ?s (<{JOIN}>(?o) AS ?all) WHERE {{ ?s <urn:p> ?o }} GROUP BY ?s', custom_aggregate_functions={JOIN: _Join})
    assert {r.s.value: r.all.value for r in rows} == {"urn:a": "x|y", "urn:b": "z"}


def test_a_function_that_returns_none_leaves_the_variable_unbound():
    rows = _graph().query(f'SELECT ?u WHERE {{ BIND(<{UP}>("a") AS ?u) }}', custom_functions={UP: lambda _t: None})
    assert [r.asdict() for r in rows] == [{}]


def test_the_functions_apply_to_that_call_only():
    g = _graph()
    g.query(f'SELECT (<{UP}>("a") AS ?u) WHERE {{}}', custom_functions={UP: _upper})
    with raises_kind("query", match="not supported"):
        g.query(f'SELECT (<{UP}>("a") AS ?u) WHERE {{}}')


def test_update_can_call_a_custom_function():
    g = _graph()
    g.update(f'INSERT {{ <urn:z> <urn:p> ?v }} WHERE {{ BIND(<{UP}>("k") AS ?v) }}', custom_functions={UP: _upper})
    assert [t[2].value for t in g.triples((ox.NamedNode("urn:z"), None, None))] == ["K"]


def test_update_on_a_default_union_dataset_can_call_a_custom_function():
    d = StarLayerDataset(default_union=True)
    d.update('INSERT DATA { GRAPH <urn:g> { <urn:a> <urn:p> "x" } }')
    d.update(f'INSERT {{ GRAPH <urn:g> {{ <urn:a> <urn:q> ?v }} }} WHERE {{ <urn:a> <urn:p> ?o BIND(<{UP}>(?o) AS ?v) }}', custom_functions={UP: _upper})
    assert [t[2].value for t in d.triples((ox.NamedNode("urn:a"), ox.NamedNode("urn:q"), None))] == ["X"]


def test_the_function_reaches_a_query_run_under_an_entailment_regime():
    g = _graph()
    rows = g.query(f'SELECT (<{UP}>("a") AS ?u) WHERE {{}}', entailment=ENTAILMENT.RDFS, custom_functions={UP: _upper})
    assert [r.u.value for r in rows] == ["A"]


def test_a_pre_bound_variable_and_a_custom_function_work_together():
    g = _graph()
    rows = g.query(f'SELECT (<{UP}>(?o) AS ?u) WHERE {{ ?s <urn:p> ?o }}', initBindings={"s": ox.NamedNode("urn:b")}, custom_functions={UP: _upper})
    assert [r.u.value for r in rows] == ["Z"]


def test_something_that_is_not_callable_is_a_type_error():
    with pytest.raises(TypeError, match="callable"):
        _graph().query("ASK {}", custom_functions={UP: "not a function"})
    with pytest.raises(TypeError, match="callable"):
        _graph().update("INSERT DATA { <urn:a> <urn:p> 1 }", custom_aggregate_functions={JOIN: 3})
