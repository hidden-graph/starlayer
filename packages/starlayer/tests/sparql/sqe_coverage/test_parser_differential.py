"""Differential and consistency testing of the regular query path (``StarLayerGraph``/``StarLayerDataset``
``.query()``: ``parse_query_12``, lowering, execution), using the same generated queries as the sqe
property tests. The sqe tests treat that path as the oracle; these tests hold the oracle itself to account.

* ``test_matches_plain_rdflib``: every generated query is SPARQL 1.1, so plain rdflib is an independent
  reference. Both are run on the same data; the rows (or the kind of run-time error) must agree.
* ``test_prepare_and_reserialize_round_trip``: ``prepare_query_12`` followed by the project's own 1.2
  serializer must give text that returns the same rows as the original.

Opt-in (``pytest --sqe-coverage``); example count from ``STARLAYER_SQE_FUZZ_EXAMPLES``.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from rdflib import Dataset
from starlayer.sparql.parse12 import prepare_query_12
from starlayer.sparql.serialize12 import _translate_algebra_12
from tests.sparql.sqe_coverage.test_sqe_features import _rows, build_dataset
from tests.sparql.sqe_coverage.test_sqe_property_based import _QUERIES, _SETTINGS

pytestmark = pytest.mark.sqe_coverage

_STARLAYER = build_dataset()
_PLAIN = build_dataset(Dataset(), rdf12=False)


def _outcome(dataset, query):
    try:
        rows = _rows(dataset, query)
    except Exception:  # noqa: BLE001 - the kind of failure is part of the outcome
        return ("error",)
    return sorted(rows, key=repr) if isinstance(rows, list) else rows


@_SETTINGS
@given(query=_QUERIES)
def test_matches_plain_rdflib(query):
    assert _outcome(_STARLAYER, query) == _outcome(_PLAIN, query)


@_SETTINGS
@given(query=_QUERIES)
def test_prepare_and_reserialize_round_trip(query):
    text = _translate_algebra_12(prepare_query_12(query))
    assert _outcome(_STARLAYER, text) == _outcome(_STARLAYER, query), f"re-serialized text:\n{text}"
