"""Validating the same data again does not run the entailment closure again: ``entailed_view`` keeps its overlay on the data graph and
returns it while the triples (of the data and of ``ont_graph``) are the same. The test of that is a change, of any kind and made any
way, being noticed: a stale overlay would give a wrong report."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph import ENTAILMENT, StarLayerGraph
from starlayer.graph.entailment import infer as infer_module
from starlayer.shacl import validate
from starlayer.shacl.engine import entailment as ent

PFX = "@prefix ex: <http://example.org/> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
EX = "http://example.org/"
RDF_TYPE = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")


def g(ttl: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=PFX + ttl, format="turtle")
    return graph


def data() -> StarLayerGraph:
    return g("ex:Employee rdfs:subClassOf ex:Person . ex:a a ex:Employee . ex:b a ex:Employee .")


def types_of(view, node: str) -> set:
    return {o for (_s, _p, o) in view.triples((ox.NamedNode(EX + node), RDF_TYPE, None))}


@pytest.fixture
def closures(monkeypatch):
    """How many times the closure ran."""
    calls: list = []
    real = infer_module._delta_for

    def counting(*args, **kwargs):
        calls.append(args[1])
        return real(*args, **kwargs)

    monkeypatch.setattr(infer_module, "_delta_for", counting)
    return calls


def test_unchanged_data_runs_the_closure_once(closures):
    d = data()
    first = ent.entailed_view(d, ENTAILMENT.RDFS)
    second = ent.entailed_view(d, ENTAILMENT.RDFS)
    assert second is first
    assert len(closures) == 1
    assert ox.NamedNode(EX + "Person") in types_of(first, "a")


def test_a_write_through_the_wrapper_is_noticed(closures):
    d = data()
    before = ent.entailed_view(d, ENTAILMENT.RDFS)
    d.add((ox.NamedNode(EX + "Person"), ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#subClassOf"), ox.NamedNode(EX + "Agent")))
    after = ent.entailed_view(d, ENTAILMENT.RDFS)
    assert after is not before and len(closures) == 2
    assert ox.NamedNode(EX + "Agent") in types_of(after, "a")
    assert ox.NamedNode(EX + "Agent") not in types_of(before, "a")


def test_a_write_straight_to_the_store_is_noticed(closures):
    """The wrapper's own write counter does not see this one; the content comparison does."""
    d = data()
    before = ent.entailed_view(d, ENTAILMENT.RDFS)
    d.store.add(ox.Quad(ox.NamedNode(EX + "c"), RDF_TYPE, ox.NamedNode(EX + "Employee"), ox.DefaultGraph()))
    after = ent.entailed_view(d, ENTAILMENT.RDFS)
    assert after is not before and len(closures) == 2
    assert ox.NamedNode(EX + "Person") in types_of(after, "c")


def test_replacing_one_triple_by_another_is_noticed(closures):
    """The same number of triples before and after, so a count alone would not see it."""
    d = data()
    before = ent.entailed_view(d, ENTAILMENT.RDFS)
    sub = (ox.NamedNode(EX + "Employee"), ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#subClassOf"), ox.NamedNode(EX + "Person"))
    d.remove(sub)
    d.add((sub[0], sub[1], ox.NamedNode(EX + "Worker")))
    after = ent.entailed_view(d, ENTAILMENT.RDFS)
    assert after is not before and len(closures) == 2
    assert ox.NamedNode(EX + "Person") not in types_of(after, "a") and ox.NamedNode(EX + "Worker") in types_of(after, "a")


def test_the_ontology_graph_is_part_of_the_key(closures):
    d = data()
    plain = ent.entailed_view(d, ENTAILMENT.RDFS)
    with_ont = ent.entailed_view(d, ENTAILMENT.RDFS, g("ex:Person rdfs:subClassOf ex:Agent ."))
    assert with_ont is not plain
    assert ox.NamedNode(EX + "Agent") in types_of(with_ont, "a") and ox.NamedNode(EX + "Agent") not in types_of(plain, "a")
    assert not any(with_ont.triples((ox.NamedNode(EX + "Person"), None, ox.NamedNode(EX + "Agent"))))  # the ontology's own triples stay out
    ont = g("ex:Person rdfs:subClassOf ex:Agent .")
    first = ent.entailed_view(d, ENTAILMENT.RDFS, ont)
    ont.add((ox.NamedNode(EX + "Agent"), ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#subClassOf"), ox.NamedNode(EX + "Thing")))
    changed = ent.entailed_view(d, ENTAILMENT.RDFS, ont)
    assert changed is not first and ox.NamedNode(EX + "Thing") in types_of(changed, "a")


def test_each_regime_is_kept_separately(closures):
    d = data()
    rdfs = ent.entailed_view(d, ENTAILMENT.RDFS)
    rdf = ent.entailed_view(d, ENTAILMENT.RDF)
    assert rdfs is not rdf
    assert ent.entailed_view(d, ENTAILMENT.RDFS) is rdfs and ent.entailed_view(d, ENTAILMENT.RDF) is rdf


def test_the_kept_overlays_are_bounded():
    d = data()
    for i in range(10):
        d_ont = g(f"ex:K{i} a ex:Employee .")
        ent.entailed_view(d, ENTAILMENT.RDFS, d_ont)
    assert len(d.__dict__[ent._KEPT_ATTRIBUTE]) <= ent._KEPT_VIEWS


def test_the_view_holds_what_the_closure_adds_and_the_data_is_untouched():
    d = data()
    before = set(d.triples((None, None, None)))
    view = ent.entailed_view(d, ENTAILMENT.RDFS)
    assert set(d.triples((None, None, None))) == before
    assert set(view.inferred) == set(d.infer(entailment=ENTAILMENT.RDFS, mode="delta").triples((None, None, None)))


def test_a_repeated_validation_gives_the_same_report_and_follows_a_change():
    shapes = g("ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:name ; sh:minCount 1 ] .")
    d = data()
    first = validate(d, shapes, inference=ENTAILMENT.RDFS)
    again = validate(d, shapes, inference=ENTAILMENT.RDFS)
    assert not first.conforms and first.conforms == again.conforms
    assert len(list(first.report_graph.subjects(RDF_TYPE, ox.NamedNode("http://www.w3.org/ns/shacl#ValidationResult")))) == 2
    assert len(list(again.report_graph.subjects(RDF_TYPE, ox.NamedNode("http://www.w3.org/ns/shacl#ValidationResult")))) == 2
    for node in ("a", "b"):
        d.add((ox.NamedNode(EX + node), ox.NamedNode(EX + "name"), ox.Literal(node)))
    assert validate(d, shapes, inference=ENTAILMENT.RDFS).conforms


def test_inplace_adds_the_inferred_triples_and_the_next_call_sees_them():
    shapes = g("ex:S a sh:NodeShape ; sh:targetClass ex:Person .")
    d = data()
    validate(d, shapes, inference=ENTAILMENT.RDFS, inplace=True)
    assert ox.NamedNode(EX + "Person") in types_of(d, "a")
    assert validate(d, shapes, inference=ENTAILMENT.RDFS).conforms


def test_a_constant_fingerprint_would_serve_a_stale_overlay(monkeypatch):
    """Mutation check for the tests above: with a comparison that sees no change, the overlay is stale after a write."""
    monkeypatch.setattr(ent, "_fingerprint", lambda triples: (0, 0))
    d = data()
    before = ent.entailed_view(d, ENTAILMENT.RDFS)
    d.add((ox.NamedNode(EX + "Person"), ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#subClassOf"), ox.NamedNode(EX + "Agent")))
    stale = ent.entailed_view(d, ENTAILMENT.RDFS)
    assert stale is before and ox.NamedNode(EX + "Agent") not in types_of(stale, "a")
