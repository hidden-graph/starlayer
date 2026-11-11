#!/usr/bin/env python3
"""Vendor a pinned snapshot of the W3C RDF 1.2 syntax suites (``rdf/rdf12`` of w3c/rdf-tests) into ``data/``.

Downloads the repository tarball at ``PINNED_SHA`` (one request) and replaces the five syntax directories under ``data/``
(``rdf-turtle``, ``rdf-trig``, ``rdf-n-triples``, ``rdf-n-quads``, ``rdf-xml``) byte for byte. The ``reports`` directories
(implementation reports, EARL) are left out: nothing reads them. Writes ``data/VENDORED_FROM.md``.

Bumping PINNED_SHA is a deliberate, reviewable change; this script never follows the branch tip. The other w3c/rdf-tests
downloaders (``w3c_turtle12``, ``w3c_sparql12``, ``w3c_sparql11``) pin the same commit: bump them together. After a bump, update
the expected count and ``KNOWN_GAPS`` in ``test_w3c_rdf12_oxigraph.py``.

Usage: python download_w3c_rdf12_tests.py
"""

from __future__ import annotations

import datetime
import io
import shutil
import tarfile
import urllib.request
from pathlib import Path

REPO = "w3c/rdf-tests"
# Bump deliberately; do not auto-follow main's tip.
PINNED_SHA = "4158bca195a29fe1fd90f92698170bc7cc385273"
SUBTREE = "rdf/rdf12/"
DIRECTORIES = ("rdf-turtle", "rdf-trig", "rdf-n-triples", "rdf-n-quads", "rdf-xml")
SKIP = "reports"

TARBALL_URL = f"https://codeload.github.com/{REPO}/tar.gz/{PINNED_SHA}"
DEST = Path(__file__).resolve().parent / "data"


def _members() -> dict[str, bytes]:
    with urllib.request.urlopen(TARBALL_URL) as resp:
        archive = resp.read()
    out: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            relative = member.name.split("/", 1)[1] if "/" in member.name else member.name  # strip "<repo>-<sha>/"
            if not relative.startswith(SUBTREE):
                continue
            relative = relative[len(SUBTREE) :]
            top, _, rest = relative.partition("/")
            if top not in DIRECTORIES or rest.split("/", 1)[0] == SKIP:
                continue
            extracted = tar.extractfile(member)
            if extracted is not None:
                out[relative] = extracted.read()
    return out


def main() -> None:
    files = _members()
    for directory in DIRECTORIES:
        if not any(name.startswith(directory + "/") for name in files):
            raise RuntimeError(f"no files under {SUBTREE}{directory}/ at {PINNED_SHA}: did the subtree move or the SHA get mistyped?")
        shutil.rmtree(DEST / directory, ignore_errors=True)
    for name, data in files.items():
        path = DEST / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    stamp = (
        "# Vendored snapshot provenance\n\n"
        "Do not hand-edit files in this directory: regenerate with `python ../download_w3c_rdf12_tests.py` after bumping `PINNED_SHA` there.\n\n"
        f"- Source: https://github.com/{REPO}/tree/{PINNED_SHA}/{SUBTREE}\n"
        f"- Pinned commit SHA: `{PINNED_SHA}` (the commit `../../w3c_turtle12/data` is pinned to)\n"
        f"- Copied: {datetime.date.today().isoformat()}, whole directories {', '.join(f'`{d}`' for d in DIRECTORIES)}, byte for byte, "
        f"except the `{SKIP}` directories (EARL implementation reports, which nothing reads). {len(files)} files.\n"
        "- Not vendored: `rdf-semantics` (entailment, not syntax) and the RDF 1.1 suites (`rdf/rdf11`, 24 MB, mostly Turtle).\n\n"
        "## License\n\n"
        "The files are copied from the W3C `rdf-tests` repository, dual-licensed under the W3C 3-Clause BSD License and the W3C Test Suite\n"
        "License (https://www.w3.org/Consortium/Legal/2008/04-testsuite-copyright.html). They are unaltered, so both licences apply.\n"
        "No W3C logos or trademarks are used, and no conformance or certification claim is made.\n"
    )
    (DEST / "VENDORED_FROM.md").write_text(stamp)
    print(f"Vendored {len(files)} files into {DEST}\nPinned SHA: {PINNED_SHA}")


if __name__ == "__main__":
    main()
