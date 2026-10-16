"""
tests/graph/unit/test_default_representation.py

Coverage for set_default_representation()/get_default_representation() - a
process-global (store factory, representation) pair StarLayerGraph()/
StarLayerDataset() pick up when constructed with no explicit store=/
backend= of their own. See starlayer_graph.py's own module-level docstring
for the full rationale (why "representation", not "backend"; why a plain
global rather than a context-manager-scoped one, on explicit user
instruction).

Every test here resets the global default in a finally block (or via the
autouse fixture below) - this is a real, unscoped process global by design,
so leaking it between tests would make unrelated tests fail depending on
run order.
"""

import pytest
from rdflib.plugins.stores.memory import Memory
from starlayer.graph import (
    Namespace,
    StarLayerDataset,
    StarLayerGraph,
    TripleTerm,
    embedded_oxigraph_store,
    get_default_representation,
    set_default_representation,
)

EX = Namespace("http://example.org/")


@pytest.fixture(autouse=True)
def _reset_default_representation():
    yield
    set_default_representation(None)


class TestNoDefaultConfigured:
    def test_bare_graph_is_ordinary_in_memory(self):
        assert get_default_representation() is None
        g = StarLayerGraph()
        assert g._is_native is False
        assert isinstance(g.store, Memory)

    def test_bare_dataset_is_ordinary_in_memory(self):
        ds = StarLayerDataset()
        assert ds._backend == "rdf-1.1"
        assert ds.default_graph._is_native is False


class TestDefaultConfigured:
    def test_bare_graph_picks_up_native_embedded_store(self):
        set_default_representation(embedded_oxigraph_store)

        g = StarLayerGraph()

        assert g._is_native is True
        g.bind("ex", EX)
        g.add_reification(EX.claim, TripleTerm(EX.bob, EX.knows, EX.carol))
        results = list(g.triples((EX.claim, None, None)))
        assert len(results) == 1
        assert isinstance(results[0][2], TripleTerm)
        g.close()

    def test_bare_dataset_picks_up_native_embedded_store(self):
        set_default_representation(embedded_oxigraph_store)

        ds = StarLayerDataset()

        assert ds._backend == "rdf-1.2"
        assert ds.default_graph._is_native is True
        ds.close()

    def test_explicit_backend_rdf11_override_is_never_overridden(self):
        set_default_representation(embedded_oxigraph_store)

        g = StarLayerGraph(backend="rdf-1.1")

        assert g._is_native is False
        assert isinstance(g.store, Memory)

    def test_explicit_matching_backend_with_no_store_still_gets_default_store(self):
        # backend='rdf-1.2' explicitly, matching the configured default,
        # but no store= given - picks up the default's store anyway
        # (otherwise this combination just fails the first time a native
        # method runs - a real, if narrow, usability improvement).
        set_default_representation(embedded_oxigraph_store)

        g = StarLayerGraph(backend="rdf-1.2")

        assert g._is_native is True
        g.add((EX.a, EX.b, EX.c))
        assert (EX.a, EX.b, EX.c) in g
        g.close()

    def test_explicit_store_overrides_the_default_entirely(self):
        set_default_representation(embedded_oxigraph_store)

        g = StarLayerGraph(store=Memory())

        assert g._is_native is False
        assert isinstance(g.store, Memory)

    def test_two_graphs_get_independent_stores_not_a_shared_one(self):
        # store_factory is called once per construction - two "new" graphs
        # must never secretly share one underlying store.
        set_default_representation(embedded_oxigraph_store)

        g1 = StarLayerGraph()
        g2 = StarLayerGraph()
        g1.add((EX.a, EX.b, EX.c))

        assert (EX.a, EX.b, EX.c) in g1
        assert (EX.a, EX.b, EX.c) not in g2
        g1.close()
        g2.close()

    def test_resetting_to_none_restores_ordinary_default(self):
        set_default_representation(embedded_oxigraph_store)
        set_default_representation(None)

        g = StarLayerGraph()

        assert g._is_native is False
        assert isinstance(g.store, Memory)
        assert get_default_representation() is None


class TestUseBaselineRepresentation:
    """use_baseline_representation=True - an escape hatch for internal,
    performance-sensitive scratch graphs (e.g. starlayer.sparql's
    query-as-RDF encoding, starlayer.shacl's TripleTermAdapter) that must
    never be influenced by a process-global set_default_representation(),
    regardless of what it's configured to. See starlayer/graph/CLAUDE.md's
    dated entry for the real catastrophic-slowdown bug this closed."""

    def test_bypasses_a_configured_default_for_starlayer_graph(self):
        set_default_representation(embedded_oxigraph_store)

        g = StarLayerGraph(use_baseline_representation=True)

        assert g._backend == "rdf-1.1"
        assert g._is_native is False
        assert isinstance(g.store, Memory)

    def test_bypasses_a_configured_default_for_starlayer_dataset(self):
        set_default_representation(embedded_oxigraph_store)

        ds = StarLayerDataset(use_baseline_representation=True)

        assert ds._backend == "rdf-1.1"
        assert ds.default_graph._is_native is False
        assert isinstance(ds.store, Memory)

    def test_works_identically_with_no_default_configured_at_all(self):
        g = StarLayerGraph(use_baseline_representation=True)
        assert g._backend == "rdf-1.1"
        assert isinstance(g.store, Memory)

    def test_exclusive_with_explicit_backend_on_graph(self):
        with pytest.raises(ValueError, match="exclusive"):
            StarLayerGraph(use_baseline_representation=True, backend="rdf-1.2")

    def test_exclusive_with_explicit_store_on_graph(self):
        with pytest.raises(ValueError, match="exclusive"):
            StarLayerGraph(use_baseline_representation=True, store=Memory())

    def test_exclusive_with_explicit_backend_on_dataset(self):
        with pytest.raises(ValueError, match="exclusive"):
            StarLayerDataset(use_baseline_representation=True, backend="rdf-1.2")

    def test_exclusive_with_explicit_store_on_dataset(self):
        with pytest.raises(ValueError, match="exclusive"):
            StarLayerDataset(use_baseline_representation=True, store=Memory())


class TestInternalScratchGraphsStayBaselineUnderAConfiguredDefault:
    """Regression coverage for the real bug this whole feature's audit
    found (2026-10-16, see starlayer/graph/CLAUDE.md's dated entry): a
    process-global native/embedded-Oxigraph default silently made
    starlayer.sparql's query-as-RDF scratch graph (query_to_rdf/
    rdf_to_query) several-thousand-times slower (each of its many small
    internal lookups paying a full SPARQL round trip instead of a Python
    dict lookup), and could have silently broken starlayer.shacl's own
    TripleTermAdapter/meta-shacl snapshot mechanisms, which exist
    specifically to escape native/remote-store limitations. Both are now
    fixed via use_baseline_representation=True at each internal call
    site - these tests confirm the fix holds, not just that the flag
    itself works in isolation (covered above)."""

    def test_query_to_rdf_scratch_graph_stays_baseline(self):
        set_default_representation(embedded_oxigraph_store)

        from starlayer.sparql import query_to_rdf
        from starlayer.sparql.parse12 import prepare_query_12

        prepared = prepare_query_12("SELECT ?s WHERE { ?s ?p ?o }")
        graph, root = query_to_rdf(prepared)

        assert graph._is_native is False
        assert isinstance(graph.store, Memory)

    def test_rdf_to_query_round_trip_stays_fast_under_a_configured_default(self):
        import time

        set_default_representation(embedded_oxigraph_store)

        from starlayer.sparql import query_to_rdf, rdf_to_query
        from starlayer.sparql.parse12 import prepare_query_12

        # A query with enough structure that the pre-fix bug (one SPARQL
        # round trip per tree-node lookup during reconstruction) would
        # have taken tens of seconds, not milliseconds, here.
        query_text = """
            SELECT * WHERE {
              { SELECT ?v { ?s ?p ?v } ORDER BY ?v OFFSET 0 LIMIT 1 }
              UNION
              { SELECT ?v { ?s ?p ?v } ORDER BY ?v OFFSET 1 LIMIT 1 }
              UNION
              { SELECT ?v { ?s ?p ?v } ORDER BY ?v OFFSET 2 LIMIT 1 }
            }
        """
        prepared = prepare_query_12(query_text)
        graph, root = query_to_rdf(prepared)

        t0 = time.time()
        rdf_to_query(graph, root)
        elapsed = time.time() - t0

        # Generous bound - a real regression here was 30+ seconds and
        # climbing, not a borderline-slow pass; anything under a second
        # confirms the fast baseline path is actually being used.
        assert elapsed < 2.0, f"rdf_to_query took {elapsed:.2f}s - the baseline-representation fix may have regressed"

    def test_shacl_triple_term_adapter_decode_graph_stays_baseline(self):
        set_default_representation(embedded_oxigraph_store)

        from starlayer.shacl.adapters import TripleTermAdapter

        adapter = TripleTermAdapter()
        decoded = adapter.decode_graph([])

        assert decoded._is_native is False
        assert isinstance(decoded.store, Memory)


class TestSetDefaultRepresentationValidation:
    def test_unsupported_representation_raises(self):
        with pytest.raises(ValueError, match="representation must be one of"):
            set_default_representation(embedded_oxigraph_store, representation="bogus")

    def test_representation_ignored_when_store_factory_is_none(self):
        # representation is meaningless when clearing the default - must
        # not raise even if left at a bogus value.
        set_default_representation(None, representation="bogus")
        assert get_default_representation() is None
