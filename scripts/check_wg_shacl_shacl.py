"""scripts/check_wg_shacl_shacl.py - is our pinned copy of the W3C Working Group's SHACL-for-SHACL still the latest?

Fetches the upstream file and compares it with ``assets/vendor/w3c-shacl-shacl.ttl``. Exits 0 if they are identical, 1 if
upstream has moved (printing what changed), 2 if the check could not be made. Needs network access, so it is not part of
the test run: run it by hand, or on a schedule, and follow ``assets/vendor/VENDORED_FROM.md`` when it reports a change.
"""

from __future__ import annotations

import difflib
import json
import os
import sys
import urllib.request

UPSTREAM_FILE = "https://raw.githubusercontent.com/w3c/data-shapes/gh-pages/shacl12-vocabularies/shacl-shacl.ttl"
UPSTREAM_COMMITS = (
    "https://api.github.com/repos/w3c/data-shapes/commits"
    "?sha=gh-pages&path=shacl12-vocabularies/shacl-shacl.ttl&per_page=3"
)
PINNED = os.path.join(os.path.dirname(__file__), "assets", "vendor", "w3c-shacl-shacl.ttl")


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "starlayer-check-wg-shacl-shacl"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed https URLs above
        return response.read()


def main() -> int:
    try:
        upstream = _get(UPSTREAM_FILE).decode("utf8")
        commits = json.loads(_get(UPSTREAM_COMMITS))
    except Exception as exc:  # network, rate limit, ...
        print(f"could not fetch the upstream file: {exc}", file=sys.stderr)
        return 2
    with open(PINNED, encoding="utf8") as handle:
        pinned = handle.read()
    if upstream == pinned:
        print("pinned copy is identical to upstream.")
        return 0
    print("upstream has changed since the pinned copy. Latest commits to the file:")
    for commit in commits:
        print(f"  {commit['sha'][:9]} {commit['commit']['committer']['date'][:10]} {commit['commit']['message'].splitlines()[0]}")
    print()
    sys.stdout.writelines(
        difflib.unified_diff(pinned.splitlines(True), upstream.splitlines(True), "pinned", "upstream", n=2)
    )
    print("\nTo update: see scripts/assets/vendor/VENDORED_FROM.md")
    return 1


if __name__ == "__main__":
    sys.exit(main())
