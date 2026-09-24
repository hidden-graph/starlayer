"""
tests/unit/test_entailment.py

End-to-end coverage for StarLayerGraph.query(..., entailment=...) - a
per-query choice, not a graph-level setting (one graph can be queried with
different, or no, entailment on different calls). See
packages/sparql/tests/unit/test_entailment_rdf.py and test_entailment_rdfs.py
for the pure rewrite functions' own unit coverage; this file exercises all
three supported values through the real StarLayerGraph.query() path.

entailment="rdf" rewrites the query at query time (starsparql.entailment_rdf,
wired in via query_cache.py::prepare_query_cached) - no data copy. Covers
just rdfD2 (every predicate used anywhere is entailed rdf:type rdf:Property) -
see entailment_rdf.py's own module docstring for exactly what's covered and
why, and its scoping boundary (only triggers for the specific class
rdf:Property, not a variable class).
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

    def test_rdf_entailment_rejected_on_native_backend(self):
        g = StarLayerGraph(backend="rdf-1.2")
        with pytest.raises(NotImplementedError, match="native"):
            g.query(_QUERY, entailment="rdf")

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


class TestQueryTimeRdfEntailment:
    """entailment="rdf" - the SPARQL spec's RDF Entailment regime (one step
    weaker than RDFS): rdfD2 only, "every predicate used anywhere is
    entailed rdf:type rdf:Property" - see starsparql.entailment_rdf's own
    module docstring for the full scope and why. Pure unit coverage of the
    rewrite itself lives in packages/sparql/tests/unit/test_entailment_rdf.py;
    this class exercises it through the real StarLayerGraph.query() path.
    """

    def test_plain_query_misses_the_fact(self):
        g = _graph()
        q = "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> SELECT ?p WHERE { ?p a rdf:Property }"
        assert list(g.query(q)) == []

    def test_entailment_rdf_finds_predicates_used_in_the_graph(self):
        g = _graph()
        q = "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> SELECT ?p WHERE { ?p a rdf:Property }"
        rows = {str(r.p) for r in g.query(q, entailment="rdf")}
        # _DATA uses rdfs:subClassOf and rdf:type (via "a") as predicates
        assert rows == {str(RDFS.subClassOf), str(RDF.type)}

    def test_no_data_is_copied_or_added(self):
        g = _graph()
        before = len(g)
        q = "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> SELECT ?p WHERE { ?p a rdf:Property }"
        list(g.query(q, entailment="rdf"))
        assert len(g) == before

    def test_variable_class_query_is_not_rewritten(self):
        # rdfD2 only fires for the specific, bound class rdf:Property - a
        # generic ?p a ?c query is untouched (see entailment_rdf.py's own
        # module docstring for why this boundary exists).
        g = _graph()
        q = "SELECT ?x ?c WHERE { ?x a ?c }"
        plain = {(str(r.x), str(r.c)) for r in g.query(q)}
        rewritten = {(str(r.x), str(r.c)) for r in g.query(q, entailment="rdf")}
        assert plain == rewritten == {(str(EX.alice), str(EX.Manager))}


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


class TestEntailmentOwlRlUnionDesign:
    """Phase D: entailment="owl-rl" queries the live union of self and a
    small cached delta, instead of caching a full closure copy - see
    _UnionForQuery and query()'s owl-rl branch."""

    def test_property_path_query_has_no_duplicate_rows(self):
        # Regression test for a real, deterministic bug in plain rdflib's
        # ReadOnlyGraphAggregate: it evaluates a property-path predicate by
        # calling p.eval() once per *member* graph rather than once against
        # the union as a whole, doubling every path-matched result for a
        # 2-member aggregate (see _UnionForQuery's own docstring). Compare
        # against a flattened oracle (self ∪ delta merged into one plain
        # Graph, same query run normally) so this pins row-for-row parity,
        # not just the result set.
        from rdflib import Graph

        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:A rdfs:subClassOf ex:B .
            ex:B rdfs:subClassOf ex:C .
        """, format="turtle12")
        q = "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> SELECT ?x ?y WHERE { ?x rdfs:subClassOf+ ?y }"

        via_union = sorted((str(r.x), str(r.y)) for r in g.query(q, entailment="owl-rl"))

        closure = g.infer(profile="owl-rl")
        oracle = Graph()
        for t in closure:
            oracle.add(t)
        via_flattened = sorted(
            (str(x), str(y)) for x, y in oracle.query(q)
        )

        assert via_union == via_flattened
        assert len(via_union) == len(set(via_union))

    def test_triple_term_bearing_graph_uses_fallback_path_and_stays_correct(self):
        # self._tt_registry non-empty routes this through the "fallback"
        # branch (a decomposed snapshot of self unioned with delta, both in
        # the same encoding) rather than the "fast" live-store-view branch -
        # results should still be correct either way.
        from rdflib import RDFS

        from starlayergraph import TripleTerm

        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data=_DATA, format="turtle12")
        g.add_reification(EX.claim, TripleTerm(EX.bob, EX.knows, EX.carol))
        assert g._tt_registry  # sanity: this graph really does exercise the fallback path

        rows = [str(r.x) for r in g.query(_QUERY, entailment="owl-rl")]
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

        list(g.query(_QUERY, entailment="owl-rl"))

        delta = g._owl_rl_cache[0]
        for t in g:
            assert t not in delta


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
