"""Fixture supplying the non-default stores to the W3C SHACL suites."""

from __future__ import annotations

import pytest

from .known_failures import (
    KNOWN_FAILURES_FUSEKI_HTTP,
    KNOWN_FAILURES_OXIGRAPH_HTTP,
    KNOWN_FAILURES_OXIGRAPH_PERSISTED,
)
from .stores import (
    OTHER_STORES,
    http_engine_available,
    http_store,
    oxigraph_store_installed,
    persisted_oxigraph_store,
)


@pytest.fixture(params=OTHER_STORES)
def store_under_test(request, tmp_path):
    """A StoreUnderTest for each non-default store, skipped when unavailable."""
    name = request.param
    if name == "oxigraph-persisted":
        if not oxigraph_store_installed():
            pytest.skip("oxrdflib/pyoxigraph not installed - pip install oxrdflib pyoxigraph")
        store = persisted_oxigraph_store(tmp_path, KNOWN_FAILURES_OXIGRAPH_PERSISTED)
    else:
        if not http_engine_available(name):
            pytest.skip(f"{name} not running")
        known = KNOWN_FAILURES_OXIGRAPH_HTTP if name == "oxigraph-http" else KNOWN_FAILURES_FUSEKI_HTTP
        store = http_store(name, known)
    yield store
    store.cleanup()
