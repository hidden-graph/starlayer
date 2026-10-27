"""Regression tests for GitHub issues #136 (SHACL Core audit) and #137 (SHACL rules audit)."""

from __future__ import annotations

import pytest
from pyshacl.errors import ConstraintLoadError, RuleLoadError
from rdflib import Namespace, URIRef
from starlayer import StarLayerGraph
from starlayer.shacl import apply_rules, validate

pytestmark = pytest.mark.shacl

SH = Namespace("http://www.w3.org/ns/shacl#")
EX = Namespace("http://ex/")
RDF_REIFIES = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")
PREFIXES = (
    "@prefix ex: <http://ex/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
)


def g(text: str) -> StarLayerGraph:
    return StarLayerGraph().parse(data=PREFIXES + text, format="turtle12")


# --- #136 -----------------------------------------------------------------------------------------------------------

IN_SHAPES = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:in (1 2) ] ."


@pytest.mark.parametrize("extra", ["", "ex:q ex:r <<( ex:x ex:y 1 )>> ."])
def test_report_does_not_degrade_when_data_holds_a_triple_term(extra):
    result = validate(g("ex:a ex:p 3 . " + extra), g(IN_SHAPES))
    assert not result.conforms
    report = result.report_graph
    assert list(report.subject_objects(SH.sourceShape)), "sh:sourceShape missing"
    assert list(report.subject_objects(SH.resultMessage)), "sh:resultMessage missing"
    assert list(report.subject_objects(SH.conformanceDisallows))
    assert "preflight" not in result.report_text


def test_passing_report_with_triple_term_has_conformance_disallows():
    result = validate(g("ex:a ex:p 1 . ex:q ex:r <<( ex:x ex:y 1 )>> ."), g(IN_SHAPES))
    assert result.conforms
    assert list(result.report_graph.subject_objects(SH.conformanceDisallows))


@pytest.mark.parametrize(
    "shapes",
    [
        "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path (ex:p ex:q) ; sh:reificationRequired true ] .",
        "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path [ sh:inversePath ex:p ] ; sh:reificationRequired true ] .",
        "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:reificationRequired true .",
    ],
)
def test_reification_on_a_non_iri_path_is_a_shapes_graph_error(shapes):
    with pytest.raises(ConstraintLoadError):
        validate(g("ex:a ex:p ex:b . ex:b ex:q 1 ."), g(shapes))


# --- #137 -----------------------------------------------------------------------------------------------------------

RULE_SHAPES = (
    "ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:rule ex:R . "
    "ex:R a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:a ; sh:object [ sh:path ex:b ] ."
)


def test_source_rule_provenance_keeps_a_triple_term_object():
    result = apply_rules(
        g("ex:x a ex:C ; ex:b <<( ex:s ex:p ex:o )>> ."), g(RULE_SHAPES), include_source_rule_provenance=True
    )
    objects = [o for _, _, o in result.inferred_graph]
    assert not any(str(o).startswith("urn:starlayer:tt:") for o in objects)
    reified = [o for _, p, o in result.inferred_graph if p == RDF_REIFIES]
    assert len(reified) == 1
    assert reified[0].object.subject == EX.s


RS_SHAPES = (
    "ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:rule ex:R1 . "
    "ex:R1 a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:a ; sh:object 1 . "
    "ex:RS1 a sh:RuleSet ; sh:hasRule ex:R1 ."
)


@pytest.mark.parametrize("rule_set", ["http://ex/RS1", URIRef("http://ex/RS1"), ["http://ex/RS1"]])
def test_rule_set_accepts_a_plain_str_iri(rule_set):
    result = apply_rules(g("ex:x a ex:C ."), g(RS_SHAPES), rule_set=rule_set)
    assert (EX.x, EX.a) in {(s, p) for s, p, _ in result.inferred_graph}


@pytest.mark.parametrize(
    "shapes",
    [
        "ex:S a sh:NodeShape ; sh:targetClass ex:D .",
        "ex:S a sh:NodeShape ; sh:targetClass ex:D ; "
        "sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:p ; sh:object 1 ] .",
    ],
)
def test_ont_graph_triples_are_not_copied_into_inferred_graph(shapes):
    ont = g("ex:E rdfs:subClassOf ex:D .")
    result = apply_rules(g("ex:a a ex:E ."), g(shapes), ont_graph=ont)
    assert not list(result.inferred_graph.triples((EX.E, None, None)))


COND_SHAPES = """
ex:Cls a sh:NodeShape, rdfs:Class ; sh:property [ sh:path ex:k ; sh:minCount 1 ] .
ex:Sup a sh:NodeShape, rdfs:Class ; sh:property [ sh:path ex:zzz ; sh:minCount 1 ] .
ex:Cls rdfs:subClassOf ex:Sup .
ex:S a sh:NodeShape ; sh:targetClass ex:C ;
  sh:rule [ a sh:TripleRule ; sh:condition ex:Cls ; sh:subject sh:this ; sh:predicate ex:cond ; sh:object 1 ] .
"""


def test_condition_class_shape_also_checks_its_shacl_superclasses():
    result = apply_rules(g("ex:a a ex:C ; ex:k ex:b ."), g(COND_SHAPES))
    assert not list(result.inferred_graph.triples((EX.a, EX.cond, None)))


def test_condition_class_shape_fires_when_superclasses_conform():
    result = apply_rules(g("ex:a a ex:C ; ex:k ex:b ; ex:zzz ex:c ."), g(COND_SHAPES))
    assert list(result.inferred_graph.triples((EX.a, EX.cond, None)))


def test_condition_ignores_a_deactivated_superclass_shape():
    shapes = COND_SHAPES.replace("ex:Sup a sh:NodeShape, rdfs:Class ;", "ex:Sup a sh:NodeShape, rdfs:Class ; sh:deactivated true ;")
    result = apply_rules(g("ex:a a ex:C ; ex:k ex:b ."), g(shapes))
    assert list(result.inferred_graph.triples((EX.a, EX.cond, None)))


@pytest.mark.parametrize("order", ['"a"', '"1.5"', "true"])
def test_non_numeric_order_is_a_rule_load_error(order):
    shapes = (
        "ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:rule [ a sh:TripleRule ; "
        f"sh:order {order} ; sh:subject sh:this ; sh:predicate ex:cond ; sh:object 1 ] ."
    )
    with pytest.raises(RuleLoadError):
        apply_rules(g("ex:a a ex:C ."), g(shapes))


def test_numeric_order_still_works():
    shapes = (
        "ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:rule [ a sh:TripleRule ; "
        "sh:order 2.5 ; sh:subject sh:this ; sh:predicate ex:cond ; sh:object 1 ] ."
    )
    assert list(apply_rules(g("ex:a a ex:C ."), g(shapes)).inferred_graph)
