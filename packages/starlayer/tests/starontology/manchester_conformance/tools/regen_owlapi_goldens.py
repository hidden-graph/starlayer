"""Regenerate the OWL API golden files for the Manchester conformance corpus.

Offline tool (needs a JVM); CI never runs it - CI compares against the committed goldens. Run it when
the corpus changes or to re-verify against a newer oracle jar:

    python tests/starontology/manchester_conformance/tools/regen_owlapi_goldens.py \\
        --jar "/path/to/manchester-owl-parser.jar" [--only case-id ...]

The jar is the ``manchester-owl/manchester-syntax-parser`` shaded build (Main entry point
``OWLAPIInterface``) bundling OWL API 5.1.20, the same oracle docs/graph/manchester_syntax_gap_analysis.md
uses. Each golden records: whether the oracle accepted the input, its Turtle output (RDF mapping), its own
Manchester rendering, and the jar's SHA-256 so a golden is always traceable to the oracle that made it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Imported by path so the tool works when run as a script from anywhere.
SUITE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUITE.parent))

from manchester_conformance.corpus import CASES  # noqa: E402

GOLDEN_DIR = SUITE / "goldens" / "owlapi-5.1.20"


def run_oracle_batch(jar: Path, cases) -> dict[str, dict]:
    """One JVM for the whole corpus. ``OwlApiDirect`` loads each document straight into the OWL API
    (no scratch ontology), so ontology-level triples (IRI, version IRI, annotations) are visible."""
    with tempfile.TemporaryDirectory() as classes:
        subprocess.run(
            ["javac", "-cp", str(jar), "-d", classes, str(SUITE / "tools" / "OwlApiDirect.java")],
            check=True, capture_output=True, text=True,
        )
        request = json.dumps([{"id": c.id, "text": c.text} for c in cases])
        proc = subprocess.run(
            ["java", "-cp", f"{jar}{os.pathsep}{classes}", "OwlApiDirect"],
            input=request, capture_output=True, text=True, timeout=1800,
        )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise SystemExit(f"oracle failed: {proc.stderr[:800]}")
    return {r["id"]: r for r in json.loads(proc.stdout.strip().splitlines()[-1])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True, type=Path)
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()

    jar_sha = hashlib.sha256(args.jar.read_bytes()).hexdigest()
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    chosen = [c for c in CASES if c.oracle and (not args.only or c.id in args.only)]
    results = run_oracle_batch(args.jar, chosen)
    for case in chosen:
        result = results[case.id]
        golden = {
            "case": case.id,
            "oracle": "OWL API 5.1.20 (direct load)",
            "jar_sha256": jar_sha,
            "accepted": bool(result.get("accepted")),
        }
        if golden["accepted"]:
            golden["turtle"] = result["turtle"]
        else:
            # Keep only the useful lines, not the Java stack trace.
            error = result.get("error") or ""
            golden["error"] = error.split("\n")[0][:400]
            golden["error_detail"] = " ".join(
                line.strip() for line in error.split("\n") if "Encountered" in line
            )[:400]
        (GOLDEN_DIR / f"{case.id}.json").write_text(
            json.dumps(golden, indent=1, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"{'ok ' if golden['accepted'] else 'REJ'} {case.id}")
    print(f"wrote {len(chosen)} goldens", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
