"""Graph factories for running the W3C SHACL 1.2 suites through different
stores. Every suite starts by cloning a parsed document into a fresh graph
(``manifest.clone_graph``), so a store axis is just a different ``new_graph``
factory handed to that one function.

``default`` is the ordinary in-memory ``StarLayerGraph()``. ``oxigraph-store``
is an in-process Oxigraph (oxrdflib's ``OxigraphStore`` over a path-less
``pyoxigraph.Store``) in ``rdf-1.2`` native mode - no server, a fresh
independent store per call.
"""

from __future__ import annotations

import pytest
from starlayer.graph.graph.starlayer_graph import StarLayerGraph


def oxigraph_store_installed() -> bool:
    try:
        import oxrdflib  # noqa: F401
        import pyoxigraph  # noqa: F401
    except ImportError:
        return False
    return True


def oxigraph_store_graph() -> StarLayerGraph:
    import pyoxigraph
    from oxrdflib import OxigraphStore

    return StarLayerGraph(store=OxigraphStore(store=pyoxigraph.Store()), backend="rdf-1.2")


oxigraph_store = pytest.mark.skipif(
    not oxigraph_store_installed(),
    reason="oxrdflib/pyoxigraph not installed - pip install oxrdflib pyoxigraph",
)
