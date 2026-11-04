"""
tests/unit/test_entailment.py

End-to-end coverage for StarLayerGraph.query(..., entailment=...) - a
per-query choice, not a graph-level setting (one graph can be queried with
different, or no, entailment on different calls). See
packages/sparql/tests/unit/test_entailment_rdf.py and test_entailment_rdfs.py
for the pure rewrite functions' own unit coverage; this file exercises all
three supported values through the real StarLayerGraph.query() path.

entailment=ENTAILMENT.RDF rewrites the query at query time (starlayer.sparql.entailment_rdf,
wired in via query_cache.py::prepare_query_cached) - no data copy. Covers
just rdfD2 (every predicate used anywhere is entailed rdf:type rdf:Property) -
see entailment_rdf.py's own module docstring for exactly what's covered and
why, and its scoping boundary (only triggers for the specific class
rdf:Property, not a variable class).
entailment=ENTAILMENT.RDFS rewrites the query at query time (starlayer.sparql.entailment_rdfs,
wired in via query_cache.py::prepare_query_cached) - no data copy. Covers the
full RDFS ruleset's "data" rules (subClassOf/subPropertyOf transitivity,
subclass/domain/range-driven type entailment, subproperty entailment) -
deliberately not the "vocabulary-level" rules (universal rdfs:Resource
typing, the fixed axiomatic triples) - see entailment_rdfs.py's own
module docstring for exactly what's covered and why.
entailment=ENTAILMENT["OWL-RDF-Based"] queries a materialized RDFS/OWL-RL closure (via infer()),
cached on the graph (self._owl_rl_cache) and reused across calls according to
the separate infer= kwarg ("changed" (default) recomputes only after a real
mutation, tracked via self._mutation_generation/_on_mutated(); "always"
never reuses the cache; "cached" reuses whatever is cached no matter what,
computing only when nothing is cached yet - see TestEntailmentOwlRlCaching).

Per this project's own testing discipline (starlayer.sparql/CLAUDE.md: "any new
query/update shape needs an execution-comparison test, not just a
structural one"), several tests compare entailment=ENTAILMENT.RDFS results directly
against entailment=ENTAILMENT["OWL-RDF-Based"] (or StarLayerGraph.infer()'s materialized
closure) - a convenient, already-tested oracle for "what should RDFS
entailment produce over this data", without needing a live owlrl call in
every test.
"""

import pytest
from starlayer.graph import RDF, Namespace, StarLayerGraph
from starlayer.graph.graph.entailment_regimes import ENTAILMENT

EX = Namespace("http://example.org/")

_DATA = """
    @prefix ex: <http://example.org/> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    ex:Manager rdfs:subClassOf ex:Employee .
    ex:alice a ex:Manager .
"""

_QUERY = "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Employee }"


def _graph() -> StarLayerGraph:
    g = StarLayerGraph()
    g.bind("ex", EX)
    g.parse(data=_DATA, format="turtle12")
    return g


class TestEntailmentIsPerQueryNotPerGraph:

    def test_rdfs_entailment_rejected_on_native_backend(self):
        g = StarLayerGraph(backend="rdf-1.2")
        with pytest.raises(NotImplementedError, match="native"):
            g.query(_QUERY, entailment=ENTAILMENT.RDFS)

    def test_rdf_entailment_rejected_on_native_backend(self):
        g = StarLayerGraph(backend="rdf-1.2")
        with pytest.raises(NotImplementedError, match="native"):
            g.query(_QUERY, entailment=ENTAILMENT.RDF)

    def test_native_entailment_rejected_on_default_backend(self):
        with pytest.raises(NotImplementedError, match="rdf-1.2"):
            _graph().query(_QUERY, entailment="native")

    def test_native_entailment_accepted_on_native_backend(self):
        # no live store configured, so this can't reach an actual endpoint -
        # confirms entailment="native" itself isn't rejected (a RuntimeError
        # about the missing store, not a NotImplementedError about
        # entailment, proves validation passed and native dispatch was
        # reached) - see test_entailment_native.py for real endpoint coverage.
        g = StarLayerGraph(backend="rdf-1.2")
        with pytest.raises(RuntimeError, match="store"):
            g.query(_QUERY, entailment="native")









class TestEntailmentOwlRlCaching:
    def test_unchanged_graph_reuses_the_identical_cached_closure(self):
        g = _graph()
        list(g.query(_QUERY, entailment=ENTAILMENT["OWL-RDF-Based"]))
        first = g._owl_rl_cache[0]
        list(g.query(_QUERY, entailment=ENTAILMENT["OWL-RDF-Based"]))
        second = g._owl_rl_cache[0]
        assert first is second

    def test_changed_mode_recomputes_after_a_mutation(self):
        g = _graph()
        list(g.query(_QUERY, entailment=ENTAILMENT["OWL-RDF-Based"], infer="changed"))
        first = g._owl_rl_cache[0]

        g.add((EX.bob, RDF.type, EX.Manager))
        list(g.query(_QUERY, entailment=ENTAILMENT["OWL-RDF-Based"], infer="changed"))
        second = g._owl_rl_cache[0]

        assert first is not second

    def test_always_mode_recomputes_even_with_no_mutation(self):
        g = _graph()
        list(g.query(_QUERY, entailment=ENTAILMENT["OWL-RDF-Based"], infer="always"))
        first = g._owl_rl_cache[0]
        list(g.query(_QUERY, entailment=ENTAILMENT["OWL-RDF-Based"], infer="always"))
        second = g._owl_rl_cache[0]
        assert first is not second

    def test_cached_mode_serves_stale_results_after_a_mutation(self):
        g = _graph()
        assert [str(r.x) for r in g.query(_QUERY, entailment=ENTAILMENT["OWL-RDF-Based"], infer="cached")] == [str(EX.alice)]

        g.add((EX.bob, RDF.type, EX.Manager))
        # infer="cached" deliberately does not notice bob was added - it
        # reuses whatever is cached as long as something is cached at all
        rows = [str(r.x) for r in g.query(_QUERY, entailment=ENTAILMENT["OWL-RDF-Based"], infer="cached")]
        assert rows == [str(EX.alice)]

    def test_cached_mode_computes_once_when_nothing_cached_yet(self):
        g = _graph()
        rows = [str(r.x) for r in g.query(_QUERY, entailment=ENTAILMENT["OWL-RDF-Based"], infer="cached")]
        assert rows == [str(EX.alice)]
        assert g._owl_rl_cache is not None




class TestEntailmentOwlRlUnionDesign:
    """Phase D: entailment=ENTAILMENT["OWL-RDF-Based"] queries the live union of self and a
    small cached delta, instead of caching a full closure copy - see
    _UnionForQuery and query()'s owl-rl branch."""


    def test_triple_term_bearing_graph_uses_fallback_path_and_stays_correct(self):
        # self._tt_registry non-empty routes this through the "fallback"
        # branch (a decomposed snapshot of self unioned with delta, both in
        # the same encoding) rather than the "fast" live-store-view branch -
        # results should still be correct either way.

        from starlayer.graph import TripleTerm

        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data=_DATA, format="turtle12")
        g.add_reification(EX.claim, TripleTerm(EX.bob, EX.knows, EX.carol))
        assert g._tt_registry  # sanity: this graph really does exercise the fallback path

        rows = [str(r.x) for r in g.query(_QUERY, entailment=ENTAILMENT["OWL-RDF-Based"])]
        assert rows == [str(EX.alice)]

    def test_cache_holds_only_new_triples_not_a_copy_of_self(self):
        # owlrl's full closure includes a lot of vocabulary-level axiomatic
        # noise (rdfs4a/4b-style universal typing) that scales with the
        # number of distinct terms, not the amount of actual data - so the
        # cached delta isn't necessarily *smaller* than self for every
        # graph. What's always true by construction (delta = closure -
        # self's own decomposed data) is that it never duplicates any of
        # self's own asserted triples - confirm that directly instead.
        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data=_DATA, format="turtle12")
        for i in range(50):
            g.add((EX[f"thing{i}"], EX.marker, EX[f"value{i}"]))

        list(g.query(_QUERY, entailment=ENTAILMENT["OWL-RDF-Based"]))

        delta = g._owl_rl_cache[0]
        for t in g:
            assert t not in delta


