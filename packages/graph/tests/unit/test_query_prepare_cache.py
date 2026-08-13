"""Regression tests for the prepared-query cache (starlayergraph.query.query_cache).

StarLayerGraph.query()/StarLayerDataset.query() used to rewrite (SPARQL 1.2 ->
1.1) and parse the query text fresh on every call, even when the same query
text is evaluated repeatedly with only initBindings differing - exactly how
pySHACL evaluates a SHACL-AF sh:construct rule or sh:sparql constraint (once
per focus node, per iteration). These tests confirm the cache actually
eliminates the redundant work, stays correct across differing
initNs/initBindings/data mutations, and doesn't change any query's result.
"""

import rdflib.plugins.sparql as _sparql_mod
import pytest
from rdflib import Namespace

from starlayergraph.graph.starlayergraph_dataset import StarLayerDataset
from starlayergraph.graph.starlayergraph_graph import StarLayerGraph

EX = Namespace("http://example.org/")
EX2 = Namespace("http://example2.org/")


@pytest.fixture
def counting_prepare_query(monkeypatch):
    """Count real calls to the actual parse+prepare entry point, patched at
    every site that could do the real work: starsparql's
    prepare_query_12 (starlayergraph.query.query_cache's own local-store path,
    the thing this cache exists to avoid redoing) and plain rdflib's own
    prepareQuery (still used by StarLayerGraph.query()'s remote-store
    fallback branch, which serializes back to text for a store that can't
    accept a prepared object - see query_cache.py's own module docstring).
    """
    calls = {"n": 0}
    from starsparql import parse12 as _parse12_mod

    original_prepare_query_12 = _parse12_mod.prepare_query_12
    original_prepareQuery = _sparql_mod.prepareQuery

    def counting_prepare_query_12(*args, **kwargs):
        calls["n"] += 1
        return original_prepare_query_12(*args, **kwargs)

    def counting_prepareQuery(*args, **kwargs):
        calls["n"] += 1
        return original_prepareQuery(*args, **kwargs)

    monkeypatch.setattr("starlayergraph.query.query_cache.prepare_query_12", counting_prepare_query_12)
    monkeypatch.setattr(_sparql_mod, "prepareQuery", counting_prepareQuery)
    return calls


def test_repeated_identical_query_parses_once(counting_prepare_query):
    g = StarLayerGraph()
    g.bind("ex", EX)
    g.add((EX.a, EX.p, EX.b))

    q = "SELECT ?o WHERE { ex:a ex:p ?o }"
    for _ in range(5):
        list(g.query(q, initNs={"ex": EX}))

    assert counting_prepare_query["n"] == 1


def test_different_query_text_parses_again(counting_prepare_query):
    g = StarLayerGraph()
    g.bind("ex", EX)
    g.add((EX.a, EX.p, EX.b))
    g.add((EX.c, EX.p, EX.d))

    list(g.query("SELECT ?o WHERE { ex:a ex:p ?o }", initNs={"ex": EX}))
    list(g.query("SELECT ?o WHERE { ex:c ex:p ?o }", initNs={"ex": EX}))

    assert counting_prepare_query["n"] == 2


def test_repeated_query_with_different_bindings_gives_correct_results():
    """The motivating pySHACL pattern: same query text, different
    initBindings per call - each call must still resolve independently and
    correctly, not accidentally share state through the cache."""
    g = StarLayerGraph()
    g.bind("ex", EX)
    g.add((EX.alice, EX.knows, EX.bob))
    g.add((EX.bob, EX.knows, EX.carol))

    q = "SELECT ?friend WHERE { ?this ex:knows ?friend }"
    for focus, expected in [(EX.alice, EX.bob), (EX.bob, EX.carol), (EX.alice, EX.bob)]:
        rows = list(g.query(q, initNs={"ex": EX}, initBindings={"this": focus}))
        assert rows == [(expected,)]


def test_different_effective_namespaces_do_not_collide(counting_prepare_query):
    """Same query text, different initNs mappings must each be parsed with
    their own prefixes - reusing a cache entry prepared for a different
    initNs would silently resolve the wrong prefix."""
    g = StarLayerGraph()
    g.bind("ex", EX)
    g.bind("ex2", EX2)
    g.add((EX.alice, EX.p, EX.first))
    g.add((EX2.alice, EX2.p, EX2.second))

    q = "SELECT ?o WHERE { ex:alice ex:p ?o }"
    rows_ex = list(g.query(q, initNs={"ex": EX}))
    assert rows_ex == [(EX.first,)]

    # Same literal query text, but "ex:" now resolves to a different
    # namespace - must not reuse the first cache entry.
    rows_ex2 = list(g.query(q, initNs={"ex": EX2}))
    assert rows_ex2 == [(EX2.second,)]
    assert counting_prepare_query["n"] == 2


def test_cache_does_not_serve_stale_data_after_mutation():
    """The cache is keyed on query text/namespaces/base, not graph content -
    confirms new triples added between two identical-query calls are still
    visible (the parsed query is reused, but it's evaluated fresh against
    current data each time, not memoized results)."""
    g = StarLayerGraph()
    g.bind("ex", EX)
    g.add((EX.a, EX.p, EX.b))

    q = "SELECT ?o WHERE { ex:a ex:p ?o }"
    first = list(g.query(q, initNs={"ex": EX}))
    assert first == [(EX.b,)]

    g.add((EX.a, EX.p, EX.c))
    second = list(g.query(q, initNs={"ex": EX}))
    assert sorted(second) == sorted([(EX.b,), (EX.c,)])


def test_construct_rule_repeated_per_focus_node_matches_pyshacl_pattern():
    """sh:construct-style repeated CONSTRUCT calls, one per focus node, same
    query text each time - the exact shape that motivated this cache."""
    g = StarLayerGraph()
    g.bind("ex", EX)
    g.add((EX.alice, EX.knows, EX.bob))
    g.add((EX.bob, EX.knows, EX.carol))

    q = "CONSTRUCT { ?this ex:metFriend ?friend } WHERE { ?this ex:knows ?friend }"
    expected = {
        EX.alice: (EX.alice, EX.metFriend, EX.bob),
        EX.bob: (EX.bob, EX.metFriend, EX.carol),
    }
    for focus, expected_triple in expected.items():
        result = g.query(q, initNs={"ex": EX}, initBindings={"this": focus})
        assert list(result.graph) == [expected_triple]


def test_triple_term_query_still_correct_with_cache():
    """A genuine SPARQL 1.2 triple-term pattern, rewritten to SPARQL 1.1 by
    the cached preparation path - confirms the rewrite (not just the parse)
    is still applied correctly when served from cache."""
    g = StarLayerGraph()
    g.bind("ex", EX)
    g.parse(data="@prefix ex: <http://example.org/> .\nex:alice ex:says <<( ex:bob ex:knows ex:carol )>> .\n", format="turtle12")

    q = "SELECT ?s ?p ?o WHERE { ex:alice ex:says <<( ?s ?p ?o )>> }"
    for _ in range(3):
        rows = list(g.query(q, initNs={"ex": EX}))
        assert rows == [(EX.bob, EX.knows, EX.carol)]


def test_dataset_repeated_query_parses_once(counting_prepare_query):
    ds = StarLayerDataset()
    ds.bind("ex", EX)
    g1 = ds.get_context(EX.g1)
    g1.add((EX.a, EX.p, EX.b))

    q = "SELECT ?o WHERE { GRAPH ex:g1 { ex:a ex:p ?o } }"
    for _ in range(4):
        list(ds.query(q, initNs={"ex": EX}))

    assert counting_prepare_query["n"] == 1


def test_dataset_query_correct_across_repeated_calls_with_bindings():
    ds = StarLayerDataset()
    ds.bind("ex", EX)
    g1 = ds.get_context(EX.g1)
    g1.add((EX.alice, EX.knows, EX.bob))
    g1.add((EX.bob, EX.knows, EX.carol))

    q = "SELECT ?friend WHERE { GRAPH ?g { ?this ex:knows ?friend } }"
    for focus, expected in [(EX.alice, EX.bob), (EX.bob, EX.carol)]:
        rows = list(ds.query(q, initNs={"ex": EX}, initBindings={"this": focus, "g": EX.g1}))
        assert rows == [(expected,)]


# ---------------------------------------------------------------------------
# store_accepts_prepared_query / SPARQLUpdateStore fallback
#
# Confirmed via real Fuseki testing (not just code reading) that
# rdflib.plugins.stores.sparqlstore.SPARQLStore/SPARQLUpdateStore - used for
# *any* remote HTTP SPARQL endpoint, not just Fuseki - hard-require a plain
# query string in their own query() method (assert isinstance(query, str)),
# raising AssertionError when handed the prepared Query object
# prepare_query_cached produces. StarLayerGraph.query() must detect this and
# fall back to a plain string for these stores; the default in-memory Memory
# store (and StarLayerDataset.query(), which always executes against its own
# always-in-memory _build_raw_execution_graph() regardless of self.store) are
# unaffected and should keep using the prepared-object optimization.
# ---------------------------------------------------------------------------


def test_store_accepts_prepared_query_false_for_sparql_update_store():
    from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore

    from starlayergraph.query.query_cache import store_accepts_prepared_query

    store = SPARQLUpdateStore(query_endpoint="http://fake.local/query", update_endpoint="http://fake.local/update")
    assert store_accepts_prepared_query(store) is False


def test_store_accepts_prepared_query_true_for_default_memory_store():
    from rdflib.plugins.stores.memory import Memory

    from starlayergraph.query.query_cache import store_accepts_prepared_query

    assert store_accepts_prepared_query(Memory()) is True


def test_starlayergraph_graph_over_sparql_update_store_falls_back_to_string(monkeypatch, counting_prepare_query):
    """A StarLayerGraph backed directly by a SPARQLUpdateStore (the rdf-1.1
    encoding path, not the native rdf-1.2 backend, which bypasses this code
    entirely) must never hand this store's own query() method a prepared
    Query object - it can't safely accept one (confirmed via real Fuseki
    testing). prepare_query_cached (the cross-call cache) is skipped
    entirely for this store type. A local, uncached prepareQuery() call
    still happens once per query() call, though - starlayergraph/query/
    remote_decompose.py needs a real algebra tree to find and strip any
    Extend that depends on a custom SPARQL function starlayergraph registers
    only in this process (TRIPLE()/SUBJECT()/etc. - see that module's
    docstring) - but its output is always translated back to a plain string
    before reaching the store.
    """
    from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore

    from starlayergraph.graph.starlayergraph_graph import StarLayerGraph

    store = SPARQLUpdateStore(query_endpoint="http://fake.local/query", update_endpoint="http://fake.local/update")
    sg = StarLayerGraph(store=store)
    sg.bind("ex", EX)

    # A real network call would hang/fail against fake.local - patch
    # Graph.query (rdflib's own base class) to capture what gets passed
    # through, without actually executing a request.
    import rdflib

    captured = {}

    def fake_graph_query(self, query_object, **kwargs):
        captured["query_object"] = query_object
        raise RuntimeError("stop before any real network call")

    monkeypatch.setattr(rdflib.Graph, "query", fake_graph_query)

    try:
        sg.query("SELECT ?o WHERE { ex:a ex:p ?o }", initNs={"ex": EX})
    except RuntimeError:
        pass

    assert isinstance(captured.get("query_object"), str)
    assert counting_prepare_query["n"] == 1
