from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF
from rdflib.util import from_n3

from starshacl.types import is_dirlangstring_like, is_triple_term_like

TT_NS = Namespace("urn:starshacl:tt:")


def _starlayer_graph_class() -> type | None:
    """The ``StarLayerGraph`` class if ``starlayergraph`` is installed,
    else ``None`` - shared by every call site that needs to check "is
    starlayergraph available" and/or "is this a StarLayerGraph" without a hard
    dependency on the optional package.
    """
    try:
        from starlayergraph.graph.starlayer_graph import StarLayerGraph
    except ImportError:
        return None
    return StarLayerGraph


class _SparqlAwareEncodedGraph(Graph):
    """Graph returned by ``TripleTermAdapter.encode_graph``.

    pySHACL preserves whatever object it's handed as ``data_graph`` and calls
    ``.query()`` on it directly for both ``sh:sparql`` constraints and
    ``sh:construct`` SHACL-AF rules (no rewrite/adaptation hook of its own).
    This subclass intercepts those calls: it decodes itself back into a real
    ``StarLayerGraph`` (via the adapter's existing ``decode_graph``) so SPARQL
    1.2 triple-term syntax and triple-term-valued bindings are handled by
    StarLayerGraph's own query engine, then re-encodes the result so the rest
    of pySHACL — which only understands the flat encoded term space — sees
    consistent output. All other Graph behavior (triples/objects/etc.) is
    untouched; only ``.query()`` is affected.
    """

    def __init__(self, *args: Any, adapter: TripleTermAdapter | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._tt_adapter = adapter
        self._mutation_version = 0
        self._decode_cache: tuple[int, Any] | None = None

    def add(self, triple: Any) -> Any:
        self._mutation_version += 1
        return super().add(triple)

    def remove(self, triple: Any) -> Any:
        self._mutation_version += 1
        return super().remove(triple)

    def addN(self, quads: Any) -> Any:
        self._mutation_version += 1
        return super().addN(quads)

    def _decode_cached(self, adapter: TripleTermAdapter) -> Any:
        """Decode self back to a StarLayerGraph, reusing the previous
        decode if nothing has been added/removed since (tracked via
        ``_mutation_version``, bumped by ``add``/``remove``/``addN``).

        A SHACL-AF ``sh:construct`` rule under ``iterate_rules=True`` calls
        ``.query()`` once per (focus node, construct) pair *per iteration*,
        against the same unmutated graph snapshot for the whole iteration -
        pySHACL only merges newly-constructed triples in (via ``add()``)
        after every focus node has been queried for that pass. Decoding the
        full graph fresh on every single one of those calls (rather than
        once per iteration) was a real, measured performance bottleneck for
        rule-heavy workloads on larger graphs (profiled: over half of total
        validation time for a 40-node linearly-growing chain).
        """
        if self._decode_cache is not None and self._decode_cache[0] == self._mutation_version:
            return self._decode_cache[1]

        decoded = adapter.decode_graph(self)
        self._decode_cache = (self._mutation_version, decoded)
        return decoded

    def query(
        self,
        query_object: Any,
        processor: str = "sparql",
        result: str = "sparql",
        initNs: Any = None,
        initBindings: Any = None,
        use_store_provided: bool = True,
        **kwargs: Any,
    ) -> Any:
        adapter = self._tt_adapter
        if adapter is None:
            return super().query(
                query_object,
                processor=processor,
                result=result,
                initNs=initNs,
                initBindings=initBindings,
                use_store_provided=use_store_provided,
                **kwargs,
            )

        StarLayerGraph = _starlayer_graph_class()

        decoded = self._decode_cached(adapter) if StarLayerGraph is not None else None
        if StarLayerGraph is None or not isinstance(decoded, StarLayerGraph):
            return super().query(
                query_object,
                processor=processor,
                result=result,
                initNs=initNs,
                initBindings=initBindings,
                use_store_provided=use_store_provided,
                **kwargs,
            )

        normalized_bindings = _normalize_init_bindings(initBindings, adapter)
        query_result = decoded.query(
            query_object,
            processor=processor,
            result=result,
            initNs=initNs,
            initBindings=normalized_bindings,
            use_store_provided=use_store_provided,
            **kwargs,
        )

        if query_result.type == "SELECT":
            query_result.bindings = [
                {
                    var: (adapter.encode_term(value) if is_triple_term_like(value) else value)
                    for var, value in row.items()
                }
                for row in query_result.bindings
            ]
        elif query_result.type == "CONSTRUCT":
            query_result.graph = adapter.encode_graph(query_result.graph)

        return query_result


def _try_decode_dirlangstring(value: Any) -> Any | None:
    """Return a ``DirLangString`` if ``value`` is a ``Literal`` using
    starlayergraph's internal dirlang-encoded datatype URI, else ``None`` (also
    ``None`` when starlayergraph isn't installed, since no such Literal could
    have been produced without it).
    """
    if getattr(value, "datatype", None) is None:
        return None

    try:
        from starlayergraph.model.dirlangstring import decode_dirlangstring
    except ImportError:
        return None

    return decode_dirlangstring(value)


def _normalize_init_bindings(init_bindings: Any, adapter: TripleTermAdapter) -> Any:
    if not init_bindings:
        return init_bindings

    normalized: dict[str, Any] = {}
    for var, value in init_bindings.items():
        decoded_value = adapter.decode_term(value)
        if is_triple_term_like(decoded_value):
            normalized[var] = (decoded_value.subject, decoded_value.predicate, decoded_value.object)
        else:
            normalized[var] = decoded_value
    return normalized


@dataclass(frozen=True)
class TripleTermValue:
    subject: Any
    predicate: Any
    object: Any


class TripleTermGraph:
    """Simple graph-like container that can hold triple-term objects directly."""

    def __init__(self, triples: Iterable[tuple[Any, Any, Any]] | None = None) -> None:
        self._triples: list[tuple[Any, Any, Any]] = []
        self.namespace_manager = None
        if triples is not None:
            for triple in triples:
                self.add(triple)

    def __iter__(self):
        return iter(self._triples)

    def __contains__(self, value: tuple[Any, Any, Any]) -> bool:
        return value in self._triples

    def add(self, triple: tuple[Any, Any, Any]) -> TripleTermGraph:
        if triple not in self._triples:
            self._triples.append(triple)
        return self

    def remove(self, pattern: tuple[Any, Any, Any]) -> TripleTermGraph:
        s, p, o = pattern
        if s is None and p is None and o is None:
            self._triples.clear()
            return self

        self._triples = [
            t for t in self._triples
            if not (
                (s is None or t[0] == s)
                and (p is None or t[1] == p)
                and (o is None or t[2] == o)
            )
        ]
        return self


class TripleTermAdapter:
    """Encode/decode triple terms so pySHACL can process RDF 1.1-compatible graphs."""

    def __init__(
        self,
        namespace: Namespace = TT_NS,
        term_factory: Callable[[Any, Any, Any], Any] | None = None,
    ) -> None:
        self.namespace = namespace
        self.term_factory = term_factory or TripleTermValue
        self._forward: dict[tuple[Any, Any, Any], URIRef] = {}
        self._reverse: dict[URIRef, tuple[Any, Any, Any]] = {}
        self._diagnostics = {
            "encode_graph_calls": 0,
            "decode_graph_calls": 0,
            "encoded_triple_terms": 0,
            "decoded_triple_terms": 0,
        }

    def reset_diagnostics(self) -> None:
        self._diagnostics = {
            "encode_graph_calls": 0,
            "decode_graph_calls": 0,
            "encoded_triple_terms": 0,
            "decoded_triple_terms": 0,
        }

    def diagnostics_snapshot(self) -> dict[str, int]:
        return dict(self._diagnostics)

    def support_triple_count(self) -> int:
        return len(self._reverse) * 3

    def clear_registry(self) -> None:
        self._forward.clear()
        self._reverse.clear()

    def export_registry(self) -> dict[str, Any]:
        entries: list[dict[str, str]] = []
        for uri, (s, p, o) in self._reverse.items():
            entries.append(
                {
                    "uri": str(uri),
                    "s": s.n3(),
                    "p": p.n3(),
                    "o": o.n3(),
                }
            )
        return {
            "namespace": str(self.namespace),
            "entries": entries,
        }

    def import_registry(
        self,
        payload: dict[str, Any],
        *,
        merge: bool = False,
        strict_namespace: bool = True,
    ) -> None:
        namespace = payload.get("namespace")
        if strict_namespace and namespace is not None and str(namespace) != str(self.namespace):
            raise ValueError(
                f"Registry namespace mismatch: expected {self.namespace}, got {namespace}."
            )

        if not merge:
            self.clear_registry()

        entries = payload.get("entries", [])
        for entry in entries:
            uri = URIRef(entry["uri"])
            key = (
                from_n3(entry["s"]),
                from_n3(entry["p"]),
                from_n3(entry["o"]),
            )

            existing_key = self._reverse.get(uri)
            if existing_key is not None and existing_key != key:
                raise ValueError(f"Registry conflict for URI {uri}: incompatible key mapping.")

            existing_uri = self._forward.get(key)
            if existing_uri is not None and existing_uri != uri:
                raise ValueError(f"Registry conflict for key {key!r}: already mapped to {existing_uri}.")

            self._reverse[uri] = key
            self._forward[key] = uri

    @classmethod
    def for_starlayergraph(cls) -> TripleTermAdapter:
        try:
            from starlayergraph.model.triple import TripleTerm
        except ImportError as exc:
            raise RuntimeError(
                "starlayergraph is not installed. Install starlayergraph or use the default adapter."
            ) from exc
        return cls(term_factory=TripleTerm)

    def encode_graph(self, graph: Iterable[tuple[Any, Any, Any]]) -> Graph:
        self._diagnostics["encode_graph_calls"] += 1
        encoded = _SparqlAwareEncodedGraph(adapter=self)
        encoded.namespace_manager = getattr(graph, "namespace_manager", None)

        for s, p, o in graph:
            es = self._encode_node(s)
            eo = self._encode_node(o)
            encoded.add((es, p, eo))

        for uri, (s, p, o) in self._reverse.items():
            encoded.add((uri, RDF.subject, s))
            encoded.add((uri, RDF.predicate, p))
            encoded.add((uri, RDF.object, o))

        return encoded

    def decode_graph(self, graph: Iterable[tuple[Any, Any, Any]]):
        self._diagnostics["decode_graph_calls"] += 1
        decoded = self._new_output_graph()
        decoded.namespace_manager = getattr(graph, "namespace_manager", None)

        for s, p, o in graph:
            if p in (RDF.subject, RDF.predicate, RDF.object) and isinstance(s, URIRef) and s in self._reverse:
                continue
            ds = self._decode_node_for_graph(s, decoded)
            do = self._decode_node_for_graph(o, decoded)
            decoded.add((ds, p, do))

        return decoded

    def replace_graph(self, target: Any, source: Iterable[tuple[Any, Any, Any]]) -> Any:
        target.remove((None, None, None))
        for triple in source:
            target.add(triple)
        return target

    def encode_term(self, value: Any) -> Any:
        return self._encode_node(value)

    def decode_term(self, value: Any) -> Any:
        return self._decode_node(value)

    def _new_output_graph(self):
        StarLayerGraph = _starlayer_graph_class()
        if StarLayerGraph is None:
            return TripleTermGraph()
        return StarLayerGraph()

    def _encode_node(self, value: Any) -> Any:
        if isinstance(value, tuple) and len(value) == 3:
            # StarLayerGraph treats a plain 3-tuple as inline triple-term shorthand
            # in any node position; a nested triple term's subject/predicate/object
            # can surface as a raw tuple rather than a term_factory instance.
            value = self.term_factory(*value)

        if is_dirlangstring_like(value):
            # StarLayerGraph yields a real DirLangString object (not an
            # rdflib term) for RDF 1.2 direction-tagged literals - pySHACL/
            # rdflib.Graph.add() would crash on it outright (AssertionError:
            # "Object ... must be an rdflib term"). Its own internal
            # encoding (a Literal with a datatype URI packing language+
            # direction) is already flat/RDF-1.1-safe, so no registry is
            # needed here - just delegate to starlayergraph's own encoder.
            from starlayergraph.model.dirlangstring import encode_dirlangstring

            return encode_dirlangstring(value)

        if not is_triple_term_like(value):
            return value

        self._diagnostics["encoded_triple_terms"] += 1

        s = self._encode_node(value.subject)
        p = self._encode_node(value.predicate)
        o = self._encode_node(value.object)

        key = (s, p, o)
        found = self._forward.get(key)
        if found is not None:
            return found

        digest = hashlib.sha256(repr(key).encode("utf-8")).hexdigest()
        uri = URIRef(f"{self.namespace}{digest}")
        self._forward[key] = uri
        self._reverse[uri] = key
        return uri

    def _decode_node(self, value: Any) -> Any:
        if isinstance(value, URIRef) and value in self._reverse:
            self._diagnostics["decoded_triple_terms"] += 1
            s, p, o = self._reverse[value]
            ds = self._decode_node(s)
            dp = self._decode_node(p)
            do = self._decode_node(o)
            return self.term_factory(ds, dp, do)

        dirlangstring = _try_decode_dirlangstring(value)
        if dirlangstring is not None:
            return dirlangstring

        return value

    def _decode_node_for_graph(self, value: Any, graph: Any) -> Any:
        if isinstance(value, URIRef) and value in self._reverse:
            self._diagnostics["decoded_triple_terms"] += 1
            s, p, o = self._reverse[value]
            ds = self._decode_node_for_graph(s, graph)
            dp = self._decode_node_for_graph(p, graph)
            do = self._decode_node_for_graph(o, graph)

            StarLayerGraph = _starlayer_graph_class()
            if StarLayerGraph is not None and isinstance(graph, StarLayerGraph):
                return (ds, dp, do)
            return self.term_factory(ds, dp, do)

        dirlangstring = _try_decode_dirlangstring(value)
        if dirlangstring is not None:
            # A plain rdflib Graph can't hold a DirLangString (not an rdflib
            # term); only StarLayerGraph.add() knows how to re-encode one.
            # Otherwise leave the internal dirlang-encoded Literal as-is,
            # same fallback shape as the TripleTerm branch above.
            StarLayerGraph = _starlayer_graph_class()
            if StarLayerGraph is not None and isinstance(graph, StarLayerGraph):
                return dirlangstring
            return value

        return value
