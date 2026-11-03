"""The public SHACL API on the native engine: result types and option handling (``starlayer.shacl._adapter``)."""

from __future__ import annotations

import pytest
from rdflib import Graph
from starlayer.shacl_engine.terms import RDF
from pyoxigraph import NamedNode as URIRef
from starlayer.graph.graph.entailment_regimes import ENTAILMENT
from starlayer.graph.oxgraph import OxGraph
from starlayer.shacl import (
    RulesResult,
    StarShaclSchema,
    ValidationResult,
    apply_rules,
    evaluate,
    extract_subgraph,
    validate,
)
from starlayer.shacl._adapter import (
    conformance_disallows_for,
    translate_validate_options,
)
from starlayer.shacl.validation_modes import resolve_mode_options
from starlayer.shacl_engine.terms import SH

PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "
EX = "http://example.org/"
SHAPES = "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:minCount 1 ] ."
BAD = "ex:a a ex:T ."
GOOD = "ex:a a ex:T ; ex:p 1 ."
RULES = (
    "ex: a sh:ShapesGraph ; sh:declare [ sh:prefix 'ex' ; sh:namespace 'http://example.org/' ] . "
    "ex:R a sh:NodeShape ; sh:targetClass ex:T ; sh:rule ex:R1 . "
    "ex:R1 a sh:SPARQLRule ; sh:prefixes ex: ; sh:construct 'CONSTRUCT { $this ex:flag ex:yes } WHERE { }' ."
)


def g(ttl: str, ident: str | None = None) -> OxGraph:
    graph = OxGraph(identifier=URIRef(ident)) if ident else OxGraph()
    graph.parse(data=PFX + ttl, format="turtle")
    return graph


# ---------------------------------------------------------------------------------------------------------------------
# results


class TestResultTypes:
    def test_native_validation_result_has_every_old_field(self):
        result = validate(g(BAD), g(SHAPES))
        assert isinstance(result, ValidationResult)
        assert result.conforms is False
        assert isinstance(result.report_graph, OxGraph)
        assert isinstance(result.report_text, str) and "Conforms: False" in result.report_text
        assert result.data_graph is None
        assert result.diagnostics is not None and result.diagnostics.report_triples == len(result.report_graph)
        assert any(True for _ in result.report_graph.subjects(RDF.type, SH.ValidationReport))

    def test_conforming_native_result(self):
        result = validate(g(GOOD), g(SHAPES))
        assert result.conforms is True and "Conforms: True" in result.report_text

    def test_positional_construction(self):
        result = ValidationResult(True, Graph(), "text", None, None)
        rules = RulesResult(Graph(), result)
        assert rules.validation is result and result.conforms is True

    def test_apply_rules_returns_a_rules_result(self):
        result = apply_rules(g(BAD + RULES), g(RULES))
        assert isinstance(result, RulesResult)
        assert isinstance(result.validation, ValidationResult)
        assert (URIRef(EX + "a"), URIRef(EX + "flag"), URIRef(EX + "yes")) in result.inferred_graph
        assert len(result.inferred_graph) == 1  # only what the rules produced, not the base triples

    def test_apply_rules_does_not_mutate_the_data_graph(self):
        data = g(BAD)
        before = set(data)
        apply_rules(data, g(RULES))
        assert set(data) == before

    def test_apply_rules_rule_set_argument(self):
        shapes = g(
            "ex: a sh:ShapesGraph ; sh:declare [ sh:prefix 'ex' ; sh:namespace 'http://example.org/' ] . "
            "ex:Set a sh:RuleSet ; sh:hasRule ex:r1 . ex:Other a sh:RuleSet ; sh:hasRule ex:r2 . "
            "ex:r1 a sh:SPARQLRule ; sh:prefixes ex: ; "
            "sh:construct 'CONSTRUCT { ex:a ex:p1 ex:v } WHERE { }' . "
            "ex:r2 a sh:SPARQLRule ; sh:prefixes ex: ; "
            "sh:construct 'CONSTRUCT { ex:a ex:p2 ex:v } WHERE { }' ."
        )
        result = apply_rules(g(BAD), shapes, rule_set=URIRef(EX + "Set"))
        predicates = {p for _, p, _ in result.inferred_graph}
        assert predicates == {URIRef(EX + "p1")}

    def test_evaluate_and_extract_subgraph_return_graphs(self):
        shapes = g(SHAPES)
        data = g(GOOD)
        evaluated = evaluate(data, shapes)
        assert (URIRef(EX + "a"), URIRef(EX + "p"), None) in evaluated
        sub = extract_subgraph(data, shapes)
        assert (URIRef(EX + "a"), URIRef(EX + "p"), None) in sub

    def test_schema_close_shape_and_extract_shapes_graph_run_natively(self):
        schema = StarShaclSchema(
            g("ex:M a sh:ShapesGraph ; rdfs:member ex:S . " + SHAPES)
        )
        assert schema.extract_shapes_graph(URIRef(EX + "M")) is not None
        closed = schema.close_shape(URIRef(EX + "S"))
        assert (URIRef(EX + "S"), SH.closed, None) in closed or len(closed) >= len(g(SHAPES))


# ---------------------------------------------------------------------------------------------------------------------
# option translation


class TestTranslation:
    def test_mode_presets(self):
        validation = translate_validate_options(resolve_mode_options("validation"))
        assert validation["rules"] is None and validation["inplace"] is False
        assert "meta_shacl" not in validation
        rules = translate_validate_options(resolve_mode_options("rules"))
        assert rules["rules"] is True and rules["inplace"] is True
        debug = translate_validate_options(resolve_mode_options("debug"))
        assert debug["rules"] is None and debug["inplace"] is False

    def test_advanced_false_means_no_rules(self):
        assert translate_validate_options(resolve_mode_options("validation", overrides={"advanced": False}))["rules"] is False

    @pytest.mark.parametrize(
        ("allow_warnings", "allow_infos", "expected"),
        [(False, False, None), (True, False, SH.Violation), (False, True, SH.Warning), (True, True, SH.Violation)],
    )
    def test_allow_warnings_and_infos_map_to_conformance_disallows(self, allow_warnings, allow_infos, expected):
        assert conformance_disallows_for(allow_warnings, allow_infos) == expected
        options = resolve_mode_options(None, overrides={"allow_warnings": allow_warnings, "allow_infos": allow_infos})
        assert translate_validate_options(options)["conformance_disallows"] == expected

    def test_direct_options_pass_through(self):
        options = resolve_mode_options(
            None, overrides={"abort_on_first": True, "max_validation_depth": 7, "inplace": True, "meta_shacl": True}
        )
        out = translate_validate_options(options)
        assert out["abort_on_first"] is True and out["max_validation_depth"] == 7
        assert out["inplace"] is True and out["meta_shacl"] is True

    @pytest.mark.parametrize(
        "name", ["js", "sparql_mode", "do_owl_imports", "focus_nodes", "use_shapes", "serialize_report_graph", "iterate_rules", "decode_report"]
    )
    def test_options_of_the_earlier_validator_are_unknown(self, name):
        with pytest.raises(TypeError, match=name):
            validate(g(GOOD), g(SHAPES), **{name: True})

    def test_the_rules_preset_runs_rules(self):
        assert translate_validate_options(resolve_mode_options("rules"))["rules"] is True

    def test_allow_warnings_changes_conformance_natively(self):
        shapes = g(
            "ex:S a sh:NodeShape ; sh:targetClass ex:T ; "
            "sh:property [ sh:path ex:p ; sh:minCount 1 ; sh:severity sh:Warning ] ."
        )
        assert validate(g(BAD), shapes).conforms is False
        assert validate(g(BAD), shapes, allow_warnings=True).conforms is True
        assert validate(g(BAD), shapes, allow_infos=True).conforms is False

    def test_inplace_adds_inferred_triples_to_the_callers_graph(self):
        data = g(BAD)
        result = validate(data, g(RULES), mode="rules")
        assert result.data_graph is data
        assert (URIRef(EX + "a"), URIRef(EX + "flag"), URIRef(EX + "yes")) in data

    def test_plain_validation_never_mutates_the_data_graph(self):
        data = g(BAD)
        before = set(data)
        result = validate(data, g(RULES))
        assert result.data_graph is None and set(data) == before

    def test_provenance_options(self):
        result = validate(
            g(GOOD),
            g(SHAPES),
            data_graph_iri=URIRef(EX + "data"),
            shapes_graph_iri=URIRef(EX + "shapes"),
        )
        report = result.report_graph
        node = next(report.subjects(RDF.type, SH.ValidationReport))
        assert (node, SH.usedDataGraph, URIRef(EX + "data")) in report
        assert (node, SH.usedShapesGraph, URIRef(EX + "shapes")) in report

    def test_ont_graph_and_inference_are_visible_to_entailment_only(self):
        shapes = g("ex:S a sh:NodeShape ; sh:targetClass ex:Super ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .")
        data = g("ex:a a ex:Sub .")
        ont = g("ex:Sub rdfs:subClassOf ex:Super .")
        assert validate(data, shapes, ont).conforms is True
        result = validate(data, shapes, ont, inference=ENTAILMENT.RDFS)
        assert result.conforms is False
        assert len(ont) == 1 and (URIRef(EX + "a"), RDF.type, URIRef(EX + "Super")) not in data

    def test_include_used_configuration(self):
        result = validate(g(GOOD), g(SHAPES), include_used_configuration=True)
        assert any(True for _ in result.report_graph.subjects(RDF.type, SH.ProcessorConfiguration))

    def test_unresolved_owl_imports_raise_like_the_old_default(self):
        shapes = g(SHAPES + " <http://example.org/onto> <http://www.w3.org/2002/07/owl#imports> <http://example.org/missing> .")
        with pytest.raises(ValueError, match="owl:imports"):
            validate(g(GOOD), shapes)
        assert validate(g(GOOD), shapes, ignore_imports=True).conforms is True

    def test_shapes_graph_loader_is_used(self):
        shapes = g(SHAPES + " <http://example.org/onto> <http://www.w3.org/2002/07/owl#imports> <http://example.org/mod> .")
        calls = []

        def loader(iri):
            calls.append(iri)
            return g("ex:Extra a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:q ; sh:minCount 1 ] .")

        result = validate(g(GOOD), shapes, shapes_graph_loader=loader)
        assert calls and result.conforms is False  # the imported shape demands ex:q

    def test_meta_shacl_preflight_rejects_a_bad_shapes_graph(self):
        bad = g("ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:minCount 'x' ; sh:path 3 .")
        with pytest.raises(Exception, match="(?i)shacl|shape|constraint|meta"):
            validate(g(GOOD), bad, meta_shacl=True)

    def test_unknown_option_is_a_type_error_before_anything_runs(self):
        with pytest.raises(TypeError, match="not_an_option"):
            validate(g(GOOD), g(SHAPES), not_an_option=1)
