"""The test groups themselves: each area is selectable alone, and the deferred checks stay out of an ordinary run."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent


def _collect(*args: str) -> list[str]:
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *args],
        cwd=TESTS.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in done.stdout.splitlines() if "::" in line]


def test_an_area_marker_selects_exactly_that_directory():
    ids = _collect("tests/kg", "tests/starontology", "-m", "kg")
    assert ids and all("/tests/kg/" in i for i in ids)


def test_deferred_checks_are_left_out_unless_asked_for():
    plain = _collect("tests/kg/unit/test_queries.py")
    with_deferred = _collect("tests/kg/unit/test_queries.py", "--deferred")
    wanted = "test_queries.py::test_the_library_is_valid"
    assert not any(wanted in i for i in plain)
    assert any(wanted in i for i in with_deferred)


def test_every_area_directory_has_a_marker():
    """A new area directory must be added to ``AREAS`` in conftest.py, or ``-m <area>`` would silently skip it."""
    from conftest import AREAS

    on_disk = {p.name for p in TESTS.iterdir() if p.is_dir() and not p.name.startswith(("_", ".")) and any(p.rglob("test_*.py"))}
    assert on_disk == set(AREAS)
