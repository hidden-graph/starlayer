"""
tests/unit/test_entailment.py

End-to-end coverage for StarLayerGraph.query(..., entailment=...) - a
per-query choice, not a graph-level setting (one graph can be queried with
different, or no, entailment on different calls). See
packages/sparql/tests/unit/test_entailment_rdfs.py for the pure "rdfs"
rewrite function's own unit coverage; this file exercises both supported
values through the real StarLayerGraph.query() path.

entailment="rdfs" rewrites the query at query time (starsparql.entailment_rdfs,
wired in via query_cache.py::prepare_query_cached) - no data copy. Covers the
full RDFS ruleset's "data" rules (subClassOf/subPropertyOf transitivity,
subclass/domain/range-driven type entailment, subproperty entailment) -
deliberately not the "vocabulary-level" rules (universal rdfs:Resource
typing, the fixed axiomatic triples) - see entailment_rdfs.py's own
module docstring for exactly what's covered and why.
entailment="owl-rl" queries a materialized RDFS/OWL-RL closure (via infer()),
cached on the graph (self._owl_rl_cache) and reused across calls according to
the separate infer= kwarg ("changed" (default) recomputes only after a real
mutation, tracked via self._mutation_generation/_on_mutated(); "always"
never reuses the cache; "cached" reuses whatever is cached no matter what,
computing only when nothing is cached yet - see TestEntailmentOwlRlCaching).

Per this project's own testing discipline (starsparql/CLAUDE.md: "any new
query/update shape needs an execution-comparison test, not just a
structural one"), several tests compare entailment="rdfs" results directly
against entailment="owl-rl" (or StarLayerGraph.infer()'s materialized
closure) - a convenient, already-tested oracle for "what should RDFS
entailment produce over this data", without needing a live owlrl call in
every test.
"""

from rdflib import RDFS

import pytest

from starlayergraph import RDF, Namespace, StarLayerGraph

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
    def test_unsupported_entailment_raises(self):
        with pytest.raises(NotImplementedError, match="rdfs"):
            _graph().query(_QUERY, entailment="owl")

    def test_rdfs_entailment_rejected_on_native_backend(self):
        g = StarLayerGraph(backend="rdf-1.2")
        with pytest.raises(NotImplementedError, match="native"):
            g.query(_QUERY, entailment="rdfs")

    def test_one_graph_answers_different_entailment_per_call(self):
        g = _graph()
        assert list(g.query(_QUERY)) == []
        assert [str(r.x) for r in g.query(_QUERY, entailment="rdfs")] == [str(EX.alice)]
        assert [str(r.x) for r in g.query(_QUERY, entailment="owl-rl")] == [str(EX.alice)]
        # plain again - not left in a rewritten/materialized state by the
        # earlier calls, since entailment is per-call, not sticky
        assert list(g.query(_QUERY)) == []


class TestQueryTimeRdfsRewrite:
    def test_plain_query_misses_the_subclass_fact(self):
        assert list(_graph().query(_QUERY)) == []

    def test_entailment_rdfs_finds_the_subclass_fact(self):
        rows = _graph().query(_QUERY, entailment="rdfs")
        assert [str(r.x) for r in rows] == [str(EX.alice)]

    def test_no_data_is_copied_or_added(self):
        g = _graph()
        before = len(g)
        list(g.query(_QUERY, entailment="rdfs"))
        assert len(g) == before == 2

    def test_repeated_call_hits_the_prepared_query_cache_and_stays_correct(self):
        g = _graph()
        first = [str(r.x) for r in g.query(_QUERY, entailment="rdfs")]
        second = [str(r.x) for r in g.query(_QUERY, entailment="rdfs")]
        assert first == second == [str(EX.alice)]

    def test_matches_infer_oracle_for_a_richer_hierarchy(self):
        g = _graph()
        g.add((EX.Employee, RDFS.subClassOf, EX.Person))
        q = "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Person }"

        rewritten = {str(r.x) for r in g.query(q, entailment="rdfs")}

        oracle = g.infer(profile="rdfs")
        materialized = {str(s) for s in oracle.subjects(RDF.type, EX.Person)}

        assert rewritten == materialized == {str(EX.alice)}

    def test_domain_entailment(self):
        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:worksAt rdfs:domain ex:Person .
            ex:alice ex:worksAt ex:Acme .
        """, format="turtle12")
        q = "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Person }"

        rewritten = {str(r.x) for r in g.query(q, entailment="rdfs")}

        oracle = g.infer(profile="rdfs")
        materialized = {str(s) for s in oracle.subjects(RDF.type, EX.Person)}

        assert rewritten == materialized == {str(EX.alice)}

    def test_range_entailment(self):
        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:worksAt rdfs:range ex:Organization .
            ex:alice ex:worksAt ex:Acme .
        """, format="turtle12")
        q = "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Organization }"

        rewritten = {str(r.x) for r in g.query(q, entailment="rdfs")}

        oracle = g.infer(profile="rdfs")
        materialized = {str(s) for s in oracle.subjects(RDF.type, EX.Organization)}

        assert rewritten == materialized == {str(EX.Acme)}

    def test_subproperty_entailment(self):
        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:hasParent rdfs:subPropertyOf ex:hasRelative .
            ex:alice ex:hasParent ex:bob .
        """, format="turtle12")
        q = "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ex:alice ex:hasRelative ?x }"

        rewritten = {str(r.x) for r in g.query(q, entailment="rdfs")}

        oracle = g.infer(profile="rdfs")
        materialized = {str(o) for o in oracle.objects(EX.alice, EX.hasRelative)}

        assert rewritten == materialized == {str(EX.bob)}


class TestEntailmentOwlRl:
    def test_no_data_is_copied_or_added_to_self(self):
        g = _graph()
        before = len(g)
        list(g.query(_QUERY, entailment="owl-rl"))
        assert len(g) == before == 2

    def test_matches_rdfs_rewrite_for_the_subclass_case(self):
        g = _graph()
        via_rewrite = [str(r.x) for r in g.query(_QUERY, entailment="rdfs")]
        via_materialization = [str(r.x) for r in g.query(_QUERY, entailment="owl-rl")]
        assert via_rewrite == via_materialization == [str(EX.alice)]

    def test_covers_owl_constructs_rdfs_rewrite_cannot(self):
        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            ex:Manager owl:equivalentClass ex:TeamLead .
            ex:alice a ex:Manager .
        """, format="turtle12")
        q = "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:TeamLead }"

        assert list(g.query(q, entailment="rdfs")) == []
        assert [str(r.x) for r in g.query(q, entailment="owl-rl")] == [str(EX.alice)]

    def test_default_infer_changed_mode_reflects_a_mutation_in_between(self):
        # the default infer="changed" mode recomputes after a real mutation
        # - no explicit "re-run reasoning" step needed after a graph edit.
        g = _graph()
        assert [str(r.x) for r in g.query(_QUERY, entailment="owl-rl")] == [str(EX.alice)]

        g.add((EX.bob, RDF.type, EX.Manager))
        rows = sorted(str(r.x) for r in g.query(_QUERY, entailment="owl-rl"))
        assert rows == [str(EX.alice), str(EX.bob)]


class TestEntailmentOwlRlCaching:
    def test_unchanged_graph_reuses_the_identical_cached_closure(self):
        g = _graph()
        list(g.query(_QUERY, entailment="owl-rl"))
        first = g._owl_rl_cache[0]
        list(g.query(_QUERY, entailment="owl-rl"))
        second = g._owl_rl_cache[0]
        assert first is second

    def test_changed_mode_recomputes_after_a_mutation(self):
        g = _graph()
        list(g.query(_QUERY, entailment="owl-rl", infer="changed"))
        first = g._owl_rl_cache[0]

        g.add((EX.bob, RDF.type, EX.Manager))
        list(g.query(_QUERY, entailment="owl-rl", infer="changed"))
        second = g._owl_rl_cache[0]

        assert first is not second

    def test_always_mode_recomputes_even_with_no_mutation(self):
        g = _graph()
        list(g.query(_QUERY, entailment="owl-rl", infer="always"))
        first = g._owl_rl_cache[0]
        list(g.query(_QUERY, entailment="owl-rl", infer="always"))
        second = g._owl_rl_cache[0]
        assert first is not second

    def test_cached_mode_serves_stale_results_after_a_mutation(self):
        g = _graph()
        assert [str(r.x) for r in g.query(_QUERY, entailment="owl-rl", infer="cached")] == [str(EX.alice)]

        g.add((EX.bob, RDF.type, EX.Manager))
        # infer="cached" deliberately does not notice bob was added - it
        # reuses whatever is cached as long as something is cached at all
        rows = [str(r.x) for r in g.query(_QUERY, entailment="owl-rl", infer="cached")]
        assert rows == [str(EX.alice)]

    def test_cached_mode_computes_once_when_nothing_cached_yet(self):
        g = _graph()
        rows = [str(r.x) for r in g.query(_QUERY, entailment="owl-rl", infer="cached")]
        assert rows == [str(EX.alice)]
        assert g._owl_rl_cache is not None

    def test_unsupported_infer_mode_raises(self):
        g = _graph()
        with pytest.raises(ValueError, match="bogus"):
            g.query(_QUERY, entailment="owl-rl", infer="bogus")

    def test_infer_kwarg_is_ignored_without_entailment_owl_rl(self):
        # infer= is only meaningful for entailment="owl-rl" - an invalid
        # value should be silently irrelevant otherwise, not raise.
        g = _graph()
        rows = list(g.query(_QUERY, infer="bogus"))
        assert rows == []


class TestEntailmentOwlRlCorrectness:
    def test_matches_owlrl_semantics_directly(self):
        # owlrl itself as the oracle, not just infer() (which wraps it) -
        # confirms the whole query()->infer()->query() path agrees with
        # owlrl.DeductiveClosure run directly on the same data.
        owlrl = pytest.importorskip("owlrl")
        from rdflib import Graph

        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            ex:partOf a owl:TransitiveProperty .
            ex:SalesTeam ex:partOf ex:SalesDept .
            ex:SalesDept ex:partOf ex:AcmeCorp .
        """, format="turtle12")
        q = "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ex:SalesTeam ex:partOf ?x }"

        via_query = {str(r.x) for r in g.query(q, entailment="owl-rl")}

        oracle = Graph()
        for t in g:
            oracle.add(t)
        owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(oracle)
        expected = {str(o) for o in oracle.objects(EX.SalesTeam, EX.partOf)}

        assert via_query == expected == {str(EX.SalesDept), str(EX.AcmeCorp)}
