"""
scripts/check_benchmark_regression.py

Compares a fresh pytest-benchmark JSON result against a committed
baseline, failing (non-zero exit) if any benchmark's time regressed
beyond THRESHOLD. The statistic compared is the minimum of each benchmark's rounds (far steadier than the mean on a
shared runner; a real slowdown raises it, noise mostly does not). Each time is divided by the minimum of the calibration
benchmark (test_calibration_reference) from the same run first, because
GitHub's runners draw a different CPU from day to day, about 2x apart, so
absolute milliseconds cannot be compared with a baseline recorded elsewhere
(GitHub issue #33). Used by .github/workflows/benchmark.yml - a failed
scheduled-workflow run is itself the "alert" (GitHub surfaces/emails
failed scheduled runs on the default branch automatically).

Run:
    python scripts/check_benchmark_regression.py <baseline.json> <current.json>

To update a baseline after an intentional, accepted performance change, record it from several runs on the CI runners (the
runner CPU varies, so a baseline from one run, or from a laptop, does not compare): see the docstring of
scripts/record_benchmark_baseline.py.
"""

import json
import sys

THRESHOLD = 0.30  # fail if a benchmark, relative to the calibration, is >30% above baseline (CPU families differ by up to ~30% after normalizing)


CALIBRATION = "test_calibration_reference"


def _load(path):
    """``(minimums, calibration)``: the minimum time of each benchmark by full name, and the calibration benchmark's (or None)."""
    with open(path) as f:
        data = json.load(f)
    means = {b["fullname"]: b["stats"]["min"] for b in data["benchmarks"]}
    calibration = next((m for name, m in means.items() if name.endswith("::" + CALIBRATION)), None)
    return means, calibration


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: check_benchmark_regression.py <baseline.json> <current.json>", file=sys.stderr)
        return 2

    baseline_path, current_path = sys.argv[1], sys.argv[2]
    baseline, base_cal = _load(baseline_path)
    current, cur_cal = _load(current_path)
    if base_cal is None or cur_cal is None:
        which = " and ".join(n for n, c in (("baseline", base_cal), ("current run", cur_cal)) if c is None)
        print(f"No {CALIBRATION} benchmark in the {which}: re-record the baseline (see the docstring).", file=sys.stderr)
        return 2
    print(f"calibration: baseline={base_cal * 1000:.3f}ms current={cur_cal * 1000:.3f}ms (this runner is {cur_cal / base_cal:.2f}x the baseline machine)\n")

    regressions = []
    missing = [name for name in baseline if name not in current]

    for name, base_mean in sorted(baseline.items()):
        if name not in current or name.endswith("::" + CALIBRATION):
            continue
        cur_mean = current[name]
        # relative to each run's own calibration, so a slower or faster CPU cancels
        change = (cur_mean / cur_cal - base_mean / base_cal) / (base_mean / base_cal)
        status = "REGRESSION" if change > THRESHOLD else "ok"
        print(
            f"{status:10} {name}: "
            f"baseline={base_mean * 1000:.3f}ms current={cur_mean * 1000:.3f}ms (relative to calibration: {change:+.1%})"
        )
        if change > THRESHOLD:
            regressions.append((name, change))

    for name in missing:
        print(f"missing    {name}: present in baseline, not in current run")

    if regressions:
        print(f"\n{len(regressions)} benchmark(s) regressed beyond {THRESHOLD:.0%}:")
        for name, change in regressions:
            print(f"  - {name}: {change:+.1%}")
        return 1

    print("\nNo regressions beyond threshold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
