"""scripts/record_benchmark_baseline.py - write a benchmark baseline from several CI runs (GitHub issue #33).

A single run's baseline carries that run's CPU: GitHub's runners draw a different CPU every day. The check
(check_benchmark_regression.py) compares each benchmark relative to the calibration benchmark, which removes most of that, so
the baseline should be the *median ratio* over several runs on the runners, not one run.

    gh workflow run benchmark.yml --ref <branch>          # four or more times, wait for them to finish
    gh run download <run-id> -n benchmark-results -D out/<run-id>        # for each run
    python scripts/record_benchmark_baseline.py packages/starlayer/benchmarks-graph/baseline.json \\
        out/*/bench-graph-result.json
    (same for benchmarks-shacl/baseline.json and out/*/bench-shacl-result.json), then commit.

The output is a pytest-benchmark file in the shape the check reads: the run with the median calibration time is the template,
and each benchmark's minimum is replaced by median(ratio to its own run's calibration) * the template's calibration.
"""

import json
import statistics
import sys

CALIBRATION = "test_calibration_reference"


def _calibration(data):
    return next(b["stats"]["min"] for b in data["benchmarks"] if b["name"] == CALIBRATION)


def build_baseline(runs: list[dict]) -> dict:
    """The baseline for these pytest-benchmark result dicts (at least two, each with a calibration benchmark)."""
    if len(runs) < 2:
        raise ValueError("record a baseline from at least two runs, preferably four or more, on different days or CPUs")
    ordered = sorted(runs, key=_calibration)
    template = json.loads(json.dumps(ordered[len(ordered) // 2]))
    template_cal = _calibration(template)
    for bench in template["benchmarks"]:
        ratios = [
            next(b["stats"]["min"] for b in run["benchmarks"] if b["fullname"] == bench["fullname"]) / _calibration(run)
            for run in runs
        ]
        bench["stats"]["min"] = statistics.median(ratios) * template_cal
    template["starlayer_baseline"] = {
        "runs": len(runs),
        "method": "median over the runs of (minimum / calibration minimum), scaled to the template run's calibration",
        "cpus": sorted({r["machine_info"].get("cpu", {}).get("brand_raw", "?") for r in runs}),
    }
    return template


def main() -> int:
    if len(sys.argv) < 4:
        print("usage: record_benchmark_baseline.py <baseline.json to write> <run.json> <run.json> [...]", file=sys.stderr)
        return 2
    out, paths = sys.argv[1], sys.argv[2:]
    runs = []
    for path in paths:
        with open(path) as f:
            runs.append(json.load(f))
    baseline = build_baseline(runs)
    with open(out, "w") as f:
        json.dump(baseline, f, indent=2)
        f.write("\n")
    print(f"wrote {out} from {len(runs)} runs ({', '.join(baseline['starlayer_baseline']['cpus'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
