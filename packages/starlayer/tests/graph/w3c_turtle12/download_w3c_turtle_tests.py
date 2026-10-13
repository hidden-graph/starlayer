"""W3C RDF 1.2 Turtle Test Suite download script.

Downloads every file referenced by both manifests W3C publishes for RDF 1.2
Turtle (eval/ - TestTurtleEval, parser output must match expected .nt; and
syntax/ - TestTurtlePositiveSyntax/TestTurtleNegativeSyntax, parse
success/failure only) from a single pinned-commit tarball snapshot of
w3c/rdf-tests (below), not from N individual live HTTP requests - mirrors
scripts/sync_w3c_shacl12_suite.py's own fetch shape (one tarball request,
pinned SHA, deliberate bump) rather than this script's own prior per-file
``requests.get()`` design, which risked GitHub's 60-req/hour unauthenticated
rate limit across this suite's 130+ files and left no record of exactly what
was fetched or when.

Both manifests land in the same flat data/ directory and one combined
manifest.csv - their filenames and test names don't collide (verified when
this was added).

Writes data/VENDORED_FROM.md recording the source, pinned SHA, and sync
date, so a reviewer can see exactly what changed by diffing one file -
same convention scripts/sync_w3c_shacl12_suite.py established.

Bumping PINNED_SHA is a deliberate, one-line, reviewable change - this
script never auto-follows ``main``'s tip. The companion SPARQL 1.2
downloaders (tests/graph/w3c_sparql12/, tests/sparql/w3c_sparql12/) pull
from the same w3c/rdf-tests repo at their own independently-pinned SHA;
bump all affected scripts together when investigating a specific upstream
change, but there's no requirement they share one SHA otherwise.

Can be run from anywhere - writes into tests/w3c_turtle12/data/ next to this
script. Always re-fetches and overwrites (the source is a pinned, immutable
commit, so there's nothing to gain from skipping files already on disk -
unlike a live, unpinned fetch, re-running this can never produce different
output until PINNED_SHA is bumped).

Usage: python download_w3c_turtle_tests.py
"""

from __future__ import annotations

import datetime
import io
import os
import re
import tarfile
import urllib.request

REPO = "w3c/rdf-tests"
# Bump deliberately - see this module's own docstring. Do not auto-follow
# main's tip.
PINNED_SHA = "d5d930b03ee6b63b388d0bb28fdb29ee78a59ec0"
SUBTREE_PREFIXES = {
    "eval": "rdf/rdf12/rdf-turtle/eval/",
    "syntax": "rdf/rdf12/rdf-turtle/syntax/",
}

TARBALL_URL = f"https://codeload.github.com/{REPO}/tar.gz/{PINNED_SHA}"

DEST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MANIFEST_FILE = os.path.join(DEST_DIR, "manifest.csv")
STAMP_FILE = os.path.join(DEST_DIR, "VENDORED_FROM.md")


def _fetch_tarball_members() -> dict[str, bytes]:
    """{category: {relative_filename: bytes}} for eval/ and syntax/."""
    with urllib.request.urlopen(TARBALL_URL) as resp:
        archive_bytes = resp.read()

    by_category: dict[str, dict[str, bytes]] = {name: {} for name in SUBTREE_PREFIXES}
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            # Archive root is "<repo>-<sha>/..." - strip that one path segment.
            relative = member.name.split("/", 1)[1] if "/" in member.name else member.name
            for category, prefix in SUBTREE_PREFIXES.items():
                if relative.startswith(prefix):
                    extracted = tar.extractfile(member)
                    if extracted is not None:
                        by_category[category][relative[len(prefix) :]] = extracted.read()
                    break
    return by_category


def parse_manifest_tests(manifest_text: str) -> list[tuple[str, str, str, str]]:
    """Parse one source's manifest.ttl into a list of (name, type, ttl, nt)
    tuples (nt is None/'' for syntax-only tests)."""
    tests: list[dict] = []
    current: dict = {}
    for line in manifest_text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # Start of a test entry (trs:... rdf:type ...)
        m = re.match(r'trs:([\w\-]+)\s+rdf:type\s+([^ ;]+)\s*;', line)
        if m:
            if current:
                tests.append(current)
            current = {'name': m.group(1), 'type': m.group(2), 'ttl': None, 'nt': None}
            continue
        # mf:action (ttl file). No trailing-punctuation requirement: the
        # terminating ';' or '.' isn't always on this same line (e.g.
        # turtle12-surrogate-pair-bad-01/02 in the syntax manifest put the
        # '.' on its own following line, since mf:action is their entry's
        # last predicate) - only the IRI itself needs capturing here.
        m = re.match(r'mf:action\s+<([^>]+\.ttl)>', line)
        if m and current:
            current['ttl'] = m.group(1)
            continue
        # mf:result (nt file) - same tolerance
        m = re.match(r'mf:result\s+<([^>]+\.nt)>', line)
        if m and current:
            current['nt'] = m.group(1)
            continue
    if current:
        tests.append(current)
    return [
        (t['name'], t['type'], t['ttl'], t['nt'])
        for t in tests
        if t.get('ttl') or t.get('nt')
    ]


def main() -> None:
    os.makedirs(DEST_DIR, exist_ok=True)

    by_category = _fetch_tarball_members()
    for category, files in by_category.items():
        if not files:
            raise RuntimeError(
                f"no files found under {SUBTREE_PREFIXES[category]!r} at {PINNED_SHA} - "
                "did the subtree move or the SHA get mistyped?"
            )

    # (category, (name, type, ttl, nt)) pairs across both manifests, so the
    # write step below knows which category's files dict each entry's
    # referenced filenames live in, even though they all land in the same
    # local data/ directory.
    all_tests: list[tuple[str, tuple[str, str, str, str]]] = []
    for category, files in by_category.items():
        manifest_bytes = files.get('manifest.ttl')
        if manifest_bytes is None:
            raise RuntimeError(f"{category}/manifest.ttl not found in tarball at {PINNED_SHA}")
        for t in parse_manifest_tests(manifest_bytes.decode('utf-8')):
            all_tests.append((category, t))

    print(f"Total: {len(all_tests)} tests across {len(by_category)} manifests.")

    # Write combined manifest
    with open(MANIFEST_FILE, "w") as mf:
        mf.write("test_name,test_type,ttl_file,nt_file\n")
        for _category, (test_name, test_type, ttl_file, nt_file) in all_tests:
            mf.write(f"{test_name},{test_type},{ttl_file or ''},{nt_file or ''}\n")

    # Write referenced files - always overwrite, the source is pinned.
    written = 0
    for category, (test_name, test_type, ttl_file, nt_file) in all_tests:
        files = by_category[category]
        for fname in (ttl_file, nt_file):
            if not fname:
                continue
            content = files.get(fname)
            if content is None:
                print(f"  MISSING in tarball: {category}/{fname} (test {test_name})")
                continue
            with open(os.path.join(DEST_DIR, fname), "wb") as f:
                f.write(content)
            written += 1

    stamp = (
        "# Vendored snapshot provenance\n\n"
        "Do not hand-edit files in this directory - regenerate with "
        "`python download_w3c_turtle_tests.py` after bumping `PINNED_SHA` "
        "there.\n\n"
        f"- Source: https://github.com/{REPO}/tree/{PINNED_SHA}/rdf/rdf12/rdf-turtle/\n"
        f"- Pinned commit SHA: `{PINNED_SHA}`\n"
        f"- Synced: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"- Files written: {written}\n"
        f"- Test entries: {len(all_tests)}\n"
    )
    with open(STAMP_FILE, "w", encoding="utf-8") as f:
        f.write(stamp)

    print(f"Wrote {written} files + manifest.csv to {DEST_DIR}")
    print(f"Pinned SHA: {PINNED_SHA}")


if __name__ == "__main__":
    main()
