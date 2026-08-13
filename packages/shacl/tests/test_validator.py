from typing import Any

import pytest
from rdflib import Graph, Literal, Namespace

from starlayergraph.graph.starlayer_graph import StarLayerGraph

from starshacl.adapters import TripleTermAdapter, TripleTermGraph, TripleTermValue
from starshacl.validator import StarShaclValidator


EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")


def test_validate_uses_encoded_graphs() -> None:
    captured = {}

    def fake_validate(**kwargs):
        captured.update(kwargs)
        report = Graph()
        report.add((EX.r, EX.status, EX.ok))
        return True, report, "ok"

    data = StarLayerGraph()
    data.add((EX.s, EX.p, (EX.a, EX.p, EX.b)))

    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=fake_validate)
    result = validator.validate(data_graph=data)

    assert result.conforms is True
    assert "data_graph" in captured
    assert captured["data_graph"] is not data


def test_apply_rules_requests_inplace_advanced_mode() -> None:
    captured = {}

    def fake_validate(**kwargs):
        captured.update(kwargs)
        report = Graph()
        return True, report, "rules"

    data = StarLayerGraph()
    shapes = StarLayerGraph()

    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=fake_validate)
    _ = validator.apply_rules(data_graph=data, shacl_graph=shapes)

    assert captured["advanced"] is True
    assert captured["iterate_rules"] is True
    assert captured["inplace"] is True


def test_validate_inplace_decodes_back_into_input_graph() -> None:
    def fake_validate(**kwargs):
        encoded_data = kwargs["data_graph"]
        encoded_data.add((EX.s2, EX.p2, EX.o2))
        report = Graph()
        return True, report, "ok"

    from starlayergraph.graph.starlayer_graph import StarLayerGraph

    data = StarLayerGraph()
    data.add((EX.s, EX.p, (EX.a, EX.p, EX.b)))

    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=fake_validate)
    result = validator.validate(data_graph=data, inplace=True)

    assert result.data_graph is data
    assert (EX.s2, EX.p2, EX.o2) in data


def test_validate_rejects_non_iterable_data_graph() -> None:
    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=lambda **_: (True, Graph(), "ok"))

    class NotAGraph:
        pass

    with pytest.raises(TypeError, match="data_graph must be a StarLayerGraph or rdflib.Graph"):
        validator.validate(data_graph=NotAGraph())


def test_validate_rejects_non_starlayergraph_data_graph() -> None:
    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=lambda **_: (True, Graph(), "ok"))
    data = TripleTermGraph()

    with pytest.raises(TypeError, match="data_graph must be a StarLayerGraph or rdflib.Graph"):
        validator.validate(data_graph=data)


def test_validate_rejects_non_iterable_shapes_graph() -> None:
    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=lambda **_: (True, Graph(), "ok"))
    data = StarLayerGraph()

    with pytest.raises(TypeError, match="shacl_graph must be a StarLayerGraph or rdflib.Graph"):
        validator.validate(data_graph=data, shacl_graph=42)


def test_apply_rules_rejects_non_starlayergraph_data_graph() -> None:
    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=lambda **_: (True, Graph(), "ok"))
    shapes = Graph()

    with pytest.raises(TypeError, match="data_graph must be a StarLayerGraph or rdflib.Graph"):
        validator.apply_rules(data_graph=((EX.s, EX.p, EX.o),), shacl_graph=shapes)


def test_validate_normalizes_rdflib_data_graph_for_inplace_updates() -> None:
    def fake_validate(**kwargs):
        encoded_data = kwargs["data_graph"]
        encoded_data.add((EX.s2, EX.p2, EX.o2))
        return True, Graph(), "ok"

    data = Graph()
    data.add((EX.s, EX.p, EX.o))

    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=fake_validate)
    result = validator.validate(data_graph=data, inplace=True)

    assert isinstance(result.data_graph, StarLayerGraph)
    assert (EX.s2, EX.p2, EX.o2) in result.data_graph


def test_validate_inplace_keeps_encoded_triples_on_starlayer_graph() -> None:
    adapter = TripleTermAdapter()

    def fake_validate(**kwargs):
        encoded_data = kwargs["data_graph"]
        encoded_tt = adapter.encode_term(TripleTermValue(EX.a, EX.p, EX.b))
        encoded_data.add((EX.s2, EX.p2, encoded_tt))
        report = Graph()
        return True, report, "ok"

    data = StarLayerGraph()
    data.add((EX.s, EX.p, (EX.x, EX.p, EX.y)))

    validator = StarShaclValidator(adapter=adapter, validate_fn=fake_validate)
    result = validator.validate(data_graph=data, inplace=True)

    assert result.data_graph is data
    assert (EX.s2, EX.p2, (EX.a, EX.p, EX.b)) in data


def test_validate_decodes_report_value_nodes() -> None:
    adapter = TripleTermAdapter()
    encoded_tt = adapter.encode_term(TripleTermValue(EX.a, EX.p, EX.b))

    def fake_validate(**kwargs):
        report = Graph()
        report.add((EX.result, EX.value, encoded_tt))
        return True, report, "ok"

    data = StarLayerGraph()
    data.add((EX.s, EX.p, (EX.a, EX.p, EX.b)))

    validator = StarShaclValidator(adapter=adapter, validate_fn=fake_validate)
    result = validator.validate(data_graph=data)

    assert (EX.result, EX.value, (EX.a, EX.p, EX.b)) in result.report_graph


def test_validate_can_skip_report_decoding() -> None:
    adapter = TripleTermAdapter()
    encoded_tt = adapter.encode_term(TripleTermValue(EX.a, EX.p, EX.b))

    def fake_validate(**kwargs):
        report = Graph()
        report.add((EX.result, EX.value, encoded_tt))
        return True, report, "ok"

    data = StarLayerGraph()
    data.add((EX.s, EX.p, (EX.a, EX.p, EX.b)))

    validator = StarShaclValidator(adapter=adapter, validate_fn=fake_validate)
    result = validator.validate(data_graph=data, decode_report=False)

    assert any(str(o).startswith("urn:starshacl:tt:") for _, _, o in result.report_graph)


def test_validate_populates_diagnostics() -> None:
    def fake_validate(**kwargs):
        report = Graph()
        report.add((EX.r, EX.status, EX.ok))
        return True, report, "ok"

    data = StarLayerGraph()
    data.add((EX.s, EX.p, (EX.a, EX.p, EX.b)))

    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=fake_validate)
    result = validator.validate(data_graph=data)

    assert result.diagnostics is not None
    assert result.diagnostics.encode_graph_calls >= 1
    assert result.diagnostics.encoded_triple_terms >= 1
    assert result.diagnostics.generated_support_triples >= 3


def test_apply_rules_carries_diagnostics() -> None:
    def fake_validate(**kwargs):
        report = Graph()
        return True, report, "ok"

    data = StarLayerGraph()
    data.add((EX.s, EX.p, (EX.a, EX.p, EX.b)))
    shapes = StarLayerGraph()

    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=fake_validate)
    result = validator.apply_rules(data_graph=data, shacl_graph=shapes)

    assert result.diagnostics is not None
    assert result.diagnostics.encode_graph_calls >= 2


def test_validate_diagnostics_reset_between_runs() -> None:
    def fake_validate(**kwargs):
        report = Graph()
        return True, report, "ok"

    data = StarLayerGraph()
    data.add((EX.s, EX.p, (EX.a, EX.p, EX.b)))

    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=fake_validate)
    first = validator.validate(data_graph=data)
    second = validator.validate(data_graph=data)

    assert first.diagnostics is not None
    assert second.diagnostics is not None
    assert first.diagnostics.encode_graph_calls == second.diagnostics.encode_graph_calls
    assert first.diagnostics.encoded_triple_terms == second.diagnostics.encoded_triple_terms


def test_validate_uses_profile_defaults() -> None:
    captured = {}

    def fake_validate(**kwargs):
        captured.update(kwargs)
        report = Graph()
        return True, report, "ok"

    data = StarLayerGraph()
    data.add((EX.s, EX.p, (EX.a, EX.p, EX.b)))

    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=fake_validate)
    _ = validator.validate(data_graph=data, profile="validation")

    assert captured["advanced"] is False
    assert captured["inplace"] is False
    # meta_shacl is consumed by starShacl's own preflight (starshacl.meta_shapes)
    # rather than forwarded to pySHACL's own (unextended) meta_shacl mechanism -
    # see validator.py::validate() - so it's intentionally absent here, not True.
    assert "meta_shacl" not in captured


def test_validate_profile_allows_overrides() -> None:
    captured = {}

    def fake_validate(**kwargs):
        captured.update(kwargs)
        report = Graph()
        return True, report, "ok"

    data = StarLayerGraph()
    data.add((EX.s, EX.p, (EX.a, EX.p, EX.b)))

    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=fake_validate)
    _ = validator.validate(data_graph=data, profile="validation", advanced=True)

    assert captured["advanced"] is True


def test_apply_rules_uses_rules_profile_defaults() -> None:
    captured = {}

    def fake_validate(**kwargs):
        captured.update(kwargs)
        report = Graph()
        return True, report, "ok"

    data = StarLayerGraph()
    data.add((EX.s, EX.p, (EX.a, EX.p, EX.b)))
    shapes = StarLayerGraph()

    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=fake_validate)
    _ = validator.apply_rules(data_graph=data, shacl_graph=shapes)

    assert captured["advanced"] is True
    assert captured["iterate_rules"] is True
    assert captured["inplace"] is True
    # meta_shacl is consumed by starShacl's own preflight (starshacl.meta_shapes)
    # rather than forwarded to pySHACL's own (unextended) meta_shacl mechanism -
    # see validator.py::validate() - so it's intentionally absent here, not True.
    assert "meta_shacl" not in captured


def test_validator_target_nodes_delegates_to_native_core() -> None:
    data = StarLayerGraph()
    shapes = StarLayerGraph()
    shape = EX.Shape

    data.add((EX.alice, EX.kind, EX.Person))
    shapes.add((shape, SH.targetNode, EX.alice))

    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=lambda **_: (True, Graph(), "ok"))
    nodes = validator.target_nodes(data_graph=data, shacl_graph=shapes, shape_node=shape)

    assert nodes == (EX.alice,)


def test_validator_evaluate_component_delegates_to_native_core() -> None:
    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=lambda **_: (True, Graph(), "ok"))
    result = validator.evaluate_component(
        component={"name": "https://github.com/hidden-graph/starshacl/ns#TripleTermNodeKind"},
        focus_node=EX.focus,
        value_nodes=((EX.s, EX.p, EX.o), EX.not_tt),
    )

    assert result.conforms is False
    assert result.violations == (EX.not_tt,)


def test_validator_build_report_delegates_to_native_core() -> None:
    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=lambda **_: (True, Graph(), "ok"))
    report_context = StarLayerGraph()
    events = (
        {
            "focus_node": EX.alice,
            "result_path": EX.says,
            "value": (EX.bob, EX.knows, EX.carol),
            "source_constraint_component": EX.SomeComponent,
        },
    )

    report = validator.build_report(events=events, graph_context=report_context)
    assert any(o == (EX.bob, EX.knows, EX.carol) for _, _, o in report.triples((None, SH.value, None)))


def test_validate_uses_integrated_literal_only_path_for_non_literal_values() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.value, (EX.a, EX.p, EX.b)))

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:PatternShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path ex:value ;
                sh:pattern "^A" ;
              ] .
        """,
        format="turtle12",
    )

    def fail_if_called(**_: Any):
        raise AssertionError("validate_fn should not be called for integrated native literal-only path")

    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=fail_if_called)
    result = validator.validate(data_graph=data, shacl_graph=shapes)

    assert result.conforms is False
    assert any(
        o == SH.PatternConstraintComponent
        for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
    )


def test_validate_falls_back_when_integrated_literal_only_path_is_unsupported() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.value, Literal("A")))

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:PatternShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path ex:value ;
                sh:pattern "^A" ;
              ] .
        """,
        format="turtle12",
    )

    def fake_validate(**_: Any):
        return True, Graph(), "ok"

    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=fake_validate)
    result = validator.validate(data_graph=data, shacl_graph=shapes)

    assert result.conforms is True


def test_validate_uses_integrated_structural_property_path_for_has_value() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.value, (EX.a, EX.p, EX.b)))

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:HasValueShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path ex:value ;
                                sh:hasValue <<( ex:a ex:p ex:b )>> ;
              ] .
        """,
        format="turtle12",
    )

    def fail_if_called(**_: Any):
        raise AssertionError("validate_fn should not be called for integrated native structural path")

    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=fail_if_called)
    result = validator.validate(data_graph=data, shacl_graph=shapes)

    assert result.conforms is True
    assert not any(True for _ in result.report_graph.triples((None, SH.sourceConstraintComponent, None)))


def test_validate_falls_back_when_integrated_structural_property_is_unsupported() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.value, Literal("A")))

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:UnsupportedShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path ex:value ;
                sh:minCount 1 ;
              ] .
        """,
        format="turtle",
    )

    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=lambda **_: (True, Graph(), "ok"))
    result = validator.validate(data_graph=data, shacl_graph=shapes)

    assert result.conforms is True


def test_validate_reification_required_violation_when_no_reifier_exists() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.value, Literal("A")))

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:ReificationShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path ex:value ;
                sh:reificationRequired true ;
              ] .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert any(
        o == SH.ReifierShapeConstraintComponent
        for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
    )
    # sh:value is the plain failing value, not the reified (focus, path,
    # value) triple term - confirmed against the W3C SHACL 1.2 test suite's
    # own reifierShape-001/002 fixtures (tests/w3c_suite/), which fixed a
    # real bug here: this assertion previously (wrongly) expected the
    # encoded triple term itself.
    assert any(o == Literal("A") for _, _, o in result.report_graph.triples((None, SH.value, None)))


def test_validate_reifier_shape_violation_survives_advanced_mode() -> None:
    # Found 2026-07-31 via the W3C SHACL 1.2 test suite: advanced=True makes
    # pyshacl.validator.Validator unconditionally clone the data graph
    # ("Forcing clone of DataGraph because advanced mode is enabled" - so
    # SHACL-AF rules don't mutate the caller's original graph).
    # RdfLibDataGraph.clone() builds the copy via pySHACL's own
    # rdfutil.clone.clone_graph(), which produces a *plain* rdflib.Graph -
    # it has no notion of starShacl's _SparqlAwareEncodedGraph wrapper or its
    # _tt_adapter back-reference, even though the clone's actual (encoded)
    # triples are faithfully copied. Without _tt_adapter,
    # ReifierShapeConstraintComponent's reifier lookup can never re-encode a
    # (focus, path, value) tuple into the matching stored URI, so it always
    # finds zero reifiers and reports vacuous conformance regardless of
    # whether one actually exists.
    #
    # Needs an *existing* reifier to expose this (unlike the
    # sh:reificationRequired "no reifier at all" case, which returns the same
    # empty reifier set whether or not the lookup key is correctly encoded,
    # and so can't tell the two cases apart) - reuses the same shapes/data as
    # test_validate_reifier_shape_violation_when_reifier_does_not_conform,
    # differing only by advanced=True. Fixed by
    # validator.py::_patch_rdflib_data_graph_clone_preserves_tt_adapter.
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice ex:value "A" {| ex:source ex:Somewhere |} .
        """,
        format="turtle12",
    )

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:ReificationShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path ex:value ;
                sh:reifierShape ex:ProvenanceShape ;
              ] .

            ex:ProvenanceShape a sh:NodeShape ;
              sh:property [
                sh:path ex:date ;
                sh:minCount 1 ;
              ] .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, advanced=True)

    assert result.conforms is False
    assert any(
        o == SH.ReifierShapeConstraintComponent
        for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
    )
    assert any(o == Literal("A") for _, _, o in result.report_graph.triples((None, SH.value, None)))


def test_validate_reification_required_conforms_when_reifier_exists() -> None:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice ex:value "A" {| ex:source ex:Somewhere |} .
        """,
        format="turtle12",
    )

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:ReificationShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path ex:value ;
                sh:reificationRequired true ;
              ] .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_validate_reifier_shape_violation_when_reifier_does_not_conform() -> None:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice ex:value "A" {| ex:source ex:Somewhere |} .
        """,
        format="turtle12",
    )

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

            ex:ReificationShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path ex:value ;
                sh:reifierShape ex:ProvenanceShape ;
              ] .

            ex:ProvenanceShape a sh:NodeShape ;
              sh:property [
                sh:path ex:date ;
                sh:minCount 1 ;
              ] .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert any(
        o == SH.ReifierShapeConstraintComponent
        for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
    )


def test_validate_reifier_shape_conforms_when_reifier_conforms() -> None:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:alice ex:value "A" {| ex:date "2019-12-05"^^xsd:date |} .
        """,
        format="turtle12",
    )

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:ReificationShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path ex:value ;
                sh:reifierShape ex:ProvenanceShape ;
              ] .

            ex:ProvenanceShape a sh:NodeShape ;
              sh:property [
                sh:path ex:date ;
                sh:minCount 1 ;
              ] .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_validate_hard_fails_when_reification_path_is_not_simple_iri() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.value, Literal("A")))

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:ReificationShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path [ sh:inversePath ex:value ] ;
                sh:reificationRequired true ;
              ] .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    with pytest.raises(NotImplementedError, match="simple IRI"):
        _ = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)


def test_validate_applies_filter_shape_compatibility_patch_correctly() -> None:
    # sh:filterShape crashes pySHACL outright (AttributeError, not just
    # "untested" per its own source comment) - confirmed directly with plain
    # RDF 1.1 data. starShacl applies a small, backward-compatible
    # compatibility shim (_patch_shape_validate_for_filter_shape) so this
    # now actually works: only ex:bob (a genuine ex:Adult) should be
    # filtered in, excluding ex:carol.
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice ex:knows ex:bob, ex:carol .
            ex:bob a ex:Adult .
        """,
        format="turtle",
    )

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:AdultShape a sh:NodeShape ; sh:class ex:Adult .

            ex:FilterExprShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:rule [
                a sh:TripleRule ;
                sh:subject sh:this ;
                sh:predicate ex:derivedAdultFriends ;
                sh:object [ sh:filterShape ex:AdultShape ; sh:nodes [ sh:path ex:knows ] ] ;
              ] .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    derived = {o for _, _, o in result.data_graph.triples((EX.alice, EX.derivedAdultFriends, None))}
    assert derived == {EX.bob}


def test_validate_hard_fails_on_sh_filter_shape_when_patch_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    # Defensive fallback: if the compatibility shim can't be applied (e.g.
    # pySHACL's internals no longer match what it expects), starShacl still
    # fails clearly rather than silently no-op-ing or crashing confusingly.
    import starshacl.validator as validator_module

    monkeypatch.setattr(validator_module, "_filter_shape_patch_status", None)
    monkeypatch.setattr(validator_module, "_patch_shape_validate_for_filter_shape", lambda: False)

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice ex:knows ex:bob .
            ex:bob a ex:Adult .
        """,
        format="turtle",
    )

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:AdultShape a sh:NodeShape ; sh:class ex:Adult .

            ex:FilterExprShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:rule [
                a sh:TripleRule ;
                sh:subject sh:this ;
                sh:predicate ex:derivedAdultFriends ;
                sh:object [ sh:filterShape ex:AdultShape ; sh:nodes [ sh:path ex:knows ] ] ;
              ] .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    with pytest.raises(NotImplementedError, match="sh:filterShape"):
        _ = validator.apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)


def test_validate_does_not_hard_fail_without_reification_constraints() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.value, Literal("A")))

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:PlainShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path ex:value ;
                sh:minCount 1 ;
              ] .
        """,
        format="turtle",
    )

    validator = StarShaclValidator(adapter=TripleTermAdapter(), validate_fn=lambda **_: (True, Graph(), "ok"))
    result = validator.validate(data_graph=data, shacl_graph=shapes)

    assert result.conforms is True


