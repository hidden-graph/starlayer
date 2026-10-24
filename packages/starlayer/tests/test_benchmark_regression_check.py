"""scripts/check_benchmark_regression.py compares each benchmark relative to a calibration benchmark (GitHub issue #33)."""

import json

import check_benchmark_regression as check
import pytest

CAL = "benchmarks-x/test_b.py::test_calibration_reference"
INSERT = "benchmarks-x/test_b.py::test_insert"
QUERY = "benchmarks-x/test_b.py::test_query"


def _write(path, **means: float) -> str:
    """A pytest-benchmark result file with the given minimum times (seconds) by full name."""
    path.write_text(json.dumps({"benchmarks": [{"fullname": name, "stats": {"min": mean}} for name, mean in means.items()]}))
    return str(path)


def _run(monkeypatch, baseline: str, current: str) -> int:
    monkeypatch.setattr("sys.argv", ["check", baseline, current])
    return check.main()


def test_a_uniformly_slower_machine_is_not_a_regression(tmp_path, monkeypatch) -> None:
    baseline = _write(tmp_path / "b.json", **{CAL: 0.010, INSERT: 0.006, QUERY: 0.150})
    current = _write(tmp_path / "c.json", **{CAL: 0.020, INSERT: 0.012, QUERY: 0.300})  # everything twice as slow
    assert _run(monkeypatch, baseline, current) == 0


def test_one_benchmark_slower_than_the_machine_explains_is_a_regression(tmp_path, monkeypatch) -> None:
    baseline = _write(tmp_path / "b.json", **{CAL: 0.010, INSERT: 0.006, QUERY: 0.150})
    current = _write(tmp_path / "c.json", **{CAL: 0.020, INSERT: 0.012, QUERY: 0.450})  # query 1.5x worse on a 2x machine
    assert _run(monkeypatch, baseline, current) == 1


def test_a_faster_machine_does_not_hide_a_regression(tmp_path, monkeypatch) -> None:
    baseline = _write(tmp_path / "b.json", **{CAL: 0.020, INSERT: 0.012})
    current = _write(tmp_path / "c.json", **{CAL: 0.010, INSERT: 0.009})  # 1.5x slower relative to a machine twice as fast
    assert _run(monkeypatch, baseline, current) == 1


def test_the_calibration_benchmark_is_never_itself_judged(tmp_path, monkeypatch, capsys) -> None:
    baseline = _write(tmp_path / "b.json", **{CAL: 0.010, INSERT: 0.006})
    current = _write(tmp_path / "c.json", **{CAL: 0.100, INSERT: 0.060})
    assert _run(monkeypatch, baseline, current) == 0
    assert "test_calibration_reference:" not in capsys.readouterr().out


@pytest.mark.parametrize("missing", ["baseline", "current"])
def test_a_file_without_calibration_is_an_error_not_a_pass(tmp_path, monkeypatch, missing) -> None:
    with_cal = {CAL: 0.010, INSERT: 0.006}
    without = {INSERT: 0.006}
    baseline = _write(tmp_path / "b.json", **(without if missing == "baseline" else with_cal))
    current = _write(tmp_path / "c.json", **(without if missing == "current" else with_cal))
    assert _run(monkeypatch, baseline, current) == 2
