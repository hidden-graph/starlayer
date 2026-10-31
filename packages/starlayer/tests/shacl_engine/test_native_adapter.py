"""The opt-in adapter that runs the old public SHACL API on the native engine (``starlayer.shacl.native_adapter``)."""

from __future__ import annotations

import pytest
from rdflib import RDF, Graph, URIRef
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl import (
    RulesResult,
    StarShaclSchema,
    ValidationResult,
    apply_rules,
    evaluate,
    extract_subgraph,
    native_adapter,
    validate,
    validate_each,
)
from starlayer.shacl.native_adapter import (
    ENV_VAR,
    NativeUnsupported,
    selected,
    translate_validate_options,
)
from starlayer.shacl.validation_modes import resolve_mode_options
from tests.shacl.w3c_shacl12.namespaces import SH

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


def g(ttl: str, ident: str | None = None) -> StarLayerGraph:
    graph = StarLayerGraph(identifier=URIRef(ident)) if ident else StarLayerGraph()
    graph.parse(data=PFX + ttl, format="turtle12")
    return graph


@pytest.fixture(autouse=True)
def _no_ambient_engine(monkeypatch):
    """Selection is the subject here: start every test with the variable unset."""
    monkeypatch.delenv(ENV_VAR, raising=False)


# ---------------------------------------------------------------------------------------------------------------------
# selection


class TestSelection:
    def test_default_is_pyshacl(self):
        assert selected() == "pyshacl"
        result = validate(g(BAD), g(SHAPES))
        assert (result.engine, result.engine_fallback_reason) == ("pyshacl", None)

    def test_env_var_selects_native(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "native")
        assert selected() == "native"
        assert validate(g(BAD), g(SHAPES)).engine == "native"

    def test_env_var_is_case_and_space_insensitive(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, " Native ")
        assert selected() == "native"

    def test_explicit_keyword_beats_env_var(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "native")
        assert validate(g(BAD), g(SHAPES), engine="pyshacl").engine == "pyshacl"
        monkeypatch.setenv(ENV_VAR, "pyshacl")
        assert validate(g(BAD), g(SHAPES), engine="native").engine == "native"

    def test_schema_default_beats_env_var_and_keyword_beats_schema(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "pyshacl")
        schema = StarShaclSchema(g(SHAPES), engine="native")
        assert schema.validate(g(BAD)).engine == "native"
        assert schema.validate(g(BAD), engine="pyshacl").engine == "pyshacl"
        monkeypatch.setenv(ENV_VAR, "native")
        assert StarShaclSchema(g(SHAPES)).validate(g(BAD)).engine == "native"
        assert StarShaclSchema(g(SHAPES), engine="pyshacl").validate(g(BAD)).engine == "pyshacl"

    @pytest.mark.parametrize("bad", ["rust", "NATIVE2", 3])
    def test_unknown_engine_is_a_value_error(self, bad):
        with pytest.raises(ValueError, match="native"):
            selected(bad)
        with pytest.raises(ValueError, match="native"):
            StarShaclSchema(g(SHAPES), engine=bad)

    def test_unknown_env_value_is_a_value_error(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "turbo")
        with pytest.raises(ValueError, match=ENV_VAR):
            selected()

    def test_empty_env_value_means_default(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "")
        assert selected() == "pyshacl"

    def test_validate_each_forwards_engine(self):
        results = validate_each([g(BAD), g(GOOD)], g(SHAPES), engine="native")
        assert [r.engine for r in results.values()] == ["native", "native"]
        assert [r.conforms for r in results.values()] == [False, True]

    def test_schema_validate_each_uses_the_schema_default(self):
        results = StarShaclSchema(g(SHAPES), engine="native").validate_each([g(BAD), g(GOOD)])
        assert [r.engine for r in results.values()] == ["native", "native"]


# ---------------------------------------------------------------------------------------------------------------------
# result types


class TestResultTypes:
    def test_native_validation_result_has_every_old_field(self):
        result = validate(g(BAD), g(SHAPES), engine="native")
        assert isinstance(result, ValidationResult)
        assert result.conforms is False
        assert isinstance(result.report_graph, StarLayerGraph)
        assert isinstance(result.report_text, str) and "Conforms: False" in result.report_text
        assert result.data_graph is None
        assert result.diagnostics is not None and result.diagnostics.report_triples == len(result.report_graph)
        assert result.engine == "native" and result.engine_fallback_reason is None
        assert any(True for _ in result.report_graph.subjects(RDF.type, SH.ValidationReport))

    def test_conforming_native_result(self):
        result = validate(g(GOOD), g(SHAPES), engine="native")
        assert result.conforms is True and "Conforms: True" in result.report_text

    def test_old_positional_construction_still_works(self):
        result = ValidationResult(True, Graph(), "text", None, None)
        assert (result.engine, result.engine_fallback_reason) == ("pyshacl", None)
        rules = RulesResult(Graph(), result)
        assert (rules.engine, rules.engine_fallback_reason) == ("pyshacl", None)

    def test_apply_rules_returns_a_rules_result(self):
        result = apply_rules(g(BAD + RULES), g(RULES), engine="native")
        assert isinstance(result, RulesResult) and result.engine == "native"
        assert isinstance(result.validation, ValidationResult) and result.validation.engine == "native"
        assert (URIRef(EX + "a"), URIRef(EX + "flag"), URIRef(EX + "yes")) in result.inferred_graph
        assert len(result.inferred_graph) == 1  # only what the rules produced, not the base triples

    def test_apply_rules_does_not_mutate_the_data_graph(self):
        data = g(BAD)
        before = set(data)
        apply_rules(data, g(RULES), engine="native")
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
        result = apply_rules(g(BAD), shapes, rule_set=URIRef(EX + "Set"), engine="native")
        predicates = {p for _, p, _ in result.inferred_graph}
        assert predicates == {URIRef(EX + "p1")}

    def test_evaluate_and_extract_subgraph_return_graphs(self):
        shapes = g(SHAPES)
        data = g(GOOD)
        evaluated = evaluate(data, shapes, engine="native")
        assert (URIRef(EX + "a"), URIRef(EX + "p"), None) in evaluated
        sub = extract_subgraph(data, shapes, engine="native")
        assert (URIRef(EX + "a"), URIRef(EX + "p"), None) in sub
        assert native_adapter.last_run() == ("native", None)

    def test_schema_close_shape_and_extract_shapes_graph_run_natively(self):
        schema = StarShaclSchema(
            g("ex:M a sh:ShapesGraph ; rdfs:member ex:S . " + SHAPES), engine="native"
        )
        assert schema.extract_shapes_graph(URIRef(EX + "M")) is not None
        closed = schema.close_shape(URIRef(EX + "S"))
        assert (URIRef(EX + "S"), SH.closed, None) in closed or len(closed) >= len(g(SHAPES))
        assert native_adapter.last_run() == ("native", None)


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
        assert native_adapter.conformance_disallows_for(allow_warnings, allow_infos) == expected
        options = resolve_mode_options(None, overrides={"allow_warnings": allow_warnings, "allow_infos": allow_infos})
        assert translate_validate_options(options)["conformance_disallows"] == expected

    def test_direct_options_pass_through(self):
        options = resolve_mode_options(
            None, overrides={"abort_on_first": True, "max_validation_depth": 7, "inplace": True, "meta_shacl": True}
        )
        out = translate_validate_options(options)
        assert out["abort_on_first"] is True and out["max_validation_depth"] == 7
        assert out["inplace"] is True and out["meta_shacl"] is True

    @pytest.mark.parametrize("name", ["js", "sparql_mode", "do_owl_imports", "focus_nodes", "use_shapes", "serialize_report_graph"])
    def test_pyshacl_only_switches_are_unsupported(self, name):
        with pytest.raises(NativeUnsupported, match=name):
            translate_validate_options(resolve_mode_options(None, overrides={name: True}))

    def test_pyshacl_only_switches_that_are_off_are_fine(self):
        translate_validate_options(resolve_mode_options(None, overrides={"js": False, "sparql_mode": None}))

    def test_explicit_iterate_rules_is_unsupported_but_the_rules_preset_is_not(self):
        translate_validate_options(resolve_mode_options("rules"))
        with pytest.raises(NativeUnsupported, match="iterate_rules"):
            translate_validate_options(resolve_mode_options("rules"), explicit_iterate_rules=True)

    def test_allow_warnings_changes_conformance_natively(self):
        shapes = g(
            "ex:S a sh:NodeShape ; sh:targetClass ex:T ; "
            "sh:property [ sh:path ex:p ; sh:minCount 1 ; sh:severity sh:Warning ] ."
        )
        assert validate(g(BAD), shapes, engine="native").conforms is False
        assert validate(g(BAD), shapes, engine="native", allow_warnings=True).conforms is True
        assert validate(g(BAD), shapes, engine="native", allow_infos=True).conforms is False

    def test_inplace_adds_inferred_triples_to_the_callers_graph(self):
        data = g(BAD)
        result = validate(data, g(RULES), engine="native", mode="rules")
        assert result.data_graph is data
        assert (URIRef(EX + "a"), URIRef(EX + "flag"), URIRef(EX + "yes")) in data

    def test_plain_validation_never_mutates_the_data_graph(self):
        data = g(BAD)
        before = set(data)
        result = validate(data, g(RULES), engine="native")
        assert result.data_graph is None and set(data) == before

    def test_provenance_options(self):
        result = validate(
            g(GOOD),
            g(SHAPES),
            engine="native",
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
        assert validate(data, shapes, ont, engine="native").conforms is True
        result = validate(data, shapes, ont, engine="native", inference="rdfs")
        assert result.conforms is False
        assert len(ont) == 1 and (URIRef(EX + "a"), RDF.type, URIRef(EX + "Super")) not in data

    def test_include_used_configuration(self):
        result = validate(g(GOOD), g(SHAPES), engine="native", include_used_configuration=True)
        assert any(True for _ in result.report_graph.subjects(RDF.type, SH.ProcessorConfiguration))

    def test_unresolved_owl_imports_raise_like_the_old_default(self):
        shapes = g(SHAPES + " <http://example.org/onto> <http://www.w3.org/2002/07/owl#imports> <http://example.org/missing> .")
        with pytest.raises(ValueError, match="owl:imports"):
            validate(g(GOOD), shapes, engine="native")
        assert validate(g(GOOD), shapes, engine="native", ignore_imports=True).conforms is True

    def test_shapes_graph_loader_is_used(self):
        shapes = g(SHAPES + " <http://example.org/onto> <http://www.w3.org/2002/07/owl#imports> <http://example.org/mod> .")
        calls = []

        def loader(iri):
            calls.append(iri)
            return g("ex:Extra a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:q ; sh:minCount 1 ] .")

        result = validate(g(GOOD), shapes, engine="native", shapes_graph_loader=loader)
        assert calls and result.conforms is False  # the imported shape demands ex:q

    def test_meta_shacl_preflight_rejects_a_bad_shapes_graph(self):
        bad = g("ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:minCount 'x' ; sh:path 3 .")
        with pytest.raises(Exception, match="(?i)shacl|shape|constraint|meta"):
            validate(g(GOOD), bad, engine="native", meta_shacl=True)

    def test_unknown_option_raises_the_old_type_error_without_running_anything(self):
        with pytest.raises(TypeError, match="not_an_option"):
            validate(g(GOOD), g(SHAPES), engine="native", not_an_option=1)


# ---------------------------------------------------------------------------------------------------------------------
# fallbacks


class TestFallback:
    def test_validate_fn_falls_back(self):
        called = []

        def fn(**kwargs):
            called.append(1)
            from pyshacl import validate as pv

            return pv(**kwargs)

        result = validate(g(BAD), g(SHAPES), engine="native", validate_fn=fn)
        assert called and result.engine == "pyshacl" and "validate_fn" in result.engine_fallback_reason
        assert result.conforms is False

    def test_custom_adapter_falls_back(self):
        from starlayer.shacl import TripleTermAdapter

        result = validate(g(BAD), g(SHAPES), engine="native", adapter=TripleTermAdapter())
        assert result.engine == "pyshacl" and "adapter" in result.engine_fallback_reason

    def test_decode_report_false_falls_back(self):
        result = validate(g(BAD), g(SHAPES), engine="native", decode_report=False)
        assert result.engine == "pyshacl" and "decode_report" in result.engine_fallback_reason

    def test_rdfs_subclass_reasoning_option_falls_back(self):
        result = validate(g(BAD), g(SHAPES), engine="native", rdfs_subclass_reasoning_includes_shapes_graph=True)
        assert result.engine == "pyshacl" and "rdfs_subclass_reasoning" in result.engine_fallback_reason

    def test_explicit_iterate_rules_falls_back(self):
        result = validate(g(BAD), g(SHAPES), engine="native", iterate_rules=True)
        assert result.engine == "pyshacl" and "iterate_rules" in result.engine_fallback_reason

    def test_pyshacl_only_switch_falls_back(self):
        result = validate(g(BAD), g(SHAPES), engine="native", js=True)
        assert result.engine == "pyshacl" and "js" in result.engine_fallback_reason

    def test_schema_with_custom_validate_fn_falls_back(self):
        from pyshacl import validate as pv

        schema = StarShaclSchema(g(SHAPES), engine="native", validate_fn=lambda **kw: pv(**kw))
        result = schema.validate(g(BAD))
        assert result.engine == "pyshacl" and "validate_fn" in result.engine_fallback_reason

    def test_schema_inference_keyword_is_still_the_old_type_error(self):
        with pytest.raises(TypeError, match="inference"):
            StarShaclSchema(g(SHAPES), engine="native").validate(g(BAD), inference="rdfs")

    def test_source_rule_provenance_falls_back_and_stamps_both_levels(self):
        result = apply_rules(g(BAD), g(RULES), engine="native", include_source_rule_provenance=True)
        assert result.engine == "pyshacl" and "include_source_rule_provenance" in result.engine_fallback_reason
        assert result.validation.engine == "pyshacl"
        assert (
            result.validation.engine_fallback_reason == result.engine_fallback_reason
        )

    def test_apply_rules_on_a_plain_graph_falls_back_and_raises_the_old_type_error(self):
        with pytest.raises(TypeError, match="StarLayerGraph"):
            apply_rules(Graph(), g(RULES), engine="native")

    def test_a_fallback_keeps_nested_calls_on_pyshacl(self, monkeypatch):
        """With the variable set, the old path's own internal validate() calls must not drift onto the engine."""
        monkeypatch.setenv(ENV_VAR, "native")
        seen = []
        real = native_adapter._validate_native

        def spy(*args, **kwargs):
            seen.append(1)
            return real(*args, **kwargs)

        monkeypatch.setattr(native_adapter, "_validate_native", spy)
        result = apply_rules(g(BAD), g(RULES), include_source_rule_provenance=True)
        assert result.engine == "pyshacl" and not seen

    def test_last_run_records_the_fallback(self):
        validate(g(BAD), g(SHAPES), engine="native", decode_report=False)
        engine, reason = native_adapter.last_run()
        assert engine == "pyshacl" and "decode_report" in reason
        validate(g(BAD), g(SHAPES), engine="native")
        assert native_adapter.last_run() == ("native", None)

    def test_native_and_old_agree_on_a_plain_case(self):
        native = validate(g(BAD), g(SHAPES), engine="native")
        old = validate(g(BAD), g(SHAPES), engine="pyshacl")
        assert native.conforms == old.conforms is False
        assert len(list(native.report_graph.subjects(RDF.type, SH.ValidationResult))) == len(
            list(old.report_graph.subjects(RDF.type, SH.ValidationResult))
        )
