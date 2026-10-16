"""TEMPORARY diagnostic conftest - not meant to be committed. Forces every
bare StarLayerGraph()/StarLayerDataset() construction across the whole
suite to use the embedded Oxigraph store (backend='rdf-1.2'), to find
non-crash failures beyond the known dirLangString `=` engine panic (see
docs/upstream-issues/oxigraph-upstream-issues.md Issue #2) - re-run after
fixing the use_baseline_representation catastrophic-slowdown bug (see
starlayer/graph/CLAUDE.md's dated entry) that caused this same diagnostic
to appear to hang at 94% progress previously.

Function-scoped and re-applied before every test, not session-scoped -
test_default_representation.py's own autouse fixture resets the global to
None after each of its own tests, so a session-scoped "set once" fixture
here would get silently clobbered for the rest of the suite the moment
that file's tests ran.
"""
import pytest


@pytest.fixture(autouse=True)
def _force_embedded_oxigraph_default():
    from starlayer.graph.backends.native_pyoxigraph import embedded_oxigraph_store
    from starlayer.graph.graph.starlayer_graph import set_default_representation

    set_default_representation(embedded_oxigraph_store)
    yield
    set_default_representation(None)
