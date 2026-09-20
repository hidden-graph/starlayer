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

    def test_matches_owlrl_run_on_the_same_decomposition(self) -> None:
        # _decompose() mints a *fresh* BNode per call for the triple term's
        # synthetic identity (by design - see its own docstring), so calling
        # it a second time here for the oracle yields a structurally
        # identical but label-different graph from what infer() produced
        # internally - compare via isomorphic(), not raw set equality.
        from starlayergraph.compare import _decompose, isomorphic

        g = _rdfs_graph()
        g.add((EX.claim, REIFIES, TripleTerm(EX.alice, EX.knows, EX.bob)))

        closed = g.infer()

        oracle = _decompose(g)
        owlrl.DeductiveClosure(owlrl.RDFS_Semantics).expand(oracle)

        assert isomorphic(closed, oracle)
        assert len(closed) == len(oracle)
