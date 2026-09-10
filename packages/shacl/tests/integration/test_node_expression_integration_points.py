"""SHACL 1.2 Node Expressions - integration points beyond the operator
library itself.

Found 2026-09-06 via a full re-read of the live SHACL 1.2 Node Expressions
spec's "Getting Started", "Constraint Components", and "Dynamic SHACL"
sections - none of which the earlier pass covered (that pass exhaustively
tested the ~22 shnex:/77 sparql: *operators*, but never checked *where else*
a node expression is allowed to appear). Confirmed live, against the real
validate() pipeline, that a spec-endorsed pattern as basic as "use a node
expression to compute a shape's target nodes" - the spec's own opening
example - silently produced garbage (a raw blank node treated as a bogus
target) rather than working or erroring clearly. This file locks in the
three real bugs found and fixed as a result:

1. sh:targetNode holding a node expression (not sh:select-wrapped) was never
   evaluated at all - see StarShaclValidator._augment_shapes_with_new_target_types.
2. sh:expression's scope never bound "value" (the current value node), and
   its "focusNode" binding was actually the *value* node on property shapes
   (pySHACL's own bug) - see _patch_expression_constraint_for_value_scope.
3. sh:deactivated holding a node expression crashed shape loading outright
   (pySHACL hard-requires a Literal) - see
   StarShaclValidator._strip_deactivated_node_expressions. A first fix
   (2026-09-05) evaluated the expression once *globally* (no focus node at
   all), based on the node-expr document's own single passing mention of
   sh:deactivated - wrong, caught by a direct user question: SHACL 1.2
   *Core*'s actual normative definition ("Deactivating Shapes and
   Constraints") is evalExpr(expr, data graph, focus node, {}), evaluated
   once **per focus node**, making sh:deactivated a dynamic per-target
   filter, not a shape-wide switch. Corrected via
   _patch_shape_focus_nodes_for_deactivated_expression.

sh:values and sh:nodeByExpression were also re-checked in the same pass and
found to already work correctly - not re-tested exhaustively here (see
test_shnex_node_expressions.py and test_node_by_expression.py).
"""

import pytest
from rdflib import Namespace
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl import StarShaclValidator

EX = Namespace("http://example.org/")

pyshacl = pytest.importorskip("pyshacl")

PREFIXES = """
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
    @prefix sparql: <http://www.w3.org/ns/sparql#> .
"""


class TestTargetNodeExpression:
    def test_spec_getting_started_example(self) -> None:
        # The spec's own opening ("Getting Started") worked example:
        # ex:EstonianCompanyShape's targets are computed dynamically as
        # every ex:Company instance whose ex:headQuarterCountry is
        # ex:Estonia.
        data = StarLayerGraph()
        data.parse(
            data="""
                @prefix ex: <http://example.org/> .
                ex:acme a ex:Company ; ex:headQuarterCountry ex:Estonia .
                ex:foo a ex:Company ; ex:headQuarterCountry ex:Germany .
            """,
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:EstonianCompanyShape a sh:NodeShape ;
              sh:targetNode [ shnex:nodes [ shnex:instancesOf ex:Company ] ;
                              shnex:filterShape [ sh:property [ sh:path ex:headQuarterCountry ;
                                                                 sh:hasValue ex:Estonia ] ] ] ;
              sh:class ex:EstonianEntity .
            """,
            format="turtle",
        )
        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
        assert result.conforms is False
        assert "ex:acme" in result.report_text or str(EX.acme) in result.report_text

    def test_nodesmatching_form(self) -> None:
        # shnex:nodesMatching - the spec's own alternative to
        # sh:targetWhere, "usable in arbitrary node expressions" (unlike
        # sh:targetWhere, which is a fixed SHACL Core predicate).
        data = StarLayerGraph()
        data.parse(
            data="""
                @prefix ex: <http://example.org/> .
                ex:acme a ex:Company ; ex:employee ex:e1, ex:e2 .
                ex:small a ex:Company ; ex:employee ex:e3 .
            """,
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:LargeCompanyShape a sh:NodeShape ;
              sh:targetNode [ shnex:nodesMatching [ a sh:NodeShape ; sh:class ex:Company ;
                                sh:property [ sh:path ex:employee ; sh:minCount 2 ] ] ] ;
              sh:class ex:LargeCo .
            """,
            format="turtle",
        )
        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
        assert result.conforms is False

    def test_empty_result_removes_target_entirely(self) -> None:
        # A node expression legitimately producing zero target nodes must
        # mean "this shape targets nothing" - not fall back to treating the
        # node expression's own blank node as a (bogus) literal target.
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice a ex:Thing .", format="turtle")
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:NodeShape ;
              sh:targetNode [ shnex:nodesMatching [ a sh:NodeShape ; sh:class ex:NoSuchClass ] ] ;
              sh:class ex:Nobody .
            """,
            format="turtle",
        )
        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
        assert result.conforms is True

    def test_select_based_target_node_still_works(self) -> None:
        # Regression guard: the sh:select form (found/fixed in an earlier
        # pass) must keep working unaffected by this new shnex:/sparql: form.
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice a ex:Thing .", format="turtle")
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:NodeShape ;
              sh:targetNode [ sh:select "SELECT ?this WHERE { ?this a <http://example.org/Thing> }" ] ;
              sh:class ex:Nobody .
            """,
            format="turtle",
        )
        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
        assert result.conforms is False

    def test_targetwhere_still_works_unaffected(self) -> None:
        # Regression guard for the exact bug found while building this fix:
        # sh:targetWhere's own resolution mechanism (_nodes_conforming_to)
        # stuffs arbitrary data-graph blank nodes into sh:targetNode as
        # plain candidates, unrelated to node expressions - one of them
        # (here, a nested property shape's own sh:path-bearing blank node,
        # picked up because data graph and shapes graph share content) was
        # wrongly mis-evaluated by pySHACL's old-form node-expression
        # fallback before the shnex:/sparql:-only gate was added.
        data = StarLayerGraph()
        data.parse(
            data="""
                @prefix ex: <http://example.org/> .
                ex:alice a ex:Person ; ex:age 19 ; ex:votedFor ex:bob .
                ex:bob a ex:Person ; ex:age 20 .
            """,
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:AdultShape a sh:NodeShape ;
              sh:targetWhere [ sh:class ex:Person ;
                                sh:property [ sh:path ex:age ; sh:minCount 1 ; sh:minInclusive 18 ] ] ;
              sh:property [ sh:path ex:votedFor ; sh:minCount 1 ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
        # ex:bob is targeted (an adult) and has no ex:votedFor -> violation.
        # ex:alice is also an adult and does have ex:votedFor -> no violation.
        assert result.conforms is False
        assert result.report_text.count("Focus Node:") == 1


class TestExpressionScope:
    def test_value_binds_to_current_value_node(self) -> None:
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice ex:score 42 .", format="turtle")
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:PropertyShape ; sh:targetNode ex:alice ; sh:path ex:score ;
              sh:expression [ sparql:equals ( [ shnex:var "value" ] 42 ) ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, advanced=True)
        assert result.conforms is True

    def test_focusnode_is_the_real_focus_not_the_value(self) -> None:
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice ex:score 42 .", format="turtle")
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:PropertyShape ; sh:targetNode ex:alice ; sh:path ex:score ;
              sh:expression [ sparql:sameTerm ( [ shnex:var "focusNode" ] ex:alice ) ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, advanced=True)
        assert result.conforms is True

    def test_focusnode_still_wrong_would_fail_this(self) -> None:
        # Mutation-style guard: if focusNode were still (wrongly) bound to
        # the value node, this assertion would flip - confirms the test
        # above is actually discriminating, not vacuously true.
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice ex:score 42 .", format="turtle")
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:PropertyShape ; sh:targetNode ex:alice ; sh:path ex:score ;
              sh:expression [ sparql:sameTerm ( [ shnex:var "focusNode" ] 42 ) ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, advanced=True)
        assert result.conforms is False

    def test_spec_iban_worked_example(self) -> None:
        # The spec's own worked example under sh:expression's own
        # definition, using both "value" and "focusNode" together.
        data = StarLayerGraph()
        data.parse(
            data="""
                @prefix ex: <http://example.org/> .
                ex:ValidGermanAccount a ex:Account ; ex:ibanNumber "DE123456" ; ex:country ex:Germany .
                ex:InvalidGermanAccount a ex:Account ; ex:ibanNumber "DE987654" ; ex:country ex:Estonia .
                ex:Estonia a ex:Country ; ex:code "ee" .
                ex:Germany a ex:Country ; ex:code "de" .
            """,
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:AccountShape a sh:NodeShape ; sh:targetClass ex:Account ; sh:property ex:AccountShape-ibanNumber .
            ex:AccountShape-ibanNumber a sh:PropertyShape ; sh:path ex:ibanNumber ; sh:datatype xsd:string ;
              sh:expression [ sparql:strstarts (
                  [ shnex:var "value" ]
                  [ sparql:ucase ( [ shnex:pathValues ( ex:country ex:code ) ; shnex:nodes [ shnex:var "focusNode" ] ] ) ]
              ) ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, advanced=True)
        assert result.conforms is False
        assert result.report_text.count("Focus Node:") == 1
        assert "InvalidGermanAccount" in result.report_text


class TestDeactivatedExpression:
    def test_evaluated_per_focus_node_not_globally(self) -> None:
        # The real, corrected semantics (SHACL 1.2 Core's "Deactivating
        # Shapes and Constraints": evalExpr(expr, data graph, focus node,
        # {})) - two targets, only one of which is legacy, so only that one
        # is excluded. The first (wrong) implementation evaluated this
        # globally and would have deactivated the *whole* shape for every
        # target, or none - never varying per node the way this test proves
        # it now does.
        data = StarLayerGraph()
        data.parse(
            data="""
                @prefix ex: <http://example.org/> .
                ex:alice a ex:Person ; ex:age 12 ; ex:legacyAccount true .
                ex:dave a ex:Person ; ex:age 12 ; ex:legacyAccount false .
            """,
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:AdultOnlyShape a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:deactivated [ shnex:exists [ shnex:filterShape ex:IsLegacy ;
                                              shnex:nodes [ shnex:var "focusNode" ] ] ] ;
              sh:property [ sh:path ex:age ; sh:minInclusive 18 ] .
            ex:IsLegacy a sh:NodeShape ; sh:property [ sh:path ex:legacyAccount ; sh:hasValue true ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
        # ex:alice (legacy) is excluded despite being 12 - no violation for her.
        # ex:dave (not legacy) is still checked and correctly violates.
        assert result.conforms is False
        assert result.report_text.count("Focus Node:") == 1
        assert "dave" in result.report_text
        assert "alice" not in result.report_text

    def test_false_for_every_target_leaves_shape_fully_active(self) -> None:
        # Before this fix, a node-expression sh:deactivated value crashed
        # shape *loading* outright (pySHACL: "must be a Literal") - this
        # confirms the fix produces a real, correctly-active shape, not just
        # "doesn't crash".
        data = StarLayerGraph()
        data.parse(
            data="""
                @prefix ex: <http://example.org/> .
                ex:alice a ex:Thing ; ex:name "x" .
            """,
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Thing ;
              sh:deactivated [ sparql:equals ( 1 2 ) ] ;
              sh:property [ sh:path ex:name ; sh:minLength 5 ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
        assert result.conforms is False  # shape active - "x" is too short

    def test_global_condition_deactivates_every_target_uniformly(self) -> None:
        # A degenerate, but legitimate, case of per-focus-node evaluation:
        # an expression that doesn't actually vary by focus node (e.g. a
        # feature flag looked up elsewhere in the data graph) deactivates
        # every target the same way - the correct per-node mechanism still
        # supports a shape-wide toggle, it's just no longer the *only*
        # thing it can express.
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:AdultOnlyShape a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:deactivated [ sparql:logical-not (
                  [ shnex:pathValues ex:strictAgeCheck ; shnex:focusNode ex:FeatureFlags ]
              ) ] ;
              sh:property [ sh:path ex:age ; sh:minInclusive 18 ] .
            """,
            format="turtle",
        )

        flag_off = StarLayerGraph()
        flag_off.parse(
            data="""
                @prefix ex: <http://example.org/> .
                ex:FeatureFlags ex:strictAgeCheck false .
                ex:alice a ex:Person ; ex:age 12 .
                ex:dave a ex:Person ; ex:age 12 .
            """,
            format="turtle",
        )
        result_off = StarShaclValidator().validate(data_graph=flag_off, shacl_graph=shapes, meta_shacl=False)
        assert result_off.conforms is True

        flag_on = StarLayerGraph()
        flag_on.parse(
            data="""
                @prefix ex: <http://example.org/> .
                ex:FeatureFlags ex:strictAgeCheck true .
                ex:alice a ex:Person ; ex:age 12 .
                ex:dave a ex:Person ; ex:age 12 .
            """,
            format="turtle",
        )
        result_on = StarShaclValidator().validate(data_graph=flag_on, shacl_graph=shapes, meta_shacl=False)
        assert result_on.conforms is False
        assert result_on.report_text.count("Focus Node:") == 2

    def test_plain_literal_deactivated_still_works(self) -> None:
        # Regression guard: ordinary (non-expression) sh:deactivated must be
        # completely unaffected by this new candidate-detection logic.
        data = StarLayerGraph()
        data.parse(
            data="""
                @prefix ex: <http://example.org/> .
                ex:alice a ex:Thing ; ex:name "x" .
            """,
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Thing ;
              sh:deactivated true ;
              sh:property [ sh:path ex:name ; sh:minLength 5 ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
        assert result.conforms is True
