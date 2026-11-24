"""A ``StarShaclProcessor`` takes ``inference=`` per call: it REPLACES the constructor's regime(s) for that call (not merged), ``None``
means no regime of the call's own, and the shapes graph's ``sh:entailment`` still applies. The kept entailed view is keyed by the set
of regimes, so alternating regimes on the same data computes each closure once."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph import ENTAILMENT, StarLayerGraph
from starlayer.graph.entailment import infer as infer_module
from starlayer.shacl import StarShaclProcessor
from tests.support.datasets import dataset_of

PFX = (
    "@prefix ex: <http://example.org/> . @prefix owl: <http://www.w3.org/2002/07/owl#> . "
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
)
EX = "http://example.org/"
RDFS = ENTAILMENT.RDFS
OWL = ENTAILMENT["OWL-RDF-Based"]

# The shape targets Person, so a node is a focus node (and fails the name constraint) only when entailment made it a Person:
# ex:b through rdfs:domain (RDFS, and OWL-RDF-Based which includes it), ex:a through owl:equivalentClass (OWL-RDF-Based only).
# No entailment: no focus node at all.
DATA = (
    "ex:Employee owl:equivalentClass ex:Person . ex:a a ex:Employee . "
    "ex:knows rdfs:domain ex:Person . ex:b ex:knows ex:c ."
)
PERSON_SHAPE = "ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:name ; sh:minCount 1 ] ."
SHAPES = PERSON_SHAPE
A, REX = ox.NamedNode(EX + "a"), ox.NamedNode(EX + "b")  # REX: the RDFS-entailed Person; A: the OWL-only one


def g(ttl: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=PFX + ttl, format="turtle")
    return graph


def focus(report) -> set:
    return {o for (_s, _p, o) in report.report_graph.triples((None, ox.NamedNode("http://www.w3.org/ns/shacl#focusNode"), None))}


def validate_focus(proc, **kw) -> set:
    return focus(proc.validate(g(DATA), **kw))


def test_the_constructor_regime_is_the_default():
    assert validate_focus(StarShaclProcessor(g(SHAPES), inference=RDFS)) == {REX}
    assert validate_focus(StarShaclProcessor(g(SHAPES), inference=OWL)) == {A, REX}
    assert validate_focus(StarShaclProcessor(g(SHAPES))) == set()


def test_a_call_none_beats_the_constructor_regime():
    proc = StarShaclProcessor(g(SHAPES), inference=RDFS)
    assert validate_focus(proc, inference=None) == set()
    assert validate_focus(proc) == {REX}  # the constructor's regime is untouched afterwards
    assert proc.inference == RDFS


def test_a_call_regime_replaces_the_constructor_regime():
    proc = StarShaclProcessor(g(SHAPES), inference=RDFS)
    assert validate_focus(proc, inference=OWL) == {A, REX}
    assert validate_focus(proc, inference=[OWL]) == {A, REX}
    assert validate_focus(proc, inference=[RDFS, OWL]) == {A, REX}


def test_replaced_not_merged():
    # constructor OWL would give {A, REX}; the call's RDFS replaces it, so the OWL-only focus node a is gone
    proc = StarShaclProcessor(g(SHAPES), inference=OWL)
    assert validate_focus(proc, inference=RDFS) == {REX}


def test_an_empty_iterable_means_none():
    proc = StarShaclProcessor(g(SHAPES), inference=OWL)
    assert validate_focus(proc, inference=[]) == set()
    assert validate_focus(proc, inference=()) == set()


def test_a_call_regime_on_a_processor_without_one():
    proc = StarShaclProcessor(g(SHAPES))
    assert validate_focus(proc, inference=RDFS) == {REX}
    assert validate_focus(proc) == set()


def test_the_shapes_graphs_own_sh_entailment_still_applies_with_inference_none():
    shapes = SHAPES + " ex:PersonShape sh:entailment <http://www.w3.org/ns/entailment/RDFS> ."
    proc = StarShaclProcessor(g(shapes), inference=OWL)
    assert validate_focus(proc, inference=None) == {REX}  # RDFS from the shapes graph, nothing from the call or the constructor
    assert validate_focus(proc, inference=OWL) == {A, REX}  # the shapes' RDFS and the call's OWL


def test_validate_each_accepts_inference():
    proc = StarShaclProcessor(g(SHAPES), inference=RDFS)
    out = proc.validate_each(dataset_of([g(DATA), g(DATA)]), inference=OWL)
    assert [focus(r) for r in out.values()] == [{A, REX}, {A, REX}]
    out = proc.validate_each(dataset_of([g(DATA)]), inference=None)
    assert [focus(r) for r in out.values()] == [set()]


def test_target_nodes_accepts_inference():
    proc = StarShaclProcessor(g(SHAPES), inference=RDFS)
    shape = ox.NamedNode(EX + "PersonShape")
    data = g(DATA)
    assert set(proc.target_nodes(data_graph=data, shape_node=shape)) == {REX}
    assert set(proc.target_nodes(data_graph=data, shape_node=shape, inference=OWL)) == {A, REX}
    assert set(StarShaclProcessor(g(SHAPES), inference=OWL).target_nodes(data_graph=data, shape_node=shape, inference=None)) == set()


def test_apply_rules_accepts_inference():
    rule = (
        "@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . "
        "ex:PersonShape sh:rule [ a sh:TripleRule ; sh:subject [ shnex:var \"focusNode\" ] ; sh:predicate ex:seen ; sh:object ex:yes ] ."
    )
    proc = StarShaclProcessor(g(SHAPES + rule), inference=RDFS)
    assert not any(True for _ in proc.apply_rules(g(DATA)).inferred_graph.triples((A, None, None)))  # a is no Person under RDFS
    over = proc.apply_rules(g(DATA), inference=OWL)
    assert any(True for _ in over.inferred_graph.triples((A, ox.NamedNode(EX + "seen"), None)))
    assert focus(proc.validate(g(DATA), inference=OWL, rules=True)) == {A, REX}  # rules, then validation, same regime
    again = proc.apply_rules(g(DATA), inference=None)
    assert len(again.inferred_graph) == 0
    assert focus(proc.validate(g(DATA), inference=None, rules=True)) == set()


def test_an_unknown_keyword_is_still_a_type_error():
    proc = StarShaclProcessor(g(SHAPES))
    with pytest.raises(TypeError):
        proc.validate(g(DATA), inferrence=RDFS)
    with pytest.raises(TypeError):
        proc.target_nodes(data_graph=g(DATA), shape_node=ox.NamedNode(EX + "PersonShape"), nonsense=1)


def test_an_unsupported_regime_on_a_call_is_refused():
    with pytest.raises(ValueError, match="Unsupported entailment regime"):
        StarShaclProcessor(g(SHAPES)).validate(g(DATA), inference="rdfs")


def test_alternating_regimes_compute_each_closure_once(monkeypatch):
    calls: list = []
    real = infer_module._delta_for

    def counting(graph, regimes, *args, **kwargs):
        calls.append(frozenset(regimes))
        return real(graph, regimes, *args, **kwargs)

    monkeypatch.setattr(infer_module, "_delta_for", counting)
    proc = StarShaclProcessor(g(SHAPES))
    data = g(DATA)
    results = [focus(proc.validate(data, inference=r)) for r in (RDFS, OWL, RDFS, OWL, RDFS)]
    assert results == [{REX}, {A, REX}, {REX}, {A, REX}, {REX}]  # correct for each regime
    assert len(calls) == 2  # RDFS once, OWL once
    assert len(set(calls)) == 2


# evaluate(): a computed sh:values on the Person shape, so a node gets ex:flag only when entailment made it a Person.
VALUES_SHAPES = (
    "ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:flag ; sh:values ex:yes ] ."
)
FLAG = ox.NamedNode(EX + "flag")


def flagged(graph) -> set:
    return {s for (s, _p, _o) in graph.triples((None, FLAG, None))}


def evaluate_flagged(proc, **kw) -> set:
    return flagged(proc.evaluate(g(DATA), **kw))


def test_evaluate_uses_the_constructor_regime():
    assert evaluate_flagged(StarShaclProcessor(g(VALUES_SHAPES), inference=RDFS)) == {REX}
    assert evaluate_flagged(StarShaclProcessor(g(VALUES_SHAPES), inference=OWL)) == {A, REX}
    assert evaluate_flagged(StarShaclProcessor(g(VALUES_SHAPES))) == set()  # no regime: nobody is a Person


def test_evaluate_call_regime_replaces_the_constructor_regime():
    proc = StarShaclProcessor(g(VALUES_SHAPES), inference=RDFS)
    assert evaluate_flagged(proc, inference=OWL) == {A, REX}
    assert evaluate_flagged(proc, inference=[OWL]) == {A, REX}
    assert evaluate_flagged(proc) == {REX}  # the constructor's regime is untouched afterwards
    # replaced, not merged: the constructor's OWL would flag a too, the call's RDFS does not
    assert evaluate_flagged(StarShaclProcessor(g(VALUES_SHAPES), inference=OWL), inference=RDFS) == {REX}


def test_evaluate_call_none_and_empty_mean_no_regime():
    proc = StarShaclProcessor(g(VALUES_SHAPES), inference=OWL)
    assert evaluate_flagged(proc, inference=None) == set()
    assert evaluate_flagged(proc, inference=[]) == set()
    assert evaluate_flagged(proc) == {A, REX}


def test_evaluate_call_regime_on_a_processor_without_one():
    proc = StarShaclProcessor(g(VALUES_SHAPES))
    assert evaluate_flagged(proc, inference=RDFS) == {REX}
    assert evaluate_flagged(proc) == set()


def test_evaluate_shapes_sh_entailment_still_applies_with_inference_none():
    proc = StarShaclProcessor(g(VALUES_SHAPES + " ex:PersonShape sh:entailment <http://www.w3.org/ns/entailment/RDFS> ."), inference=OWL)
    assert evaluate_flagged(proc, inference=None) == {REX}
    assert evaluate_flagged(proc, inference=OWL) == {A, REX}


def test_evaluate_with_validate_gating_follows_the_call_regime():
    proc = StarShaclProcessor(g(VALUES_SHAPES), inference=RDFS)
    assert evaluate_flagged(proc, inference=OWL, validate=True) == {A, REX}
    assert evaluate_flagged(proc, inference=None, validate=True) == set()


def test_evaluate_never_mutates_the_callers_data_graph():
    proc = StarShaclProcessor(g(VALUES_SHAPES), inference=RDFS)
    data = g(DATA)
    before = set(data.triples((None, None, None)))
    for kw in ({}, {"inference": OWL}, {"inference": None}):
        proc.evaluate(data, **kw)
        assert set(data.triples((None, None, None))) == before


def test_evaluate_alternating_regimes_compute_each_closure_once(monkeypatch):
    calls: list = []
    real = infer_module._delta_for

    def counting(graph, regimes, *args, **kwargs):
        calls.append(frozenset(regimes))
        return real(graph, regimes, *args, **kwargs)

    monkeypatch.setattr(infer_module, "_delta_for", counting)
    proc = StarShaclProcessor(g(VALUES_SHAPES))
    data = g(DATA)
    results = [flagged(proc.evaluate(data, inference=r)) for r in (RDFS, OWL, RDFS, OWL)]
    assert results == [{REX}, {A, REX}, {REX}, {A, REX}]
    assert len(calls) == 2


def test_evaluate_still_refuses_the_validation_only_options():
    proc = StarShaclProcessor(g(VALUES_SHAPES))
    with pytest.raises(TypeError):
        proc.evaluate(g(DATA), allow_warnings=True)
