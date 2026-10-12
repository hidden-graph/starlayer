"""
scripts/check_benchmark_regression.py

Compares a fresh pytest-benchmark JSON result against a committed
baseline, failing (non-zero exit) if any benchmark's mean time regressed
beyond THRESHOLD. Used by .github/workflows/benchmark.yml - a failed
scheduled-workflow run is itself the "alert" (GitHub surfaces/emails
failed scheduled runs on the default branch automatically).

Run:
    python scripts/check_benchmark_regression.py <baseline.json> <current.json>

To update a baseline after an intentional, accepted performance change,
regenerate it the same way the CI job produces a current run:
    pytest benchmarks-graph/test_bench_graph.py --benchmark-only \
        --benchmark-json=benchmarks-graph/baseline.json
(same pattern for benchmarks-shacl/) and commit the result.
"""

import json
import sys

THRESHOLD = 0.20  # fail if a benchmark's mean time is >20% slower than baseline


def _load(path):
    with open(path) as f:
        data = json.load(f)
    return {b["fullname"]: b["stats"]["mean"] for b in data["benchmarks"]}


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: check_benchmark_regression.py <baseline.json> <current.json>", file=sys.stderr)
        return 2

    baseline_path, current_path = sys.argv[1], sys.argv[2]
    baseline = _load(baseline_path)
    current = _load(current_path)

    regressions = []
    missing = [name for name in baseline if name not in current]

    for name, base_mean in sorted(baseline.items()):
        if name not in current:
            continue
        cur_mean = current[name]
        change = (cur_mean - base_mean) / base_mean
        status = "REGRESSION" if change > THRESHOLD else "ok"
        print(
            f"{status:10} {name}: "
            f"baseline={base_mean * 1000:.3f}ms current={cur_mean * 1000:.3f}ms ({change:+.1%})"
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
