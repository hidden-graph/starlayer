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


# ---------------------------------------------------------------------------
# More stores: the two HTTP engines and an on-disk (persisted) Oxigraph
# ---------------------------------------------------------------------------
#
# Each W3C test needs two independent graphs (data and shapes). Against a
# server both live in the same dataset, each in its own uniquely-named graph
# (rdf-1.2 native mode scopes every read/write with GRAPH <identifier>), and
# are cleared when the test ends. Note what this exercises: validate() reads
# the graphs back through the store and re-encodes them for pySHACL, so the
# server is the storage and read source here - SHACL itself still runs in
# memory.

import uuid  # noqa: E402

from rdflib import URIRef  # noqa: E402

OXIGRAPH_BASE = "http://localhost:7878"
OXIGRAPH_QUERY_URL = f"{OXIGRAPH_BASE}/query"
OXIGRAPH_UPDATE_URL = f"{OXIGRAPH_BASE}/update"

FUSEKI_BASE = "http://localhost:3030/starlayergraph"
FUSEKI_QUERY_URL = f"{FUSEKI_BASE}/query"
FUSEKI_UPDATE_URL = f"{FUSEKI_BASE}/update"

_HTTP_ENGINES = {
    "oxigraph-http": (OXIGRAPH_BASE, OXIGRAPH_QUERY_URL, OXIGRAPH_UPDATE_URL),
    "fuseki-http": ("http://localhost:3030/$/ping", FUSEKI_QUERY_URL, FUSEKI_UPDATE_URL),
}

OTHER_STORES = [*_HTTP_ENGINES, "oxigraph-persisted"]


def http_engine_available(name: str) -> bool:
    import requests

    try:
        return requests.get(_HTTP_ENGINES[name][0], timeout=2).status_code == 200
    except Exception:
        return False


class StoreUnderTest:
    """A graph factory plus cleanup for one non-default store."""

    def __init__(self, name: str, new_graph, cleanup=lambda: None, known_failures=None):
        self.name = name
        self.new_graph = new_graph
        self._cleanup = cleanup
        self.known_failures = known_failures or {}

    def cleanup(self) -> None:
        self._cleanup()


def http_store(name: str, known_failures=None) -> StoreUnderTest:
    """Data and shapes graphs on one server dataset.

    The FIRST graph made in a test (every suite clones the data graph first)
    is the server's default graph, cleared on creation; later graphs are
    uniquely-named graphs. That ordering matters: a native graph sends query
    text to the server unscoped, so a SPARQL query inside a fixture (a
    ``sh:select`` target or node expression) can only see data held in the
    default graph. Everything is cleared when the test ends."""
    import requests
    from rdflib.graph import DATASET_DEFAULT_GRAPH_ID
    from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore

    _, query_url, update_url = _HTTP_ENGINES[name]
    store = SPARQLUpdateStore(query_endpoint=query_url, update_endpoint=update_url)
    created: list[URIRef] = []
    default_used = []

    def _update(text: str) -> None:
        requests.post(
            update_url, data=text, headers={"Content-Type": "application/sparql-update"}, timeout=10
        ).raise_for_status()

    def new_graph() -> StarLayerGraph:
        if not default_used:
            default_used.append(True)
            _update("CLEAR SILENT DEFAULT")
            return StarLayerGraph(store=store, identifier=DATASET_DEFAULT_GRAPH_ID, backend="rdf-1.2")
        ident = URIRef(f"urn:w3c-test:{uuid.uuid4().hex}")
        created.append(ident)
        return StarLayerGraph(store=store, identifier=ident, backend="rdf-1.2")

    def cleanup() -> None:
        for ident in created:
            _update(f"CLEAR SILENT GRAPH <{ident}>")
        if default_used:
            _update("CLEAR SILENT DEFAULT")
        created.clear()
        default_used.clear()

    return StoreUnderTest(name, new_graph, cleanup, known_failures)


def persisted_oxigraph_store(tmp_path, known_failures=None) -> StoreUnderTest:
    """An Oxigraph opened directly on a RocksDB directory (in-process, but on
    disk - the same engine as 'oxigraph-store', different storage layer)."""
    import pyoxigraph
    from oxrdflib import OxigraphStore

    counter = iter(range(1_000_000))

    def new_graph() -> StarLayerGraph:
        path = tmp_path / f"db{next(counter)}"
        return StarLayerGraph(store=OxigraphStore(store=pyoxigraph.Store(str(path))), backend="rdf-1.2")

    return StoreUnderTest("oxigraph-persisted", new_graph, known_failures=known_failures)
