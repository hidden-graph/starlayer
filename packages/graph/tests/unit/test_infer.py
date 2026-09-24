"""
tests/unit/test_infer.py

Coverage for StarLayerGraph.infer(), which formalizes the manual
owlrl.DeductiveClosure workflow shown in docs/guides/02b-graphs-inferencing.ipynb
into real API. Per this project's own testing discipline (starsparql/CLAUDE.md:
"any new query/update shape needs an execution-comparison test, not just a
structural one"), every test here compares infer()'s output against owlrl
itself run directly - owlrl is the oracle, since plain rdflib has no
entailment of its own to compare against.

Requires the `reasoning` extra: pip install -e ".[reasoning]"
"""

from rdflib import RDFS, Graph, URIRef
from rdflib.namespace import OWL

import pytest

from starlayergraph import RDF, Namespace, StarLayerGraph, TripleTerm

try:
    import owlrl
    _OWLRL_AVAILABLE = True
except ImportError:
    _OWLRL_AVAILABLE = False

owlrl_extra = pytest.mark.skipif(
    not _OWLRL_AVAILABLE,
    reason='owlrl not installed — install with: pip install -e ".[reasoning]"',
)

EX = Namespace("http://example.org/")
REIFIES = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")


def _rdfs_graph() -> StarLayerGraph:
    g = StarLayerGraph()
    g.bind("ex", EX)
    g.add((EX.Dog, RDFS.subClassOf, EX.Animal))
    g.add((EX.fido, RDF.type, EX.Dog))
    return g


@owlrl_extra
class TestInferRdfs:
    def test_matches_owlrl_run_directly(self) -> None:
        g = _rdfs_graph()

        closed = g.infer()

        oracle = Graph()
        for t in g:
            oracle.add(t)
        owlrl.DeductiveClosure(owlrl.RDFS_Semantics).expand(oracle)

        assert set(closed) == set(oracle)

    def test_entails_the_subclass_type(self) -> None:
        closed = _rdfs_graph().infer()
        assert (EX.fido, RDF.type, EX.Animal) in closed

    def test_returns_a_new_graph_original_untouched(self) -> None:
        g = _rdfs_graph()
        before = set(g)

        closed = g.infer()

        assert set(g) == before
        assert closed is not g
        assert isinstance(closed, StarLayerGraph)

    def test_target_graph_receives_entailed_triples_without_being_cleared(self) -> None:
        g = _rdfs_graph()
        target = StarLayerGraph()
        target.bind("ex", EX)
        target.add((EX.someone, EX.marker, EX.value))

        result = g.infer(target_graph=target)

        assert result is target
        assert (EX.someone, EX.marker, EX.value) in result
        assert (EX.fido, RDF.type, EX.Animal) in result

    def test_target_graph_must_be_a_starlayergraph(self) -> None:
        with pytest.raises(TypeError, match="StarLayerGraph"):
            _rdfs_graph().infer(target_graph=Graph())

    def test_unsupported_profile_raises(self) -> None:
        with pytest.raises(ValueError, match="bogus"):
            _rdfs_graph().infer(profile="bogus")


@owlrl_extra
class TestInferOwlRl:
    def test_owl_rl_profile_entails_beyond_plain_rdfs(self) -> None:
        # owl:equivalentClass is an OWL construct with no RDFS-only analogue -
        # a plain "rdfs" profile run should not entail fido's Animal
        # membership through it, but "owl-rl" should.
        g = StarLayerGraph()
        g.bind("ex", EX)
        g.add((EX.Dog, OWL.equivalentClass, EX.Canine))
        g.add((EX.fido, RDF.type, EX.Canine))

        rdfs_only = g.infer(profile="rdfs")
        owl_rl = g.infer(profile="owl-rl")

        assert (EX.fido, RDF.type, EX.Dog) not in rdfs_only
        assert (EX.fido, RDF.type, EX.Dog) in owl_rl

    def test_matches_owlrl_run_directly(self) -> None:
        g = StarLayerGraph()
        g.bind("ex", EX)
        g.add((EX.Dog, OWL.equivalentClass, EX.Canine))
        g.add((EX.fido, RDF.type, EX.Canine))

        closed = g.infer(profile="owl-rl")

        oracle = Graph()
        for t in g:
            oracle.add(t)
        owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(oracle)

        assert set(closed) == set(oracle)


@owlrl_extra
class TestInferDelta:
    def test_delta_excludes_originals_includes_new_facts(self) -> None:
        g = _rdfs_graph()

        delta = g.infer(mode="delta")

        assert (EX.Dog, RDFS.subClassOf, EX.Animal) not in delta
        assert (EX.fido, RDF.type, EX.Dog) not in delta
        assert (EX.fido, RDF.type, EX.Animal) in delta

    def test_original_decomposed_union_delta_equals_closure(self) -> None:
        from starlayergraph.compare import _decompose

        g = _rdfs_graph()

        closure = g.infer(mode="full")
        delta = g.infer(mode="delta")
        original_decomposed = _decompose(g)

        assert set(closure) == set(original_decomposed) | set(delta)

    def test_target_graph_receives_only_delta_without_being_cleared(self) -> None:
        g = _rdfs_graph()
        target = StarLayerGraph()
        target.bind("ex", EX)
        target.add((EX.someone, EX.marker, EX.value))

        result = g.infer(mode="delta", target_graph=target)

        assert result is target
        assert (EX.someone, EX.marker, EX.value) in result
        assert (EX.fido, RDF.type, EX.Animal) in result
        assert (EX.Dog, RDFS.subClassOf, EX.Animal) not in result

    def test_triple_term_case_still_correct(self) -> None:
        # Mirrors TestInferWithTripleTerms.test_matches_owlrl_run_on_the_same_decomposition -
        # isomorphic(), not raw equality, for the same _decompose()-mints-a-
        # fresh-BNode-per-call reason.
        from starlayergraph.compare import _decompose, isomorphic

        g = _rdfs_graph()
        g.add((EX.claim, REIFIES, TripleTerm(EX.alice, EX.knows, EX.bob)))

        delta = g.infer(mode="delta")

        oracle_before = _decompose(g)
        oracle_after = Graph()
        for t in oracle_before:
            oracle_after.add(t)
        owlrl.DeductiveClosure(owlrl.RDFS_Semantics).expand(oracle_after)
        oracle_before_set = set(oracle_before)
        oracle_delta = StarLayerGraph()
        for t in oracle_after:
            if t not in oracle_before_set:
                oracle_delta.add(t)

        assert isomorphic(delta, oracle_delta)
        assert len(delta) == len(oracle_delta)

    def test_unsupported_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="bogus"):
            _rdfs_graph().infer(mode="bogus")


@owlrl_extra
class TestInferWithTripleTerms:
    def test_does_not_crash_and_still_entails_plain_rdfs_facts(self) -> None:
        # owlrl's RDFS closure asserts "x rdf:type rdfs:Resource" for every
        # term seen anywhere in a triple, including subject position - a
        # triple term is never legal there under RDF 1.2, so infer() must
        # decompose it first (see infer()'s own docstring) rather than
        # handing owlrl a graph owlrl would otherwise crash on.
        g = _rdfs_graph()
        g.add((EX.claim, REIFIES, TripleTerm(EX.alice, EX.knows, EX.bob)))

        closed = g.infer()

        assert (EX.fido, RDF.type, EX.Animal) in closed

    def test_original_triple_term_is_preserved_not_decomposed(self) -> None:
        # The whole point of decomposing before handing the graph to owlrl
        # is to avoid the crash - not to leak that internal representation
        # into the output. self's own triples (including the real
        # TripleTerm) are copied into the closure as-is; only the
        # newly-*entailed* portion can still be decomposed (see the next
        # test, and infer()'s own docstring for exactly why that part is
        # unavoidable).
        g = _rdfs_graph()
        tt = TripleTerm(EX.alice, EX.knows, EX.bob)
        g.add((EX.claim, REIFIES, tt))

        closed = g.infer()

        assert (EX.claim, REIFIES, tt) in closed

    def test_delta_matches_owlrl_run_on_the_same_decomposition(self) -> None:
        # _decompose() mints a *fresh* BNode per call for the triple term's
        # synthetic identity (by design - see its own docstring), so calling
        # it a second time here for the oracle yields a structurally
        # identical but label-different graph from what infer() produced
        # internally - compare via isomorphic(), not raw set equality.
        # Comparing the *delta* specifically (not the whole closure, which
        # now preserves the real triple term for its own portion - see the
        # previous test) is the correct oracle comparison for the part that
        # genuinely still goes through decomposition.
        from starlayergraph.compare import _decompose, isomorphic

        g = _rdfs_graph()
        g.add((EX.claim, REIFIES, TripleTerm(EX.alice, EX.knows, EX.bob)))

        delta = g.infer(mode="delta")

        oracle_before = _decompose(g)
        oracle_after = Graph()
        for t in oracle_before:
            oracle_after.add(t)
        owlrl.DeductiveClosure(owlrl.RDFS_Semantics).expand(oracle_after)
        oracle_before_set = set(oracle_before)
        oracle_delta = StarLayerGraph()
        for t in oracle_after:
            if t not in oracle_before_set:
                oracle_delta.add(t)

        assert isomorphic(delta, oracle_delta)
        assert len(delta) == len(oracle_delta)

    def test_closure_equals_self_triples_union_delta(self) -> None:
        # Two separate infer() calls, each decomposing self independently -
        # the delta portion of each mints its own fresh BNode for the
        # triple term (same reason as the tests above), so compare via
        # isomorphic() rather than raw set equality.
        from starlayergraph.compare import isomorphic

        g = _rdfs_graph()
        g.add((EX.claim, REIFIES, TripleTerm(EX.alice, EX.knows, EX.bob)))

        closure = g.infer(mode="full")
        delta = g.infer(mode="delta")

        union = StarLayerGraph()
        for t in g:
            union.add(t)
        for t in delta:
            union.add(t)

        assert isomorphic(closure, union)
        assert len(closure) == len(union)


@owlrl_extra
class TestInferCombinedProfile:
    def _domain_graph(self) -> StarLayerGraph:
        g = StarLayerGraph()
        g.bind("ex", EX)
        g.add((EX.a, EX.p, EX.b))
        g.add((EX.p, RDFS.domain, EX.C))
        return g

    def test_combined_is_a_real_superset_of_owl_rl_alone(self) -> None:
        # OWLRL_Semantics.rules() never calls RDFS_Semantics.rules() -
        # confirmed live - so universal rdfs:Resource typing only shows up
        # once RDFS's own rules run alongside OWL-RL's.
        owl_rl_only = self._domain_graph().infer(profile="owl-rl")
        combined = self._domain_graph().infer(profile="rdfs+owl-rl")

        assert (EX.a, RDF.type, RDFS.Resource) not in owl_rl_only
        assert (EX.a, RDF.type, RDFS.Resource) in combined

    def test_matches_owlrl_run_directly(self) -> None:
        g = self._domain_graph()

        closed = g.infer(profile="rdfs+owl-rl")

        oracle = Graph()
        for t in g:
            oracle.add(t)
        owlrl.DeductiveClosure(owlrl.RDFS_OWLRL_Semantics).expand(oracle)

        assert set(closed) == set(oracle)


@owlrl_extra
class TestInferInPlace:
    def test_mutates_and_returns_self(self) -> None:
        g = _rdfs_graph()
        before = len(g)

        result = g.infer(mode="in-place")

        assert result is g
        assert len(g) > before
        assert (EX.fido, RDF.type, EX.Animal) in g

    def test_target_graph_with_in_place_raises(self) -> None:
        g = _rdfs_graph()
        target = StarLayerGraph()
        with pytest.raises(ValueError, match="target_graph"):
            g.infer(mode="in-place", target_graph=target)

    def test_native_self_no_longer_blocked_by_mode_itself(self) -> None:
        # mode="in-place" only ever adds the delta into self, never a
        # re-decomposed copy of self's own data - so it no longer needs to
        # refuse a native self outright. No live store is configured here,
        # so this still fails, but on the actual native operation (a
        # RuntimeError about the missing store), not a NotImplementedError
        # about entailment/mode - confirming the mode-level restriction is
        # gone.
        g = StarLayerGraph(backend="rdf-1.2")
        with pytest.raises(RuntimeError, match="store"):
            g.infer(mode="in-place")

    def test_triple_term_bearing_self_preserves_the_real_triple_term(self) -> None:
        g = _rdfs_graph()
        tt = TripleTerm(EX.alice, EX.knows, EX.bob)
        g.add((EX.claim, REIFIES, tt))

        result = g.infer(mode="in-place")

        assert result is g
        assert (EX.claim, REIFIES, tt) in g
        assert (EX.fido, RDF.type, EX.Animal) in g

    def test_matches_mode_delta_merged_into_self(self) -> None:
        g_in_place = _rdfs_graph()
        g_delta_source = _rdfs_graph()
        original = set(g_delta_source)
        delta = g_delta_source.infer(mode="delta")

        g_in_place.infer(mode="in-place")

        assert set(g_in_place) == original | set(delta)

    def test_unsupported_profile_still_raises(self) -> None:
        with pytest.raises(ValueError, match="bogus"):
            _rdfs_graph().infer(profile="bogus", mode="in-place")
