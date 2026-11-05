"""Differential and consistency testing of the regular query path (``StarLayerGraph``/``StarLayerDataset``
``.query()``: ``parse_query_12``, lowering, execution), using the same generated queries as the sqe
property tests. The sqe tests treat that path as the oracle; these tests hold the oracle itself to account.

* ``test_matches_plain_rdflib``: every generated query is SPARQL 1.1, so plain rdflib is an independent
  reference. Both are run on the same data; the rows (or the kind of run-time error) must agree.

(The ``prepare_query_12`` + rdflib-algebra serializer round trip that used to be tested here is dropped: rdflib's
``translateAlgebra`` moves a FILTER into an aggregate for some generated queries, and ``sqe_tree_to_text``, which
``test_sqe_property_based`` checks, replaces that path. See ``docs/working/d2-gaps.md`` G10.)

Opt-in (``pytest --sqe-coverage``); example count from ``STARLAYER_SQE_FUZZ_EXAMPLES``.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from tests.sparql.sqe_coverage.test_sqe_features import _rows, build_dataset
from tests.sparql.sqe_coverage.test_sqe_property_based import _QUERIES, _SETTINGS

pytestmark = pytest.mark.sqe_coverage

_STARLAYER = build_dataset()
_PLAIN = build_dataset(rdf12=False).to_rdflib()  # the same data as a plain rdflib Dataset, the independent reference


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
