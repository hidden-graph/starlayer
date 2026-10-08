"""tests/shacl/unit/test_entailment.py

Coverage for starlayer.shacl.entailment - reading sh:entailment
declarations from a shapes graph and applying them via
StarLayerGraph.infer(). See that module's own docstring for the spec
citations (SHACL 1.2 Core §1.4: shapes-graph-scoped, multiple regimes
combine into one pass) and its documented v1 scope limitation
(ont_graph-only axioms aren't seen).
"""

from rdflib import Namespace
from rdflib.namespace import RDF, RDFS

import pytest

from starlayer.graph import ENTAILMENT, StarLayerGraph
from starlayer.shacl.entailment import apply_entailment, declared_entailment_regimes

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")


def _shapes(*entailment_regimes) -> StarLayerGraph:
    g = StarLayerGraph()
    g.bind("ex", EX)
    g.add((EX.SomeShape, RDF.type, SH.NodeShape))
    for regime in entailment_regimes:
        g.add((EX.SomeShape, SH.entailment, regime))
    return g


class TestDeclaredEntailmentRegimes:
    def test_empty_when_none_declared(self) -> None:
        assert declared_entailment_regimes(_shapes()) == frozenset()

    def test_single_regime(self) -> None:
        assert declared_entailment_regimes(_shapes(ENTAILMENT.RDFS)) == frozenset({ENTAILMENT.RDFS})

    def test_multiple_regimes_combine_into_one_set(self) -> None:
        regimes = declared_entailment_regimes(_shapes(ENTAILMENT.RDFS, ENTAILMENT["OWL-RDF-Based"]))
        assert regimes == frozenset({ENTAILMENT.RDFS, ENTAILMENT["OWL-RDF-Based"]})

    def test_not_scoped_to_a_particular_shape(self) -> None:
        # Spec: "a shapes graph contains any triple with the predicate
        # sh:entailment" - shapes-graph-level, not per-shape. A second,
        # unrelated subject declaring sh:entailment still counts.
        g = _shapes(ENTAILMENT.RDFS)
        g.add((EX.SomeOtherNode, SH.entailment, ENTAILMENT["OWL-RDF-Based"]))
        assert declared_entailment_regimes(g) == frozenset({ENTAILMENT.RDFS, ENTAILMENT["OWL-RDF-Based"]})


class TestApplyEntailment:
    def test_noop_when_nothing_declared_inplace_true(self) -> None:
        data = StarLayerGraph()
        data.add((EX.alice, EX.knows, EX.bob))
        before = set(data)

        result = apply_entailment(data, _shapes(), inplace=True)

        assert result is data
        assert set(data) == before

    def test_noop_when_nothing_declared_inplace_false(self) -> None:
        data = StarLayerGraph()
        data.add((EX.alice, EX.knows, EX.bob))

        result = apply_entailment(data, _shapes(), inplace=False)

        assert result is data

    def test_inplace_true_mutates_and_returns_the_same_object(self) -> None:
        data = StarLayerGraph()
        data.bind("ex", EX)
        data.add((EX.Manager, RDFS.subClassOf, EX.Employee))
        data.add((EX.alice, RDF.type, EX.Manager))

        result = apply_entailment(data, _shapes(ENTAILMENT.RDFS), inplace=True)

        assert result is data
        assert (EX.alice, RDF.type, EX.Employee) in data

    def test_inplace_false_returns_a_new_graph_leaving_caller_data_untouched(self) -> None:
        # Regression coverage: an earlier version of apply_entailment()
        # always mutated data_graph in place regardless of inplace=,
        # silently breaking validate()'s own documented guarantee that
        # the plain "validation" profile (inplace=False) never mutates
        # the caller's data - confirmed live via StarShaclSchema.validate()
        # before this parameter was added.
        data = StarLayerGraph()
        data.bind("ex", EX)
        data.add((EX.Manager, RDFS.subClassOf, EX.Employee))
        data.add((EX.alice, RDF.type, EX.Manager))
        before = set(data)

        result = apply_entailment(data, _shapes(ENTAILMENT.RDFS), inplace=False)

        assert result is not data
        assert set(data) == before
        assert (EX.alice, RDF.type, EX.Employee) not in data
        assert (EX.alice, RDF.type, EX.Employee) in result

    def test_ont_graph_only_axiom_is_seen(self) -> None:
        # rdfs:domain declared only in ont_graph, not data_graph - the gap
        # found via a live worked example this session (apply_entailment()
        # previously only ever read data_graph).
        data = StarLayerGraph()
        data.bind("ex", EX)
        data.add((EX.alice, EX.worksAt, EX.Acme))
        ont = StarLayerGraph()
        ont.add((EX.worksAt, RDFS.domain, EX.Employee))

        result = apply_entailment(data, _shapes(ENTAILMENT.RDFS), ont, inplace=True)

        assert result is data
        assert (EX.alice, RDF.type, EX.Employee) in data

    def test_ont_graph_itself_is_never_mutated(self) -> None:
        data = StarLayerGraph()
        data.bind("ex", EX)
        data.add((EX.alice, EX.worksAt, EX.Acme))
        ont = StarLayerGraph()
        ont.add((EX.worksAt, RDFS.domain, EX.Employee))
        before_ont = set(ont)

        apply_entailment(data, _shapes(ENTAILMENT.RDFS), ont, inplace=True)

        assert set(ont) == before_ont

    def test_ont_graphs_own_raw_triples_are_not_copied_into_the_result(self) -> None:
        # Only the newly-*entailed* delta gets materialized - ont_graph's
        # own raw axiom triple itself must not leak into data_graph.
        data = StarLayerGraph()
        data.bind("ex", EX)
        data.add((EX.alice, EX.worksAt, EX.Acme))
        ont = StarLayerGraph()
        ont.add((EX.worksAt, RDFS.domain, EX.Employee))

        apply_entailment(data, _shapes(ENTAILMENT.RDFS), ont, inplace=True)

        assert (EX.worksAt, RDFS.domain, EX.Employee) not in data

    def test_ont_graph_none_behaves_exactly_as_before(self) -> None:
        data = StarLayerGraph()
        data.bind("ex", EX)
        data.add((EX.Manager, RDFS.subClassOf, EX.Employee))
        data.add((EX.alice, RDF.type, EX.Manager))

        result = apply_entailment(data, _shapes(ENTAILMENT.RDFS), None, inplace=True)

        assert result is data
        assert (EX.alice, RDF.type, EX.Employee) in data

    def test_combines_multiple_declared_regimes_into_one_pass(self) -> None:
        data = StarLayerGraph()
        data.bind("ex", EX)
        data.add((EX.alice, EX.knows, EX.bob))

        apply_entailment(data, _shapes(ENTAILMENT.RDFS, ENTAILMENT["OWL-RDF-Based"]), inplace=True)

        # Universal rdfs:Resource typing is only present when RDFS's own
        # rules run alongside OWL-RL's (see infer()'s own docstring) -
        # confirms this went through the combined pass, not just one.
        assert (EX.alice, RDF.type, RDFS.Resource) in data

    def test_unsupported_regime_raises(self) -> None:
        bogus = Namespace("http://www.w3.org/ns/entailment/")["D"]
        data = StarLayerGraph()
        data.add((EX.alice, EX.knows, EX.bob))

        with pytest.raises(ValueError, match="Unsupported entailment regime"):
            apply_entailment(data, _shapes(bogus), inplace=True)

    def test_unrecognized_regime_raises(self) -> None:
        data = StarLayerGraph()
        data.add((EX.alice, EX.knows, EX.bob))

        with pytest.raises(ValueError, match="Unsupported entailment regime"):
            apply_entailment(data, _shapes(EX.NotARealRegime), inplace=True)
