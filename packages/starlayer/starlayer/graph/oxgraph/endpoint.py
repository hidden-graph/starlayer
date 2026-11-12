"""A graph or a dataset held by a SPARQL endpoint (Oxigraph server, Fuseki), over the SPARQL 1.1 Protocol.

``Endpoint`` is the client: ``query`` (SELECT / ASK / CONSTRUCT, parsed by pyoxigraph into the types ``Store.query`` gives) and
``update``, over plain HTTP. ``BackedStore`` stands in for the ``pyoxigraph.Store`` of a ``StarLayerGraph(endpoint=...)`` (one graph of
the endpoint: the default graph, or the named graph the ``StarLayerGraph`` is a view of) or of a ``StarLayerDataset(endpoint=...)`` (all
of its graphs), and keeps a local copy:

* ``cache="full"``: the copy is pulled once and stays. A write goes to the endpoint first, then to the copy, so a failed request
  leaves the copy as it was; the two agree for the writes made through this object. A SPARQL ``update()`` text runs on the endpoint
  only (``NOW()``, ``UUID()``, ``LOAD`` would not give the same result twice) and the copy is pulled again. Another writer's changes
  are seen by ``sync()``, or by itself after ``max_age`` seconds.
* ``cache="temporary"``: a write goes to the endpoint only. See below for what makes a copy.

**What needs the copy (``cache="temporary"``).** The copy is the whole graph, pulled once, and is kept while a ``with graph.local():``
block is open (``validate``, ``evaluate``, ``apply_rules``, ``extract_subgraph`` and ``target_nodes`` open one for the call), until the
next write, or until ``release()``. Without a copy:

* a **point read**, a ``triples`` / ``objects`` / ``subjects`` / ``value`` / ``in`` pattern with at least one bound term and no blank
  node, is one query to the endpoint, and makes no copy;
* everything else is a **whole-graph read** and pulls the copy: ``len``, iteration, ``triples()`` with no bound term, ``query()``
  (it runs locally, with the library's own entailment and pre-binding), ``serialize``, ``copy``, the set operations and every helper
  that walks the graph.

**Blank nodes.** The endpoint gives a blank node it receives a new identifier, so the copy and the endpoint could not agree on which
is which. A blank node in a write is therefore skolemized (``starlayer.graph.oxgraph.helpers.rewrite.skolem_iri``, the IRI
``graph.skolemize()`` makes) before it is sent, and the copy gets the same IRI. A blank node that came *from* the endpoint (it is in
the copy) cannot be addressed there: writing it is a ``ValueError``. The local copy is a ``pyoxigraph.Store``, which normalises
literal lexical forms (starlayer #190); an endpoint that keeps them as written (Fuseki) can differ in spelling. A dataset is pulled
with a SELECT over ``GRAPH ?g``, so a named graph with no triples is not seen.
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


    def pull_dataset(self) -> list[ox.Quad]:
        """Every quad of the endpoint's dataset: its default graph and each named graph."""
        rows = self.query("SELECT ?g ?s ?p ?o WHERE { { ?s ?p ?o } UNION { GRAPH ?g { ?s ?p ?o } } }")
        return [ox.Quad(r["s"], r["p"], r["o"], ox.DefaultGraph() if r["g"] is None else r["g"]) for r in rows]


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
    (``dataset=True``): reads go to a local copy, writes to the endpoint first (see the module docstring)."""

    def __init__(
        self, endpoint: Endpoint, graph: Any = None, *, dataset: bool = False, cache: str = "full", max_age: float | None = None
    ) -> None:
        if cache not in ("full", "temporary"):
            raise ValueError(f"cache must be 'full' or 'temporary', not {cache!r}")
        self.endpoint, self.dataset = endpoint, dataset
        self.graph = ox.DefaultGraph() if _is_default(graph) else graph
        self.cache, self.max_age = cache, max_age
        self._copy: ox.Store | None = None
        self._pulled_at = 0.0
        self._holds = 0  # open ``with graph.local()`` blocks
        self._skolem: dict[ox.BlankNode, ox.NamedNode] = {}
        if cache == "full":
            self.sync()

    # ---- the local copy ----------------------------------------------------------------------------------------------
    def sync(self) -> None:
        """Pull again and replace the local copy."""
        fresh = ox.Store()
        if self.dataset:
            fresh.extend(self.endpoint.pull_dataset())
        else:
            fresh.extend(ox.Quad(t.subject, t.predicate, t.object, self.graph) for t in self.endpoint.pull(self.graph))
        self._copy, self._pulled_at = fresh, time.monotonic()

    def release(self) -> None:
        """Drop a temporary copy, unless a ``local()`` block holds it (a full copy is the cache and stays)."""
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
        """A write reached the endpoint: bring a full copy along, drop a temporary one."""
        if self.cache == "full" and self._copy is not None:
            self._copy.extend(quads)
        elif self.cache == "temporary":
            self._copy = None

    # ---- blank nodes and scope of a write ---------------------------------------------------------------------------
    def _skolemize(self, term: Any) -> Any:
        from starlayer.graph.oxgraph.helpers.rewrite import skolem_iri

        if isinstance(term, ox.Triple):
            return ox.Triple(self._skolemize(term.subject), term.predicate, self._skolemize(term.object))
        if not isinstance(term, ox.BlankNode):
            return term
        if term not in self._skolem:
            if self._copy is not None and (
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

    # ---- reads -------------------------------------------------------------------------------------------------------
    def quads_for_pattern(self, subject: Any, predicate: Any, object: Any, graph_name: Any = None) -> Iterator[ox.Quad]:  # noqa: A002
        """With no copy, a pattern with a bound term is one query to the endpoint; otherwise the copy answers."""
        if self._copy is None and self.cache == "temporary" and not self._holds:
            remote = self._point_read(subject, predicate, object, graph_name)
            if remote is not None:
                return iter(remote)
        return self._local().quads_for_pattern(subject, predicate, object, graph_name)

    def _point_read(self, s: Any, p: Any, o: Any, g: Any) -> list[ox.Quad] | None:
        """The quads matching a pattern, asked of the endpoint; ``None`` when the pattern is not a point read (nothing bound, or a
        blank node, which the endpoint cannot match)."""
        terms = (s, p, o)
        if all(t is None for t in terms) or any(isinstance(t, ox.BlankNode) or _has_blank(t) for t in terms):
            return None
        if g is None and not self.dataset:
            g = self.graph
        names = ("?s", "?p", "?o")
        shown = [_term(t) if t is not None else n for t, n in zip(terms, names, strict=True)]
        pattern = " ".join(shown)
        wanted = [n for t, n in zip(terms, names, strict=True) if t is None]
        if not wanted and g is not None:  # every term bound: is the statement there?
            where = pattern if _is_default(g) else f"GRAPH {_term(g)} {{ {pattern} }}"
            return [ox.Quad(s, p, o, ox.DefaultGraph() if _is_default(g) else g)] if self.endpoint.ask(f"ASK {{ {where} }}") else []
        if not wanted:  # a dataset, every graph, all terms bound
            wanted = ["?s"]
        if g is None:  # a dataset, every graph
            where = f"{{ {pattern} }} UNION {{ GRAPH ?g {{ {pattern} }} }}"
            rows = self.endpoint.query(f"SELECT ?g {' '.join(wanted)} WHERE {{ {where} }}")
            graph_of = lambda row: ox.DefaultGraph() if row["g"] is None else row["g"]  # noqa: E731
        else:
            where = pattern if _is_default(g) else f"GRAPH {_term(g)} {{ {pattern} }}"
            rows = self.endpoint.query(f"SELECT {' '.join(wanted)} WHERE {{ {where} }}")
            graph_of = lambda row, g=g: ox.DefaultGraph() if _is_default(g) else g  # noqa: E731
        out = []
        for row in rows:
            got = [row[n[1:]] if t is None else t for t, n in zip(terms, names, strict=True)]
            out.append(ox.Quad(got[0], got[1], got[2], graph_of(row)))
        return out

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
            self.endpoint.update(f"INSERT DATA {{ {self._blocks(chunk)} }}")
            self._wrote(chunk)

    bulk_extend = extend

    def add(self, quad: Any) -> None:
        self.extend([quad])

    def remove(self, quad: Any) -> None:
        (q,) = self._mine([quad])
        self.endpoint.update(f"DELETE DATA {{ {self._blocks([q])} }}")
        if self.cache == "full" and self._copy is not None:
            self._copy.remove(q)
        elif self.cache == "temporary":
            self._copy = None

    def _forget(self, apply: Any) -> None:
        if self.cache == "full" and self._copy is not None:
            apply(self._copy)
        elif self.cache == "temporary":
            self._copy = None

    def clear_graph(self, graph: Any) -> None:
        if not self.dataset and graph != self.graph:
            raise ValueError(f"this store holds graph {self.graph}; it cannot clear graph {graph}")
        self.endpoint.update("CLEAR DEFAULT" if _is_default(graph) else f"CLEAR SILENT GRAPH {_term(graph)}")
        self._forget(lambda copy: copy.clear_graph(graph))

    def add_graph(self, graph: Any) -> None:
        if not self.dataset:
            if graph != self.graph:
                raise ValueError(f"this store holds graph {self.graph}; it cannot add graph {graph}")
            return
        if not _is_default(graph):
            self.endpoint.update(f"CREATE SILENT GRAPH {_term(graph)}")
            self._forget(lambda copy: copy.add_graph(graph))

    def remove_graph(self, graph: Any) -> None:
        if not self.dataset:
            raise NotImplementedError("a store backed by an endpoint holds one graph; drop it with an update on the endpoint")
        self.endpoint.update("CLEAR DEFAULT" if _is_default(graph) else f"DROP SILENT GRAPH {_term(graph)}")
        self._forget(lambda copy: copy.clear_graph(graph) if _is_default(graph) else copy.remove_graph(graph))

    def clear(self) -> None:
        if not self.dataset:
            raise NotImplementedError("clear() would empty the whole endpoint; clear this graph with graph.clear()")
        self.endpoint.update("CLEAR ALL")
        self._forget(lambda copy: copy.clear())

    def update(self, update: str, *args: Any, **kwargs: Any) -> None:
        """SPARQL Update runs on the endpoint only; a full copy is pulled again, a temporary one dropped."""
        self.endpoint.update(update)
        if self.cache == "full":
            self.sync()
        else:
            self._copy = None

    def load(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError("load into an endpoint-backed graph with graph.parse()")

    bulk_load = load


def _has_blank(term: Any) -> bool:
    return isinstance(term, ox.Triple) and (
        isinstance(term.subject, ox.BlankNode) or isinstance(term.object, ox.BlankNode) or _has_blank(term.subject) or _has_blank(term.object)
    )
