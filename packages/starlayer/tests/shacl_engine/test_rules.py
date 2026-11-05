"""Unit tests for ``starlayer.shacl_engine.rules`` (SHACL 1.2 inference rules)."""

from __future__ import annotations

import pytest
from pyoxigraph import NamedNode as URIRef
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.shacl_engine.rules import (
    InferredView,
    RuleError,
    apply_rules,
    entailment_selection,
    validate_with_rules,
)
from starlayer.shacl_engine.terms import integer

EX = "http://example.com/ns#"
PRE = """
@prefix ex: <http://example.com/ns#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex: a sh:ShapesGraph ; sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.com/ns#" ] .
"""


def g(ttl: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=PRE + ttl, format="turtle")
    return graph


def ex(name: str) -> URIRef:
    return URIRef(EX + name)


def snapshot(graph) -> set:
    return set(graph.triples((None, None, None)))


CHAIN = """
ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:rule ex:R1 .
ex:R1 a sh:SPARQLRule ; sh:prefixes ex: ; sh:construct "CONSTRUCT { $this ex:p 1 } WHERE { }" .
ex:a a ex:C .
"""


def test_base_graph_untouched_and_overlay_has_inferred() -> None:
    data = g(CHAIN)
    before = snapshot(data)
    res = apply_rules(data)
    assert snapshot(data) == before
    assert (ex("a"), ex("p"), integer(1)) in res.view
    assert res.inferred == {t for t in snapshot(res.view) if t not in before}
    assert isinstance(res.view, InferredView) and res.ok


def test_view_protocol() -> None:
    data = g("ex:a ex:q ex:b .")
    view = InferredView(data)
    assert view.add((ex("a"), ex("q"), ex("c")))
    assert not view.add((ex("a"), ex("q"), ex("b")))  # already in base
    assert set(view.objects(ex("a"), ex("q"))) == {ex("b"), ex("c")}
    assert set(view.subjects(ex("q"), ex("c"))) == {ex("a")}
    assert (ex("a"), ex("q"), ex("c")) in view and (ex("a"), ex("q"), ex("c")) not in data
    assert len(list(view.predicate_objects(ex("a")))) == 2
    assert len(view.sparql_query("SELECT ?o WHERE { <http://example.com/ns#a> <http://example.com/ns#q> ?o }").rows) == 2
    view.remove((ex("a"), ex("q"), ex("c")))
    assert len(view.sparql_query("SELECT ?o WHERE { <http://example.com/ns#a> <http://example.com/ns#q> ?o }").rows) == 1


def test_deactivated_rule_and_shape() -> None:
    assert apply_rules(g(CHAIN + "ex:R1 sh:deactivated true .")).inferred == frozenset()
    assert apply_rules(g(CHAIN + "ex:S sh:deactivated true .")).inferred == frozenset()


def test_iterates_to_fixpoint() -> None:
    data = g(
        """
        ex:R a sh:SPARQLRule ; sh:prefixes ex: ;
          sh:construct "CONSTRUCT { ?a ex:reach ?c } WHERE { ?a ex:next|ex:reach ?b . ?b ex:next|ex:reach ?c }" .
        ex:n1 ex:next ex:n2 . ex:n2 ex:next ex:n3 . ex:n3 ex:next ex:n4 .
        """
    )
    res = apply_rules(data)
    assert (ex("n1"), ex("reach"), ex("n4")) in res.inferred
    assert res.iterations >= 2


def test_non_terminating_rule_fails() -> None:
    data = g(CHAIN.replace("$this ex:p 1", "$this ex:p _:fresh"))
    with pytest.raises(RuleError):
        apply_rules(data, max_iterations=5)
    res = apply_rules(data, max_iterations=5, raise_on_failure=False)
    assert not res.ok and res.failures


def test_layers_run_in_order() -> None:
    data = g(
        """
        ex:L1 a sh:SPARQLRule ; sh:prefixes ex: ; sh:layer 1 ;
          sh:construct "CONSTRUCT { ex:r ex:late ex:x } WHERE { FILTER NOT EXISTS { ex:r ex:early ex:x } }" .
        ex:L0 a sh:SPARQLRule ; sh:prefixes ex: ; sh:layer 0 ;
          sh:construct "CONSTRUCT { ex:r ex:early ex:x } WHERE { }" .
        """
    )
    res = apply_rules(data)
    assert (ex("r"), ex("early"), ex("x")) in res.inferred
    assert (ex("r"), ex("late"), ex("x")) not in res.inferred  # layer 1 saw layer 0's triple


def test_order_groups_do_not_see_each_other() -> None:
    data = g(
        """
        ex:A a sh:SPARQLRule ; sh:prefixes ex: ; sh:runOnce true ;
          sh:construct "CONSTRUCT { ex:r ex:a 1 } WHERE { }" .
        ex:B a sh:SPARQLRule ; sh:prefixes ex: ; sh:runOnce true ;
          sh:construct "CONSTRUCT { ex:r ex:b 1 } WHERE { ex:r ex:a 1 }" .
        """
    )
    res = apply_rules(data)  # same order group: B evaluates against the graph before A's output
    assert (ex("r"), ex("b"), integer(1)) not in res.inferred
    data2 = g(
        """
        ex:A a sh:SPARQLRule ; sh:prefixes ex: ; sh:runOnce true ; sh:order 1 ;
          sh:construct "CONSTRUCT { ex:r ex:a 1 } WHERE { }" .
        ex:B a sh:SPARQLRule ; sh:prefixes ex: ; sh:runOnce true ; sh:order 2 ;
          sh:construct "CONSTRUCT { ex:r ex:b 1 } WHERE { ex:r ex:a 1 }" .
        """
    )
    assert any(t[1] == ex("b") for t in apply_rules(data2).inferred)


def test_run_once_per_focus_node_with_blank_nodes() -> None:
    data = g(
        """
        ex:S1 a sh:NodeShape ; sh:targetNode ex:a ; sh:rule ex:R .
        ex:S2 a sh:NodeShape ; sh:targetNode ex:a ; sh:rule ex:R .
        ex:R a sh:SPARQLRule ; sh:prefixes ex: ; sh:runOnce true ;
          sh:construct "CONSTRUCT { $this ex:made _:m } WHERE { }" .
        """
    )
    assert len([t for t in apply_rules(data).inferred if t[1] == ex("made")]) == 1


def test_condition_with_class_superclasses() -> None:
    data = g(
        """
        ex:Base a sh:NodeShape, rdfs:Class ; sh:property [ sh:path ex:ok ; sh:minCount 1 ] .
        ex:Cond a sh:NodeShape, rdfs:Class ; rdfs:subClassOf ex:Base .
        ex:S a sh:NodeShape ; sh:targetNode ex:a, ex:b ; sh:rule ex:R .
        ex:R a sh:SPARQLRule ; sh:prefixes ex: ; sh:condition ex:Cond ;
          sh:construct "CONSTRUCT { $this ex:p 1 } WHERE { }" .
        ex:a ex:ok true .
        """
    )
    res = apply_rules(data)
    assert {t[0] for t in res.inferred} == {ex("a")}


def test_temp_triples_removed() -> None:
    data = g(
        """
        ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:rule ex:R1, ex:R2 .
        ex:R1 a sh:SPARQLRule ; sh:prefixes ex: ; sh:layer 0 ; sh:runOnce true ; sh:construct
          "CONSTRUCT { $this ex:tmp 1 . _:r <http://www.w3.org/ns/shacl#tempTriple> true . _:r <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> <<( $this ex:tmp 1 )>> } WHERE { }" .
        ex:R2 a sh:SPARQLRule ; sh:prefixes ex: ; sh:layer 1 ;
          sh:construct "CONSTRUCT { $this ex:final 2 } WHERE { $this ex:tmp 1 }" .
        """
    )
    res = apply_rules(data)
    assert {t[1] for t in res.inferred} == {ex("final")}


def test_rule_set_selection_and_inclusion() -> None:
    ttl = """
    ex:Set1 a sh:RuleSet ; sh:hasRule ex:R1 ; sh:includesRuleSet ex:Set2 .
    ex:Set2 a sh:RuleSet ; sh:hasRule ex:R2 .
    ex:R1 a sh:SPARQLRule ; sh:prefixes ex: ; sh:construct "CONSTRUCT { ex:s ex:one 1 } WHERE { }" .
    ex:R2 a sh:SPARQLRule ; sh:prefixes ex: ; sh:construct "CONSTRUCT { ex:s ex:two 1 } WHERE { }" .
    ex:R3 a sh:SPARQLRule ; sh:prefixes ex: ; sh:construct "CONSTRUCT { ex:s ex:three 1 } WHERE { }" .
    """
    preds = lambda r: {t[1] for t in r.inferred}  # noqa: E731
    assert preds(apply_rules(g(ttl))) == {ex("one"), ex("two"), ex("three")}
    assert preds(apply_rules(g(ttl), rule_sets=[ex("Set1")])) == {ex("one"), ex("two")}
    assert preds(apply_rules(g(ttl), rule_sets=[ex("Set2")])) == {ex("two")}


def test_entailment_selection_and_validate_hook() -> None:
    assert entailment_selection(g(CHAIN)) == (False, [])
    data = g(CHAIN + "ex: sh:entailment sh:RulesEntailment .")
    assert entailment_selection(data) == (True, [])
    outcome, res = validate_with_rules(data)
    assert res is not None and res.inferred and outcome.conforms
    _, none = validate_with_rules(g(CHAIN))
    assert none is None


def test_validation_sees_inferred_triples() -> None:
    data = g(
        CHAIN
        + """
        ex:Check a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .
        """
    )
    from starlayer.shacl_engine import validate

    assert not validate(data).conforms
    outcome, _ = validate_with_rules(data, rules=True)
    assert outcome.conforms


def test_sparql_rule_template() -> None:
    data = g(
        """
        ex:Tmpl a sh:SPARQLRuleTemplate ; rdfs:subClassOf sh:Rule ;
          sh:parameter [ sh:path ex:target ] ;
          sh:prefixes ex: ;
          sh:construct "CONSTRUCT { $this ex:tag ?target } WHERE { }" .
        ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:rule ex:Inst .
        ex:Inst a ex:Tmpl ; ex:target "t" .
        """
    )
    assert any(t[1] == ex("tag") for t in apply_rules(data).inferred)


def test_unsupported_rule_processor_fails() -> None:
    with pytest.raises(RuleError):
        apply_rules(g(CHAIN + "ex:R1 sh:ruleProcessor ex:Custom ."))


def test_rule_without_type_fails() -> None:
    with pytest.raises(RuleError):
        apply_rules(g("ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:rule ex:Bad ."))


def test_triple_rule() -> None:
    pytest.importorskip(
        "starlayer.shacl_engine.expressions", reason="sh:TripleRule needs node expressions (expressions.py not present yet)"
    )
    data = g(
        """
        ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:rule ex:T .
        ex:T a sh:TripleRule ; sh:predicate ex:flag ; sh:object true .
        ex:a a ex:C .
        """
    )
    res = apply_rules(data)
    assert any(t[0] == ex("a") and t[1] == ex("flag") for t in res.inferred)
