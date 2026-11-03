"""Options of ``shacl_engine.api.validate`` against the old validator on the same inline Turtle."""

from __future__ import annotations

import pytest
from pyoxigraph import Literal
from starlayer.shacl_engine.terms import RDF
from pyoxigraph import NamedNode as URIRef
from starlayer.graph.graph.entailment_regimes import ENTAILMENT
from starlayer.graph.oxgraph import OxGraph
from starlayer.shacl import validate as old_validate
from starlayer.shacl_engine.api import validate as new_validate
from starlayer.shacl_engine.plan import ShapeError
from starlayer.shacl_engine.terms import SH, XSD

PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "
EX = "http://example.org/"


def g(ttl: str, ident: str | None = None) -> OxGraph:
    graph = OxGraph(identifier=URIRef(ident)) if ident else OxGraph()
    graph.parse(data=PFX + ttl, format="turtle")
    return graph


def report_node(graph):
    return next(graph.subjects(RDF.type, SH.ValidationReport))


def results_of(graph):
    return len(list(graph.objects(report_node(graph), SH.result)))


SHAPES = "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:minCount 1 ; sh:message 'need p'@en, 'brauche p'@de ] ."
BAD = "ex:a a ex:T . ex:b a ex:T ."
GOOD = "ex:a a ex:T ; ex:p 1 ."


def both(data, shapes, **kw):
    old = old_validate(g(data), g(shapes), meta_shacl=False, ignore_imports=True, **kw)
    return old, new_validate(g(data), g(shapes), **{k: v for k, v in kw.items() if k in NEW_KW})


NEW_KW = {"data_graph_iri", "shapes_graph_iri", "shapes_graph_resource", "include_used_configuration", "abort_on_first"}


# --- provenance -----------------------------------------------------------------------------------------------------
def test_used_graphs_match_the_old_validator() -> None:
    kw = {"data_graph_iri": EX + "d", "shapes_graph_iri": EX + "s"}
    old, new = both(GOOD, SHAPES, **kw)
    for r in (old.report_graph, new.report_graph):
        n = report_node(r)
        assert set(r.objects(n, SH.usedDataGraph)) == {URIRef(EX + "d")}
        assert set(r.objects(n, SH.usedShapesGraph)) == {URIRef(EX + "s")}
    # both graph identities known, conforming: the Profiling sh:conformsTo rule fired in both
    assert (URIRef(EX + "d"), SH.conformsTo, URIRef(EX + "s")) in old.report_graph
    assert (URIRef(EX + "d"), SH.conformsTo, URIRef(EX + "s")) in new.report_graph


def test_graph_identifier_is_the_fallback() -> None:
    old = old_validate(g(GOOD, EX + "dd"), g(SHAPES, EX + "ss"), meta_shacl=False, ignore_imports=True)
    new = new_validate(g(GOOD, EX + "dd"), g(SHAPES, EX + "ss"))
    for r in (old.report_graph, new.report_graph):
        n = report_node(r)
        assert set(r.objects(n, SH.usedDataGraph)) == {URIRef(EX + "dd")}
        assert set(r.objects(n, SH.usedShapesGraph)) == {URIRef(EX + "ss")}


def test_no_identity_no_provenance() -> None:
    old, new = both(GOOD, SHAPES)
    for r in (old.report_graph, new.report_graph):
        assert not list(r.triples((None, SH.usedDataGraph, None)))
        assert not list(r.triples((None, SH.usedShapesGraph, None)))
        assert not list(r.triples((None, SH.usedConfiguration, None)))


def test_used_configuration() -> None:
    old, new = both(BAD, SHAPES, include_used_configuration=True)
    for r in (old.report_graph, new.report_graph):
        cfg = next(r.objects(report_node(r), SH.usedConfiguration))
        assert (cfg, RDF.type, SH.ProcessorConfiguration) in r
    cfg = next(new.report_graph.objects(report_node(new.report_graph), SH.usedConfiguration))
    assert len(list(new.report_graph.predicate_objects(cfg))) > 1  # the new engine records the run's options too


MODULES = """
ex:M1 a sh:ShapesGraph . ex:M2 a sh:ShapesGraph .
ex:S1 a sh:NodeShape ; rdfs:isDefinedBy ex:M1 ; sh:targetNode ex:a ; sh:property [ sh:path ex:x ; sh:minCount 1 ] .
ex:S2 a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:y ; sh:minCount 1 ] .
ex:M2 rdfs:member ex:S2 .
"""


def test_shapes_graph_resource_selects_a_module() -> None:
    data = "ex:a ex:x 1 ."  # S1 satisfied, S2 (ex:y) not
    old = old_validate(g(data), g(MODULES), shapes_graph_resource=EX + "M1", meta_shacl=False, ignore_imports=True)
    new = new_validate(g(data), g(MODULES), shapes_graph_resource=URIRef(EX + "M1"))
    assert old.conforms is new.conforms is True
    for r in (old.report_graph, new.report_graph):
        assert set(r.objects(report_node(r), SH.usedShapesGraph)) == {URIRef(EX + "M1")}
    old2 = old_validate(g(data), g(MODULES), shapes_graph_resource=EX + "M2", meta_shacl=False, ignore_imports=True)
    new2 = new_validate(g(data), g(MODULES), shapes_graph_resource=URIRef(EX + "M2"))
    assert old2.conforms is new2.conforms is False


def test_shapes_graph_resource_not_a_module_is_a_tag() -> None:
    old = old_validate(g(BAD), g(SHAPES), shapes_graph_resource=EX + "tag", meta_shacl=False, ignore_imports=True)
    new = new_validate(g(BAD), g(SHAPES), shapes_graph_resource=URIRef(EX + "tag"))
    assert old.conforms is new.conforms is False
    for r in (old.report_graph, new.report_graph):
        assert set(r.objects(report_node(r), SH.usedShapesGraph)) == {URIRef(EX + "tag")}


def test_shapes_graph_resource_needs_a_shapes_graph() -> None:
    with pytest.raises(ValueError):
        old_validate(g(BAD), None, shapes_graph_resource=EX + "M1", meta_shacl=False, ignore_imports=True)
    with pytest.raises(ValueError):
        new_validate(g(BAD), None, shapes_graph_resource=URIRef(EX + "M1"))


# --- messages and annotations ---------------------------------------------------------------------------------------
def test_shape_messages_keep_their_language() -> None:
    old, new = both(BAD, SHAPES)
    want = {Literal("need p", language="en"), Literal("brauche p", language="de")}
    for r in (old.report_graph, new.report_graph):
        assert set(r.objects(None, SH.resultMessage)) >= want


ANNOTATED = """
ex:S a sh:NodeShape ; sh:targetSubjectsOf ex:score ;
  sh:sparql [
    sh:select "PREFIX ex: <http://example.org/> SELECT $this ?actual WHERE { $this ex:score ?actual . FILTER(?actual < 50) }" ;
    sh:resultAnnotation [ sh:annotationProperty ex:reported ; sh:annotationVarName "actual" ] ,
                        [ sh:annotationProperty ex:origin ; sh:annotationValue "score-check" ] ,
                        [ sh:annotationProperty ex:unbound ; sh:annotationVarName "nope" ] ;
  ] .
"""


def test_result_annotations_match_the_old_validator() -> None:
    data = "ex:alice ex:score 20 . ex:bob ex:score 80 ."
    old, new = both(data, ANNOTATED)
    for r in (old.report_graph, new.report_graph):
        assert [o for _, _, o in r.triples((None, URIRef(EX + "reported"), None))] == [Literal("20", datatype=XSD.integer)]
        assert [o for _, _, o in r.triples((None, URIRef(EX + "origin"), None))] == [Literal("score-check")]
        assert not list(r.triples((None, URIRef(EX + "unbound"), None)))


# --- abort_on_first -------------------------------------------------------------------------------------------------
def test_abort_on_first() -> None:
    old_all, new_all = both(BAD, SHAPES)
    assert results_of(old_all.report_graph) == results_of(new_all.report_graph) == 2
    old, new = both(BAD, SHAPES, abort_on_first=True)
    assert old.conforms is new.conforms is False
    assert results_of(new.report_graph) == 1
    assert results_of(old.report_graph) >= 1  # the old validator reports every focus node of the first failing component


def test_abort_on_first_conforming() -> None:
    old, new = both(GOOD, SHAPES, abort_on_first=True)
    assert old.conforms is new.conforms is True


# --- max_validation_depth -------------------------------------------------------------------------------------------
DEEP = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:node [ sh:node [ sh:node [ sh:closed false ] ] ] ."


def test_max_validation_depth_is_a_failure_in_both() -> None:
    with pytest.raises(Exception):  # noqa: B017  (old: ReportableRuntimeError)
        old_validate(g("ex:a ex:p 1 ."), g(DEEP), meta_shacl=False, ignore_imports=True, max_validation_depth=2)
    with pytest.raises(ShapeError, match="too deep"):
        new_validate(g("ex:a ex:p 1 ."), g(DEEP), max_validation_depth=2)
    assert new_validate(g("ex:a ex:p 1 ."), g(DEEP), max_validation_depth=10).conforms
    assert old_validate(g("ex:a ex:p 1 ."), g(DEEP), meta_shacl=False, ignore_imports=True, max_validation_depth=30).conforms


# --- recursion ------------------------------------------------------------------------------------------------------
PERSON = "ex:P a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:name ; sh:minCount 1 ] , [ sh:path ex:friend ; sh:node ex:P ] ."


def test_positive_cycle_conforms_like_the_old_validator() -> None:
    data = "ex:a a ex:Person ; ex:name 'A' ; ex:friend ex:b . ex:b ex:name 'B' ; ex:friend ex:a ."
    old, new = both(data, PERSON)
    assert old.conforms is new.conforms is True


def test_positive_cycle_with_a_violation_is_found() -> None:
    data = "ex:a a ex:Person ; ex:name 'A' ; ex:friend ex:b . ex:b ex:friend ex:a ."
    old, new = both(data, PERSON)
    assert old.conforms is new.conforms is False


def test_chain_is_evaluated_in_full() -> None:
    data = "ex:a a ex:Person ; ex:name 'A' ; ex:friend ex:b . ex:b ex:name 'B' ; ex:friend ex:c . ex:c ex:friend ex:d . ex:d a ex:Thing ."
    old, new = both(data, PERSON)
    assert old.conforms is new.conforms is False


NOT_CYCLE = "ex:N a sh:NodeShape ; sh:targetNode ex:a ; sh:not [ sh:property [ sh:path ex:next ; sh:node ex:N ] ] ."


def test_a_cycle_through_sh_not_is_a_failure() -> None:
    data = "ex:a ex:next ex:a ."
    with pytest.raises(ShapeError, match="sh:not"):
        new_validate(g(data), g(NOT_CYCLE))


def test_sh_not_without_a_data_cycle_is_fine() -> None:
    data = "ex:a ex:next ex:b ."
    old, new = both(data, NOT_CYCLE)
    assert old.conforms is new.conforms


def test_double_negation_cycle_is_a_failure_too() -> None:
    """Even through two sh:not the cycle has two consistent readings (the old validator picks one by evaluation order)."""
    shapes = "ex:N a sh:NodeShape ; sh:targetNode ex:a ; sh:not [ sh:not [ sh:property [ sh:path ex:next ; sh:node ex:N ] ] ] ."
    with pytest.raises(ShapeError, match="sh:not"):
        new_validate(g("ex:a ex:next ex:a ."), g(shapes))


def test_negation_in_a_chain_that_never_returns_is_evaluated() -> None:
    shapes = "ex:N a sh:NodeShape ; sh:targetNode ex:a ; sh:not [ sh:not [ sh:property [ sh:path ex:next ; sh:node ex:N ] ] ] ."
    old, new = both("ex:a ex:next ex:b .", shapes)
    assert old.conforms is new.conforms


# --- inplace --------------------------------------------------------------------------------------------------------
def test_inplace_adds_entailed_triples_to_the_data_graph() -> None:
    data = g("ex:T rdfs:subClassOf ex:U . " + GOOD)
    before = len(data)
    plain = new_validate(data, g(SHAPES), inference=ENTAILMENT.RDFS)
    assert plain.data_graph is None and len(data) == before
    out = new_validate(data, g(SHAPES), inference=ENTAILMENT.RDFS, inplace=True)
    assert out.data_graph is data
    assert (URIRef(EX + "a"), RDF.type, URIRef(EX + "U")) in data
