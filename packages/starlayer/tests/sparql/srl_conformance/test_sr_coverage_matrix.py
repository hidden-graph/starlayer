"""Every production of the SRL grammar must be exercised by the corpus."""

from __future__ import annotations

import pytest

from .corpus import CASES
from .grammar import ALL_ROWS, PRODUCTIONS
from .known_failures import UNCOVERED_PRODUCTIONS


def _covered() -> set[str]:
    return {name for case in CASES for name in case.covers}


@pytest.mark.srl_conformance
def test_case_ids_are_unique():
    ids = [c.id for c in CASES]
    assert len(ids) == len(set(ids)), sorted({i for i in ids if ids.count(i) > 1})


@pytest.mark.srl_conformance
def test_every_covers_name_is_a_real_production():
    bad = {(c.id, n) for c in CASES for n in c.covers if n not in PRODUCTIONS}
    assert not bad, f"cases name productions that are not in the grammar table: {sorted(bad)}"


@pytest.mark.srl_conformance
def test_every_production_has_a_case():
    missing = sorted(set(ALL_ROWS) - _covered() - set(UNCOVERED_PRODUCTIONS))
    assert not missing, f"productions with no corpus case (add one, or record why): {missing}"


@pytest.mark.srl_conformance
def test_uncovered_registry_has_no_stale_entries():
    stale = sorted(n for n in UNCOVERED_PRODUCTIONS if n in _covered() or n not in PRODUCTIONS)
    assert not stale, f"UNCOVERED_PRODUCTIONS entries that are now covered or unknown: {stale}"
