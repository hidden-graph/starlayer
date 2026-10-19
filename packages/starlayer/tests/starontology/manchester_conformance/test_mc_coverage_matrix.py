"""The coverage matrix: every W3C Manchester Syntax production must be exercised by the corpus.

This is the guard against "we never even listed that construct". A production with no case is a hole in
the suite itself, reported by name, before any question of whether the parser handles it.
"""

from __future__ import annotations

import pytest

from .corpus import CASES
from .grammar import ALL_ROWS, LABELLED_ALTERNATIVES, LIST_INSTANTIATIONS, PRODUCTIONS
from .known_failures import UNCOVERED_PRODUCTIONS

KNOWN_NAMES = set(PRODUCTIONS) | set(LABELLED_ALTERNATIVES) | set(LIST_INSTANTIATIONS)


def _covered() -> set[str]:
    return {name for case in CASES for name in case.covers}


@pytest.mark.manchester_conformance
def test_case_ids_are_unique():
    ids = [c.id for c in CASES]
    assert len(ids) == len(set(ids)), sorted({i for i in ids if ids.count(i) > 1})


@pytest.mark.manchester_conformance
def test_every_covers_name_is_a_real_production():
    bad = {(c.id, n) for c in CASES for n in c.covers if n not in KNOWN_NAMES}
    assert not bad, f"cases name productions that are not in the grammar table: {sorted(bad)}"


@pytest.mark.manchester_conformance
def test_every_production_has_a_case():
    missing = sorted(set(ALL_ROWS) - _covered() - set(UNCOVERED_PRODUCTIONS))
    assert not missing, f"productions with no corpus case (add one, or record why in UNCOVERED_PRODUCTIONS): {missing}"


@pytest.mark.manchester_conformance
def test_uncovered_registry_has_no_stale_entries():
    stale = sorted(n for n in UNCOVERED_PRODUCTIONS if n in _covered() or n not in KNOWN_NAMES)
    assert not stale, f"UNCOVERED_PRODUCTIONS entries that are now covered or unknown: {stale}"
