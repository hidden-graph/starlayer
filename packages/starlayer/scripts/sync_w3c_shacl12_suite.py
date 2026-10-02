#!/usr/bin/env python3
"""Vendor a pinned snapshot of the W3C SHACL 1.2 test suite into tests/vendor/.

Source: https://github.com/w3c/data-shapes/tree/gh-pages/shacl12-test-suite

Downloads the ``shacl12-test-suite/`` subtree at a pinned commit SHA (below)
by fetching the repository's tarball snapshot (one HTTP request - the suite
has ~400 files, and GitHub's unauthenticated REST API rate limit of 60
requests/hour makes a per-file "git blobs" API approach infeasible) and
writes it verbatim into ``tests/vendor/shacl12-test-suite/``, replacing
whatever was there. Writes a ``VENDORED_FROM.md`` stamp recording the
source, pinned SHA, sync date, and file counts, so a reviewer can see
exactly what changed by diffing one file.

Bumping the pinned SHA is a deliberate, one-line, reviewable change - this
script never auto-follows the branch tip. See
docs/w3c-shacl12-test-suite-plan.md for the full integration plan and the
procedure for absorbing suite growth over time.

Usage: python scripts/sync_w3c_shacl12_suite.py
"""

from __future__ import annotations

import datetime
import io
import tarfile
import urllib.request
from pathlib import Path

REPO = "w3c/data-shapes"
# Bump deliberately - see docs/w3c-shacl12-test-suite-plan.md's "Ongoing
# maintenance" section for the review/bump procedure. Do not auto-follow
# gh-pages's tip.
PINNED_SHA = "59b38cd7061ff3e6e3dc9e216836ef848f7d8baf"
SUBTREE_PREFIX = "shacl12-test-suite/"

REPO_ROOT = Path(__file__).resolve().parents[1]
DEST = REPO_ROOT / "tests" / "vendor" / "shacl12-test-suite"

TARBALL_URL = f"https://codeload.github.com/{REPO}/tar.gz/{PINNED_SHA}"


def _fetch_tarball_members() -> list[tuple[str, bytes]]:
    with urllib.request.urlopen(TARBALL_URL) as resp:
        archive_bytes = resp.read()

    members: list[tuple[str, bytes]] = []
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            # Archive root is "<repo>-<sha>/..." - strip that one path segment.
            relative = member.name.split("/", 1)[1] if "/" in member.name else member.name
            if not relative.startswith(SUBTREE_PREFIX):
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            members.append((relative[len(SUBTREE_PREFIX) :], extracted.read()))
    return members


def main() -> None:
    entries = _fetch_tarball_members()
    if not entries:
        raise RuntimeError(
            f"no files found under {SUBTREE_PREFIX!r} at {PINNED_SHA} - "
            "did the subtree move or the SHA get mistyped?"
        )

    if DEST.exists():
        for path in sorted(DEST.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
        for path in sorted(DEST.rglob("*"), reverse=True):
            if path.is_dir():
                path.rmdir()

    for relative_path, content in entries:
        dest_path = DEST / relative_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(content)

    file_count = len(entries)
    ttl_count = sum(1 for path, _ in entries if path.endswith(".ttl"))
    srl_count = sum(1 for path, _ in entries if path.endswith(".srl"))

    stamp = DEST / "VENDORED_FROM.md"
    stamp.write_text(
        "# Vendored snapshot provenance\n\n"
        "Do not hand-edit files under this directory - regenerate with "
        "`python scripts/sync_w3c_shacl12_suite.py` after bumping "
        "`PINNED_SHA` there.\n\n"
        f"- Source: https://github.com/{REPO}/tree/gh-pages/{SUBTREE_PREFIX}\n"
        f"- Pinned commit SHA: `{PINNED_SHA}`\n"
        f"- Synced: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"- Files vendored: {file_count} ({ttl_count} `.ttl`, {srl_count} `.srl`)\n",
        encoding="utf-8",
    )

    print(f"Vendored {file_count} files ({ttl_count} .ttl, {srl_count} .srl) to {DEST}")
    print(f"Pinned SHA: {PINNED_SHA}")


if __name__ == "__main__":
    main()
