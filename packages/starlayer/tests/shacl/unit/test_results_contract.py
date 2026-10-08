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
