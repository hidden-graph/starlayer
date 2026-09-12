"""StarShaclValidator.evaluate() - a third, independent processing mode
alongside validate() (checks conformance, never mutates) and apply_rules()
(executes sh:rule, materializes real triples).

Designed 2026-09-07 in direct conversation: pySHACL has no notion of this
mode at all - sh:values ("virtual"/on-demand computed properties, per the
SHACL 1.2 Node Expressions spec's own "Getting Started" framing: "typically
compute[d] only on demand... do not lead to the creation of triples in the
data graph") is only ever wired into Shape.value_nodes() (pySHACL's
constraint-evaluation path), so a caller who just wants to *read* a computed
value - without validating anything, and without it ever touching a real
rule - had no way to do that at all before evaluate() existed.

evaluate() returns a *throwaway* graph: a copy of data_graph with every
sh:values-declared virtual property computed and merged in, for every focus
node it applies to. The caller's own data_graph is never mutated, and the
result is documented as not meant to be persisted.
"""

import pytest
from rdflib import Literal, Namespace
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl import EvaluationResult, StarShaclValidator

EX = Namespace("http://example.org/")

pyshacl = pytest.importorskip("pyshacl")

PREFIXES = """
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
    @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""


class TestBasicComputation:
    def test_computed_value_appears_in_result(self) -> None:
        data = StarLayerGraph()
        data.parse(
            data="""
                @prefix ex: <http://example.org/> .
                ex:alice a ex:Person ; ex:friend ex:bob, ex:carol .
            """,
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:property [ sh:path ex:friendCount ; sh:datatype xsd:integer ;
                            sh:values [ shnex:count [ shnex:pathValues ex:friend ] ] ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().evaluate(data_graph=data, shacl_graph=shapes)
        assert isinstance(result, EvaluationResult)
        assert [v.toPython() for v in result.data_graph.objects(EX.alice, EX.friendCount)] == [2]

    def test_original_data_graph_never_mutated(self) -> None:
        data = StarLayerGraph()
        data.parse(
            data="@prefix ex: <http://example.org/> . ex:alice a ex:Person ; ex:friend ex:bob .",
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:property [ sh:path ex:friendCount ; sh:values [ shnex:count [ shnex:pathValues ex:friend ] ] ] .
            """,
            format="turtle",
        )
        before = set(data)
        result = StarShaclValidator().evaluate(data_graph=data, shacl_graph=shapes)
        assert set(data) == before  # untouched
        assert result.data_graph is not data  # a genuinely different object
        assert (EX.alice, EX.friendCount, None) not in [(s, p, None) for s, p, _o in data]

    def test_multiple_focus_nodes_each_get_their_own_value(self) -> None:
        data = StarLayerGraph()
        data.parse(
            data="""
                @prefix ex: <http://example.org/> .
                ex:alice a ex:Person ; ex:friend ex:bob, ex:carol .
                ex:dave a ex:Person ; ex:friend ex:erin .
            """,
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:property [ sh:path ex:friendCount ; sh:values [ shnex:count [ shnex:pathValues ex:friend ] ] ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().evaluate(data_graph=data, shacl_graph=shapes)
        assert [v.toPython() for v in result.data_graph.objects(EX.alice, EX.friendCount)] == [2]
        assert [v.toPython() for v in result.data_graph.objects(EX.dave, EX.friendCount)] == [1]

    def test_multivalued_computed_property_becomes_multiple_triples(self) -> None:
        data = StarLayerGraph()
        data.parse(
            data="@prefix ex: <http://example.org/> . ex:alice a ex:Person ; ex:friend ex:bob, ex:carol .",
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:property [ sh:path ex:friendEcho ; sh:values [ shnex:pathValues ex:friend ] ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().evaluate(data_graph=data, shacl_graph=shapes)
        assert set(result.data_graph.objects(EX.alice, EX.friendEcho)) == {EX.bob, EX.carol}

    def test_standalone_property_shape_with_its_own_direct_target(self) -> None:
        # sh:values isn't only reachable via a node shape's sh:property - a
        # PropertyShape can carry its own direct sh:targetNode/sh:targetClass
        # too, per ordinary SHACL Core target semantics.
        data = StarLayerGraph()
        data.parse(
            data="@prefix ex: <http://example.org/> . ex:alice ex:friend ex:bob, ex:carol .",
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:PS a sh:PropertyShape ; sh:targetNode ex:alice ; sh:path ex:friendCount ;
              sh:values [ shnex:count [ shnex:pathValues ex:friend ] ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().evaluate(data_graph=data, shacl_graph=shapes)
        assert [v.toPython() for v in result.data_graph.objects(EX.alice, EX.friendCount)] == [2]

    def test_sh_values_unions_with_a_conflicting_stored_value_not_replaces_it(self) -> None:
        # SHACL 1.2 Core's own "Value Nodes of Property Shapes" algorithm is
        # explicit: real path-based values and sh:values-computed values are
        # both unconditionally *added* to the same set (only sh:defaultValue
        # is conditional, on the set still being empty) - a UNION, not a
        # replacement. Confirmed live 2026-09-08, prompted by a direct user
        # question ("is the draft standard clean on what should happen?"):
        # an earlier version of both this test and the implementation
        # assumed "replace", checked only against this project's own prior
        # (also-wrong) validate() behavior rather than the actual spec text.
        data = StarLayerGraph()
        data.parse(
            data="""
                @prefix ex: <http://example.org/> .
                ex:alice a ex:Person ; ex:friend ex:bob, ex:carol ; ex:friendCount 99 .
            """,
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:property [ sh:path ex:friendCount ; sh:datatype xsd:integer ;
                            sh:values [ shnex:count [ shnex:pathValues ex:friend ] ] ;
                            sh:hasValue 2 ] .
            """,
            format="turtle",
        )
        # validate() sees the UNION {99, 2} - sh:hasValue 2 conforms because
        # 2 (the computed value) is a member of that set, not because 99 (the
        # real stored value) was ever discarded.
        validate_result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
        assert validate_result.conforms is True

        # sh:hasValue 99 (the *real* stored value) must equally conform -
        # confirming the stored value is still genuinely part of the value
        # set, not merely "not yet proven absent".
        shapes_99 = StarLayerGraph()
        shapes_99.parse(
            data=PREFIXES
            + """
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:property [ sh:path ex:friendCount ; sh:datatype xsd:integer ;
                            sh:values [ shnex:count [ shnex:pathValues ex:friend ] ] ;
                            sh:hasValue 99 ] .
            """,
            format="turtle",
        )
        validate_result_99 = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes_99, meta_shacl=False)
        assert validate_result_99.conforms is True

        eval_result = StarShaclValidator().evaluate(data_graph=data, shacl_graph=shapes)
        assert sorted(v.toPython() for v in eval_result.data_graph.objects(EX.alice, EX.friendCount)) == [2, 99]
        # The original data_graph itself is still untouched either way.
        assert list(data.objects(EX.alice, EX.friendCount)) == [Literal(99)]
        assert set(eval_result.data_graph.objects(EX.alice, EX.friend)) == {EX.bob, EX.carol}

    def test_no_sh_values_present_is_a_harmless_no_op(self) -> None:
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice a ex:Person .", format="turtle")
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES + "ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:name ] .",
            format="turtle",
        )
        result = StarShaclValidator().evaluate(data_graph=data, shacl_graph=shapes)
        assert set(result.data_graph) == set(data)
        assert result.data_graph is not data

    def test_complex_path_is_skipped_not_crashed(self) -> None:
        # Only a simple, single-predicate sh:path is supported - a property
        # path expression (sequence, here) is silently skipped rather than
        # raising, matching this module's general tolerance for unsupported
        # forms elsewhere.
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice ex:friend ex:bob .", format="turtle")
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:property [ sh:path ( ex:friend ex:friend ) ; sh:values [ shnex:pathValues ex:friend ] ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().evaluate(data_graph=data, shacl_graph=shapes)
        assert set(result.data_graph) == set(data)

    def test_requires_a_shapes_graph(self) -> None:
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice a ex:Person .", format="turtle")
        with pytest.raises(ValueError, match="shapes graph"):
            StarShaclValidator().evaluate(data_graph=data, shacl_graph=None)


class TestIsolationFromApplyRules:
    """The design premise, confirmed live before evaluate() was built:
    sh:values-computed properties stay purely virtual against apply_rules() -
    a rule reading one via ordinary path traversal finds nothing, and the
    only way a rule ever produces a real triple with the "same" value is by
    recomputing it itself, entirely independently of any sh:values
    declaration elsewhere. evaluate() must not change this - it's a
    read-only projection, never a rule-execution side channel.
    """

    def test_rule_reading_virtual_property_by_path_finds_nothing(self) -> None:
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice ex:friend ex:bob, ex:carol .", format="turtle")
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:property [ sh:path ex:friendCount ; sh:values [ shnex:count [ shnex:pathValues ex:friend ] ] ] .
            ex:R a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:echoedCount ;
                        sh:object [ shnex:pathValues ex:friendCount ] ] .
            """,
            format="turtle",
        )
        rule_result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)
        assert list(rule_result.data_graph.objects(EX.alice, EX.echoedCount)) == []
        assert list(rule_result.data_graph.triples((None, EX.friendCount, None))) == []

    def test_rule_recomputing_the_same_expression_materializes_a_real_triple(self) -> None:
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice ex:friend ex:bob, ex:carol .", format="turtle")
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:R a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:friendCount ;
                        sh:object [ shnex:count [ shnex:pathValues ex:friend ] ] ] .
            """,
            format="turtle",
        )
        rule_result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)
        assert [v.toPython() for v in rule_result.data_graph.objects(EX.alice, EX.friendCount)] == [2]

    def test_evaluate_and_apply_rules_compose_without_interference(self) -> None:
        # A shapes graph declaring both an sh:values virtual property and an
        # unrelated sh:rule - evaluate() sees the virtual value, apply_rules()
        # produces its own rule-derived triple, neither affects the other.
        data = StarLayerGraph()
        data.parse(
            data="@prefix ex: <http://example.org/> . ex:alice a ex:Person ; ex:friend ex:bob, ex:carol .",
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:property [ sh:path ex:friendCount ; sh:values [ shnex:count [ shnex:pathValues ex:friend ] ] ] .
            ex:R a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:greeting ; sh:object "hi" ] .
            """,
            format="turtle",
        )
        eval_result = StarShaclValidator().evaluate(data_graph=data, shacl_graph=shapes)
        rule_result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

        assert [v.toPython() for v in eval_result.data_graph.objects(EX.alice, EX.friendCount)] == [2]
        assert list(eval_result.data_graph.objects(EX.alice, EX.greeting)) == []  # evaluate() never runs rules

        assert list(rule_result.data_graph.objects(EX.alice, EX.friendCount)) == []  # apply_rules() never sees sh:values
        assert [v.toPython() for v in rule_result.data_graph.objects(EX.alice, EX.greeting)] == ["hi"]


class TestDefaultValueFallback:
    """sh:defaultValue's step 3 of the "Value Nodes of Property Shapes"
    algorithm, on the evaluate() side - mirrors test_sh_values.py's
    TestDefaultValueFallback, which covers the same algorithm for
    validate().

    Found missing entirely (2026-09-10) while building a notebook example
    that put sh:values and sh:defaultValue on the same property shape:
    evaluate() silently produced no ex:nickname triple at all for a focus
    node with neither a stored value nor a non-empty sh:values computation,
    instead of falling back to sh:defaultValue - both because the original
    loop only ever iterated shapes carrying sh:values (a defaultValue-only
    shape was never visited at all), and because even a visited shape never
    consulted sh:defaultValue once its sh:values computation came back
    empty. This is a real, previously-undetected inconsistency between
    evaluate() and validate() (which already got this right via
    _patch_shape_value_nodes_for_sh_values) - evaluate()'s entire premise is
    exposing the same computation validate() already uses, so the two
    silently disagreeing was a genuine bug, not a documentation gap.
    """

    def test_default_value_fills_in_when_neither_stored_nor_computed_exists(self) -> None:
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:carol a ex:Person .", format="turtle")
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:property [ sh:path ex:nickname ;
                            sh:values [ shnex:pathValues ex:preferredName ] ;
                            sh:defaultValue "Anonymous" ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().evaluate(data_graph=data, shacl_graph=shapes)
        assert list(result.data_graph.objects(EX.carol, EX.nickname)) == [Literal("Anonymous")]
        assert list(data.objects(EX.carol, EX.nickname)) == []  # original graph untouched

    def test_default_value_is_skipped_once_sh_values_computes_something(self) -> None:
        data = StarLayerGraph()
        data.parse(
            data='@prefix ex: <http://example.org/> . ex:bob a ex:Person ; ex:preferredName "Bobby" .',
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:property [ sh:path ex:nickname ;
                            sh:values [ shnex:pathValues ex:preferredName ] ;
                            sh:defaultValue "Anonymous" ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().evaluate(data_graph=data, shacl_graph=shapes)
        assert list(result.data_graph.objects(EX.bob, EX.nickname)) == [Literal("Bobby")]

    def test_default_value_is_skipped_once_a_real_stored_value_exists(self) -> None:
        # Even with sh:values present but producing nothing for this focus
        # node, a real stored value alone is enough to keep sh:defaultValue
        # from firing.
        data = StarLayerGraph()
        data.parse(
            data='@prefix ex: <http://example.org/> . ex:dave a ex:Person ; ex:nickname "Davey" .',
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:property [ sh:path ex:nickname ;
                            sh:values [ shnex:pathValues ex:preferredName ] ;
                            sh:defaultValue "Anonymous" ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().evaluate(data_graph=data, shacl_graph=shapes)
        assert list(result.data_graph.objects(EX.dave, EX.nickname)) == [Literal("Davey")]

    def test_default_value_alone_with_no_sh_values_at_all_still_works(self) -> None:
        # A defaultValue-only property shape (no sh:values triple at all)
        # must still be visited - the original bug's loop only ever
        # iterated sh:values triples, so this shape was silently skipped
        # entirely.
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:erin a ex:Person .", format="turtle")
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:property [ sh:path ex:role ; sh:defaultValue "guest" ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().evaluate(data_graph=data, shacl_graph=shapes)
        assert list(result.data_graph.objects(EX.erin, EX.role)) == [Literal("guest")]


class TestDefaultValueAsNodeExpression:
    """sh:defaultValue's value is itself a node expression per SHACL 1.2
    Core's algorithm, not just a plain constant - mirrors
    test_sh_values.py's identically-named class for validate(). Found
    missing (2026-09-11) the same way: evaluate() added the raw,
    unevaluated blank node as a bogus value instead of evaluating it.
    """

    def test_default_value_as_a_path_expression_falls_back_to_a_sibling_property(self) -> None:
        data = StarLayerGraph()
        data.parse(
            data='@prefix ex: <http://example.org/> . ex:alice ex:firstName "Alexandra" .',
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:property [ sh:path ex:nickname ; sh:defaultValue [ shnex:pathValues ex:firstName ] ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().evaluate(data_graph=data, shacl_graph=shapes)
        assert list(result.data_graph.objects(EX.alice, EX.nickname)) == [Literal("Alexandra")]

    def test_default_value_as_a_path_expression_is_skipped_once_a_real_value_exists(self) -> None:
        data = StarLayerGraph()
        data.parse(
            data="""
                @prefix ex: <http://example.org/> .
                ex:bob ex:firstName "Robert" ; ex:nickname "Bobby" .
            """,
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
              sh:property [ sh:path ex:nickname ; sh:defaultValue [ shnex:pathValues ex:firstName ] ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().evaluate(data_graph=data, shacl_graph=shapes)
        assert list(result.data_graph.objects(EX.bob, EX.nickname)) == [Literal("Bobby")]
