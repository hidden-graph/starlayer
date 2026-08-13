"""Phase 1 of docs/w3c-shacl12-test-suite-plan.md: every manifest file under
tests/core/ and tests/sparql/ must at least *parse*, independent of what
test type it defines.

A handful of vendored fixtures use ordinary Turtle constructs
StarLayerTurtleParser doesn't yet support (see
docs/starlayergraph-upstream-change-log.md's 2026-07-30 entries). iter_manifest_entries
turns a load failure into a synthetic ManifestEntry (entry_type=None,
parse_error set) instead of raising, so it doesn't hide every other entry
in that file's ancestry from collection - but that also means those
entries are invisible to test_w3c_validate.py's type-filtered walk (it has
no way to know what type an unparseable file's entry would have been).
This module is where they're surfaced instead, so a load failure gets a
reasoned, visible disposition rather than silently vanishing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .ids import portable_id
from .known_failures import KNOWN_FAILURES
from .manifest import ManifestEntry, iter_manifest_entries

VENDOR_ROOT = Path(__file__).resolve().parents[1] / "vendor" / "shacl12-test-suite"
_SCOPES = ("core", "sparql")


def _collect_parse_errors() -> list[ManifestEntry]:
    entries: list[ManifestEntry] = []
    for scope in _SCOPES:
        manifest_path = VENDOR_ROOT / "tests" / scope / "manifest.ttl"
        if not manifest_path.exists():
            continue
        entries.extend(entry for entry in iter_manifest_entries(manifest_path) if entry.parse_error is not None)
    return entries


_PARSE_ERRORS = _collect_parse_errors()


def pytest_generate_tests(metafunc):
    if "entry" not in metafunc.fixturenames:
        return
    if _PARSE_ERRORS:
        metafunc.parametrize("entry", _PARSE_ERRORS, ids=[portable_id(e, VENDOR_ROOT) for e in _PARSE_ERRORS])
    else:
        metafunc.parametrize(
            "entry",
            [pytest.param(None, marks=pytest.mark.skip(reason="no vendored suite, or nothing failed to parse"))],
            ids=["no-parse-errors"],
        )


def test_w3c_file_parses(entry: ManifestEntry | None) -> None:
    if entry is None:
        return
    entry_key = portable_id(entry, VENDOR_ROOT)
    if entry_key in KNOWN_FAILURES:
        pytest.xfail(KNOWN_FAILURES[entry_key])
    pytest.fail(f"{entry.source_path} failed to parse and has no known_failures.py entry: {entry.parse_error}")
