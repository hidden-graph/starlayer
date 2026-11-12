"""A graph held by a SPARQL endpoint: the ``Endpoint`` client, and ``StarLayerGraph(endpoint=..., cache="full" | "temporary")``.

Every test runs against a mock endpoint (a ``pyoxigraph.Store`` behind ``http.server``) and, when they answer on localhost, against a
real Oxigraph server (``:7878``) and Fuseki (``:3030/ds``): see ``benchmarks-graph/README.md`` for the docker commands. A test names its own
graph so a real server is left as it was found.
"""

from __future__ import annotations

import io
import threading
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import pyoxigraph as ox
import pytest
from starlayer.graph import Endpoint, EndpointError, StarLayerGraph

EX = "http://example.org/"
XSD_INT = ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer")


def _n(name: str) -> ox.NamedNode:
    return ox.NamedNode(EX + name)


class _Mock:
    """An endpoint in this process: ``/query`` and ``/update`` over a ``pyoxigraph.Store``; it records the last request headers."""

    def __init__(self) -> None:
        self.store = ox.Store()
        self.headers: dict[str, str] = {}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                pass

            def do_POST(self) -> None:
                outer.headers = dict(self.headers)
                text = self.rfile.read(int(self.headers["Content-Length"])).decode()
                try:
                    if self.path == "/update":
                        outer.store.update(text)
                        self.send_response(204)
                        self.end_headers()
                        return
                    result = outer.store.query(text)
                except Exception as exc:  # noqa: BLE001  (a bad request is a 400, as a real endpoint says)
                    body = str(exc).encode()
                    self.send_response(400)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                out = io.BytesIO()
                if isinstance(result, (ox.QuerySolutions, ox.QueryBoolean)):
                    result.serialize(out, ox.QueryResultsFormat.JSON)
                    mime = "application/sparql-results+json"
                else:
                    result.serialize(out, ox.RdfFormat.N_TRIPLES)
                    mime = "application/n-triples"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(out.getvalue())))
                self.end_headers()
                self.wfile.write(out.getvalue())

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        port = self.server.server_address[1]
        self.endpoint = Endpoint(f"http://127.0.0.1:{port}/query", f"http://127.0.0.1:{port}/update")


def _reachable(url: str) -> bool:
    try:
        urllib.request.urlopen(urllib.request.Request(url + "?query=ASK%7B%7D", headers={"Accept": "application/sparql-results+json"}), timeout=1)
        return True
    except OSError:
        return False


_REAL = {"oxigraph": ("http://localhost:7878/query", "http://localhost:7878/update"), "fuseki": ("http://localhost:3030/ds/query", "http://localhost:3030/ds/update")}


@pytest.fixture(scope="module")
def mock():
    return _Mock()


@pytest.fixture(params=["mock", *_REAL])
def endpoint(request, mock):
    if request.param == "mock":
        return mock.endpoint
    query_url, update_url = _REAL[request.param]
    if not _reachable(query_url):
        pytest.skip(f"no {request.param} server at {query_url}")
    return Endpoint(query_url, update_url)


@pytest.fixture
def graph_name(endpoint):
    name = _n(f"test-{uuid.uuid4().hex}")
    yield name
    endpoint.update(f"DROP SILENT GRAPH <{name.value}>")


def _remote(endpoint, name) -> set:
    return {(t.subject, t.predicate, t.object) for t in endpoint.pull(name)}


def _seed(endpoint, name, *triples) -> None:
    body = " ".join(f"<{s}> <{p}> {o} ." for s, p, o in triples)
    endpoint.update(f"INSERT DATA {{ GRAPH <{name.value}> {{ {body} }} }}")


# ------------------------------------------------------------------------------------------------------------ the client
def test_the_client_returns_pyoxigraph_results(endpoint, graph_name) -> None:
    _seed(endpoint, graph_name, (EX + "a", EX + "v", "1"), (EX + "a", EX + "v", '"x"@en'))
    graph = f"GRAPH <{graph_name.value}>"
    solutions = endpoint.query(f"SELECT ?o WHERE {{ {graph} {{ ?s ?p ?o }} }} ORDER BY ?o")
    assert isinstance(solutions, ox.QuerySolutions) and len(list(solutions)) == 2
    assert endpoint.ask(f"ASK {{ {graph} {{ <{EX}a> <{EX}v> 1 }} }}") is True
    triples = endpoint.query(f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ {graph} {{ ?s ?p ?o }} }}")
    assert len(triples) == 2 and all(isinstance(t, ox.Triple) for t in triples)


def test_a_bad_query_is_an_endpoint_error_with_the_status(endpoint) -> None:
    with pytest.raises(EndpointError) as caught:
        endpoint.query("SELEKT nonsense")
    assert caught.value.status == 400


def test_an_unreachable_endpoint_is_an_endpoint_error() -> None:
    with pytest.raises(EndpointError, match="cannot reach"):
        Endpoint("http://127.0.0.1:9/query", timeout=1).query("ASK {}")


def test_a_read_only_endpoint_refuses_an_update(mock) -> None:
    with pytest.raises(EndpointError, match="read-only"):
        Endpoint(mock.endpoint.query_url).update("CLEAR DEFAULT")


def test_basic_auth_and_headers_are_sent(mock) -> None:
    client = Endpoint(mock.endpoint.query_url, auth=("ada", "secret"), headers={"X-Test": "1"})
    client.query("ASK {}")
    assert mock.headers["Authorization"].startswith("Basic ") and mock.headers["X-Test"] == "1"


# ----------------------------------------------------------------------------------------------------------- cache="full"
def test_a_full_cache_pulls_the_graph_and_reads_locally(endpoint, graph_name) -> None:
    _seed(endpoint, graph_name, (EX + "a", EX + "v", "1"))
    g = StarLayerGraph(endpoint=endpoint, identifier=graph_name)
    assert len(g) == 1 and (_n("a"), _n("v"), ox.Literal("1", datatype=XSD_INT)) in set(g)


def test_a_write_is_recorded_on_the_endpoint_and_in_the_copy(endpoint, graph_name) -> None:
    g = StarLayerGraph(endpoint=endpoint, identifier=graph_name)
    g.add((_n("a"), _n("v"), ox.Literal("1", datatype=XSD_INT)))
    g.extend([(_n("b"), _n("v"), ox.Literal("x", language="en")), (_n("c"), _n("t"), ox.Triple(_n("s"), _n("p"), _n("o")))])
    assert len(g) == 3 and len(_remote(endpoint, graph_name)) == 3
    g.remove((_n("b"), None, None))
    assert len(g) == 2 and len(_remote(endpoint, graph_name)) == 2
    g.parse(data="@prefix ex: <http://example.org/> . ex:d ex:v 4 .", format="turtle")
    assert len(g) == 3 and (_n("d"), _n("v"), ox.Literal("4", datatype=XSD_INT)) in _remote(endpoint, graph_name)
    g.clear()
    assert len(g) == 0 and _remote(endpoint, graph_name) == set()


def test_rdf_12_terms_round_trip(endpoint, graph_name) -> None:
    g = StarLayerGraph(endpoint=endpoint, identifier=graph_name)
    directional = ox.Literal("y", language="en", direction=ox.BaseDirection.LTR)
    g.add((_n("a"), _n("label"), directional))
    g.add((_n("a"), _n("claim"), ox.Triple(_n("s"), _n("p"), _n("o"))))
    fresh = StarLayerGraph(endpoint=endpoint, identifier=graph_name)  # pulled again from the endpoint
    assert set(fresh) == set(g) and (_n("a"), _n("label"), directional) in set(fresh)


def test_a_failed_endpoint_write_leaves_the_copy_as_it_was(mock) -> None:
    g = StarLayerGraph(endpoint=Endpoint(mock.endpoint.query_url, mock.endpoint.update_url), identifier=_n(f"fail-{uuid.uuid4().hex}"))
    g.add((_n("a"), _n("v"), _n("b")))
    g.store.endpoint.update_url = "http://127.0.0.1:9/update"  # now unreachable
    g.store.endpoint.timeout = 1
    with pytest.raises(EndpointError):
        g.add((_n("c"), _n("v"), _n("d")))
    assert len(g) == 1


def test_a_blank_node_is_refused_before_anything_is_written(endpoint, graph_name) -> None:
    g = StarLayerGraph(endpoint=endpoint, identifier=graph_name)
    with pytest.raises(ValueError, match="skolemize"):
        g.extend([(_n("a"), _n("v"), _n("b")), (ox.BlankNode(), _n("v"), _n("c"))])
    assert len(g) == 0 and _remote(endpoint, graph_name) == set()


def test_a_sparql_update_runs_on_the_endpoint_and_the_copy_is_pulled_again(endpoint, graph_name) -> None:
    g = StarLayerGraph(endpoint=endpoint, identifier=graph_name)
    g.add((_n("a"), _n("v"), ox.Literal("1", datatype=XSD_INT)))
    g.update(f"INSERT {{ GRAPH <{graph_name.value}> {{ ?s <{EX}w> ?o }} }} WHERE {{ GRAPH <{graph_name.value}> {{ ?s <{EX}v> ?o }} }}")
    assert (_n("a"), _n("w"), ox.Literal("1", datatype=XSD_INT)) in set(g) and len(_remote(endpoint, graph_name)) == 2


def test_another_writers_change_is_seen_by_sync_and_by_max_age(endpoint, graph_name) -> None:
    g = StarLayerGraph(endpoint=endpoint, identifier=graph_name)
    _seed(endpoint, graph_name, (EX + "a", EX + "v", "1"))
    assert len(g) == 0  # a copy is in sync with its own writes
    assert len(g.sync()) == 1
    aging = StarLayerGraph(endpoint=endpoint, identifier=graph_name, max_age=0.0)
    _seed(endpoint, graph_name, (EX + "b", EX + "v", "2"))
    assert len(aging) == 2


def test_the_default_graph_can_be_held_too(mock) -> None:
    mock.store.update("CLEAR DEFAULT")
    g = StarLayerGraph(endpoint=mock.endpoint)
    g.add((_n("a"), _n("v"), _n("b")))
    assert mock.store.query("ASK { <http://example.org/a> <http://example.org/v> <http://example.org/b> }")
    g.clear()
    assert len(g) == 0 and not mock.store.query("ASK { ?s ?p ?o }")


# ----------------------------------------------------------------------------------------------------- cache="temporary"
def test_a_temporary_cache_writes_to_the_endpoint_and_copies_only_when_read(endpoint, graph_name) -> None:
    g = StarLayerGraph(endpoint=endpoint, identifier=graph_name, cache="temporary")
    g.add((_n("a"), _n("v"), _n("b")))
    assert g.store._copy is None  # a write needs no copy
    assert len(_remote(endpoint, graph_name)) == 1
    assert len(g) == 1 and g.store._copy is not None  # a read makes it
    g.add((_n("c"), _n("v"), _n("d")))
    assert g.store._copy is None  # the next write drops it
    assert len(g) == 2


def test_local_holds_one_copy_for_the_block_and_drops_it_after(endpoint, graph_name) -> None:
    _seed(endpoint, graph_name, (EX + "a", EX + "v", f"<{EX}b>"))
    g = StarLayerGraph(endpoint=endpoint, identifier=graph_name, cache="temporary")
    with g.local():
        assert len(g) == 1
        copy = g.store._copy
        assert len(g) == 1 and g.store._copy is copy  # one pull for the block
    assert g.store._copy is None
    g.release()  # harmless when there is none


# ------------------------------------------------------------------------------------------------------------ validation
_SHAPES = """
@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:P ; sh:property [ sh:path ex:v ; sh:minCount 1 ] .
"""


@pytest.mark.parametrize("cache", ["full", "temporary"])
def test_validate_and_extract_work_on_an_endpoint_graph(endpoint, graph_name, cache) -> None:
    from starlayer.shacl import extract_subgraph, validate

    shapes = StarLayerGraph()
    shapes.parse(data=_SHAPES, format="turtle12")
    g = StarLayerGraph(endpoint=endpoint, identifier=graph_name, cache=cache)
    g.add((_n("a"), ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), _n("P")))
    assert not validate(g, shapes, meta_shacl=False).conforms
    g.add((_n("a"), _n("v"), ox.Literal("1", datatype=XSD_INT)))
    assert validate(g, shapes, meta_shacl=False).conforms
    assert len(extract_subgraph(g, shapes)) == 2
    if cache == "temporary":
        assert g.store._copy is None  # validation held its copy for the call only
