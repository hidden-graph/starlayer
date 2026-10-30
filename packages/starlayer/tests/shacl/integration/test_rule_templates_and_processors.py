"""SPARQL rule templates (SHACL 1.2 Inference Rules 12) and ``sh:ruleProcessor`` (10).

A template is a class (``sh:SPARQLRuleTemplate``, ``rdfs:subClassOf sh:Rule``) with one ``sh:construct`` and parameters; its
instances are the rules, global or attached to a shape with ``sh:rule``, and each parameter is pre-bound in the query as a variable
named after the local name of its ``sh:path``. A required parameter without a value is a failure. An engine that cannot handle a
``sh:ruleProcessor`` value of a rule or rule set it is to run must report a failure; this one has only the default algorithm.
"""

import pytest
from pyshacl.errors import RuleLoadError
from rdflib import Literal, Namespace
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl import StarShaclSchema

EX = Namespace("http://example.org/")

pyshacl = pytest.importorskip("pyshacl")

PREFIXES = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <http://example.org/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""


def _graph(turtle: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=PREFIXES + turtle, format="turtle")
    return graph


def _apply(shapes: str, data: str, **kwargs):
    return StarShaclSchema(shacl_graph=_graph(shapes)).apply_rules(data_graph=_graph(data), meta_shacl=False, **kwargs)


SYMMETRIC = """
ex:SymmetricPropertyRule a sh:SPARQLRuleTemplate ;
  rdfs:subClassOf sh:Rule ;
  sh:parameter [ a sh:Parameter ; sh:path ex:property ; sh:name "property" ; sh:nodeKind sh:IRI ] ;
  sh:construct "CONSTRUCT { ?o $property ?s . } WHERE { ?s $property ?o . }" .
"""


class TestTemplates:
    def test_global_instances_run_with_their_parameter_pre_bound(self) -> None:
        """Example 14 of the draft: one template, two rules."""
        shapes = SYMMETRIC + """
            ex:MarriedToRule a ex:SymmetricPropertyRule ; ex:property ex:marriedTo .
            ex:OverlapsRule a ex:SymmetricPropertyRule ; ex:property ex:overlaps .
        """
        result = _apply(shapes, "ex:John ex:marriedTo ex:Mary . ex:A ex:overlaps ex:B . ex:X ex:other ex:Y .")

        graph = result.inferred_graph
        assert (EX.Mary, EX.marriedTo, EX.John) in graph
        assert (EX.B, EX.overlaps, EX.A) in graph
        assert (EX.Y, EX.other, EX.X) not in graph

    def test_an_instance_attached_to_a_shape_has_the_focus_node_as_this(self) -> None:
        """Example 15: unit conversion, three parameters, ``$this``."""
        shapes = """
            ex:InferValueViaMultiply a sh:SPARQLRuleTemplate ; rdfs:subClassOf sh:Rule ;
              sh:parameter [ sh:path ex:sourceProperty ] , [ sh:path ex:targetProperty ] , [ sh:path ex:multiplier ] ;
              sh:construct "CONSTRUCT { $this $targetProperty ?t . } WHERE { $this $sourceProperty ?s . BIND (?s * $multiplier AS ?t) }" .
            ex:Measurement a sh:NodeShape ; sh:targetClass ex:Measurement ; sh:rule ex:FeetRule .
            ex:FeetRule a ex:InferValueViaMultiply ; ex:sourceProperty ex:meters ; ex:targetProperty ex:feet ; ex:multiplier 2 .
        """
        result = _apply(shapes, "ex:M1 a ex:Measurement ; ex:meters 3 .")

        assert (EX.M1, EX.feet, Literal(6)) in result.inferred_graph

    def test_a_subclass_of_a_template_has_instances_too(self) -> None:
        shapes = SYMMETRIC + """
            ex:Friendly rdfs:subClassOf ex:SymmetricPropertyRule .
            ex:R a ex:Friendly ; ex:property ex:knows .
        """
        result = _apply(shapes, "ex:a ex:knows ex:b .")

        assert (EX.b, EX.knows, EX.a) in result.inferred_graph

    def test_the_template_prefixes_apply_to_its_instances(self) -> None:
        shapes = """
            ex:Decl a sh:PrefixDeclaration ; sh:prefix "e" ; sh:namespace "http://example.org/"^^xsd:anyURI .
            ex:Prefixes sh:declare ex:Decl .
            ex:T a sh:SPARQLRuleTemplate ; rdfs:subClassOf sh:Rule ; sh:prefixes ex:Prefixes ;
              sh:parameter [ sh:path ex:property ] ;
              sh:construct "CONSTRUCT { ?o $property ?s . } WHERE { ?s $property ?o . ?s a e:Thing }" .
            ex:R a ex:T ; ex:property ex:knows .
        """
        result = _apply(shapes, "ex:a a ex:Thing ; ex:knows ex:b .")

        assert (EX.b, EX.knows, EX.a) in result.inferred_graph

    def test_an_optional_parameter_without_a_value_is_left_unbound(self) -> None:
        shapes = """
            ex:T a sh:SPARQLRuleTemplate ; rdfs:subClassOf sh:Rule ;
              sh:parameter [ sh:path ex:property ] , [ sh:path ex:extra ; sh:optional true ] ;
              sh:construct "CONSTRUCT { ?s ex:seen true . } WHERE { ?s $property ?o . FILTER (!BOUND($extra)) }" .
            ex:R a ex:T ; ex:property ex:knows .
        """
        result = _apply(shapes, "ex:a ex:knows ex:b .")

        assert (EX.a, EX.seen, Literal(True)) in result.inferred_graph

    def test_a_required_parameter_without_a_value_is_a_failure(self) -> None:
        shapes = SYMMETRIC + "ex:R a ex:SymmetricPropertyRule ."

        with pytest.raises(RuleLoadError, match="no value for the required parameter"):
            _apply(shapes, "ex:a ex:knows ex:b .")

    def test_a_required_parameter_without_a_value_is_a_failure_for_an_attached_instance_too(self) -> None:
        shapes = SYMMETRIC + "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:rule ex:R . ex:R a ex:SymmetricPropertyRule ."

        with pytest.raises(RuleLoadError, match="no value for the required parameter"):
            _apply(shapes, "ex:a ex:knows ex:b .")

    def test_a_parameter_with_two_values_is_a_failure(self) -> None:
        shapes = SYMMETRIC + "ex:R a ex:SymmetricPropertyRule ; ex:property ex:knows, ex:likes ."

        with pytest.raises(RuleLoadError, match="several values"):
            _apply(shapes, "ex:a ex:knows ex:b .")

    def test_an_instance_of_two_templates_is_a_failure(self) -> None:
        shapes = SYMMETRIC + """
            ex:Other a sh:SPARQLRuleTemplate ; rdfs:subClassOf sh:Rule ; sh:construct "CONSTRUCT { } WHERE { }" .
            ex:R a ex:SymmetricPropertyRule, ex:Other ; ex:property ex:knows .
        """
        with pytest.raises(RuleLoadError, match="more than one"):
            _apply(shapes, "ex:a ex:knows ex:b .")

    def test_instances_belong_to_rule_sets_and_layers_like_any_rule(self) -> None:
        shapes = SYMMETRIC + """
            ex:Set a sh:RuleSet ; sh:hasRule ex:In .
            ex:In a ex:SymmetricPropertyRule ; ex:property ex:knows .
            ex:Out a ex:SymmetricPropertyRule ; ex:property ex:likes .
        """
        result = _apply(shapes, "ex:a ex:knows ex:b . ex:c ex:likes ex:d .", rule_set=EX.Set)

        assert (EX.b, EX.knows, EX.a) in result.inferred_graph
        assert (EX.d, EX.likes, EX.c) not in result.inferred_graph

    def test_a_deactivated_instance_is_ignored(self) -> None:
        shapes = SYMMETRIC + "ex:R a ex:SymmetricPropertyRule ; sh:deactivated true ; ex:property ex:knows ."

        result = _apply(shapes, "ex:a ex:knows ex:b .")

        assert (EX.b, EX.knows, EX.a) not in result.inferred_graph

    def test_the_shapes_graph_is_left_as_it_was(self) -> None:
        """An attached instance is typed ``sh:SPARQLRule`` only while pySHACL gathers the rules."""
        shapes = _graph(SYMMETRIC + "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:rule ex:R . ex:R a ex:SymmetricPropertyRule ; ex:property ex:knows .")
        before = set(shapes)

        StarShaclSchema(shacl_graph=shapes).apply_rules(data_graph=_graph("ex:a ex:knows ex:b ."), meta_shacl=False)

        assert set(shapes) == before


class TestRuleProcessor:
    RULE = "ex:R a sh:TripleRule ; sh:subject ex:a ; sh:predicate ex:p ; sh:object ex:b ."

    def test_a_rule_that_names_a_processor_is_a_failure(self) -> None:
        with pytest.raises(RuleLoadError, match="rule processor"):
            _apply(self.RULE + " ex:R sh:ruleProcessor ex:Engine .", "ex:n ex:m true .")

    def test_a_string_names_a_processor_too(self) -> None:
        with pytest.raises(RuleLoadError, match="SRL 1.2"):
            _apply(self.RULE + ' ex:R sh:ruleProcessor "SRL 1.2" .', "ex:n ex:m true .")

    def test_a_deactivated_rule_is_not_asked(self) -> None:
        result = _apply(self.RULE + " ex:R sh:ruleProcessor ex:Engine ; sh:deactivated true .", "ex:n ex:m true .")

        assert (EX.a, EX.p, EX.b) not in result.inferred_graph

    def test_a_rule_that_is_not_selected_is_not_asked(self) -> None:
        shapes = self.RULE + """
            ex:Other a sh:TripleRule ; sh:subject ex:c ; sh:predicate ex:p ; sh:object ex:d ; sh:ruleProcessor ex:Engine .
            ex:Set a sh:RuleSet ; sh:hasRule ex:R .
        """
        result = _apply(shapes, "ex:n ex:m true .", rule_set=EX.Set)

        assert (EX.a, EX.p, EX.b) in result.inferred_graph

    def test_a_selected_rule_set_that_names_a_processor_is_a_failure(self) -> None:
        shapes = self.RULE + " ex:Set a sh:RuleSet ; sh:hasRule ex:R ; sh:ruleProcessor ex:Engine ."

        with pytest.raises(RuleLoadError, match="rule processor"):
            _apply(shapes, "ex:n ex:m true .", rule_set=EX.Set)

    def test_a_processor_of_an_included_rule_set_applies_to_the_including_one(self) -> None:
        shapes = self.RULE + """
            ex:Inner a sh:RuleSet ; sh:ruleProcessor ex:Engine .
            ex:Outer a sh:RuleSet ; sh:includesRuleSet ex:Inner ; sh:hasRule ex:R .
        """
        with pytest.raises(RuleLoadError, match="rule processor"):
            _apply(shapes, "ex:n ex:m true .", rule_set=EX.Outer)

    def test_a_rule_set_that_is_not_selected_is_not_asked(self) -> None:
        shapes = self.RULE + " ex:Set a sh:RuleSet ; sh:hasRule ex:R ; sh:ruleProcessor ex:Engine ."

        result = _apply(shapes, "ex:n ex:m true .")

        assert (EX.a, EX.p, EX.b) in result.inferred_graph

    def test_entailment_naming_such_a_rule_set_is_a_failure(self) -> None:
        shapes = self.RULE + " ex:Set a sh:RuleSet ; sh:hasRule ex:R ; sh:ruleProcessor ex:Engine . ex:G a sh:ShapesGraph ; sh:entailment ex:Set ."

        with pytest.raises(RuleLoadError, match="rule processor"):
            StarShaclSchema(shacl_graph=_graph(shapes)).validate(data_graph=_graph("ex:n ex:m true ."))
