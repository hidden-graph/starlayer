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


def _result(cal: float, **mins: float) -> dict:
    benches = [{"name": "test_calibration_reference", "fullname": CAL, "stats": {"min": cal}}]
    benches += [{"name": n, "fullname": f"benchmarks-x/test_b.py::{n}", "stats": {"min": m}} for n, m in mins.items()]
    return {"benchmarks": benches, "machine_info": {"cpu": {"brand_raw": "cpu"}}}


def test_the_recorded_baseline_is_the_median_ratio_to_the_calibration() -> None:
    import record_benchmark_baseline as record

    runs = [_result(0.010, test_a=0.010), _result(0.020, test_a=0.040), _result(0.040, test_a=0.200)]  # ratios 1, 2, 5
    baseline = record.build_baseline(runs)
    cal = next(b["stats"]["min"] for b in baseline["benchmarks"] if b["name"] == "test_calibration_reference")
    a = next(b["stats"]["min"] for b in baseline["benchmarks"] if b["name"] == "test_a")
    assert cal == 0.020  # the run with the median calibration is the template
    assert a / cal == pytest.approx(2.0)  # the median of 1, 2 and 5
    assert baseline["starlayer_baseline"]["runs"] == 3


def test_a_baseline_needs_more_than_one_run() -> None:
    import record_benchmark_baseline as record

    with pytest.raises(ValueError, match="at least two"):
        record.build_baseline([_result(0.010, test_a=0.010)])


def test_a_run_passes_against_a_baseline_recorded_from_runs_on_other_cpus(tmp_path, monkeypatch) -> None:
    import record_benchmark_baseline as record

    runs = [_result(0.010, test_a=0.010), _result(0.020, test_a=0.021), _result(0.015, test_a=0.016)]
    baseline = tmp_path / "base.json"
    baseline.write_text(json.dumps(record.build_baseline(runs)))
    fresh = tmp_path / "fresh.json"
    fresh.write_text(json.dumps(_result(0.030, test_a=0.033)))  # a slower CPU again
    assert _run(monkeypatch, str(baseline), str(fresh)) == 0


def test_a_baseline_benchmark_missing_from_the_current_run_fails(tmp_path, monkeypatch, capsys) -> None:
    baseline = _write(tmp_path / "b.json", **{CAL: 0.010, INSERT: 0.006, QUERY: 0.150})
    current = _write(tmp_path / "c.json", **{CAL: 0.010, INSERT: 0.006})  # test_query was renamed or removed
    assert _run(monkeypatch, baseline, current) == 1
    assert QUERY in capsys.readouterr().out


@pytest.mark.parametrize("short_calibration", [0.010, 0.030])
def test_recording_a_baseline_names_a_benchmark_missing_from_a_run(short_calibration) -> None:
    import record_benchmark_baseline as record

    short, full = _result(short_calibration, test_a=0.01), _result(0.020, test_a=0.02, test_b=0.03)
    with pytest.raises(ValueError, match="test_b"):
        record.build_baseline([short, full, _result(0.020, test_a=0.02, test_b=0.03)])


def test_recording_a_baseline_from_a_run_without_calibration_is_a_clear_error() -> None:
    import record_benchmark_baseline as record

    no_cal = {"benchmarks": [{"name": "test_a", "fullname": "x::test_a", "stats": {"min": 1.0}}], "machine_info": {}}
    with pytest.raises(ValueError, match="test_calibration_reference"):
        record.build_baseline([no_cal, no_cal])
