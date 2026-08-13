"""
tests/test_w3c_sparql12_oxigraph_roundtrip.py

Proves this project's core claim - that translating a SPARQL 1.2 query
through its RDF algebra representation and back preserves semantics - using
a real, independent, spec-conformant RDF 1.2 engine (Oxigraph) as the
execution ground truth on *both* sides of the comparison.

This is a different check from test_w3c_sparql12.py's own eval tests, which
compare the *regenerated* query's results against the W3C suite's official
expected output, executed via starlayergraph's in-memory (rdf-1.1) backend. That
conflates two independent questions: (a) did this project's translation
preserve the query's semantics, and (b) does starlayergraph's in-memory backend
execute SPARQL 1.2 correctly at all - the latter has known, unrelated bugs
(see the sibling starlayergraph repo's own test suite: its W3C harness
currently xfails/fails op-2, order-1, order-2, construct-5 against its
in-memory backend specifically, all traced to how that backend represents
triple terms internally during query evaluation - nothing to do with this
project's translation).

The methodology here isolates question (a) cleanly:
  1. Load the entry's RDF 1.2 data into a live Oxigraph-backed
     StarLayerGraph/StarLayerDataset (backend='rdf-1.2', no query rewriting
     - see starlayergraph's own native.py module docstring).
  2. Run the *original* W3C query text (Q) against it.
  3. Translate Q -> this project's RDF algebra -> regenerate SPARQL 1.2
     text (Q').
  4. Run Q' against the *same* already-loaded Oxigraph data.
  5. Compare Q's results directly against Q''s results. If they match,
     translation preserved semantics for this query - independent of
     whether the W3C fixture's own expected answer or starlayergraph's
     in-memory backend are involved at all.

Requires a running Oxigraph instance - see starlayergraph's own
tests/integration/test_oxigraph_backend.py module docstring for the
docker run command. Skips cleanly if unreachable.
"""

from __future__ import annotations

import pytest
import requests
from rdflib.compare import to_isomorphic
from rdflib.graph import DATASET_DEFAULT_GRAPH_ID
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore

from starlayergraph.graph.starlayergraph_dataset import StarLayerDataset
from starlayergraph.graph.starlayergraph_graph import StarLayerGraph

from starsparql import query_to_rdf, rdf_to_query
from starsparql.parse12 import prepare_query_12
from starsparql.serialize12 import translate_algebra_12
from w3c_sparql12.harness import bindings_match, load_index, skolemize_graph

pytestmark = pytest.mark.w3c_sparql12

# ---------------------------------------------------------------------------
# Endpoint config - same container/URLs as starlayergraph's own
# tests/integration/test_oxigraph_backend.py.
# ---------------------------------------------------------------------------

OXIGRAPH_BASE = "http://localhost:7878"
OXIGRAPH_QUERY_URL = f"{OXIGRAPH_BASE}/query"
OXIGRAPH_UPDATE_URL = f"{OXIGRAPH_BASE}/update"

# Same dataset name/endpoint shape as starlayergraph's own
# tests/integration/test_fuseki_backend.py - create it first with:
#   curl -X POST http://localhost:3030/$/datasets -u admin:admin \
#     --data 'dbName=starlayergraph&dbType=mem'
FUSEKI_BASE = "http://localhost:3030/starlayergraph"
FUSEKI_QUERY_URL = f"{FUSEKI_BASE}/query"
FUSEKI_UPDATE_URL = f"{FUSEKI_BASE}/update"

_ENDPOINTS = {
    "oxigraph": (OXIGRAPH_BASE, OXIGRAPH_QUERY_URL, OXIGRAPH_UPDATE_URL),
    "fuseki": (FUSEKI_BASE, FUSEKI_QUERY_URL, FUSEKI_UPDATE_URL),
}


def _backend_available(name: str) -> bool:
    base = _ENDPOINTS[name][0]
    try:
        url = base if name == "oxigraph" else f"{base.rsplit('/', 1)[0]}/$/ping"
        return requests.get(url, timeout=2).status_code == 200
    except Exception:
        return False


@pytest.fixture(params=list(_ENDPOINTS))
def backend(request) -> str:
    name = request.param
    if not _backend_available(name):
        pytest.skip(f"{name} not running")
    return name


def _clear_store(backend: str) -> None:
    _, _, update_url = _ENDPOINTS[backend]
    requests.post(
        update_url,
        data="CLEAR ALL",
        headers={"Content-Type": "application/sparql-update"},
        timeout=10,
    ).raise_for_status()


# ---------------------------------------------------------------------------
# Data loading - same format dispatch as test_w3c_sparql12.py's own
# _data_format(), duplicated rather than imported (that module isn't a
# package other test modules import from, matching this project's existing
# convention of each test file being self-contained).
# ---------------------------------------------------------------------------

_DATA_FORMAT_BY_SUFFIX = {
    ".ttl": "turtle12",
    ".trig": "trig12",
    ".nq": "nq12",
    ".nt": "nt12",
}
_DATASET_FORMATS = {"trig12", "nq12"}


def _data_format(entry) -> str:
    for suffix, fmt in _DATA_FORMAT_BY_SUFFIX.items():
        if entry.data_file.endswith(suffix):
            return fmt
    raise ValueError(f"no known RDF-1.2 format for data file {entry.data_file!r}")


def _new_oxigraph_graph(entry, backend: str = "oxigraph") -> StarLayerGraph | StarLayerDataset:
    """A fixture's data may define named graphs (TriG/N-Quads) - those need
    a real multi-graph StarLayerDataset, matching starlayergraph's own
    test_w3c_sparql12_eval.py::_new_oxigraph_graph(). A plain (non-dataset)
    StarLayerGraph is given DATASET_DEFAULT_GRAPH_ID as its identifier so
    its triples land in the endpoint's real (unnamed) default graph - what
    an unmodified query with no GRAPH clause looks at by default (see
    StarLayerGraph._native_scoped()'s own docstring in the sibling repo).
    Name kept as `_new_oxigraph_graph` (not renamed to something backend-
    generic) since Oxigraph remains the default/primary target - `backend`
    lets the parametrized `backend` fixture route the identical fixture data
    at a second engine (Fuseki) instead, to distinguish a genuine translation
    bug from an engine-specific quirk.
    """
    _, query_url, update_url = _ENDPOINTS[backend]
    store = SPARQLUpdateStore(query_endpoint=query_url, update_endpoint=update_url)
    if entry.data_file and _data_format(entry) in _DATASET_FORMATS:
        return StarLayerDataset(store=store, backend="rdf-1.2")
    return StarLayerGraph(store=store, identifier=DATASET_DEFAULT_GRAPH_ID, backend="rdf-1.2")


def _regenerate(query_text: str) -> str:
    """Q -> this project's RDF algebra -> Q' (SPARQL 1.2 text)."""
    prepared = prepare_query_12(query_text)
    graph, root = query_to_rdf(prepared)
    reconstructed = rdf_to_query(graph, root)
    return translate_algebra_12(reconstructed)


ALL_ENTRIES = load_index()
EVAL_SELECT = [
    e for e in ALL_ENTRIES if e.test_type == "QueryEvaluationTest" and e.result_file.endswith(".srj")
]
EVAL_CONSTRUCT = [
    e for e in ALL_ENTRIES if e.test_type == "QueryEvaluationTest" and e.result_file.endswith(".ttl")
]

_no_data = pytest.mark.skipif(
    not ALL_ENTRIES, reason="W3C SPARQL 1.2 test data not fetched - run download_w3c_sparql12_tests.py"
)


@_no_data
@pytest.mark.parametrize("entry", EVAL_SELECT, ids=lambda e: e.test_iri)
def test_select_semantic_equivalence_oxigraph(backend, entry):
    query_text = entry.read(entry.query_file)
    regenerated_text = _regenerate(query_text)

    _clear_store(backend)
    g = _new_oxigraph_graph(entry, backend)
    if entry.data_file:
        g.parse(data=entry.read(entry.data_file), format=_data_format(entry))

    original = [dict(row) for row in g.query(query_text).bindings]
    regenerated = [dict(row) for row in g.query(regenerated_text).bindings]

    assert bindings_match(original, regenerated), (
        f"original query and regenerated query disagree against the same "
        f"{backend}-backed data.\noriginal Q:\n{query_text}\n\nregenerated Q':\n{regenerated_text}"
    )


@_no_data
@pytest.mark.parametrize("entry", EVAL_CONSTRUCT, ids=lambda e: e.test_iri)
def test_construct_semantic_equivalence_oxigraph(backend, entry):
    query_text = entry.read(entry.query_file)
    regenerated_text = _regenerate(query_text)

    _clear_store(backend)
    g = _new_oxigraph_graph(entry, backend)
    if entry.data_file:
        g.parse(data=entry.read(entry.data_file), format=_data_format(entry))

    original_graph = g.query(query_text).graph
    regenerated_graph = g.query(regenerated_text).graph

    assert to_isomorphic(skolemize_graph(original_graph)) == to_isomorphic(skolemize_graph(regenerated_graph)), (
        f"original query and regenerated query disagree against the same "
        f"Oxigraph-backed data.\noriginal Q:\n{query_text}\n\nregenerated Q':\n{regenerated_text}"
    )
