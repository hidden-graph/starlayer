"""A graph or a dataset held by a SPARQL endpoint (Oxigraph server, Fuseki), over the SPARQL 1.1 Protocol.

``Endpoint`` is the client: ``query`` (SELECT / ASK / CONSTRUCT, parsed by pyoxigraph into the types ``Store.query`` gives) and
``update``, over plain HTTP. ``BackedStore`` stands in for the ``pyoxigraph.Store`` of a ``StarLayerGraph(endpoint=...)`` (one graph of
the endpoint: the default graph, or the named graph the ``StarLayerGraph`` is a view of) or of a ``StarLayerDataset(endpoint=...)`` (all
of its graphs), and keeps a **full local copy**:

* The copy is pulled when the object is made, as a stream (the response is parsed as it arrives, never held whole).
* Reads are local. A write goes to the endpoint first, then to the copy, so a failed request leaves the copy as it was; the two
  agree for the writes made through this object.
* A SPARQL ``update()`` text runs on the endpoint only (``NOW()``, ``UUID()``, ``LOAD`` would not give the same result twice) and the
  copy is pulled again. Another writer's changes are seen by ``sync()``, or by itself after ``max_age`` seconds.
* The copy is in memory, or on disk with ``path=``: an Oxigraph store of its own, so the size of the graph is not bound by memory (an
  in-memory store takes about 500 to 650 bytes a triple, an on-disk one about 70 bytes on disk and a small, fixed amount of memory). A
  graph that does not fit even on disk is not served by this: validating it would need the work done on the server.
  ``pull=False`` opens an existing on-disk copy without asking the endpoint (it is then as old as its last pull).

**Blank nodes.** The endpoint gives a blank node it receives a new identifier, so the copy and the endpoint could not agree on which
is which. A blank node in a write is therefore skolemized (``starlayer.graph.oxgraph.helpers.rewrite.skolem_iri``, the IRI
``graph.skolemize()`` makes) before it is sent, and the copy gets the same IRI. A blank node that came *from* the endpoint (it is in
the copy) cannot be addressed there: writing it is a ``ValueError``. The copy is a ``pyoxigraph.Store``, which normalises literal
lexical forms (starlayer #190); an endpoint that keeps them as written (Fuseki) can differ in spelling. A dataset is pulled with a
SELECT over ``GRAPH ?g``, so a named graph with no triples is not seen. A pull that fails part way leaves an on-disk copy incomplete;
it is marked stale and the next read pulls again.
"""

from __future__ import annotations

import base64
import contextlib
import io
import os
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
        """Carry the HTTP status of the failed request next to the message."""
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
        """Hold the endpoint URLs and the request settings; nothing is sent until a query or update is made.

        Args:
            auth: ``(user, password)`` for HTTP Basic; it sets ``Authorization`` and so replaces one given in ``headers``.
            timeout: Seconds to wait on each request.
        """
        self.query_url, self.update_url, self.timeout = query_url, update_url, timeout
        self.headers = dict(headers or {})
        if auth is not None:
            self.headers["Authorization"] = "Basic " + base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()

    @contextlib.contextmanager
    def _open(self, url: str, content_type: str, accept: str, text: str) -> Iterator[tuple[str, Any]]:
        """The response of a POST as ``(content type, readable stream)``; the connection closes when the block ends."""
        request = urllib.request.Request(
            url, data=text.encode(), method="POST", headers={"Content-Type": content_type, "Accept": accept, **self.headers}
        )
        try:
            response = urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:200].decode(errors="replace").strip()
            raise EndpointError(f"{url} answered HTTP {exc.code}: {detail}", exc.code) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise EndpointError(f"cannot reach {url}: {getattr(exc, 'reason', exc)}") from exc
        with response:
            yield response.headers.get("Content-Type", "").split(";")[0].strip(), response

    def _post(self, url: str, content_type: str, accept: str, text: str) -> tuple[str, bytes]:
        with self._open(url, content_type, accept, text) as (mime, stream):
            return mime, stream.read()

    @contextlib.contextmanager
    def stream(self, text: str) -> Iterator[Any]:
        """Run a query and yield its result as it arrives: ``QuerySolutions`` or ``QueryBoolean``, or an iterator of ``Triple``. The
        result must be consumed inside the block."""
        with self._open(self.query_url, "application/sparql-query", _ACCEPT, text) as (mime, stream):
            if mime == _RESULTS:
                yield ox.parse_query_results(stream, ox.QueryResultsFormat.JSON)
            elif mime in _RDF_FORMATS:
                yield (ox.Triple(q.subject, q.predicate, q.object) for q in ox.parse(stream, _RDF_FORMATS[mime]))
            else:
                raise EndpointError(f"{self.query_url} answered with the unsupported content type {mime!r}")

    def query(self, text: str) -> Any:
        """Run a query: ``QuerySolutions`` for SELECT, ``QueryBoolean`` for ASK, a list of ``Triple`` for CONSTRUCT / DESCRIBE (the
        whole answer is read; ``stream()`` is for a large one)."""
        mime, body = self._post(self.query_url, "application/sparql-query", _ACCEPT, text)
        if mime == _RESULTS:
            return ox.parse_query_results(io.BytesIO(body), ox.QueryResultsFormat.JSON)
        if mime not in _RDF_FORMATS:
            raise EndpointError(f"{self.query_url} answered with the unsupported content type {mime!r}")
        return [ox.Triple(q.subject, q.predicate, q.object) for q in ox.parse(io.BytesIO(body), _RDF_FORMATS[mime])]

    def ask(self, text: str) -> bool:
        """Run an ASK query and return its boolean answer."""
        return bool(self.query(text))

    def update(self, text: str) -> None:
        """Run a SPARQL Update on the endpoint; a read-only endpoint (no ``update_url``) raises ``EndpointError``."""
        if self.update_url is None:
            raise EndpointError("this endpoint has no update URL (it is read-only)")
        self._post(self.update_url, "application/sparql-update", "*/*", text)

    def pull(self, graph: Any = None) -> list[ox.Triple]:
        """Every triple of one graph of the endpoint (``None`` / ``DefaultGraph``: the default graph), read whole."""
        where = "?s ?p ?o" if _is_default(graph) else f"GRAPH {_term(graph)} {{ ?s ?p ?o }}"
        return self.query(f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ {where} }}")

    @contextlib.contextmanager
    def pull_quads(self, graph: Any = None, *, dataset: bool = False) -> Iterator[Iterator[ox.Quad]]:
        """The quads of one graph (or of the whole dataset) as a stream, to be consumed inside the block."""
        if dataset:
            with self.stream("SELECT ?g ?s ?p ?o WHERE { { ?s ?p ?o } UNION { GRAPH ?g { ?s ?p ?o } } }") as rows:
                yield (ox.Quad(r["s"], r["p"], r["o"], ox.DefaultGraph() if r["g"] is None else r["g"]) for r in rows)
            return
        name = ox.DefaultGraph() if _is_default(graph) else graph
        where = "?s ?p ?o" if _is_default(graph) else f"GRAPH {_term(graph)} {{ ?s ?p ?o }}"
        with self.stream(f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ {where} }}") as triples:
            yield (ox.Quad(t.subject, t.predicate, t.object, name) for t in triples)


def _is_default(graph: Any) -> bool:
    return graph is None or isinstance(graph, ox.DefaultGraph)


def _term(term: Any) -> str:
    """A term as it is written in a SPARQL update (the N-Triples form, which SPARQL 1.2 reads too)."""
    if isinstance(term, ox.BlankNode):
        raise ValueError(f"a blank node ({term}) has no form in a SPARQL update that an endpoint would keep; it is skolemized first")
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
    """The ``pyoxigraph.Store`` of an endpoint-backed ``StarLayerGraph`` (``dataset=False``: one graph) or ``StarLayerDataset``
    (``dataset=True``): reads go to the local copy, writes to the endpoint first (see the module docstring)."""

    def __init__(
        self,
        endpoint: Endpoint,
        graph: Any = None,
        *,
        dataset: bool = False,
        max_age: float | None = None,
        path: Any = None,
        pull: bool = True,
    ) -> None:
        """Open the local copy of the endpoint's data, in memory or on disk at ``path``, and fill it by pulling.

        Args:
            graph: The graph this store holds; ``None`` is the default graph. Not used when ``dataset`` is true.
            max_age: Seconds after which a read pulls the copy again; ``None`` never refreshes by age.
            path: Directory of an on-disk Oxigraph store to use as the copy; ``None`` keeps it in memory.
            pull: ``False`` skips the initial pull so an existing on-disk copy is reused. With ``max_age`` set, the first read still pulls.
        """
        self.endpoint, self.dataset, self.max_age = endpoint, dataset, max_age
        self.graph = ox.DefaultGraph() if _is_default(graph) else graph
        self.path = None if path is None else os.fspath(path)
        self._copy: ox.Store = ox.Store(self.path)
        self._pulled_at = 0.0
        self._stale = False
        self._skolem: dict[ox.BlankNode, ox.NamedNode] = {}
        if pull:
            self.sync()

    # ---- the local copy ----------------------------------------------------------------------------------------------
    def sync(self) -> None:
        """Pull again and replace the local copy. In memory the new copy is built beside the old one and swapped in; on disk the
        copy is emptied and filled, so a pull that fails leaves it incomplete and marked stale (the next read pulls again)."""
        in_memory = self.path is None
        target = ox.Store() if in_memory else self._copy
        self._stale = True
        if not in_memory:
            target.clear()
        with self.endpoint.pull_quads(self.graph, dataset=self.dataset) as quads:
            target.bulk_extend(quads)
        if not in_memory:
            target.flush()
        self._copy, self._pulled_at, self._stale = target, time.monotonic(), False

    def _local(self) -> ox.Store:
        if self._stale or (self.max_age is not None and time.monotonic() - self._pulled_at > self.max_age):
            self.sync()
        return self._copy

    def _wrote(self, quads: list[ox.Quad]) -> None:
        self._copy.extend(quads)

    # ---- blank nodes and scope of a write ---------------------------------------------------------------------------
    def _skolemize(self, term: Any) -> Any:
        from starlayer.graph.oxgraph.helpers.rewrite import skolem_iri

        if isinstance(term, ox.Triple):
            return ox.Triple(self._skolemize(term.subject), term.predicate, self._skolemize(term.object))
        if not isinstance(term, ox.BlankNode):
            return term
        if term not in self._skolem:
            if (
                next(self._copy.quads_for_pattern(term, None, None, None), None) is not None
                or next(self._copy.quads_for_pattern(None, None, term, None), None) is not None
            ):
                raise ValueError(
                    f"the blank node {term} came from the endpoint and cannot be addressed there (the endpoint would give it a new "
                    "identifier); give the node an IRI, or write it as a new blank node"
                )
            self._skolem[term] = skolem_iri(term)
        return self._skolem[term]

    def _mine(self, quads: Iterable[Any]) -> list[ox.Quad]:
        """The quads of a write, in this store's scope and with blank nodes skolemized."""
        out = []
        for q in quads:
            if not self.dataset and q.graph_name != self.graph:
                raise ValueError(f"this store holds graph {self.graph}; it cannot write a quad of graph {q.graph_name}")
            out.append(ox.Quad(self._skolemize(q.subject), q.predicate, self._skolemize(q.object), q.graph_name))
        return out

    def _blocks(self, quads: list[ox.Quad]) -> str:
        """The triples of quads as the body of INSERT DATA / DELETE DATA, one ``GRAPH`` block per named graph."""
        by_graph: dict[Any, list[ox.Quad]] = {}
        for q in quads:
            by_graph.setdefault(q.graph_name, []).append(q)
        return " ".join(_data_block(group, graph) for graph, group in by_graph.items())

    # ---- reads: the local copy ---------------------------------------------------------------------------------------
    def __getattr__(self, name: str) -> Any:
        """Forward any other public name to the local ``pyoxigraph.Store``, pulling first if the copy is stale or older than ``max_age``."""
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._local(), name)

    def __len__(self) -> int:
        """Number of quads in the local copy."""
        return len(self._local())

    def __iter__(self) -> Iterator[ox.Quad]:
        """Iterate the quads of the local copy."""
        return iter(self._local())

    def __contains__(self, quad: Any) -> bool:
        """Whether the local copy holds the quad."""
        return quad in self._local()

    # ---- writes: the endpoint first ----------------------------------------------------------------------------------
    def extend(self, quads: Iterable[Any]) -> None:
        """Insert quads on the endpoint in chunks, adding each chunk to the copy once the endpoint has accepted it."""
        for chunk in _chunks(self._mine(quads), _CHUNK):
            self.endpoint.update(f"INSERT DATA {{ {self._blocks(chunk)} }}")
            self._wrote(chunk)

    bulk_extend = extend

    def add(self, quad: Any) -> None:
        """Insert one quad; see ``extend``."""
        self.extend([quad])

    def remove(self, quad: Any) -> None:
        """Delete one quad on the endpoint, then from the copy."""
        (q,) = self._mine([quad])
        self.endpoint.update(f"DELETE DATA {{ {self._blocks([q])} }}")
        self._copy.remove(q)

    def clear_graph(self, graph: Any) -> None:
        """Empty a graph on the endpoint, then in the copy; a graph store may clear only its own graph."""
        if not self.dataset and graph != self.graph:
            raise ValueError(f"this store holds graph {self.graph}; it cannot clear graph {graph}")
        self.endpoint.update("CLEAR DEFAULT" if _is_default(graph) else f"CLEAR SILENT GRAPH {_term(graph)}")
        self._copy.clear_graph(graph)

    def add_graph(self, graph: Any) -> None:
        """Create an empty named graph on the endpoint (dataset only); on a graph store this is a no-op for its own graph."""
        if not self.dataset:
            if graph != self.graph:
                raise ValueError(f"this store holds graph {self.graph}; it cannot add graph {graph}")
            return
        if not _is_default(graph):
            self.endpoint.update(f"CREATE SILENT GRAPH {_term(graph)}")
            self._copy.add_graph(graph)

    def remove_graph(self, graph: Any) -> None:
        """Drop a named graph on the endpoint, then in the copy; the default graph is cleared. Not available on a graph store."""
        if not self.dataset:
            raise NotImplementedError("a store backed by an endpoint holds one graph; drop it with an update on the endpoint")
        self.endpoint.update("CLEAR DEFAULT" if _is_default(graph) else f"DROP SILENT GRAPH {_term(graph)}")
        self._copy.clear_graph(graph) if _is_default(graph) else self._copy.remove_graph(graph)

    def clear(self) -> None:
        """Empty every graph of the endpoint; refused on a graph store so one graph cannot wipe the others."""
        if not self.dataset:
            raise NotImplementedError("clear() would empty the whole endpoint; clear this graph with graph.clear()")
        self.endpoint.update("CLEAR ALL")
        self._copy.clear()

    def update(self, update: str, *args: Any, **kwargs: Any) -> None:
        """SPARQL Update runs on the endpoint only; the copy is pulled again."""
        self.endpoint.update(update)
        self.sync()

    def load(self, *args: Any, **kwargs: Any) -> None:
        """Not supported; load into an endpoint-backed graph with ``graph.parse()``."""
        raise NotImplementedError("load into an endpoint-backed graph with graph.parse()")

    bulk_load = load
