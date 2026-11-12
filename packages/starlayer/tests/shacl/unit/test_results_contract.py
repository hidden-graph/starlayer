from starlayer.shacl.results import ExecutionDiagnostics, RulesResult, ValidationResult


def test_validation_result_shape() -> None:
    result = ValidationResult(
        conforms=True,
        report_graph={"report": "ok"},
        report_text="ok",
        data_graph={"data": "g"},
        diagnostics=ExecutionDiagnostics(encoded_triple_terms=2),
    )

    assert result.conforms is True
    assert result.report_text == "ok"
    assert result.data_graph == {"data": "g"}
    assert result.diagnostics is not None
    assert result.diagnostics.encoded_triple_terms == 2


def test_rules_result_shape() -> None:
    result = RulesResult(
        inferred_graph={"d": 1},
        validation=ValidationResult(
            conforms=False,
            report_graph={"r": 1},
            report_text="failed",
            diagnostics=ExecutionDiagnostics(decode_graph_calls=1),
        ),
    )

    assert result.validation.conforms is False
    assert result.validation.report_text == "failed"
    assert result.inferred_graph == {"d": 1}
    assert result.validation.diagnostics is not None
    assert result.validation.diagnostics.decode_graph_calls == 1


def test_validate_builds_report_text_only_when_read(monkeypatch) -> None:
    """``report_text`` is the costly part of a result (about half of a ``validate()`` call on small data); callers that read ``conforms`` or
    the report graph never pay for it, and the text is built once."""
    from starlayer import StarLayerGraph
    from starlayer.shacl import validate
    from starlayer.shacl_engine import text as engine_text

    calls = []
    original = engine_text.report_text
    monkeypatch.setattr(engine_text, "report_text", lambda *a, **k: calls.append(1) or original(*a, **k))
    shapes = StarLayerGraph()
    shapes.parse(
        data="@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.org/> . ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .",
        format="turtle",
    )
    data = StarLayerGraph()
    result = validate(data, shapes)
    assert result.conforms is False and result.report_graph is not None
    assert calls == []
    text = result.report_text
    assert "Validation Report" in text and len(calls) == 1
    assert result.report_text is text and len(calls) == 1
