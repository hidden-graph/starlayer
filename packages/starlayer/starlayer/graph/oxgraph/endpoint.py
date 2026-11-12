"""A graph held by a SPARQL endpoint (Oxigraph server, Fuseki), over the SPARQL 1.1 Protocol.

``Endpoint`` is the client: ``query`` (SELECT / ASK / CONSTRUCT, parsed by pyoxigraph into the types ``Store.query`` gives) and
``update``, over plain HTTP. ``BackedStore`` stands in for the ``pyoxigraph.Store`` of a ``StarLayerGraph(endpoint=...)`` and
keeps a local copy of one graph of the endpoint (the default graph, or the named graph the ``StarLayerGraph`` is a view of):

* ``cache="full"``: the local copy is pulled once and stays. A write goes to the endpoint first, then to the copy, so a failed
  request leaves the copy as it was; the two are in sync for the writes made through this object. A SPARQL ``update()`` text
  runs on the endpoint only (``NOW()``, ``UUID()``, ``LOAD`` would not give the same result twice) and the copy is pulled again.
  Another writer's changes are seen by ``sync()``, or by itself after ``max_age`` seconds.
* ``cache="temporary"``: a write goes to the endpoint only. A copy is made when something needs the triples (validation, a read)
  and is dropped by the next write, by ``release()`` or at the end of ``with graph.local():``.

A blank node cannot be written: the endpoint gives its own blank nodes new identifiers, so the copy and the endpoint could not
agree on which is which. Skolemize first (``graph.skolemize()``). The local copy is a ``pyoxigraph.Store``, which normalises
literal lexical forms (starlayer #190); an endpoint that keeps them as written (Fuseki) can differ in spelling.
"""

from __future__ import annotations

import base64
import io
import time
import urllib.error
import urllib.request
from collections.abc import Iterable, Iterator
from typing import Any

import pyoxigraph as ox

_RESULTS = "application/sparql-results+json"
_ACCEPT = f"{_RESULTS}, application/n-triples;q=0.9, text/turtle;q=0.8"
_RDF_FORMATS = {"application/n-triples": ox.RdfFormat.N_TRIPLES, "text/turtle": ox.RdfFormat.TURTLE}
_CHUNK = 2000  # triples per INSERT DATA / DELETE DATA request


class EndpointError(OSError):
    """The endpoint could not be reached or answered with an error status (``status`` is the HTTP status, ``None`` if there was
    no answer)."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class Endpoint:
    """A SPARQL endpoint: ``query_url`` for reads and ``update_url`` (omitted: read-only) for writes. ``auth`` is a
    ``(user, password)`` pair for HTTP Basic, ``headers`` any extra request headers."""

    def __init__(
        self,
        query_url: str,
        update_url: str | None = None,
        *,
        auth: tuple[str, str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.query_url, self.update_url, self.timeout = query_url, update_url, timeout
        self.headers = dict(headers or {})
        if auth is not None:
            self.headers["Authorization"] = "Basic " + base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()

    def _post(self, url: str, content_type: str, accept: str, text: str) -> tuple[str, bytes]:
        request = urllib.request.Request(
            url, data=text.encode(), method="POST", headers={"Content-Type": content_type, "Accept": accept, **self.headers}
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.headers.get("Content-Type", "").split(";")[0].strip(), response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:200].decode(errors="replace").strip()
            raise EndpointError(f"{url} answered HTTP {exc.code}: {detail}", exc.code) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise EndpointError(f"cannot reach {url}: {getattr(exc, 'reason', exc)}") from exc

    def query(self, text: str) -> Any:
        """Run a query: ``QuerySolutions`` for SELECT, ``QueryBoolean`` for ASK, a list of ``Triple`` for CONSTRUCT / DESCRIBE."""
        mime, body = self._post(self.query_url, "application/sparql-query", _ACCEPT, text)
        if mime == _RESULTS:
            return ox.parse_query_results(io.BytesIO(body), ox.QueryResultsFormat.JSON)
        if mime not in _RDF_FORMATS:
            raise EndpointError(f"{self.query_url} answered with the unsupported content type {mime!r}")
        return [ox.Triple(q.subject, q.predicate, q.object) for q in ox.parse(io.BytesIO(body), _RDF_FORMATS[mime])]

    def ask(self, text: str) -> bool:
        return bool(self.query(text))

    def update(self, text: str) -> None:
        if self.update_url is None:
            raise EndpointError("this endpoint has no update URL (it is read-only)")
        self._post(self.update_url, "application/sparql-update", "*/*", text)

    def pull(self, graph: Any = None) -> list[ox.Triple]:
        """Every triple of one graph of the endpoint (``None`` / ``DefaultGraph``: the default graph)."""
        where = "?s ?p ?o" if _is_default(graph) else f"GRAPH {_term(graph)} {{ ?s ?p ?o }}"
        return self.query(f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ {where} }}")


def _is_default(graph: Any) -> bool:
    return graph is None or isinstance(graph, ox.DefaultGraph)


def _term(term: Any) -> str:
    """A term as it is written in a SPARQL update (the N-Triples form, which SPARQL 1.2 reads too)."""
    if isinstance(term, ox.BlankNode):
        raise ValueError(
            "a blank node cannot be written to a graph held by an endpoint (the endpoint gives it a new identifier, so the copy and "
            "the endpoint cannot agree on it); skolemize the data first (graph.skolemize())"
        )
    if isinstance(term, ox.Triple):
        return f"<<( {_term(term.subject)} {_term(term.predicate)} {_term(term.object)} )>>"
    return str(term)


def _data_block(triples: Iterable[Any], graph: Any) -> str:
    body = " ".join(f"{_term(t[0])} {_term(t[1])} {_term(t[2])} ." for t in triples)
    return body if _is_default(graph) else f"GRAPH {_term(graph)} {{ {body} }}"


def _chunks(items: list[Any], size: int) -> Iterator[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class BackedStore:
    """The ``pyoxigraph.Store`` of an endpoint-backed ``StarLayerGraph``: reads go to a local copy of one graph, writes to the endpoint
    first (see the module docstring for the two modes)."""

    def __init__(self, endpoint: Endpoint, graph: Any = None, *, cache: str = "full", max_age: float | None = None) -> None:
        if cache not in ("full", "temporary"):
            raise ValueError(f"cache must be 'full' or 'temporary', not {cache!r}")
        self.endpoint = endpoint
        self.graph = ox.DefaultGraph() if _is_default(graph) else graph
        self.cache, self.max_age = cache, max_age
        self._copy: ox.Store | None = None
        self._pulled_at = 0.0
        self._holds = 0  # nested ``with graph.local()`` blocks
        if cache == "full":
            self.sync()

    # ---- the local copy ----------------------------------------------------------------------------------------------
    def sync(self) -> None:
        """Pull the graph again and replace the local copy with it."""
        triples = self.endpoint.pull(self.graph)
        fresh = ox.Store()
        fresh.extend(ox.Quad(t.subject, t.predicate, t.object, self.graph) for t in triples)
        self._copy, self._pulled_at = fresh, time.monotonic()

    def release(self) -> None:
        """Drop a temporary copy (a full copy is kept: it is the cache)."""
        if self.cache == "temporary" and not self._holds:
            self._copy = None

    def hold(self) -> None:
        self._holds += 1

    def unhold(self) -> None:
        self._holds -= 1
        self.release()

    def _local(self) -> ox.Store:
        if self._copy is None or (self.max_age is not None and time.monotonic() - self._pulled_at > self.max_age):
            self.sync()
        assert self._copy is not None
        return self._copy

    def _wrote(self, quads: list[ox.Quad]) -> None:
        """A write reached the endpoint: bring the copy along (full), or drop it (temporary)."""
        if self.cache == "full" and self._copy is not None:
            self._copy.extend(quads)
        elif self.cache == "temporary":
            self._copy = None

    def _mine(self, quads: Iterable[Any]) -> list[ox.Quad]:
        out = []
        for q in quads:
            if q.graph_name != self.graph:
                raise ValueError(f"this store holds graph {self.graph}; it cannot write a quad of graph {q.graph_name}")
            out.append(q)
        return out

    # ---- reads: the local copy ---------------------------------------------------------------------------------------
    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._local(), name)

    def __len__(self) -> int:
        return len(self._local())

    def __iter__(self) -> Iterator[ox.Quad]:
        return iter(self._local())

    def __contains__(self, quad: Any) -> bool:
        return quad in self._local()

    # ---- writes: the endpoint first ----------------------------------------------------------------------------------
    def extend(self, quads: Iterable[Any]) -> None:
        for chunk in _chunks(self._mine(quads), _CHUNK):
            self.endpoint.update(f"INSERT DATA {{ {_data_block(chunk, self.graph)} }}")
            self._wrote(chunk)

    bulk_extend = extend

    def add(self, quad: Any) -> None:
        self.extend([quad])

    def remove(self, quad: Any) -> None:
        (q,) = self._mine([quad])
        self.endpoint.update(f"DELETE DATA {{ {_data_block([q], self.graph)} }}")
        if self.cache == "full" and self._copy is not None:
            self._copy.remove(q)
        elif self.cache == "temporary":
            self._copy = None

    def clear_graph(self, graph: Any) -> None:
        if graph != self.graph:
            raise ValueError(f"this store holds graph {self.graph}; it cannot clear graph {graph}")
        self.endpoint.update("CLEAR DEFAULT" if _is_default(graph) else f"CLEAR SILENT GRAPH {_term(graph)}")
        if self.cache == "full" and self._copy is not None:
            self._copy.clear_graph(graph)
        elif self.cache == "temporary":
            self._copy = None

    def add_graph(self, graph: Any) -> None:
        if graph != self.graph:
            raise ValueError(f"this store holds graph {self.graph}; it cannot add graph {graph}")

    def update(self, update: str, *args: Any, **kwargs: Any) -> None:
        """SPARQL Update runs on the endpoint only; a full copy is pulled again, a temporary one dropped."""
        self.endpoint.update(update)
        if self.cache == "full":
            self.sync()
        else:
            self._copy = None

    def clear(self) -> None:
        raise NotImplementedError("clear() would empty the whole endpoint; clear this graph with graph.clear()")

    def remove_graph(self, graph: Any) -> None:
        raise NotImplementedError("a store backed by an endpoint holds one graph; drop it with an update on the endpoint")

    def load(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError("load into an endpoint-backed graph with graph.parse()")

    bulk_load = load
