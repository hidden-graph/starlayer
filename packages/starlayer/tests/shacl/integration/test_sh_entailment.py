"""tests/shacl/integration/test_sh_entailment.py

End-to-end coverage for sh:entailment (SHACL 1.2 Core §1.4), via
StarShaclSchema.validate()/apply_rules() - see starlayer.shacl.entailment's
own module docstring for the spec citations this is built from.

Deliberately NOT testing plain rdfs:subClassOf-driven class membership
(e.g. a Dog/Canine example) - SHACL's own "SHACL type"/"SHACL instance"
definitions already give that unconditionally, with no sh:entailment
declaration needed at all (see test_subclass_reasoning_scope.py). These
tests instead use rdfs:domain, which genuinely needs an entailment regime
to take effect - a real, not vacuous, exercise of this feature.
"""

import pytest
from rdflib import Namespace
from rdflib.namespace import RDF

from starlayer.graph.graph.entailment_regimes import ENTAILMENT
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl import StarShaclSchema

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")

SHAPES = """
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    ex:EmployeeShape a sh:NodeShape ;
        sh:targetClass ex:Employee ;
        sh:property [ sh:path ex:name ; sh:minCount 1 ] .
"""

DATA = """
    @prefix ex: <http://example.org/> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    ex:worksAt rdfs:domain ex:Employee .
    ex:alice ex:worksAt ex:Acme .
"""


def _shapes() -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=SHAPES, format="turtle")
    return g


def _data() -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=DATA, format="turtle")
    return g


class TestValidateRespectsShEntailment:
    def test_without_sh_entailment_alice_is_not_targeted(self) -> None:
        result = StarShaclSchema(shacl_graph=_shapes()).validate(data_graph=_data(), meta_shacl=False)
        assert result.conforms is True

    def test_with_sh_entailment_alice_becomes_a_target_and_violates(self) -> None:
        shapes = _shapes()
        shapes.add((EX.EmployeeShape, SH.entailment, ENTAILMENT.RDFS))

        result = StarShaclSchema(shacl_graph=shapes).validate(data_graph=_data(), meta_shacl=False)

        assert result.conforms is False
        assert "ex:alice" in result.report_text or "alice" in result.report_text

    def test_plain_validation_profile_never_mutates_the_callers_data_graph(self) -> None:
        # Regression coverage: apply_entailment() used to mutate data_graph
        # in place unconditionally, silently breaking the "validation"
        # profile's own documented never-mutate-the-caller's-data
        # guarantee - confirmed live (len(data) grew after a plain
        # validate() call) before apply_entailment() gained its own
        # inplace= parameter.
        shapes = _shapes()
        shapes.add((EX.EmployeeShape, SH.entailment, ENTAILMENT.RDFS))
        data = _data()
        before = set(data)

        StarShaclSchema(shacl_graph=shapes).validate(data_graph=data, meta_shacl=False)

        assert set(data) == before
        assert (EX.alice, RDF.type, EX.Employee) not in data

    def test_unsupported_regime_declared_raises(self) -> None:
        shapes = _shapes()
        shapes.add((EX.EmployeeShape, SH.entailment, ENTAILMENT.D))

        with pytest.raises(ValueError, match="Unsupported entailment regime"):
            StarShaclSchema(shacl_graph=shapes).validate(data_graph=_data(), meta_shacl=False)


class TestApplyRulesSeesEntailmentBeforeRulesRun:
    """apply_rules() gets "entailment before rules" for free, since
    shape-attached sh:rule execution happens inside the same validate()
    call that now applies sh:entailment first - see
    starlayer/shacl/CLAUDE.md's own dated entry for the full design.

    The entailed triple itself (ex:alice a ex:Employee) is never returned -
    result.inferred_graph is strictly the rules' own output (the spec's
    "inference graph"); entailment only needed to be visible to let the
    rule *fire* in the first place."""

    def test_rule_targeting_entailed_class_fires(self) -> None:
        shapes = StarLayerGraph()
        shapes.parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix sh: <http://www.w3.org/ns/shacl#> .
                ex:EmployeeRuleShape a sh:NodeShape ;
                    sh:targetClass ex:Employee ;
                    sh:rule [
                        a sh:TripleRule ;
                        sh:subject sh:this ;
                        sh:predicate ex:flagged ;
                        sh:object true ;
                    ] ;
                    sh:entailment <http://www.w3.org/ns/entailment/RDFS> .
            """,
            format="turtle",
        )
        data = _data()

        result = StarShaclSchema(shacl_graph=shapes).apply_rules(data_graph=data, meta_shacl=False)

        assert (EX.alice, RDF.type, EX.Employee) not in result.inferred_graph
        assert any(result.inferred_graph.triples((EX.alice, EX.flagged, None)))


class TestApplyRulesValidatesGlobalRuleOutput:
    """The other gap this same session's design closes, independent of
    sh:entailment: apply_rules()'s conforms/report_graph used to only ever
    reflect the state BEFORE the global sh:SPARQLRule pass - triples that
    pass produces were never actually validated at all. See
    starlayer/shacl/CLAUDE.md's dated entry and the comment at
    apply_rules()'s own final re-validation call site."""

    def test_conforms_reflects_a_shape_violated_only_by_global_rule_output(self) -> None:
        shapes = StarLayerGraph()
        shapes.parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix sh: <http://www.w3.org/ns/shacl#> .
                # Global rule - not attached to any shape's own sh:rule -
                # types anyone with an ex:friend relation as ex:HasFriend.
                ex:HasFriendRule a sh:SPARQLRule ;
                  sh:construct \"\"\"
                    PREFIX ex: <http://example.org/>
                    CONSTRUCT { ?s a ex:HasFriend . }
                    WHERE { ?s ex:friend ?o . }
                  \"\"\" .
                ex:HasFriendShape a sh:NodeShape ;
                    sh:targetClass ex:HasFriend ;
                    sh:property [ sh:path ex:verifiedBy ; sh:minCount 1 ] .
            """,
            format="turtle",
        )
        data = StarLayerGraph()
        data.parse(
            data="""
                @prefix ex: <http://example.org/> .
                ex:bob ex:friend ex:caren .
            """,
            format="turtle",
        )

        result = StarShaclSchema(shacl_graph=shapes).apply_rules(data_graph=data, meta_shacl=False)

        assert (EX.bob, RDF.type, EX.HasFriend) in result.inferred_graph
        assert result.validation.conforms is False


class TestTargetNodesRespectsEntailment:
    """2026-10-08: target_nodes() closed a consistency gap - it's now the
    fifth processing function to see sh:entailment/inference=, matching
    validate()/apply_rules()/evaluate()/extract_subgraph(). Same DATA/SHAPES
    fixture as TestValidateRespectsShEntailment above: ex:worksAt
    rdfs:domain ex:Employee genuinely needs an entailment regime to put
    ex:alice in ex:EmployeeShape's own sh:targetClass membership - a
    vacuous rdfs:subClassOf/"SHACL type" case wouldn't actually exercise
    this."""

    def test_without_entailment_alice_is_not_a_target(self) -> None:
        from starlayer.shacl.engine import target_nodes

        nodes = target_nodes(data_graph=_data(), shacl_graph=_shapes(), shape_node=EX.EmployeeShape)
        assert nodes == ()

    def test_inference_keyword_makes_alice_a_target(self) -> None:
        from starlayer.shacl.engine import target_nodes

        nodes = target_nodes(
            data_graph=_data(), shacl_graph=_shapes(), shape_node=EX.EmployeeShape, inference=ENTAILMENT.RDFS
        )
        assert nodes == (EX.alice,)

    def test_declared_sh_entailment_makes_alice_a_target_with_no_keyword(self) -> None:
        from starlayer.shacl.engine import target_nodes

        shapes = _shapes()
        shapes.add((EX.EmployeeShape, SH.entailment, ENTAILMENT.RDFS))

        nodes = target_nodes(data_graph=_data(), shacl_graph=shapes, shape_node=EX.EmployeeShape)
        assert nodes == (EX.alice,)

    def test_neither_data_graph_nor_ont_graph_is_mutated(self) -> None:
        from starlayer.shacl.engine import target_nodes

        data = _data()
        ont = StarLayerGraph()
        before_data, before_ont = set(data), set(ont)

        target_nodes(
            data_graph=data,
            shacl_graph=_shapes(),
            shape_node=EX.EmployeeShape,
            ont_graph=ont,
            inference=ENTAILMENT.RDFS,
        )

        assert set(data) == before_data
        assert set(ont) == before_ont

    def test_starshaclschema_method_threads_its_own_bound_ont_graph(self) -> None:
        ont = StarLayerGraph()
        ont.parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
                ex:worksAt rdfs:domain ex:Employee .
            """,
            format="turtle",
        )
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice ex:worksAt ex:Acme .", format="turtle")

        schema = StarShaclSchema(shacl_graph=_shapes(), ont_graph=ont, inference=ENTAILMENT.RDFS)
        nodes = schema.target_nodes(data_graph=data, shape_node=EX.EmployeeShape)
        assert nodes == (EX.alice,)
