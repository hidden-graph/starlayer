"""Fixtures shared by the code-KG tests. The code graph is large, so it is parsed once per run, in one place
(``starlayer.codekg.queries``, which caches it for the process the way an application would), and every test reads that
copy: the dataset fixture, the merged graph behind ``run_query`` and ``run_sparql``, and the query library."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def codekg_dataset():
    """The code KG (source modules, test modules, curated layer) as a dataset, parsed once per run. Read it; never change it."""
    from starlayer.codekg import queries

    return queries._dataset()


@pytest.fixture(scope="session")
def loaded_kg(codekg_dataset):
    """The merged code KG that the query functions read, checked to be in memory before any query test runs."""
    from starlayer.codekg import CODEKG_NS, queries

    graph = queries._kg()
    assert queries._kg() is graph, "the merged KG must be built once and reused, not rebuilt per query"
    assert queries._dataset() is codekg_dataset, "the dataset fixture and the query functions must share one parsed copy"
    modules = sum(1 for _ in graph.subjects(CODEKG_NS.filePath, None))
    assert modules > 0, "the code KG loaded empty: run `python scripts/build.py --only codekg`"
    return graph


@pytest.fixture(autouse=True)
def _kg_is_in_memory_before_a_kg_test(request):
    """Every test that reads the code KG (``deferred`` or ``codekg_queries``) starts with the graph already in memory and checked."""
    if request.node.get_closest_marker("deferred") or request.node.get_closest_marker("codekg_queries"):
        request.getfixturevalue("loaded_kg")
