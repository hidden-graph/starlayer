import pytest
from rdflib import Graph, Namespace
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl import StarShaclValidator
from starshacl.meta_shapes import meta_validate

EX = Namespace("http://example.org/")

pyshacl = pytest.importorskip("pyshacl")

# SHACL 1.2 Node Expressions' "Custom Node Expressions" section
# (https://w3c.github.io/data-shapes/shacl12-node-expr/#custom-node-expressions),
# confirmed against the live editor's draft 2026-09-05 (unchanged from the
# 2026-07-21 baseline docs/shacl12-gap-matrix.md already tracks for this
# document - this feature was simply never implemented, not a spec-drift
# gap). Two distinct mechanisms, both wired into starshacl/node_expressions.py:
#
# - Custom List Parameter Functions (sh:ListParameterExpressionFunction):
#   called by using the function's own IRI as a node expression's defining
#   predicate, object a list of argument node expressions - e.g.
#   "[ ex:spacedConcat ( "a" "b" ) ]". Arguments are read inside the
#   function's sh:bodyExpression via "[ shnex:arg 0 ]", "[ shnex:arg 1 ]"
#   (xsd:integer position).
# - Custom Named Parameter Functions (sh:NamedParameterExpressionFunction):
#   called by using one of the function's own *key parameters'* sh:path IRI
#   as the defining predicate, object a single node expression - e.g.
#   "[ ex:average [ shnex:pathValues ex:employee ] ]" where ex:average is
#   ex:AverageExpression's declared sh:keyParameter true parameter path.
#   Read inside sh:bodyExpression via "[ shnex:arg ex:average ]" (the
#   parameter's own sh:path IRI, not an integer).
#
# Both examples below are taken directly from the spec's own worked
# examples (spacedConcat, AverageExpression) - confirmed to produce the
# spec's own stated results, not just "doesn't crash".

PREFIXES = """
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
    @prefix sparql: <http://www.w3.org/ns/sparql#> .
    @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""

SPACED_CONCAT_FUNCTION = """
    ex:spacedConcat a sh:ListParameterExpressionFunction ;
      rdfs:label "Spaced concat expression"@en ;
      sh:bodyExpression [ sparql:concat ( [ shnex:arg 0 ] " " [ shnex:arg 1 ] ) ] ;
      sh:parameter [ a sh:Parameter ; sh:path shnex:arg0 ; sh:name "first string" ] ;
      sh:parameter [ a sh:Parameter ; sh:path shnex:arg1 ; sh:name "second string" ] .
"""

AVERAGE_FUNCTION = """
    ex:AverageExpression a sh:NamedParameterExpressionFunction ;
      rdfs:label "Average expression"@en ;
      sh:parameter ex:AverageExpression-average ;
      sh:bodyExpression [ sparql:divide (
          [ shnex:sum [ shnex:arg ex:average ] ]
          [ shnex:count [ shnex:arg ex:average ] ]
      ) ] .
    ex:AverageExpression-average a sh:Parameter ;
      sh:path ex:average ; sh:name "average" ; sh:keyParameter true .
"""


class TestCustomListParameterFunction:
    def test_spacedconcat_matches_spec_worked_example(self) -> None:
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice a ex:Thing .", format="turtle")

        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
            + SPACED_CONCAT_FUNCTION
            + """
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:expression [ sparql:equals ( [ ex:spacedConcat ( "hello" "world" ) ] "hello world" ) ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, advanced=True)
        assert result.conforms is True

    def test_spacedconcat_wrong_expected_value_does_not_conform(self) -> None:
        # Confirms the check is actually exercising the function's real
        # output, not vacuously true - per this package's CLAUDE.md
        # "verify coverage adversarially" discipline.
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice a ex:Thing .", format="turtle")

        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
            + SPACED_CONCAT_FUNCTION
            + """
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:expression [ sparql:equals ( [ ex:spacedConcat ( "hello" "world" ) ] "wrong" ) ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, advanced=True)
        assert result.conforms is False

    def test_spacedconcat_via_triple_rule(self) -> None:
        # Custom functions must work through pySHACL's *other* node-expression
        # call site too (sh:TripleRule's sh:object), not just sh:expression -
        # both are patched by patch_node_expressions_for_shnex.
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice a ex:Thing .", format="turtle")

        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
            + SPACED_CONCAT_FUNCTION
            + """
            ex:R a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:greeting ;
                        sh:object [ ex:spacedConcat ( "hello" "world" ) ] ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)
        derived = list(result.data_graph.triples((EX.alice, EX.greeting, None)))
        assert len(derived) == 1
        assert str(derived[0][2]) == "hello world"


class TestCustomNamedParameterFunction:
    def test_average_matches_spec_worked_example(self) -> None:
        # ex:alice's employees earn 10 and 20 -> average 15, matching the
        # spec's own AverageExpression/ex:CompanyShape-averageIncome example.
        data = StarLayerGraph()
        data.parse(
            data="""
                @prefix ex: <http://example.org/> .
                ex:alice ex:employee ex:bob, ex:carol .
                ex:bob ex:income 10 .
                ex:carol ex:income 20 .
            """,
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
            + AVERAGE_FUNCTION
            + """
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:expression [ sparql:equals (
                  [ ex:average [ shnex:pathValues ( ex:employee ex:income ) ] ]
                  15
              ) ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, advanced=True)
        assert result.conforms is True

    def test_average_wrong_expected_value_does_not_conform(self) -> None:
        data = StarLayerGraph()
        data.parse(
            data="""
                @prefix ex: <http://example.org/> .
                ex:alice ex:employee ex:bob, ex:carol .
                ex:bob ex:income 10 .
                ex:carol ex:income 20 .
            """,
            format="turtle",
        )
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
            + AVERAGE_FUNCTION
            + """
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:expression [ sparql:equals (
                  [ ex:average [ shnex:pathValues ( ex:employee ex:income ) ] ]
                  999
              ) ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, advanced=True)
        assert result.conforms is False

    def test_body_sees_the_real_focus_node_via_shnex_var(self) -> None:
        # Confirms arg_scope really does seed "focusNode" (per the spec's
        # evalExpr(expr, focusGraph, focusNode, scope) -> evalExpr(body,
        # focusGraph, focusNode, argScope) - focusNode is threaded through
        # unchanged even though argScope otherwise replaces scope wholesale),
        # not just that the call doesn't crash - shnex:var "focusNode" inside
        # the function body must resolve to the shape's actual focus node.
        function = """
            ex:identity a sh:NamedParameterExpressionFunction ;
              sh:parameter ex:identity-value ;
              sh:bodyExpression [ shnex:var "focusNode" ] .
            ex:identity-value a sh:Parameter ; sh:path ex:value ; sh:keyParameter true .
        """
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice a ex:Thing .", format="turtle")
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
            + function
            + """
            ex:R a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:same ;
                        sh:object [ ex:value 42 ] ] .
            """,
            format="turtle",
        )
        result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)
        derived = list(result.data_graph.triples((EX.alice, EX.same, None)))
        assert derived == [(EX.alice, EX.same, EX.alice)]


class TestCustomFunctionMetaShaclWellFormedness:
    def test_list_parameter_function_call_recognized(self) -> None:
        shapes = Graph()
        shapes.parse(
            data=PREFIXES
            + "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
            + SPACED_CONCAT_FUNCTION
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:p ;
                        sh:object [ ex:spacedConcat ( "a" "b" ) ] ] .
            """,
            format="turtle",
        )
        conforms, _report_graph, _report_text = meta_validate(shapes)
        assert conforms is True

    def test_named_parameter_function_call_recognized(self) -> None:
        # Regression guard for the exact gap found live 2026-09-05: this call
        # form's object is a blank node (not an rdf:first-bearing list), so
        # it does not match stsh:NodeExpressionFunctionCallShape's generic
        # structural test the way the list-parameter form above does -
        # confirmed rejected before stsh:NamedParameterFunctionCallShape was
        # added.
        shapes = Graph()
        shapes.parse(
            data=PREFIXES
            + "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
            + AVERAGE_FUNCTION
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:p ;
                        sh:object [ ex:average [ shnex:pathValues ex:employee ] ] ] .
            """,
            format="turtle",
        )
        conforms, _report_graph, _report_text = meta_validate(shapes)
        assert conforms is True

    def test_undeclared_predicate_still_rejected(self) -> None:
        # Confirms stsh:NamedParameterFunctionCallShape's shapes-graph lookup
        # doesn't degrade into the same overly-broad "any single-predicate
        # blank node" match a purely structural test would need - a genuinely
        # unrecognized predicate (not any function's key parameter path) must
        # still be rejected exactly like before this feature existed.
        shapes = Graph()
        shapes.parse(
            data=PREFIXES
            + "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
            + AVERAGE_FUNCTION
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:p ;
                        sh:object [ ex:totallyUndeclared ex:x ] ] .
            """,
            format="turtle",
        )
        with pytest.raises(pyshacl.errors.ReportableRuntimeError):
            meta_validate(shapes)


class TestCustomFunctionAmbiguity:
    def test_blank_node_matching_two_functions_key_parameters_raises(self) -> None:
        # Two distinct sh:NamedParameterExpressionFunctions whose key
        # parameters are both bound on the same blank node - the spec
        # requires key parameters to be globally disjoint, so this is a
        # genuinely malformed shapes graph; eval-time detection (not just
        # meta-shacl) matters because meta_shacl defaults to off.
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice a ex:Thing .", format="turtle")
        shapes = StarLayerGraph()
        shapes.parse(
            data=PREFIXES
            + "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
            + AVERAGE_FUNCTION
            + """
            ex:OtherExpression a sh:NamedParameterExpressionFunction ;
              sh:parameter ex:OtherExpression-other ;
              sh:bodyExpression [ shnex:arg ex:other ] .
            ex:OtherExpression-other a sh:Parameter ; sh:path ex:other ; sh:keyParameter true .

            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:expression [ ex:average ex:x ; ex:other ex:y ] .
            """,
            format="turtle",
        )
        with pytest.raises(ValueError, match="more than one custom"):
            StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, advanced=True)
