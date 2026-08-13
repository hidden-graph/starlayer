from starshacl.results import ExecutionDiagnostics, RulesResult, ValidationResult


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
        conforms=False,
        report_graph={"r": 1},
        report_text="failed",
        data_graph={"d": 1},
        diagnostics=ExecutionDiagnostics(decode_graph_calls=1),
    )

    assert result.conforms is False
    assert result.report_text == "failed"
    assert result.data_graph == {"d": 1}
    assert result.diagnostics is not None
    assert result.diagnostics.decode_graph_calls == 1
