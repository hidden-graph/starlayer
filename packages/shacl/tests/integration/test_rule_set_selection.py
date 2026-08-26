"""sh:RuleSet / sh:hasRule / sh:includesRuleSet (SHACL 1.2 SPARQL Extensions
section 8.2.1, added upstream 2026-08-21, re-verified live 2026-08-26):
StarShaclValidator.apply_rules(..., rule_set=<IRI>) restricts execution to
a named, caller-selected subset of a shapes graph's rules. The spec's own
default rule set ("the set of all rules in the graph") is exactly
apply_rules()'s pre-existing no-`rule_set` behavior, so that case is a pure
regression guard here, not new functionality.

Covers both rule-execution paths, since each needed its own hook:
- global (shape-independent) sh:SPARQLRule, filtered in
  validator.py::_global_sparql_rules directly (starshacl's own code).
- shape-attached sh:rule (sh:TripleRule/sh:SPARQLRule), filtered via
  _patch_rule_apply_for_rule_set_filtering wrapping TripleRule.apply/
  SPARQLRule.apply - the same style, and independent of,
  _patch_rule_apply_for_source_rule_provenance.
"""

import pytest
from rdflib import RDF, Namespace
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl import StarShaclValidator

EX = Namespace("http://example.org/")

pyshacl = pytest.importorskip("pyshacl")

_GLOBAL_RULE_SHAPES = """
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .

    ex:RuleSetA a sh:RuleSet ; sh:hasRule ex:RuleA .
    ex:RuleSetB a sh:RuleSet ; sh:hasRule ex:RuleB .

    ex:RuleA a sh:SPARQLRule ;
      sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { ?s ex:markedByA true } WHERE { ?s ex:knows ?o }" .
    ex:RuleB a sh:SPARQLRule ;
      sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { ?s ex:markedByB true } WHERE { ?s ex:knows ?o }" .
"""


def _data_with_knows() -> StarLayerGraph:
    data = StarLayerGraph()
    data.add((EX.alice, EX.knows, EX.bob))
    return data


class TestGlobalRulesPath:
    def test_no_rule_set_runs_every_rule(self) -> None:
        shapes = StarLayerGraph()
        shapes.parse(data=_GLOBAL_RULE_SHAPES, format="turtle")
        result = StarShaclValidator().apply_rules(data_graph=_data_with_knows(), shacl_graph=shapes, meta_shacl=False)
        assert (EX.alice, EX.markedByA, None) in result.data_graph
        assert (EX.alice, EX.markedByB, None) in result.data_graph

    def test_rule_set_restricts_to_its_own_members(self) -> None:
        shapes = StarLayerGraph()
        shapes.parse(data=_GLOBAL_RULE_SHAPES, format="turtle")
        result = StarShaclValidator().apply_rules(
            data_graph=_data_with_knows(), shacl_graph=shapes, meta_shacl=False, rule_set=EX.RuleSetA
        )
        assert (EX.alice, EX.markedByA, None) in result.data_graph
        assert (EX.alice, EX.markedByB, None) not in result.data_graph

    def test_different_rule_set_selects_different_rules(self) -> None:
        shapes = StarLayerGraph()
        shapes.parse(data=_GLOBAL_RULE_SHAPES, format="turtle")
        result = StarShaclValidator().apply_rules(
            data_graph=_data_with_knows(), shacl_graph=shapes, meta_shacl=False, rule_set=EX.RuleSetB
        )
        assert (EX.alice, EX.markedByA, None) not in result.data_graph
        assert (EX.alice, EX.markedByB, None) in result.data_graph

    def test_transitive_includes_rule_set_with_cycle(self) -> None:
        # A includes B includes C includes A (cycle) - closure from A must
        # still reach all three rules exactly once, not infinite-loop or
        # give an order-dependent answer.
        shapes = StarLayerGraph()
        shapes.parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix sh: <http://www.w3.org/ns/shacl#> .

                ex:RuleSetA a sh:RuleSet ; sh:hasRule ex:RuleA ; sh:includesRuleSet ex:RuleSetB .
                ex:RuleSetB a sh:RuleSet ; sh:hasRule ex:RuleB ; sh:includesRuleSet ex:RuleSetC .
                ex:RuleSetC a sh:RuleSet ; sh:hasRule ex:RuleC ; sh:includesRuleSet ex:RuleSetA .

                ex:RuleA a sh:SPARQLRule ;
                  sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { ?s ex:markedByA true } WHERE { ?s ex:knows ?o }" .
                ex:RuleB a sh:SPARQLRule ;
                  sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { ?s ex:markedByB true } WHERE { ?s ex:knows ?o }" .
                ex:RuleC a sh:SPARQLRule ;
                  sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { ?s ex:markedByC true } WHERE { ?s ex:knows ?o }" .
            """,
            format="turtle",
        )
        result = StarShaclValidator().apply_rules(
            data_graph=_data_with_knows(), shacl_graph=shapes, meta_shacl=False, rule_set=EX.RuleSetA
        )
        assert (EX.alice, EX.markedByA, None) in result.data_graph
        assert (EX.alice, EX.markedByB, None) in result.data_graph
        assert (EX.alice, EX.markedByC, None) in result.data_graph

    def test_empty_rule_set_runs_nothing_and_does_not_error(self) -> None:
        shapes = StarLayerGraph()
        shapes.parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix sh: <http://www.w3.org/ns/shacl#> .
                ex:EmptyRuleSet a sh:RuleSet .
                ex:RuleA a sh:SPARQLRule ;
                  sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { ?s ex:markedByA true } WHERE { ?s ex:knows ?o }" .
            """,
            format="turtle",
        )
        result = StarShaclValidator().apply_rules(
            data_graph=_data_with_knows(), shacl_graph=shapes, meta_shacl=False, rule_set=EX.EmptyRuleSet
        )
        assert (EX.alice, EX.markedByA, None) not in result.data_graph


class TestShapeAttachedRulesPath:
    _SHAPES = """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .

        ex:RuleSetA a sh:RuleSet ; sh:hasRule ex:TripleRuleA .

        ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:rule ex:TripleRuleA , ex:TripleRuleB .

        ex:TripleRuleA a sh:TripleRule ;
          sh:subject sh:this ; sh:predicate ex:taggedByA ; sh:object true .
        ex:TripleRuleB a sh:TripleRule ;
          sh:subject sh:this ; sh:predicate ex:taggedByB ; sh:object true .
    """

    def _data_person(self) -> StarLayerGraph:
        data = StarLayerGraph()
        data.add((EX.alice, RDF.type, EX.Person))
        return data

    def test_no_rule_set_runs_every_shape_attached_rule(self) -> None:
        shapes = StarLayerGraph()
        shapes.parse(data=self._SHAPES, format="turtle")
        result = StarShaclValidator().apply_rules(data_graph=self._data_person(), shacl_graph=shapes, meta_shacl=False)
        assert (EX.alice, EX.taggedByA, None) in result.data_graph
        assert (EX.alice, EX.taggedByB, None) in result.data_graph

    def test_rule_set_restricts_shape_attached_rules_too(self) -> None:
        shapes = StarLayerGraph()
        shapes.parse(data=self._SHAPES, format="turtle")
        result = StarShaclValidator().apply_rules(
            data_graph=self._data_person(), shacl_graph=shapes, meta_shacl=False, rule_set=EX.RuleSetA
        )
        assert (EX.alice, EX.taggedByA, None) in result.data_graph
        assert (EX.alice, EX.taggedByB, None) not in result.data_graph

    def test_rule_set_and_source_rule_provenance_compose(self) -> None:
        # The two contextvar-gated patches (this one, and the pre-existing
        # sh:sourceRule provenance one) wrap the same two classes
        # independently - confirm they compose correctly rather than one
        # silently overriding the other.
        shapes = StarLayerGraph()
        shapes.parse(data=self._SHAPES, format="turtle")
        result = StarShaclValidator().apply_rules(
            data_graph=self._data_person(),
            shacl_graph=shapes,
            meta_shacl=False,
            rule_set=EX.RuleSetA,
            include_source_rule_provenance=True,
        )
        assert (EX.alice, EX.taggedByA, None) in result.data_graph
        assert (EX.alice, EX.taggedByB, None) not in result.data_graph
        # Only RuleA actually ran, so only RuleA should have provenance -
        # RuleB was filtered out before pySHACL's real apply() ever ran,
        # so there's nothing for the provenance diff to have observed.
        from rdflib import Namespace as _NS

        SH = _NS("http://www.w3.org/ns/shacl#")
        source_rules = {o for _, _, o in result.data_graph.triples((None, SH.sourceRule, None))}
        assert EX.TripleRuleA in source_rules
        assert EX.TripleRuleB not in source_rules
