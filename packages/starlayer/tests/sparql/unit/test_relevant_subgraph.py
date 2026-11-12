"""``relevant_subgraph``: the query gives the same answer on the subgraph as on the whole graph.

The property is checked on hand-written cases (each construct the support queries handle, and each they fall back on) and on
randomly generated queries over random small graphs: monotone patterns, ``OPTIONAL``, ``UNION``, ``FILTER``, ``FILTER NOT
EXISTS`` and ``MINUS``, aggregates, ``ORDER BY`` with ``LIMIT``. ``STARLAYER_FUZZ_EXAMPLES`` sets the number of random examples.
"""

from __future__ import annotations

import os

import pyoxigraph as ox
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.sparql.relevant import relevant_subgraph, relevant_triples

PROLOGUE = "PREFIX : <http://e/> "


def _graph(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data="@prefix : <http://e/> . " + ttl, format="turtle")
    return g


def _answer(graph: StarLayerGraph, query: str, bindings: dict | None = None):
    result = graph.query(query, initBindings=bindings or {})
    if isinstance(result, bool):
        return result
    if hasattr(result, "boolean") and result.boolean is not None:
        return result.boolean
    return sorted(repr(row) for row in result)


def _same_answer(graph: StarLayerGraph, query: str, bindings: dict | None = None) -> StarLayerGraph:
    fragment = relevant_subgraph(graph, query, bindings)
    assert set(fragment) <= set(graph), "the subgraph holds a triple that is not in the graph"
    assert _answer(fragment, query, bindings) == _answer(graph, query, bindings), f"{query}\n{sorted(map(str, fragment))}"
    return fragment


DATA = _graph(
    """
    :a :p 1, 2 ; :q :b ; :n "x" . :b :p 5 ; :blk :a ; :q :c . :c :p 7 ; :n "y" . :d :r :a .
    """
)

EXACT = {
    "join": "SELECT ?s ?o WHERE { ?s :p ?o . ?s :q ?t }",
    "filter": "SELECT ?s ?o WHERE { ?s :p ?o FILTER(?o > 1) }",
    "optional": "SELECT ?s ?o ?n WHERE { ?s :p ?o OPTIONAL { ?s :n ?n } }",
    "union": "SELECT ?s WHERE { { ?s :n ?x } UNION { ?s :blk ?y } }",
    "not exists": "SELECT ?s WHERE { ?s :p ?o FILTER NOT EXISTS { ?s :n ?z } }",
    "exists": "SELECT ?s WHERE { ?s :p ?o FILTER EXISTS { ?s :n ?z } }",
    "minus": "SELECT ?s WHERE { ?s :p ?o MINUS { ?s :q ?w } }",
    "aggregate": "SELECT ?s (COUNT(?o) AS ?c) WHERE { ?s :p ?o } GROUP BY ?s",
    "aggregate with not exists": "SELECT (COUNT(?s) AS ?c) WHERE { ?s :p ?o FILTER NOT EXISTS { ?s :n ?z } }",
    "order and limit": "SELECT ?s ?o WHERE { ?s :p ?o } ORDER BY DESC(?o) ?s LIMIT 2",
    "ask true": "ASK { ?s :p ?o . ?s :q ?t }",
    "ask false": "ASK { ?s :p 99 }",
    "construct": "CONSTRUCT { ?s :seen ?o } WHERE { ?s :p ?o }",
    "bind and values": "SELECT ?s ?x WHERE { VALUES ?s { :a :b } ?s :p ?o BIND(?o + 1 AS ?x) }",
    "variable predicate": "SELECT ?p ?o WHERE { :a ?p ?o }",
    "property path": "SELECT ?s ?o WHERE { ?s :q+ ?o }",
    "sequence path": "ASK { ?s :p/:q ?o }",
    "two not exists": "SELECT ?s WHERE { ?s :p ?o FILTER NOT EXISTS { ?s :n ?z } FILTER NOT EXISTS { ?s :blk ?w } }",
    "not exists in a union branch": "SELECT ?s WHERE { { ?s :p ?o FILTER NOT EXISTS { ?s :n ?z } } UNION { ?s :blk ?y } }",
}

FALLBACK = {
    "sub-select": "SELECT ?s WHERE { { SELECT ?s WHERE { ?s :p ?o } } ?s :q ?t }",
    "not exists inside optional": "SELECT ?s ?n WHERE { ?s :p ?o OPTIONAL { ?s :n ?n FILTER NOT EXISTS { ?s :blk ?w } } }",
    "blank node in a pattern": "SELECT ?s WHERE { ?s :q _:x . _:x :p ?o }",
    "anonymous node": "SELECT ?s WHERE { ?s :q [ :p ?o ] }",
}


def _exact(graph: StarLayerGraph, query: str) -> bool:
    return relevant_triples(graph, PROLOGUE + query, {}, lambda text: graph.query(text))[1]


@pytest.mark.parametrize("name", EXACT)
def test_the_answer_is_the_same_on_the_subgraph_and_the_support_queries_are_used(name: str) -> None:
    query = PROLOGUE + EXACT[name]
    _same_answer(DATA, query)
    assert _exact(DATA, EXACT[name])


@pytest.mark.parametrize("name", FALLBACK)
def test_a_construct_the_support_queries_cannot_follow_falls_back_and_stays_correct(name: str) -> None:
    query = PROLOGUE + FALLBACK[name]
    _same_answer(DATA, query)
    assert not _exact(DATA, FALLBACK[name])


def test_the_subgraph_is_smaller_than_the_graph_when_the_query_reads_little() -> None:
    fragment = _same_answer(DATA, PROLOGUE + "SELECT ?o WHERE { :a :p ?o }")
    assert set(fragment) == {t for t in DATA if t[0] == ox.NamedNode("http://e/a") and t[1] == ox.NamedNode("http://e/p")}


def test_not_exists_keeps_the_triple_that_excludes_the_solution() -> None:
    query = PROLOGUE + "SELECT ?s WHERE { ?s :p ?o FILTER NOT EXISTS { ?s :n ?z } }"
    fragment = _same_answer(DATA, query)
    assert (ox.NamedNode("http://e/a"), ox.NamedNode("http://e/n"), ox.Literal("x")) in set(fragment)


def test_prebound_variables_apply() -> None:
    query = PROLOGUE + "SELECT ?o WHERE { ?s :p ?o }"
    bindings = {"s": ox.NamedNode("http://e/b")}
    fragment = _same_answer(DATA, query, bindings)
    assert {t[0] for t in fragment} == {ox.NamedNode("http://e/b")}


def test_init_ns_declares_prefixes_and_the_public_name_is_exported() -> None:
    from starlayer.sparql import relevant_subgraph as exported

    fragment = exported(DATA, "SELECT ?o WHERE { :a :p ?o }", init_ns={"": "http://e/"})
    assert len(fragment) == 2


def test_an_update_is_refused() -> None:
    with pytest.raises(ValueError):
        relevant_subgraph(DATA, PROLOGUE + "DESCRIBE :a")


# ------------------------------------------------------------------------------------------ random queries, random graphs
_NODES = [":n0", ":n1", ":n2"]
_PREDS = [":p", ":q", ":r"]
_OBJECTS = _NODES + ["1", "2", "3"]
_VARS = ["?a", "?b", "?c"]


@st.composite
def _graph_ttl(draw) -> str:
    triples = draw(
        st.lists(
            st.tuples(st.sampled_from(_NODES), st.sampled_from(_PREDS), st.sampled_from(_OBJECTS)),
            min_size=0,
            max_size=14,
        )
    )
    return " ".join(f"{s} {p} {o} ." for s, p, o in triples)


@st.composite
def _pattern(draw) -> str:
    s = draw(st.sampled_from(_VARS + _NODES))
    p = draw(st.sampled_from(_PREDS + ["?p"]))
    o = draw(st.sampled_from(_VARS + _OBJECTS))
    return f"{s} {p} {o} ."


@st.composite
def _group(draw, allow_negation: bool = True) -> str:
    parts = draw(st.lists(_pattern(), min_size=1, max_size=3))
    extras = []
    if draw(st.booleans()):
        extras.append("OPTIONAL { " + draw(_pattern()) + " }")
    if draw(st.booleans()):
        extras.append("{ " + draw(_pattern()) + " } UNION { " + draw(_pattern()) + " }")
    if draw(st.booleans()):
        extras.append(f"FILTER({draw(st.sampled_from(_VARS))} != {draw(st.sampled_from(_NODES + ['1', '2']))})")
    if allow_negation and draw(st.booleans()):
        extras.append("FILTER NOT EXISTS { " + draw(_pattern()) + " }")
    if allow_negation and draw(st.booleans()):
        extras.append("FILTER EXISTS { " + draw(_pattern()) + " }")
    if allow_negation and draw(st.booleans()):
        extras.append("MINUS { " + draw(_pattern()) + " }")
    return " ".join(parts + extras)


@st.composite
def _query(draw) -> str:
    group = draw(_group())
    shape = draw(st.sampled_from(["select", "distinct", "count", "group", "ask", "order"]))
    if shape == "ask":
        return f"ASK {{ {group} }}"
    if shape == "count":
        return f"SELECT (COUNT(*) AS ?n) WHERE {{ {group} }}"
    if shape == "group":
        return f"SELECT ?a (COUNT(*) AS ?n) WHERE {{ {group} }} GROUP BY ?a"
    if shape == "order":
        return f"SELECT ?a ?b ?c WHERE {{ {group} }} ORDER BY ?a ?b ?c LIMIT {draw(st.integers(1, 4))}"
    return f"SELECT {'DISTINCT ' if shape == 'distinct' else ''}* WHERE {{ {group} }}"


_EXAMPLES = int(os.environ.get("STARLAYER_FUZZ_EXAMPLES", "200"))


@settings(
    max_examples=_EXAMPLES,
    deadline=None,
    suppress_health_check=list(HealthCheck),
    derandomize=os.environ.get("STARLAYER_FUZZ_SEED", "") == "ci",
)
@given(_graph_ttl(), _query())
def test_random_queries_give_the_same_answer_on_the_subgraph(ttl: str, query: str) -> None:
    graph = _graph(ttl)
    _same_answer(graph, PROLOGUE + query)
