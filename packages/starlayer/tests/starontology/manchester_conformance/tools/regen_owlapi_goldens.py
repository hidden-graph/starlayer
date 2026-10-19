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
import subprocess
import sys
from pathlib import Path

# Imported by path so the tool works when run as a script from anywhere.
SUITE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUITE.parent))

from manchester_conformance.corpus import CASES  # noqa: E402

ONTOLOGY_IRI = "http://example.org/o"
GOLDEN_DIR = SUITE / "goldens" / "owlapi-5.1.20"


def run_oracle(jar: Path, text: str) -> dict:
    request = json.dumps({"ontologyIRI": ONTOLOGY_IRI, "rawFormat": "manchester", "rawText": text})
    proc = subprocess.run(
        ["java", "-cp", str(jar), "OWLAPIInterface", "parse"],
        input=request, capture_output=True, text=True, timeout=120,
    )
    out = proc.stdout.strip()
    if not out:
        return {"success": False, "error": f"no output; stderr={proc.stderr[:500]}"}
    return json.loads(out.splitlines()[-1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True, type=Path)
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()

    jar_sha = hashlib.sha256(args.jar.read_bytes()).hexdigest()
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    wrote = 0
    for case in CASES:
        if not case.oracle or (args.only and case.id not in args.only):
            continue
        result = run_oracle(args.jar, case.text)
        golden = {
            "case": case.id,
            "oracle": "OWL API 5.1.20",
            "jar_sha256": jar_sha,
            "accepted": bool(result.get("success")),
        }
        if golden["accepted"]:
            golden["turtle"] = result["rdf"]
            golden["manchester"] = result["manchester"]
        else:
            # Keep only the one-line reason, not the Java stack trace.
            golden["error"] = (result.get("error") or "").split("\n")[0][:400]
            golden["error_detail"] = " ".join(
                line.strip() for line in (result.get("error") or "").split("\n") if "Encountered" in line
            )[:400]
        (GOLDEN_DIR / f"{case.id}.json").write_text(
            json.dumps(golden, indent=1, sort_keys=True) + "\n", encoding="utf-8"
        )
        wrote += 1
        print(f"{'ok ' if golden['accepted'] else 'REJ'} {case.id}")
    print(f"wrote {wrote} goldens", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
