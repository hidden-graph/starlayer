"""Fixtures shared by the code-KG tests. The code graph is large, so it is parsed once per run, in one place
(``codekg.queries``, which caches it for the process the way an application would), and every test reads that
copy: the dataset fixture, the merged graph behind ``run_query`` and ``run_sparql``, and the query library."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="session")
def built_kg_files():
    """The generated graphs exist: ``codekg.trig`` and ``testskg.trig`` (extractor) and ``starlayer-kg.trig`` (combined).

    They are not committed, so a fresh checkout builds them here (about 30 seconds, then 75 more for the combined file);
    an existing build is used as it is.
    """
    from codekg import KG_TRIG_PATH, ensure_built

    ensure_built()
    if not KG_TRIG_PATH.exists():
        subprocess.run([sys.executable, str(_ROOT / "scripts" / "build_kg.py")], check=True, cwd=_ROOT)


@pytest.fixture(scope="session")
def codekg_dataset(built_kg_files):
    """The code KG (source modules, test modules, curated layer) as a dataset, parsed once per run. Read it; never change it."""
    from codekg import queries

    return queries._dataset()


@pytest.fixture(scope="session")
def loaded_kg(codekg_dataset):
    """The merged code KG that the query functions read, checked to be in memory before any query test runs."""
    from codekg import CODEKG_NS, queries

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
