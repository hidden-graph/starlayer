"""
docs/spec_snapshots/refresh_snapshots.py

Re-fetches the current W3C RDF 1.2 / SPARQL 1.2 spec documents and overwrites
the local .txt snapshots in this directory. Run this, then `git diff
docs/spec_snapshots/` to see exactly what changed in the spec text since the
last snapshot - the whole point of keeping these files (see README.md).

Requires: pip install html2text (dev-only, not a project dependency)

Run from anywhere:
    python3 docs/spec_snapshots/refresh_snapshots.py
"""

import os
import re
import subprocess
import urllib.request

SPECS = [
    ("rdf12-concepts",  "RDF 1.2 Concepts and Abstract Data Model"),
    ("rdf12-schema",    "RDF 1.2 Schema"),
    ("rdf12-turtle",    "RDF 1.2 Turtle"),
    ("rdf12-n-triples", "RDF 1.2 N-Triples"),
    ("rdf12-xml",       "RDF 1.2 XML Syntax"),
    ("sparql12-query",  "SPARQL 1.2 Query Language"),
    ("sparql12-update", "SPARQL 1.2 Update"),
]

DEST_DIR = os.path.dirname(os.path.abspath(__file__))


def fetch(slug, title):
    url = f"https://www.w3.org/TR/{slug}/"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", errors="replace")

    m = re.search(r'"generatedSubtitle":\s*"([^"]+)"', html)
    subtitle = m.group(1) if m else "unknown status"
    m2 = re.search(r'"publishISODate":\s*"([^"]+)"', html)
    pub_date = m2.group(1)[:10] if m2 else "unknown date"

    result = subprocess.run(
        ["python3", "-m", "html2text", "--body-width=0"],
        input=html, capture_output=True, text=True, check=True,
    )

    header = (
        f"{title}\n"
        f"Snapshot source: {url}\n"
        f"Status at fetch time: {subtitle}\n"
        f"Published: {pub_date}\n"
        f"Copyright © 2004-2026 World Wide Web Consortium. Distributed under the\n"
        f"W3C Software and Document License: https://www.w3.org/copyright/software-license-2023/\n"
        f"See docs/spec_snapshots/README.md for how this snapshot is used and regenerated.\n"
        f"{'=' * 70}\n\n"
    )

    out_path = os.path.join(DEST_DIR, f"{slug}.txt")
    with open(out_path, "w") as f:
        f.write(header + result.stdout)
    print(f"{slug}: {subtitle} ({pub_date}) -> {out_path}")


def main():
    for slug, title in SPECS:
        fetch(slug, title)
    print("\nDone. Run: git diff docs/spec_snapshots/*.txt")


if __name__ == "__main__":
    main()
