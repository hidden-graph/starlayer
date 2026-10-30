"""``sh:entailment`` naming rules (SHACL 1.2 Inference Rules, section 6).

``sh:RulesEntailment`` runs every rule of the shapes graph before validation; a rule set IRI runs only that set and the sets it
includes; several values run together as one set. The validated graph is the base graph plus the inferred triples, and the
caller's data is not changed. Both used to be refused as unsupported entailment regimes.
"""

import pytest
from rdflib import Namespace
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl import StarShaclSchema

EX = Namespace("http://example.org/")

pyshacl = pytest.importorskip("pyshacl")

PREFIXES = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <http://example.org/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
"""

SHAPES = """
ex:Needs a sh:NodeShape ; sh:targetNode ex:n ;
  sh:property [ sh:path ex:p ; sh:minCount 1 ] ,
              [ sh:path ex:q ; sh:minCount 1 ] .
ex:SetP a sh:RuleSet ; sh:hasRule ex:GiveP .
ex:SetQ a sh:RuleSet ; sh:hasRule ex:GiveQ .
ex:SetBoth a sh:RuleSet ; sh:includesRuleSet ex:SetP, ex:SetQ .
ex:GiveP a sh:TripleRule ; sh:subject ex:n ; sh:predicate ex:p ; sh:object ex:a .
ex:GiveQ a sh:TripleRule ; sh:subject ex:n ; sh:predicate ex:q ; sh:object ex:b .
"""


def _validate(*entailment: str):
    declared = "".join(f"ex:Shapes sh:entailment {value} .\n" for value in entailment)
    shapes = StarLayerGraph()
    shapes.parse(data=PREFIXES + "ex:Shapes a sh:ShapesGraph .\n" + declared + SHAPES, format="turtle")
    data = StarLayerGraph()
    data.parse(data=PREFIXES + "ex:n ex:marker true .", format="turtle")
    before = set(data)
    result = StarShaclSchema(shacl_graph=shapes).validate(data_graph=data)
    assert set(data) == before, "the base graph is not changed"
    return result


def test_without_the_declaration_the_rules_are_not_run_before_validation() -> None:
    assert not _validate().conforms


def test_rules_entailment_runs_every_rule_before_validation() -> None:
    assert _validate("sh:RulesEntailment").conforms


def test_a_rule_set_runs_only_its_own_rules() -> None:
    result = _validate("ex:SetP")

    assert not result.conforms
    assert result.report_text.count("Constraint Violation") == 1, "p was inferred, q was not"


def test_a_rule_set_includes_the_sets_it_includes() -> None:
    assert _validate("ex:SetBoth").conforms


def test_several_rule_sets_run_together() -> None:
    assert _validate("ex:SetP", "ex:SetQ").conforms


def test_rules_entailment_among_other_values_runs_every_rule() -> None:
    assert _validate("sh:RulesEntailment", "ex:SetP").conforms


def test_rules_entailment_combines_with_an_entailment_regime() -> None:
    from starlayer.graph.graph.entailment_regimes import ENTAILMENT

    shapes = StarLayerGraph()
    shapes.parse(
        data=PREFIXES
        + """
        ex:Shapes a sh:ShapesGraph ; sh:entailment sh:RulesEntailment, <%s> .
        ex:Needs a sh:NodeShape ; sh:targetClass ex:Animal ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .
        ex:Give a sh:SPARQLRule ;
          sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { ?s ex:p ex:a . } WHERE { ?s a ex:Animal . }" .
        """
        % ENTAILMENT.RDFS,
        format="turtle",
    )
    data = StarLayerGraph()
    data.parse(data=PREFIXES + "ex:Dog rdfs:subClassOf ex:Animal . ex:rex a ex:Dog .", format="turtle")

    assert StarShaclSchema(shacl_graph=shapes).validate(data_graph=data).conforms


def test_an_iri_that_is_neither_a_regime_nor_a_rule_set_is_still_refused() -> None:
    with pytest.raises(ValueError, match="Unsupported entailment"):
        _validate("ex:NotARuleSet")


def test_apply_rules_on_such_a_shapes_graph_does_not_run_the_rules_twice_over() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=PREFIXES + "ex:Shapes a sh:ShapesGraph ; sh:entailment sh:RulesEntailment .\n" + SHAPES, format="turtle")
    data = StarLayerGraph()
    data.parse(data=PREFIXES + "ex:n ex:marker true .", format="turtle")

    result = StarShaclSchema(shacl_graph=shapes).apply_rules(data_graph=data)

    assert (EX.n, EX.p, EX.a) in result.inferred_graph
    assert result.validation.conforms
