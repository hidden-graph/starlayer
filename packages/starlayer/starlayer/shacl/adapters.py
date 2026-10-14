from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF
from rdflib.util import from_n3

from starlayer.shacl.types import is_dirlangstring_like, is_triple_term_like

TT_NS = Namespace("urn:starlayer:tt:")


def _starlayer_graph_class() -> type | None:
    """The ``StarLayerGraph`` class if ``starlayer.graph`` is installed,
    else ``None`` - shared by every call site that needs to check "is
    starlayer.graph available" and/or "is this a StarLayerGraph" without a hard
    dependency on the optional package.
    """
    try:
        from starlayer.graph.graph.starlayer_graph import StarLayerGraph
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
        """Initialize like ``rdflib.Graph``, additionally binding the
        ``TripleTermAdapter`` that encoded this graph (used by ``query()``
        to decode/re-encode) and resetting the mutation-tracking state
        ``_decode_cached()`` uses to avoid redundant decodes.

        Args:
            adapter: The adapter that produced this graph via
                ``encode_graph()``, or ``None`` if this graph has no
                triple-term encoding to decode (``query()`` then behaves
                like a plain ``Graph``).
        """
        super().__init__(*args, **kwargs)
        self._tt_adapter = adapter
        self._mutation_version = 0
        self._decode_cache: tuple[int, Any] | None = None

    def add(self, triple: Any) -> Any:
        """Add ``triple`` like ``rdflib.Graph.add()``, bumping
        ``_mutation_version`` first so ``_decode_cached()`` knows any
        previously cached decode is now stale.
        """
        self._mutation_version += 1
        return super().add(triple)

    def remove(self, triple: Any) -> Any:
        """Remove ``triple`` like ``rdflib.Graph.remove()``, bumping
        ``_mutation_version`` first so ``_decode_cached()`` knows any
        previously cached decode is now stale.
        """
        self._mutation_version += 1
        return super().remove(triple)

    def addN(self, quads: Any) -> Any:
        """Add ``quads`` like ``rdflib.Graph.addN()``, bumping
        ``_mutation_version`` first so ``_decode_cached()`` knows any
        previously cached decode is now stale.
        """
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
        full graph fresh on every single one of those calls, rather than
        once per iteration, was profiled at over half of total validation
        time for a 40-node linearly-growing chain - a real bottleneck for
        rule-heavy workloads on larger graphs that this cache avoids.

        Args:
            adapter: The adapter to decode with on a cache miss.

        Returns:
            The decoded graph - either the cached one from the last call
            at the current ``_mutation_version``, or a freshly decoded
            one.
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
        """Run a SPARQL query, routing it through a decoded
        ``StarLayerGraph`` when triple-term-aware evaluation is available,
        then re-encoding the result back into this graph's own flat term
        space - see the class docstring for why this interception exists.

        Falls back to plain ``rdflib.Graph.query()`` unchanged whenever no
        adapter is bound, ``starlayer.graph`` isn't installed, or decoding
        doesn't actually produce a ``StarLayerGraph``. Otherwise: decodes
        self (reusing the cached decode when nothing has mutated since -
        see ``_decode_cached()``), normalizes any triple-term-valued
        ``initBindings`` to match the decoded graph's own term space, runs
        the query against it, then re-encodes the output - each SELECT
        row's triple-term-like bindings back into flat ``tt:HASH``
        URIRefs, or a CONSTRUCT result's whole output graph back into
        encoded form - so the rest of pySHACL, which only understands the
        flat encoding, sees consistent output either way.

        Args:
            query_object: The SPARQL query (string or pre-parsed algebra),
                as accepted by ``rdflib.Graph.query()``.
            initBindings: Pre-bound variable values; any triple-term-like
                value is normalized against the bound adapter before the
                query runs.

        Returns:
            The ``rdflib.query.Result``, with any triple-term values in a
            SELECT result's bindings or a CONSTRUCT result's graph
            re-encoded into this graph's own flat term space.
        """
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
    starlayer.graph's internal dirlang-encoded datatype URI, else ``None`` (also
    ``None`` when starlayer.graph isn't installed, since no such Literal could
    have been produced without it).
    """
    if getattr(value, "datatype", None) is None:
        return None

    try:
        from starlayer.graph.model.dirlangstring import decode_dirlangstring
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
        """Create an adapter with its own, independent encode/decode
        registry.

        Args:
            namespace: The namespace under which encoded triple-term
                URIRefs are minted (``<namespace><sha256 digest>``).
            term_factory: Builds a decoded triple-term value from its
                ``(subject, predicate, object)`` components - defaults to
                the plain ``TripleTermValue`` dataclass; ``for_starlayer_graph()``
                passes ``starlayer.graph.model.triple.TripleTerm`` instead.
        """
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
        """Reset the call/encode/decode counters returned by
        ``diagnostics_snapshot()`` back to zero, without touching the
        encode/decode registry itself.
        """
        self._diagnostics = {
            "encode_graph_calls": 0,
            "decode_graph_calls": 0,
            "encoded_triple_terms": 0,
            "decoded_triple_terms": 0,
        }

    def diagnostics_snapshot(self) -> dict[str, int]:
        """Return a copy of the current diagnostic counters
        (``encode_graph_calls``, ``decode_graph_calls``,
        ``encoded_triple_terms``, ``decoded_triple_terms``).
        """
        return dict(self._diagnostics)

    def support_triple_count(self) -> int:
        """Return the number of ``rdf:subject``/``rdf:predicate``/
        ``rdf:object`` encoding triples this adapter's registry would add
        to a graph - 3 per registered triple term.
        """
        return len(self._reverse) * 3

    def clear_registry(self) -> None:
        """Drop every registered triple-term mapping, forward and reverse."""
        self._forward.clear()
        self._reverse.clear()

    def export_registry(self) -> dict[str, Any]:
        """Serialize the current registry to a plain JSON-able dict, for
        persisting or transferring it (see ``import_registry()``).

        Returns:
            A dict with ``"namespace"`` (this adapter's namespace, as a
            string) and ``"entries"`` (one dict per registered triple
            term, its encoded URI and its subject/predicate/object each
            in N3 form).
        """
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
        """Load a registry previously produced by ``export_registry()``.

        Args:
            payload: A dict in ``export_registry()``'s own format.
            merge: If ``False`` (default), clears the existing registry
                first; if ``True``, adds to it, checking each incoming
                entry against the current entries for conflicts.
            strict_namespace: If ``True`` (default), raises
                ``ValueError`` when ``payload``'s own namespace doesn't
                match this adapter's.

        Raises:
            ValueError: ``payload``'s namespace doesn't match (when
                ``strict_namespace``), or an incoming entry's URI/key
                conflicts with one already in the registry (same URI
                mapped to a different key, or vice versa).
        """
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
    def for_starlayer_graph(cls) -> TripleTermAdapter:
        """Create an adapter whose decoded triple terms are real
        ``starlayer.graph.model.triple.TripleTerm`` instances (instead of
        the default, dependency-free ``TripleTermValue``) - for use
        wherever the decoded graph needs to interoperate with
        ``StarLayerGraph``.

        Raises:
            RuntimeError: ``starlayer.graph`` is not installed.
        """
        try:
            from starlayer.graph.model.triple import TripleTerm
        except ImportError as exc:
            raise RuntimeError(
                "starlayer.graph is not installed. Install starlayer.graph or use the default adapter."
            ) from exc
        return cls(term_factory=TripleTerm)

    def encode_graph(self, graph: Iterable[tuple[Any, Any, Any]]) -> Graph:
        """Return a flat, RDF-1.1-compatible ``_SparqlAwareEncodedGraph``
        copy of ``graph``, with every triple-term node (in any position)
        replaced by its content-addressed ``tt:HASH`` URIRef and a
        DirLangString literal replaced by its internal encoded datatype
        form.

        Every triple term encountered anywhere in ``graph`` is registered
        in this adapter's registry (see ``_encode_node()``), and the
        resulting graph also carries that registry's own
        ``rdf:subject``/``rdf:predicate``/``rdf:object`` triples for every
        term registered so far (not just the ones from this one call), so
        a consumer with no access to the adapter itself (e.g. plain
        pySHACL machinery) can still see each encoded term's components
        as ordinary triples.

        Args:
            graph: The triples to encode - any iterable of ``(s, p, o)``.

        Returns:
            A new ``_SparqlAwareEncodedGraph`` bound to this adapter.
        """
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
        """Return the inverse of ``encode_graph()``: a copy of ``graph``
        with every registered ``tt:HASH`` URIRef resolved back to a real
        triple term (and a dirlang-encoded Literal back to a
        ``DirLangString``), dropping the
        ``rdf:subject``/``rdf:predicate``/``rdf:object`` encoding triples
        ``encode_graph()`` added for each registered term - those are
        internal bookkeeping, not part of the decoded graph's own
        content.

        Args:
            graph: The triples to decode.

        Returns:
            A ``StarLayerGraph`` if ``starlayer.graph`` is installed, else
            a plain ``TripleTermGraph`` (see ``_new_output_graph()``).
        """
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
        """Replace every triple in ``target`` with the triples from
        ``source``, in place, via ``target``'s own ``remove()``/``add()``
        (not a reassignment) - so any identity a caller holds to
        ``target`` itself stays valid.

        Args:
            target: The graph to empty and refill, mutated in place.
            source: The triples to add after ``target`` is cleared.

        Returns:
            ``target``, for convenience chaining.
        """
        target.remove((None, None, None))
        for triple in source:
            target.add(triple)
        return target

    def encode_term(self, value: Any) -> Any:
        """Encode a single term the way ``encode_graph()`` encodes one
        node - see ``_encode_node()``.
        """
        return self._encode_node(value)

    def decode_term(self, value: Any) -> Any:
        """Decode a single term the way ``decode_graph()`` decodes one
        node (but without a target graph, so a decoded triple term always
        comes back as a ``term_factory`` instance, never a plain tuple) -
        see ``_decode_node()``.
        """
        return self._decode_node(value)

    def _new_output_graph(self):
        """Return a fresh, empty graph to decode into: a
        ``StarLayerGraph`` if ``starlayer.graph`` is installed (so a
        decoded triple term round-trips through its native triple-term
        support), else a plain ``TripleTermGraph`` fallback that can
        still hold one directly.
        """
        StarLayerGraph = _starlayer_graph_class()
        if StarLayerGraph is None:
            return TripleTermGraph()
        return StarLayerGraph()

    def _encode_node(self, value: Any) -> Any:
        """Encode one node value for use in a flat, RDF-1.1-compatible
        graph.

        A plain 3-tuple is first treated as inline triple-term shorthand
        (via ``term_factory``); a DirLangString-like value is encoded via
        ``starlayer.graph``'s own dirlang datatype encoding; anything else
        that isn't triple-term-like is returned unchanged. A
        triple-term-like value has its own subject/predicate/object
        encoded recursively first (so a nested triple term is fully
        flattened), then is registered under a content-addressed URIRef
        (``<namespace><sha256 of the encoded (s, p, o) key>``) - returning
        the existing URIRef if this exact (s, p, o) triple was already
        registered, so the same triple term always encodes to the same
        URI within this adapter's lifetime.

        Args:
            value: The node to encode.

        Returns:
            ``value`` unchanged if it's not triple-term-like or
            dirlang-like, the dirlang-encoded ``Literal``, or the
            content-addressed ``tt:HASH`` ``URIRef`` for a triple term.
        """
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
            # needed here - just delegate to starlayer.graph's own encoder.
            from starlayer.graph.model.dirlangstring import encode_dirlangstring

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
        """Decode one node value with no target graph in mind.

        A registered ``tt:HASH`` URIRef is resolved back to its
        ``(subject, predicate, object)`` - each component decoded
        recursively - and rebuilt via ``term_factory``. A dirlang-encoded
        ``Literal`` is decoded back to a ``DirLangString``. Anything else
        is returned unchanged.

        Args:
            value: The node to decode.

        Returns:
            The decoded value, always a ``term_factory`` instance for a
            decoded triple term (never a plain tuple) - see
            ``_decode_node_for_graph()`` for the target-graph-aware
            variant that can return a tuple instead.
        """
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
        """Decode one node value for insertion into ``graph``
        specifically - the variant ``decode_graph()`` uses, which can
        shape its output differently depending on what kind of graph it's
        decoding into.

        A registered ``tt:HASH`` URIRef is resolved back to its
        ``(subject, predicate, object)`` (each component decoded
        recursively via this same method). When ``graph`` is a
        ``StarLayerGraph``, the plain ``(ds, dp, do)`` tuple is returned
        as-is - ``StarLayerGraph.add()`` recognizes a bare 3-tuple as
        inline triple-term shorthand and knows how to store it directly -
        otherwise it's wrapped via ``term_factory``, matching
        ``_decode_node()``'s own unconditional behavior. A
        dirlang-encoded ``Literal`` is decoded to a real ``DirLangString``
        only when ``graph`` is a ``StarLayerGraph`` (the only kind of
        graph that can actually hold one - a plain ``rdflib.Graph`` would
        crash on ``.add()``); otherwise the original encoded ``Literal``
        is left as-is. Anything else is returned unchanged.

        Args:
            value: The node to decode.
            graph: The graph this decoded value is being added to - only
                its type (``StarLayerGraph`` or not) affects the result.

        Returns:
            The decoded value, shaped for ``graph``.
        """
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
