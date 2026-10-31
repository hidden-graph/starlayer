"""The same scenarios on the old ``StarLayerGraph`` / ``StarLayerDataset`` and the new ``OxGraph`` / ``OxDataset``.

A scenario not in ``conformance.KNOWN`` must give identical normalised results. One that is listed is a documented
difference (verdict ``accepted give-up`` or ``bug``) and must still differ: when a change makes the two agree the entry is
stale and the test fails, so the list in docs/working/oxgraph-wrapper.md cannot rot silently.
"""

from __future__ import annotations

import pytest

from .conformance import KNOWN, NONDETERMINISTIC, SCENARIOS, NewImpl, OldImpl

_CACHE: dict = {}


def _both(name):
    if name not in _CACHE:
        _CACHE[name] = (SCENARIOS[name](OldImpl()), SCENARIOS[name](NewImpl()))
    return _CACHE[name]


@pytest.mark.parametrize("name", [n for n in SCENARIOS if n not in KNOWN and n not in NONDETERMINISTIC])
def test_same_result(name):
    old, new = _both(name)
    assert old == new


@pytest.mark.parametrize("name", list(KNOWN))
def test_documented_difference_still_exists(name):
    old, new = _both(name)
    verdict, why = KNOWN[name]
    assert verdict in ("accepted give-up", "bug") and why
    assert old != new, f"{name} no longer differs: delete its KNOWN entry"


def test_select_star_columns_are_alphabetical_in_the_new_class():
    """Known difference: Oxigraph orders ``SELECT *`` columns alphabetically; rdflib's order comes from a set (it varies with the
    hash seed, so it is not asserted), here the variables are the same set."""
    old, new = _both("select_star_column_order")
    assert new == sorted(new) and set(old) == set(new)
