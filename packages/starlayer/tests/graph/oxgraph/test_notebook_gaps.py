"""Wrapper methods the guide notebooks use that the first cut of ``StarLayerGraph`` / ``StarLayerDataset`` lacked."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph.oxgraph import StarLayerDataset, StarLayerGraph, reification

N = ox.NamedNode
EX = "http://example.org/"
A, B, C, P, Q = (N(EX + x) for x in ("a", "b", "c", "p", "q"))
REIFIES = N("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")


def test_triple_terms_and_has_triple_term():
    g = StarLayerGraph()
    t1, t2 = ox.Triple(A, P, B), ox.Triple(A, Q, C)
    g.add((N(EX + "r"), REIFIES, t1))
    g.add((N(EX + "r2"), REIFIES, t1))
    g.add((N(EX + "m"), N(EX + "reported"), t2))  # a triple term outside rdf:reifies
    g.add((A, P, C))  # asserted, but not a triple term
    assert set(g.triple_terms()) == {t1, t2} and len(list(g.triple_terms())) == 2  # distinct
    assert set(g.triple_terms(subject=A, predicate=Q)) == {t2} and list(g.triple_terms(object=A)) == []
    assert g.has_triple_term(A, P, B) and g.has_triple_term(A, Q, C)
    assert not g.has_triple_term(A, P, C)  # asserted directly, never the object of a triple


def test_remove_reification():
    g = StarLayerGraph()
    t1, t2, r = ox.Triple(A, P, B), ox.Triple(A, P, C), N(EX + "r")
    g.add_reification(r, t1).add_reification(r, t2)
    g.add((r, Q, ox.Literal("note")))
    assert g.remove_reification(r, t1) is g
    assert (r, REIFIES, t1) not in g and (r, REIFIES, t2) in g and (r, Q, ox.Literal("note")) in g
    g.remove_reification(r, (B, P, C))  # absent: a no-op
    g.remove_reification(r)  # every link; the annotation stays
    assert list(g.reified_triples(r)) == [] and (r, Q, ox.Literal("note")) in g


def test_qname_term_and_namespaces():
    g = StarLayerGraph()
    g.bind("ex", EX)
    assert g.qname_term(A) == "ex:a"
    assert g.qname_term(N("http://other.org/x")) == "<http://other.org/x>" and "ns1" not in g.prefixes  # no prefix invented
    assert g.qname_term(ox.BlankNode("b0")) == "_:b0"
    assert g.qname_term(ox.Literal("hi", language="en")) == '"hi"@en'
    assert g.qname_term(ox.Literal("plain")) == '"plain"'
    xsd = "http://www.w3.org/2001/XMLSchema#"
    assert g.qname_term(ox.Literal("5", datatype=N(xsd + "integer"))) == f'"5"^^<{xsd}integer>'  # no default prefixes
    g.bind("xsd", xsd)
    assert g.qname_term(ox.Literal("5", datatype=N(xsd + "integer"))) == '"5"^^xsd:integer'
    assert g.qname_term(ox.Triple(A, P, ox.Triple(B, Q, C))) == "<<( ex:a ex:p <<( ex:b ex:q ex:c )>> )>>"
    assert g.qname_term((A, P, B)) == "<<( ex:a ex:p ex:b )>>"
    with pytest.raises(TypeError):
        g.qname_term("ex:a")
    assert ("ex", EX) in set(g.namespaces()) and dict(g.namespaces()) == g.prefixes
    assert str(A) == "<http://example.org/a>"  # what replaces term.n3()


def test_dataset_default_graph_and_to_graph():
    ds = StarLayerDataset()
    ds.bind("ex", EX)
    ds.add((A, P, B))
    ds.graph(N(EX + "g")).add((A, P, C))
    ds.graph(N(EX + "h")).add((A, P, C))  # the same triple in a second graph collapses
    dg = ds.default_graph
    assert isinstance(dg.identifier, ox.DefaultGraph) and list(dg.triples()) == [(A, P, B)]
    assert ds.graph(dg.identifier).identifier == dg.identifier
    merged = ds.to_graph()
    assert isinstance(merged, StarLayerGraph) and set(merged.triples()) == {(A, P, B), (A, P, C)} and merged.prefixes == ds.prefixes
    merged.add((B, P, A))
    assert len(ds.to_graph()) == 2  # a copy


def test_dataset_reifier_methods_keep_graphs():
    ds = StarLayerDataset()
    t = ox.Triple(A, P, B)
    ann, r = ds.graph(N(EX + "ann")), N(EX + "claim")
    ann.add_reification(r, t)
    ann.add((r, Q, ox.Literal("src")))
    ds.graph(N(EX + "facts")).add((A, P, B))
    for result in (ds.reifiers(TT=t), ds.reifications(), ds.reifier_annotations(t), ds.reified_triples(r)):
        assert isinstance(result, StarLayerDataset) and len(result) > 0
        assert result.graph_names() == [N(EX + "ann")]  # the facts graph holds no reifier
    assert len(ds.reifiers(TT=t)) == 2 and len(ds.reifications()) == 1 and len(ds.reifier_annotations(t)) == 1
    assert len(ds.reified_triples(r)) == 1 and len(ds.reifiers(TT=ox.Triple(B, P, A))) == 0
    assert set(ds.reifiers(TT=t).graph(N(EX + "ann")).triples()) == set(ann.triples())
    assert ds.reifiers(TT=t).prefixes == ds.prefixes
    assert list(reification.reifiers(ds)) == [r]  # the function form still yields the nodes


def test_backend_keyword_is_rejected_with_directions():
    for cls in (StarLayerGraph, StarLayerDataset):
        with pytest.raises(TypeError, match=r"store=.*path=.*SERVICE"):
            cls(backend="rdf-1.2")
    assert StarLayerGraph(backend=None).prefixes is not None
