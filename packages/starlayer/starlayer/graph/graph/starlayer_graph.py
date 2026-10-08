"""
starlayer.graph.graph.starlayer_graph

StarLayerGraph — rdflib.Graph subclass with RDF 1.2 triple-term support.

A plain Python 3-tuple in any node position is treated as an inline TripleTerm.
All rdflib.Graph methods work identically; core traversal methods are extended
to accept and return TripleTerm objects while hiding the internal encoding.

Encoding: triple terms are stored as content-addressed URIRefs under TT_NS
(same triple content always maps to the same URI). The rdf:subject/predicate/object
triples that define the encoding are hidden from callers.
"""

from __future__ import annotations

from typing import Generator

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.graph import DATASET_DEFAULT_GRAPH_ID, ReadOnlyGraphAggregate
from rdflib.namespace import RDF
from rdflib.paths import Path
from rdflib.query import Result
from rdflib.term import IdentifiedNode, Node

from starlayer.graph.model.dirlangstring import (
    DirLangString,
    decode_dirlangstring,
    encode_dirlangstring,
)
from starlayer.graph.model.encoding import ENCODING_PREDS as _ENCODING_PREDS
from starlayer.graph.model.encoding import (
    TT_NS,
    lookup_tt_hash,
    restore_select_bindings,
    term_key,
    tt_hash,
)
from starlayer.graph.model.triple import TripleTerm

from starlayer.graph.graph.entailment_regimes import ENTAILMENT, SUPPORTED_REGIMES

# Pure-stdlib (multiprocessing/os/signal/time only) - safe to import
# unconditionally, unlike owl_dl.py/owl_dl_rustdl.py themselves, which stay
# lazily imported so owlready2/rustdl remain genuinely optional.
from starlayer.graph.graph import _timeout as _owl_dl_timeout

_OWL_DL_TIMEOUT_DEFAULT = _owl_dl_timeout.DEFAULT_TIMEOUT_SECONDS

SL_NS           = 'https://github.com/hidden-graph/starlayergraph/ns#'
SL_TRIPLE_TERM  = URIRef(SL_NS + 'TripleTerm')   # kept for export / backward compat
SL_REIFICATION  = URIRef(SL_NS + 'Reification')  # kept for export / backward compat
RDF_REIFIES     = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')

# Valid backend mode identifiers
VALID_BACKENDS = frozenset({'rdf-1.1', 'rdf-1.2'})
# A per-query choice (query()'s own entailment= kwarg, not a graph-level
# setting - see that method's docstring). None = today's plain
# simple-entailment behavior. ENTAILMENT.RDF rewrites the query at query
# time for RDF entailment (starlayer.sparql.entailment_rdf - the SPARQL
# Entailment Regimes spec's regime one step weaker than RDFS: only rdfD2,
# "every term used as a predicate is entailed rdf:type rdf:Property") - no
# data is copied. ENTAILMENT.RDFS rewrites the query at query time for
# RDFS entailment (starlayer.sparql.entailment_rdfs - the full ruleset's
# "data" rules: subClassOf/subPropertyOf transitivity, subclass/domain/
# range-driven type entailment, subproperty entailment) - no data is
# copied. ENTAILMENT["OWL-RDF-Based"] materializes a full RDFS/OWL-RL
# closure via infer() - see query()'s own docstring and VALID_INFER_MODES
# for how much of that work gets reused across calls (controlled by the
# separate infer= kwarg). ENTAILMENT["OWL-Direct"] is the OWL 2 DL
# counterpart - the SPARQL Entailment Regimes spec's own name for
# OWL-Direct-Semantics-backed querying: a live union of self and a small
# cached delta from infer(profile=ENTAILMENT["OWL-Direct"], engine=...)
# (mode="delta"), refreshed on the same infer=-governed cadence, but via
# genuine tableau DL reasoning (see query()'s own docstring for the real
# cost difference this implies, and the separate engine= kwarg it also
# reads). "native" delegates entailment to the endpoint itself - only
# legal with backend='rdf-1.2', where native_query() already sends text
# straight through with zero rewriting (see backends/native.py's own
# module docstring); this value adds no new behavior on that path, it's a
# self-documenting label plus the guard that using it against the default
# backend (nothing to delegate to) is a mistake, not a silent no-op. See
# packages/graph/docs/fuseki-reasoning-setup.md for how to actually
# configure an endpoint that makes this meaningful. See
# entailment_regimes.py's own module docstring for why these are real
# IRIs (ENTAILMENT = Namespace(...)), not starlayer-invented strings, and
# why "native"/None stay as-is (not regimes at all).
VALID_ENTAILMENTS = frozenset({None, 'native'} | SUPPORTED_REGIMES)
# query()'s infer= kwarg - only consulted when entailment=ENTAILMENT["OWL-RDF-Based"]; ignored
# otherwise. Controls reuse of the one materialized-closure cache this
# graph keeps (self._owl_rl_cache), stamped with the mutation generation
# (self._mutation_generation, bumped by _on_mutated()) it was computed at:
#   "changed" (default) - reuse the cache iff no mutation happened since it
#       was computed; recompute otherwise. Cheap (an int compare), and
#       always correct as long as every real mutation goes through
#       _on_mutated() (see that method's own docstring for the mutation
#       surface it covers).
#   "always"  - ignore the cache entirely, always recompute and refresh it.
#   "cached"  - reuse the cache if one exists at all, even if stale;
#       compute only when there is no cache yet. For a caller who wants to
#       pin one materialization and keep querying it explicitly, without
#       StarLayerGraph deciding when to refresh it.
VALID_INFER_MODES = frozenset({'always', 'cached', 'changed'})
# infer()'s own mode= kwarg (distinct from VALID_INFER_MODES above, which is
# query()'s infer= reuse-cadence kwarg for entailment=ENTAILMENT["OWL-RDF-Based"]) - selects
# what infer() actually returns. All three ultimately reach the same
# closure (the deductive-closure concept - self's own data plus everything
# entailed from it); what differs is where that ends up and how much of it
# comes back as a distinct value:
#   "full"    (default) - a NEW graph with original triples plus everything
#       newly entailed, today's original/only behavior, unchanged.
#   "delta"   - a NEW graph with only the newly-entailed triples, none of
#       the originals. The foundation query()'s entailment=ENTAILMENT["OWL-RDF-Based"] path is
#       built on (see that branch's own comment) - querying self live,
#       unioned with a small cached delta, rather than caching a full
#       closure copy of self.
#   "in-place" - adds just the newly-entailed triples into self directly
#       (self already has the originals) and returns self - works for any
#       self, including native and triple-term-bearing ones, since only the
#       delta is ever added, never a re-decomposed copy of self's own data -
#       see infer()'s own docstring for the one narrow leftover caveat this
#       still doesn't avoid.
VALID_INFER_RETURN_MODES = frozenset({'full', 'delta', 'in-place'})

# rdf:TripleTerm type URI — emitted by the JSON-LD 1.2 serializer; treated as
# internal encoding so it is never surfaced through triples() / __len__ etc.
_RDF_TRIPLE_TERM = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#TripleTerm'

# Unbound reference to Graph.triples — used to bypass our override safely
_raw_triples = Graph.triples


class _UnionForQuery(ReadOnlyGraphAggregate):
    """A 2-member ReadOnlyGraphAggregate, fixed to evaluate a property-path
    predicate exactly once against the union as a whole, instead of once per
    member graph.

    Confirmed live: plain rdflib's ReadOnlyGraphAggregate.triples() evaluates
    a Path-typed predicate by calling p.eval(self, s, o) *inside* its own
    per-member loop (rdflib/graph.py's own triples() implementation) - for a
    fixed 2-member aggregate this means the whole path is evaluated against
    the entire aggregate twice, a deterministic doubling of every
    path-matched solution row. Ordinary (non-Path) triple patterns are
    unaffected by this bug and don't need the override - used here to union
    a graph with its own owl-rl entailment delta (query()'s
    entailment=ENTAILMENT["OWL-RDF-Based"] - see that branch), which are provably disjoint by
    construction (a delta triple is defined as "not already present"), so a
    plain triple can never double-yield either way.
    """
    def triples(self, triple):
        s, p, o = triple
        if isinstance(p, Path):
            for _s, _o in p.eval(self, s, o):
                yield _s, p, _o
            return
        yield from super().triples(triple)


def _unfold_tt_encoding(g) -> Graph:
    """Return a plain rdflib.Graph with every triple term replaced by a
    freshly minted BNode (with rdf:subject/predicate/object triples
    describing it), recursively for nested triple terms.

    Used only by StarLayerGraph.isomorphic() so rdflib's BNode-aware
    comparison can see a BNode embedded in a triple term as relabelable, the
    same as any other BNode, instead of it being baked into a fixed ground
    term the algorithm can't relabel. Repeated references to "the same"
    triple term within one graph map to the same fresh BNode, preserving
    shared-identity shape.

    Dispatches on getattr(g, '_is_native', False) rather than
    isinstance(g, StarLayerGraph) (this function is defined before that
    class exists, and per this method's own docstring "other need not be a
    StarLayerGraph" - a plain rdflib.Graph correctly falls to the rdf-1.1
    path below, a no-op since it has no tt: content at all):
    - rdf-1.1 (or non-StarLayerGraph): works on the *raw* store directly -
      every tt:HASH URIRef (StarLayerGraph's own on-disk encoding) and its
      encoding triples become one fresh BNode each. Needs no
      StarLayerGraph-specific registry state.
    - native (backend='rdf-1.2'): there is no tt:HASH encoding to unfold -
      the store already holds real TripleTerm values. Walks g.triples()
      (the *decoded* public view, which for a native backend already
      returns real TripleTerm objects) and unfolds those instead.
    """
    if getattr(g, '_is_native', False):
        return _unfold_native_triple_terms(g)

    fresh = {}

    def unfold_node(n):
        if isinstance(n, URIRef) and str(n).startswith(TT_NS):
            if n not in fresh:
                fresh[n] = BNode()
            return fresh[n]
        return n

    out = Graph()
    for s, p, o in _raw_triples(g, (None, None, None)):
        out.add((unfold_node(s), p, unfold_node(o)))
    return out


def _unfold_native_triple_terms(g) -> Graph:
    """_unfold_tt_encoding()'s native-backend counterpart: g.triples()
    already returns real TripleTerm objects (no tt:HASH encoding involved
    at all for a native backend), so this unfolds *those* directly into a
    fresh-BNode-based reification shape instead of decoding store-level
    encoding triples.
    """
    fresh: dict = {}

    def unfold(node):
        if isinstance(node, TripleTerm):
            if node not in fresh:
                bn = BNode()
                fresh[node] = bn
                out.add((bn, RDF.subject,   unfold(node.subject)))
                out.add((bn, RDF.predicate, node.predicate))
                out.add((bn, RDF.object,    unfold(node.object)))
            return fresh[node]
        return node

    out = Graph()
    for s, p, o in g.triples((None, None, None)):
        out.add((unfold(s), p, unfold(o)))
    return out


# Sentinel returned by _coerce_tt_read when a TripleTerm is not in the registry.
# Distinct from None (which means wildcard) so callers can detect "no match".
_TT_NOT_FOUND = object()


def _is_tt_like(node):
    return isinstance(node, (TripleTerm, tuple)) and (
        isinstance(node, TripleTerm) or len(node) == 3
    )


def _needs_encoding(node):
    """True if node is a Python value type that _coerce_tt/_coerce_tt_read
    must translate to its internal store representation before it can be
    written or matched: a TripleTerm/tuple (→ tt:HASH URIRef) or a
    DirLangString (→ Literal with the internal dirlang: datatype)."""
    return _is_tt_like(node) or isinstance(node, DirLangString)


def _read_source_text(source=None, file=None, location=None, data=None) -> str:
    """Resolve rdflib's four parse() source arguments to a single text string.

    Precedence matches rdflib's own parse() convention: data, then file,
    then location, then source. Shared by StarLayerGraph.parse() and
    StarLayerDataset._read_source() (which previously each implemented this
    exact resolution independently).
    """
    from pathlib import Path
    if data is not None:
        return data
    if file is not None:
        return file.read() if hasattr(file, 'read') else Path(file).read_text()
    if location is not None:
        return Path(location).read_text()
    if source is not None:
        p = Path(source) if isinstance(source, (str, Path)) else None
        if p and p.exists():
            return p.read_text()
        if isinstance(source, str):
            return source
        raise ValueError(f'Cannot read source: {source!r}')
    raise ValueError('No source data to parse')


def _check_single_graph(graph_ids, *, format: str) -> None:
    """Raise MultipleGraphsError if graph_ids - the distinct graph
    identifiers found while parsing a quad-shaped (nquads/trig/trix,
    bare or 12-variant) document - names more than one graph.

    Shared by every quad-format branch of StarLayerGraph.parse() (nq12,
    trig12, trix12, and the bare nquads/trig/trix fallback below) so all
    six formats enforce the identical rule: at most one distinct graph
    (including the trivial all-default-graph case, graph_ids == {None})
    parses normally into this graph; two or more raises, since flattening
    them together would silently mix unrelated graphs with no way for the
    caller to know.
    """
    if len(graph_ids) > 1:
        from starlayer.graph.parsers.errors import MultipleGraphsError
        raise MultipleGraphsError(format, sorted(str(g) for g in graph_ids))


class StarLayerGraph(Graph):
    """rdflib.Graph extended with RDF 1.2 triple-term support.

    Triple terms are represented as Python 3-tuples or TripleTerm objects.
    Internally they are encoded as content-addressed URIRefs under TT_NS in
    the rdflib store; that encoding is completely hidden from callers.

    All unoverridden rdflib.Graph methods (namespace management, SPARQL,
    serialization, etc.) are inherited and work without modification.
    """

    def __init__(self, *args, backend: str = 'rdf-1.1', **kwargs):
        if backend not in VALID_BACKENDS:
            raise ValueError(f"backend must be one of {sorted(VALID_BACKENDS)}, got {backend!r}")
        if backend == 'rdf-1.2' and len(args) < 2 and kwargs.get('identifier') is None:
            # Without this, a native graph constructed with no explicit
            # identifier=  gets rdflib's own default (a fresh random BNode) -
            # but query()/update() send SPARQL text straight through
            # unscoped (the endpoint's own default graph), while
            # infer()/triples()/plain iteration wrap every pattern in
            # GRAPH <self.identifier> { ... } via _native_scoped() unless
            # self.identifier is exactly DATASET_DEFAULT_GRAPH_ID. A random
            # BNode identifier satisfies neither exemption, so those two
            # halves of the API would silently disagree about which graph
            # is "self's data" - query()/update() see the endpoint's real
            # default graph, infer()/triples() see an empty, unreachable
            # GRAPH <random-bnode-iri> instead. Confirmed live. Defaulting
            # here - only when the caller supplied no identifier of their
            # own (len(args) < 2 leaves a *positional* identifier alone;
            # kwargs.get('identifier') is None covers both "omitted" and
            # explicit identifier=None, which rdflib's own Graph.__init__
            # already treats the same way) - makes the common case agree
            # by construction, rather than requiring every _native_scoped()
            # call site to somehow detect and raise on the mismatch after
            # the fact (which couldn't distinguish "wrong scope" from "a
            # real named graph that's legitimately still empty" anyway).
            kwargs['identifier'] = DATASET_DEFAULT_GRAPH_ID
        super().__init__(*args, **kwargs)
        self._backend = backend
        self._tt_registry: dict = {}   # canonical (s_key, p, o_key) -> URIRef (rdf-1.1 only)
        self._tt_nodes: dict = {}      # URIRef -> TripleTerm (rdf-1.1 only)
        self._invalidate_callback = None  # set by StarLayerDataset to clear raw query cache
        self._prepared_query_cache: dict = {}  # see starlayer.graph.query.query_cache.prepare_query_cached
        self._native_bnode_provenance: dict = {}  # native backend only - see _native_triples()
        # Bumped by _on_mutated() on every real mutation - the staleness
        # signal query()'s entailment=ENTAILMENT["OWL-RDF-Based"], infer="changed" path checks
        # _owl_rl_cache against (see VALID_INFER_MODES).
        self._mutation_generation: int = 0
        # (delta_graph, generation_it_was_computed_at) | None - the cached
        # owl-rl entailment delta (see infer(mode="delta")), populated and
        # read by query()'s entailment=ENTAILMENT["OWL-RDF-Based"] handling. Holds only the
        # newly-entailed triples, not a full closure copy of self - queried
        # as a live union with self (or, when self is native-backed or has
        # triple terms, with a decomposed snapshot of self refreshed on the
        # same cadence - see that branch's own comment for why).
        self._owl_rl_cache: "tuple[Graph, int] | None" = None
        # Only used on the "fallback" path above (native backend, or self
        # has triple terms) - a decomposed snapshot of self's own data,
        # refreshed together with _owl_rl_cache since unioning it with a
        # live view of self isn't representation-safe in that case (see
        # query()'s entailment=ENTAILMENT["OWL-RDF-Based"] branch).
        self._owl_rl_snapshot_cache: "Graph | None" = None
        # query()'s entailment=ENTAILMENT["OWL-Direct"] counterpart to _owl_rl_cache/
        # _owl_rl_snapshot_cache above - same (delta, generation) shape and
        # same fast-path/fallback-path split, but keyed by engine ("hermit"/
        # "rustdl") rather than a single shared slot: HermiT's and RustDL's
        # delta genuinely differ for the same graph (RustDL's documented
        # under-approximation of property assertions vs HermiT's complete
        # one - see owl_dl_rustdl.py's own module docstring), so a caller
        # switching engine= between calls on an unmutated graph must not
        # silently thrash a single cache slot every time - that's the exact
        # staleness bug this cache exists to prevent, just triggered by
        # engine choice instead of mutation.
        self._owl_dl_cache: "dict[str, tuple[Graph, int]]" = {}
        self._owl_dl_snapshot_cache: "dict[str, Graph]" = {}

    def _on_mutated(self) -> None:
        """Called from every place this graph's own triple content changes
        (add/addN/remove, parse(), update(), add_reification()) - notifies
        StarLayerDataset's raw-query-cache hook (_invalidate_callback, if
        set), and bumps _mutation_generation (see VALID_INFER_MODES).
        Consolidates what used to be six separate "if
        self._invalidate_callback: self._invalidate_callback()" call sites
        into one, and closes three gaps found while doing so (update() on
        both backends, the non-native turtle12/trig12 parse() branches,
        add_reification()'s non-native branch all used to bypass the hook
        entirely).
        """
        if self._invalidate_callback:
            self._invalidate_callback()
        self._mutation_generation += 1

    @property
    def _is_native(self) -> bool:
        """True when using the native RDF 1.2 backend (no tt:HASH encoding)."""
        return self._backend == 'rdf-1.2'

    @property
    def _needs_bnode_skolemization(self) -> bool:
        """True when this graph's own store is a plain rdflib
        SPARQLUpdateStore - which categorically cannot write, or be
        queried with, a real blank node at all (``_node_to_sparql()``
        raises "SPARQLStore does not support BNodes!" unconditionally,
        for reads or writes, native backend or not - confirmed live).

        The native (rdf-1.2) backend already has its own answer to this
        (``_native_add``/``_native_add_many`` skolemize or batch to
        preserve real blank-node semantics; ``_native_triples`` resolves a
        bound BNode via a provenance-tracked join). This property gates a
        second, independent, *simpler* fix for the non-native (default
        rdf-1.1, tt:HASH-encoded) backend, which had no blank-node handling
        of its own at all - ordinary ``.add()``/``.parse()`` of a real
        BNode against a SPARQLUpdateStore failed outright, for perfectly
        ordinary RDF 1.1 content with no triple terms or SHACL involved.

        Unlike the native path, this one always skolemizes (write) and
        always deskolemizes (read) via the same deterministic
        ``skolemize_bnode()``/``deskolemize_bnode()`` mapping already used
        there - no provenance tracking needed, since skolemizing is a pure
        function of the BNode's own label, so a bound BNode obtained from
        an earlier read can always be re-skolemized to find the same
        stored term again, with no dependence on how (or whether) the
        server itself re-labels blank nodes across separate queries. The
        trade-off (accepted here, unlike in native mode): a real blank
        node's own term-kind is not preserved once round-tripped - this
        backend is already an *encoded simulation* of RDF 1.2 (tt:HASH
        URIs standing in for real triple terms), so extending that same
        "encode for storage, decode for the caller" philosophy to blank
        nodes here is consistent with what this mode already does, not a
        new category of infidelity introduced just for this.

        Checked once, cheaply, per call site - not cached, since ``self.store``
        can change (``StarLayerGraph.__init__`` accepts ``store=`` once, but
        nothing prevents a caller reassigning it later).
        """
        try:
            from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore
        except ImportError:
            return False
        return isinstance(self.store, SPARQLUpdateStore)

    # ------------------------------------------------------------------
    # Native backend (rdf-1.2)
    # ------------------------------------------------------------------

    def _store_http(self) -> tuple:
        """Return (query_url, update_url, extra_headers) from the backing store.

        Raises RuntimeError if the store does not expose HTTP endpoints
        (e.g. in-memory stores). See starlayer.graph.backends.native.resolve_store_http()
        - shared with StarLayerDataset's own native-backend dispatch, since a
        dataset's contexts all share the same underlying store.
        """
        from starlayer.graph.backends.native import resolve_store_http
        return resolve_store_http(self.store, self._backend)

    def _native_scoped(self, body: str) -> str:
        """Wrap ``body`` in ``GRAPH <self.identifier> { ... }``, unless this
        graph stands for a dataset's own default graph, in which case
        ``body`` is returned bare.

        ``self.identifier`` is ``rdflib.graph.DATASET_DEFAULT_GRAPH_ID``
        (``urn:x-rdflib:default``) exactly when a ``StarLayerDataset``
        created this context via ``_load_context(DATASET_DEFAULT_GRAPH_ID)``
        for content the source document put in its own default graph (see
        ``StarLayerDataset.parse()``) - never a real graph name a document
        or caller chose. Wrapping that case in ``GRAPH <urn:x-rdflib:...>``
        anyway would silently turn "no GRAPH clause" content into a genuine
        named graph on the wire: a raw, unmodified SPARQL query with no
        GRAPH clause of its own (the normal way to address a dataset's
        default graph) would then see nothing, and a variable-graph pattern
        (``GRAPH ?g { ... }``) would wrongly enumerate it as if it were a
        real named graph. Every other identifier is a real graph name and
        keeps the explicit GRAPH wrapper as before.
        """
        if self.identifier == DATASET_DEFAULT_GRAPH_ID:
            return body
        return f'GRAPH <{self.identifier}> {{ {body} }}'

    def _native_add(self, s, p, obj) -> None:
        from starlayer.graph.backends.native import http_update, sparql_term
        from starlayer.graph.model.triple import TripleTerm as _TT
        q_url, u_url, hdrs = self._store_http()
        s_str = sparql_term(s)
        p_str = sparql_term(p)
        o_str = sparql_term(obj)
        triple_str = f'{s_str} {p_str} {o_str} .'
        # INSERT DATA disallows triple terms in subject position and nested
        # triple terms in some stores (SPARQL 1.2 restriction); INSERT...WHERE
        # with an empty WHERE is equivalent but unrestricted.
        has_tt = isinstance(s, _TT) or isinstance(obj, _TT)
        if has_tt:
            sparql = f'INSERT {{ {self._native_scoped(triple_str)} }} WHERE {{}}'
        else:
            sparql = f'INSERT DATA {{ {self._native_scoped(triple_str)} }}'
        http_update(u_url, sparql, hdrs)

    def _native_add_many(self, triples) -> None:
        """Write every ``(s, p, obj)`` in ``triples`` to this graph in a
        single SPARQL Update request, rather than one ``_native_add()`` HTTP
        call per triple.

        Real, unskolemized blank-node syntax is used here (unlike the
        single-triple ``add()`` -> ``_native_add()`` path) - safe
        specifically *because* every triple goes out together in one
        request, so SPARQL 1.1 Update's per-request blank-node scoping (the
        whole reason ``skolemize_bnode()`` exists - see its docstring) never
        comes into play: a blank node repeated across these triples keeps
        its real identity for free, and Oxigraph's own engine still
        recognizes it as a genuine blank node (correct ``ORDER BY`` term-kind
        position, ``isBLANK()``) rather than the URI ``skolemize_bnode()``
        would otherwise turn it into. Confirmed via the W3C SPARQL 1.2
        eval-triple-terms/order-1 and order-2 fixtures, whose ``ORDER BY``
        over a blank node alongside an IRI/literal/triple-term only sorts
        correctly this way.

        Used by ``parse()``/``addN()`` for a single ``StarLayerGraph``,
        where every triple is known up front and destined for this one
        graph. Not used by ``StarLayerDataset.parse()``'s own per-context
        loop: a blank node there may be shared *across* different named-graph
        contexts (data-4.trig's ``_:b``, referenced from both ``:g1`` and
        ``:g2``), each its own separate ``StarLayerGraph``/HTTP request -
        only ``skolemize_bnode()`` keeps that case safe, so that path still
        goes through ``add()`` one triple at a time.
        """
        if not triples:
            return
        from starlayer.graph.backends.native import http_update, sparql_term
        from starlayer.graph.model.triple import TripleTerm as _TT

        parts = []
        for s, p, obj in triples:
            if isinstance(s, (_TT, tuple)):
                raise ValueError(
                    "RDF 1.2: triple terms are not permitted in subject position of a triple."
                )
            if isinstance(s, DirLangString):
                raise ValueError(
                    "RDF 1.2: a literal (dirLangString) is not permitted in subject position of a triple."
                )
            s_str = sparql_term(s, skolemize_bnodes=False)
            p_str = sparql_term(p, skolemize_bnodes=False)
            o_str = sparql_term(obj, skolemize_bnodes=False)
            parts.append(f'{s_str} {p_str} {o_str} .')

        _, u_url, hdrs = self._store_http()
        sparql = f'INSERT {{ {self._native_scoped(" ".join(parts))} }} WHERE {{}}'
        http_update(u_url, sparql, hdrs)
        self._on_mutated()

    def _native_triples(self, triple):
        from rdflib import BNode
        from rdflib.term import Variable

        from starlayer.graph.backends.native import http_ask, http_select, sparql_term
        q_url, _, hdrs = self._store_http()
        s, p, o = triple

        free = []
        bnode_filters = {}  # var -> BNode, only when no provenance is known (best-effort fallback)
        join_triples = []   # extra join patterns resolving a provenance-tracked BNode via a real join

        def _provenance_join(node) -> str | None:
            # Keyed by id(node), not node's own value/hash: two BNode
            # objects can be == equal (same label) while denoting genuinely
            # different stored nodes - confirmed live against Fuseki, whose
            # per-query blank-node numbering resets each request, so two
            # separate discovery queries can each hand back a node labeled
            # "b0" for two different underlying nodes. Value-based keying
            # would let the second overwrite the first's entry, silently
            # misdirecting a later join for the first. The dict holds a
            # strong reference to `node` specifically to keep id(node) from
            # being reused by a later, unrelated object once this one is
            # garbage collected.
            entry = self._native_bnode_provenance.get(id(node))
            if entry is None:
                return None
            _kept_node, prov = entry
            anchor = f"_pj{len(join_triples)}"
            found_pos, other1, other2 = prov
            if found_pos == 's':
                join_triples.append(f"?{anchor} {sparql_term(other1)} {sparql_term(other2)} .")
            else:
                join_triples.append(f"{sparql_term(other1)} {sparql_term(other2)} ?{anchor} .")
            return anchor

        def _slot(node, var: str) -> str:
            if node is None:
                free.append(var)
                return f'?{var}'
            if isinstance(node, BNode):
                # A bound BNode can't safely be pushed into the query text
                # at all. sparql_term()'s skolemized form only matches
                # content written via the single-triple add() path
                # (_native_add()) - parse()/addN() for a single graph go
                # through _native_add_many() instead, which deliberately
                # writes a real, unskolemized blank node (batched into one
                # request specifically to preserve real SPARQL
                # isBLANK()/ORDER BY term-kind semantics - see that
                # function's own docstring), so the skolemized form finds
                # nothing there. The BNode's own raw n3() form fares even
                # worse: confirmed live (against Oxigraph, inside a
                # GRAPH <uri> {} block) that a blank-node label used in a
                # query pattern is not restricted to matching the store's
                # actual blank nodes at all - it matched an unrelated
                # *URI* subject's own unrelated triple.
                #
                # The fix that actually holds up: whenever a BNode is
                # first yielded from a free-variable slot elsewhere in this
                # method, its single-hop discovery pattern (the other,
                # concrete parts of that triple) is recorded in
                # self._native_bnode_provenance. A later bound-BNode query
                # re-derives it via a genuine SPARQL join against that
                # recorded anchor - correct on any backend, since the join
                # is resolved within one query's own variable scope, not by
                # comparing labels across two separate requests. That
                # comparison is NOT safe in general: confirmed live that
                # Fuseki resets its blank-node numbering per query, so two
                # DIFFERENT stored blank nodes can legitimately share the
                # same label ("b0") across two separate queries - only
                # Oxigraph's labels are stable/content-derived enough for
                # that to work. The label-based fallback below only runs
                # when no provenance was recorded (e.g. a caller built or
                # obtained the BNode some other way) - correct on Oxigraph,
                # not guaranteed on backends with per-query label resets.
                anchor = _provenance_join(node)
                if anchor is not None:
                    return f'?{anchor}'
                bnode_filters[var] = node
                return f'?{var}'
            return sparql_term(node)

        s_str = _slot(s, 's')
        p_str = _slot(p, 'p')
        o_str = _slot(o, 'o')
        pattern = ' '.join(join_triples) + (' ' if join_triples else '') + f'{s_str} {p_str} {o_str} .'
        body = self._native_scoped(pattern)

        if not free and not bnode_filters:
            sparql = f'ASK {{ {body} }}'
            if http_ask(q_url, sparql, hdrs):
                yield (s, p, o)
            return

        projected = free + list(bnode_filters.keys())
        sel = ' '.join(f'?{v}' for v in projected)
        distinct = 'DISTINCT ' if bnode_filters else ''
        sparql = f'SELECT {distinct}{sel} WHERE {{ {body} }}'
        vars_, bindings = http_select(q_url, sparql, hdrs)
        for row in bindings:
            if any(row.get(Variable(v)) != bn for v, bn in bnode_filters.items()):
                continue
            s_val = row.get(Variable('s'), s) if 's' in free else s
            p_val = row.get(Variable('p'), p) if 'p' in free else p
            o_val = row.get(Variable('o'), o) if 'o' in free else o
            if (
                isinstance(s_val, BNode)
                and p_val is not None and not isinstance(p_val, BNode)
                and o_val is not None and not isinstance(o_val, BNode)
            ):
                self._native_bnode_provenance.setdefault(id(s_val), (s_val, ('s', p_val, o_val)))
            if (
                isinstance(o_val, BNode)
                and s_val is not None and not isinstance(s_val, BNode)
                and p_val is not None and not isinstance(p_val, BNode)
            ):
                self._native_bnode_provenance.setdefault(id(o_val), (o_val, ('o', s_val, p_val)))
            yield (s_val, p_val, o_val)

    # ------------------------------------------------------------------
    # Internal helpers (rdf-1.1 encoding layer)
    # ------------------------------------------------------------------

    def _coerce_tt(self, node):
        """Translate a tuple/TripleTerm to its internal URIRef, or a DirLangString
        to its internal datatype-encoded Literal, creating it if new.
        Use only on write paths (add, add_reification). For reads use _coerce_tt_read."""
        if node is None:
            return None
        if isinstance(node, TripleTerm):
            return self._intern_tt(node)
        if isinstance(node, tuple) and len(node) == 3:
            if all(x is not None for x in node):
                return self._intern_tt(TripleTerm(*node))
            return None
        if isinstance(node, DirLangString):
            return encode_dirlangstring(node)
        return node

    def _coerce_tt_read(self, node):
        """Translate a tuple/TripleTerm to its URIRef, or a DirLangString to its
        internal datatype-encoded Literal, for read-only paths.
        Returns _TT_NOT_FOUND if the TripleTerm is not registered — never creates.
        A DirLangString always succeeds — unlike a TripleTerm, its encoding is a
        pure function of its own value and needs no registry lookup to exist.
        Partial-wildcard tuples (containing None) are not handled here; callers
        should check _is_tt_wildcard and use _matching_tt_uris instead."""
        if node is None:
            return None
        if isinstance(node, TripleTerm):
            return self._tt_registry.get(node._key(), _TT_NOT_FOUND)
        if isinstance(node, tuple) and len(node) == 3:
            if all(x is not None for x in node):
                return self._tt_registry.get(TripleTerm(*node)._key(), _TT_NOT_FOUND)
            # Partial wildcard — caller must use _matching_tt_uris
            return _TT_NOT_FOUND
        if isinstance(node, DirLangString):
            return encode_dirlangstring(node)
        return node

    @staticmethod
    def _is_tt_wildcard(node) -> bool:
        """True if node is a tuple pattern containing at least one None — a wildcard triple-term."""
        return (
            isinstance(node, tuple)
            and len(node) == 3
            and not all(x is not None for x in node)
        )

    def _matching_tt_uris(self, pattern: tuple):
        """Yield tt:HASH URIRefs for every registered TripleTerm matching the tuple pattern.

        Each component of pattern may be None (wildcard) or a ground value.
        Comparison is against the TripleTerm's stored subject/predicate/object.
        """
        s_pat, p_pat, o_pat = pattern
        for uri, tt in self._tt_nodes.items():
            if s_pat is not None and tt.subject != s_pat:
                continue
            if p_pat is not None and tt.predicate != p_pat:
                continue
            if o_pat is not None and tt.object != o_pat:
                continue
            yield uri

    def _coerce_choices(self, node):
        """Coerce a subject/object slot in triples_choices.

        Returns (coerced, skip):
          skip=True  → the caller should yield nothing (TripleTerm not in registry)
          skip=False → coerced is the value or list to pass to the store
        """
        if node is None:
            return None, False
        if _needs_encoding(node):
            c = self._coerce_tt_read(node)
            return (None, True) if c is _TT_NOT_FOUND else (c, False)
        if isinstance(node, list):
            out = []
            for item in node:
                if _needs_encoding(item):
                    c = self._coerce_tt_read(item)
                    if c is not _TT_NOT_FOUND:
                        out.append(c)
                else:
                    out.append(item)
            return out, False
        return node, False

    def _encode_init_bindings(self, init_bindings):
        """Resolve TripleTerm/tuple values in a SPARQL initBindings mapping to
        their internal tt:HASH URIRef, mirroring every other read path.

        A triple term not already registered in this graph resolves to a fresh
        BNode that cannot match anything in the store, giving correct "zero
        rows" semantics rather than silently comparing a raw Python object
        against store terms it can never equal.
        """
        if not init_bindings:
            return init_bindings

        encoded = {}
        for var, value in init_bindings.items():
            if _needs_encoding(value):
                resolved = self._coerce_tt_read(value)
                encoded[var] = resolved if resolved is not _TT_NOT_FOUND else BNode()
            else:
                encoded[var] = value
        return encoded

    def _intern_tt(self, tt: TripleTerm) -> URIRef:
        """Return the content-addressed URIRef encoding of tt, creating it if new."""
        key = tt._key()
        if key in self._tt_registry:
            return self._tt_registry[key]
        # Coerce nested triple terms to their URIRef form first
        s_n = self._coerce_tt(tt.subject) if _needs_encoding(tt.subject) else tt.subject
        o_n = self._coerce_tt(tt.object)  if _needs_encoding(tt.object)  else tt.object
        uri = URIRef(TT_NS + tt_hash(term_key(s_n), term_key(tt.predicate), term_key(o_n)))
        self._tt_registry[key] = uri
        # Cache the normalized form (s_n/o_n, matching what's actually stored below),
        # not the original tt - a nested triple-term component may still be a raw
        # tuple or unnormalized TripleTerm on tt itself, which _restore() couldn't
        # resolve further since it only follows tt:HASH URIRef chains.
        self._tt_nodes[uri] = TripleTerm(s_n, tt.predicate, o_n)
        super().add((uri, RDF.subject,   s_n))
        super().add((uri, RDF.predicate, tt.predicate))
        super().add((uri, RDF.object,    o_n))
        return uri

    def _restore(self, node):
        """Convert a TT URIRef to TripleTerm, or a dirlang-encoded Literal to a
        DirLangString; pass all other nodes through.

        Recurses for TripleTerm so a nested triple term (whose subject/object
        component is itself an encoded tt:HASH URIRef) resolves fully rather
        than leaving an inner URIRef unresolved. DirLangString decoding needs
        no recursion — its encoding is a single self-describing Literal, not a
        chain of triples.
        """
        if isinstance(node, URIRef) and str(node).startswith(TT_NS):
            tt = self._tt_nodes.get(node)
            if tt is None:
                # Not registered in this graph - it may be a fully-ground
                # TRIPLE()/<<( )>> value that was computed but never written
                # anywhere (see starlayer.graph.model.encoding's TT_HASH_FN memo).
                remembered = lookup_tt_hash(node)
                if remembered is not None:
                    tt = TripleTerm(*remembered)
            if tt is not None:
                restored = TripleTerm(self._restore(tt.subject), tt.predicate, self._restore(tt.object))
                restored._namespace_manager = self.namespace_manager
                return restored
        elif isinstance(node, Literal):
            dls = decode_dirlangstring(node)
            if dls is not None:
                return dls
        return node

    def _is_encoding_triple(self, s, p, o):
        """True if (s, p, o) is internal infrastructure that must not be surfaced."""
        if isinstance(s, URIRef) and str(s).startswith(TT_NS):
            if p in _ENCODING_PREDS:
                return True
            # rdf:type rdf:TripleTerm is emitted by the JSON-LD 1.2 serializer so
            # that standard JSON-LD parsers can reconstruct triple terms; filter it
            # here so it never appears in user-visible results.
            if p == RDF.type and isinstance(o, URIRef) and str(o) == _RDF_TRIPLE_TERM:
                return True
        return False

    def _build_registry_from_store(self):
        """Scan the underlying store for TT_NS URIRefs and populate the registry.

        No-op for the native rdf-1.2 backend, which stores triple terms
        directly in the backend rather than via tt:HASH encoding.
        """
        if self._is_native:
            return
        tt_uris = set(
            s for s, p, o in _raw_triples(self, (None, RDF.subject, None))
            if isinstance(s, URIRef) and str(s).startswith(TT_NS)
        )

        def reconstruct(uri):
            if uri in self._tt_nodes:
                return self._tt_nodes[uri]
            s_n = next((o for _, _, o in _raw_triples(self, (uri, RDF.subject,   None))), None)
            p_n = next((o for _, _, o in _raw_triples(self, (uri, RDF.predicate, None))), None)
            o_n = next((o for _, _, o in _raw_triples(self, (uri, RDF.object,    None))), None)
            s = reconstruct(s_n) if isinstance(s_n, URIRef) and str(s_n).startswith(TT_NS) else s_n
            o = reconstruct(o_n) if isinstance(o_n, URIRef) and str(o_n).startswith(TT_NS) else o_n
            tt = TripleTerm(s, p_n, o)
            self._tt_registry[tt._key()] = uri
            self._tt_nodes[uri] = tt
            return tt

        for uri in tt_uris:
            reconstruct(uri)

    # ------------------------------------------------------------------
    # Persistent store lifecycle
    # ------------------------------------------------------------------

    def open(self, configuration, create: bool = False) -> StarLayerGraph:
        """Open a persistent store and rebuild the TripleTerm registry.

        Delegates to rdflib's Graph.open() then scans the store for any
        existing tt:HASH encoding triples so TripleTerms are immediately
        usable without a separate rebuild call. Returns self, not whatever
        status value rdflib's own Graph.open() returns (fixed 2026-10-04 -
        this override used to blindly forward that raw result, even though
        its own annotation already claimed StarLayerGraph).

        The store backend (e.g. Sleepycat, rdflib-sqlalchemy) is not a
        StarLayer dependency — install and configure it separately, then
        pass store='StoreName' to the constructor before calling open().

        Example::

            sg = StarLayerGraph(store='Sleepycat')
            sg.open('/path/to/db', create=True)
        """
        super().open(configuration, create)
        if not self._is_native:
            self._build_registry_from_store()
        return self

    def close(self, commit_pending_transaction: bool = False) -> None:
        """Close the underlying store, optionally committing pending writes."""
        self.store.close(commit_pending_transaction=commit_pending_transaction)

    # ------------------------------------------------------------------
    # Overridden rdflib.Graph methods
    # ------------------------------------------------------------------

    def add(self, triple) -> StarLayerGraph:
        """Add a triple. A TripleTerm (or plain 3-tuple) in the object position is
        converted to its internal encoding automatically. Returns self, matching
        rdflib's own Graph.add() - fixed 2026-10-04, this override used to fall
        off the end and return None instead, silently breaking chaining
        (g.add(...).add(...)) that works fine on plain rdflib.Graph.

            g.add((s, p, o))              # plain triple
            g.add((s, p, TripleTerm(...))) # TripleTerm as object
            g.add((s, p, (a, b, c)))      # plain tuple treated as TripleTerm
        """
        s, p, obj = triple
        if isinstance(s, (TripleTerm, tuple)):
            raise ValueError(
                "RDF 1.2: triple terms are not permitted in subject position of a triple."
            )
        if isinstance(s, DirLangString):
            raise ValueError(
                "RDF 1.2: a literal (dirLangString) is not permitted in subject position of a triple."
            )
        if self._is_native:
            self._native_add(s, p, obj)
            self._on_mutated()
            return self
        s_n, o_n = self._coerce_tt(s), self._coerce_tt(obj)
        if self._needs_bnode_skolemization:
            from starlayer.graph.backends.native import skolemize_bnode
            if isinstance(s_n, BNode):
                s_n = skolemize_bnode(s_n)
            if isinstance(o_n, BNode):
                o_n = skolemize_bnode(o_n)
        super().add((s_n, p, o_n))
        self._on_mutated()
        return self

    def addN(self, quads) -> StarLayerGraph:
        """Add multiple quads, encoding all TripleTerms in one store.addN() call.

        Unlike the default Graph.addN() → store.addN() path, this override
        collects encoding triples (rdf:subject/predicate/object for each
        TripleTerm) together with the main triples so that all inserts are
        submitted to the store in a single batch.  On transaction-aware
        backends (SQLAlchemy, Sleepycat) this means one commit instead of
        three per triple term, which is significantly faster for bulk loads.
        """
        if self._is_native:
            own_triples = [
                (s, p, o) for s, p, o, c in quads
                if isinstance(c, Graph) and c.identifier is self.identifier
            ]
            self._native_add_many(own_triples)
            return self

        all_quads: list = []

        def _collect(tt: TripleTerm) -> URIRef:
            key = tt._key()
            if key in self._tt_registry:
                return self._tt_registry[key]
            s_n = _collect(tt.subject) if isinstance(tt.subject, TripleTerm) else \
                  (_collect(TripleTerm(*tt.subject))
                   if isinstance(tt.subject, tuple) and len(tt.subject) == 3 else tt.subject)
            o_n = _collect(tt.object) if isinstance(tt.object, TripleTerm) else \
                  (_collect(TripleTerm(*tt.object))
                   if isinstance(tt.object, tuple) and len(tt.object) == 3 else
                   (encode_dirlangstring(tt.object) if isinstance(tt.object, DirLangString) else tt.object))
            s_key = term_key(self._tt_registry.get(tt.subject._key(), s_n)
                        if isinstance(tt.subject, TripleTerm) else s_n)
            o_key = term_key(self._tt_registry.get(tt.object._key(),  o_n)
                        if isinstance(tt.object,  TripleTerm) else o_n)
            uri = URIRef(TT_NS + tt_hash(s_key, term_key(tt.predicate), o_key))
            self._tt_registry[key] = uri
            self._tt_nodes[uri] = tt
            all_quads.append((uri, RDF.subject,   s_n,          self))
            all_quads.append((uri, RDF.predicate, tt.predicate, self))
            all_quads.append((uri, RDF.object,    o_n,          self))
            return uri

        def _enc(node):
            if isinstance(node, TripleTerm):
                return _collect(node)
            if isinstance(node, tuple) and len(node) == 3 and all(x is not None for x in node):
                return _collect(TripleTerm(*node))
            if isinstance(node, DirLangString):
                return encode_dirlangstring(node)
            return node

        for s, p, o, c in quads:
            if not (isinstance(c, Graph) and c.identifier is self.identifier):
                continue
            if isinstance(s, TripleTerm):
                raise ValueError(
                    "RDF 1.2: triple terms are not permitted in subject position of a triple."
                )
            if isinstance(s, DirLangString):
                raise ValueError(
                    "RDF 1.2: a literal (dirLangString) is not permitted in subject position of a triple."
                )
            all_quads.append((_enc(s), p, _enc(o), self))

        self.store.addN(all_quads)
        self._on_mutated()
        return self

    def _native_remove(self, s, p, obj) -> None:
        """Remove triples matching (s, p, obj) via raw SPARQL Update -
        mirrors _native_add()/_native_triples()'s own dispatch rather than
        rdflib's own ``Graph.remove()`` -> ``store.remove()``, which
        previously reached rdflib's ``SPARQLUpdateStore`` directly and
        crashed outright on any BNode (``_node_to_sparql()`` raises
        "SPARQLStore does not support BNodes!", confirmed live against
        Oxigraph - it has no ``skolemize_bnode()`` of its own to fall
        back on, unlike this class's own read/write paths).

        None in any position is a wildcard (matching rdflib's own
        ``Graph.remove()`` contract), handled with a ``DELETE {p} WHERE
        {p}`` pattern-delete rather than ``DELETE DATA`` - the latter only
        accepts fully ground triples.
        """
        from starlayer.graph.backends.native import http_update, sparql_term
        from starlayer.graph.model.triple import TripleTerm as _TT
        _, u_url, hdrs = self._store_http()

        # A removal can invalidate a previously-recorded bnode discovery
        # handle (_native_triples()'s join-based fix for bound-BNode
        # queries) - clear rather than try to reason about which entries
        # are still valid.
        self._native_bnode_provenance.clear()

        free = []
        def _slot(node, var: str) -> str:
            if node is None:
                free.append(var)
                return f'?{var}'
            return sparql_term(node)

        pattern = f'{_slot(s, "s")} {_slot(p, "p")} {_slot(obj, "o")} .'
        scoped = self._native_scoped(pattern)

        has_tt = isinstance(s, _TT) or isinstance(obj, _TT)
        if free or has_tt:
            # DELETE DATA disallows both variables and (in some stores)
            # triple terms - DELETE/WHERE with a matching pattern on both
            # sides is the unrestricted equivalent, same rationale
            # _native_add() already uses for INSERT.
            sparql = f'DELETE {{ {scoped} }} WHERE {{ {scoped} }}'
        else:
            sparql = f'DELETE DATA {{ {scoped} }}'
        http_update(u_url, sparql, hdrs)

    def remove(self, triple) -> StarLayerGraph:
        """Remove a triple. Returns self (matching rdflib's own Graph.remove(),
        fixed 2026-10-04 - same missing-return bug as add() above) immediately
        if a TripleTerm in the pattern is not registered."""
        s, p, obj = triple
        if self._is_native:
            self._native_remove(s, p, obj)
            self._on_mutated()
            return self
        s_n, o_n = self._coerce_tt_read(s), self._coerce_tt_read(obj)
        if s_n is _TT_NOT_FOUND or o_n is _TT_NOT_FOUND:
            return self
        if self._needs_bnode_skolemization:
            from starlayer.graph.backends.native import skolemize_bnode
            if isinstance(s_n, BNode):
                s_n = skolemize_bnode(s_n)
            if isinstance(o_n, BNode):
                o_n = skolemize_bnode(o_n)
        super().remove((s_n, p, o_n))
        self._on_mutated()
        return self

    def triples(self, triple) -> Generator[tuple, None, None]:
        """Iterate triples matching the pattern. Filters internal encoding triples.

        TripleTerms in results are returned as TripleTerm objects, not raw URIRefs.
        Returns nothing if a TripleTerm in the pattern is not registered in this graph.

        Wildcard triple-term patterns — tuples containing None — are supported in
        subject and object positions.  ``(None, None, None)`` matches any triple
        term; ``(EX.alice, None, None)`` matches only triple terms whose subject
        is EX.alice.  The fan-out is O(k) where k is the number of registered
        triple terms that match the pattern.
        """
        if self._is_native:
            yield from self._native_triples(triple)
            return
        s, p, obj = triple
        s_wild = self._is_tt_wildcard(s)
        o_wild = self._is_tt_wildcard(obj)

        if s_wild or o_wild:
            yield from self._triples_tt_wildcard(s, p, obj, s_wild, o_wild)
            return

        s_n, o_n = self._coerce_tt_read(s), self._coerce_tt_read(obj)
        if s_n is _TT_NOT_FOUND or o_n is _TT_NOT_FOUND:
            return
        if self._needs_bnode_skolemization:
            # A bound BNode is re-skolemized deterministically (a pure
            # function of its own label - see _needs_bnode_skolemization's
            # docstring) to find the same stored term .add()/.parse()
            # wrote it as; a BNode-shaped result coming back is
            # deskolemized before being handed to the caller, so the
            # round-trip is transparent - the caller only ever sees real
            # BNode objects, never the internal skolemized URI.
            from starlayer.graph.backends.native import deskolemize_bnode, skolemize_bnode
            if isinstance(s_n, BNode):
                s_n = skolemize_bnode(s_n)
            if isinstance(o_n, BNode):
                o_n = skolemize_bnode(o_n)
            for s_r, p_r, o_r in super().triples((s_n, p, o_n)):
                if not self._is_encoding_triple(s_r, p_r, o_r):
                    yield (deskolemize_bnode(self._restore(s_r)), p_r, deskolemize_bnode(self._restore(o_r)))
            return
        for s_r, p_r, o_r in super().triples((s_n, p, o_n)):
            if not self._is_encoding_triple(s_r, p_r, o_r):
                yield (self._restore(s_r), p_r, self._restore(o_r))

    def _triples_tt_wildcard(self, s, p, obj, s_wild: bool, o_wild: bool):
        """Fan-out triples() for wildcard triple-term patterns.

        For each registered TripleTerm whose encoding matches the wildcard
        pattern, issues one store query with the concrete tt:HASH URI and
        unions the results.  A seen-set prevents duplicates when both
        subject and object carry wildcard patterns.
        """
        s_uris  = list(self._matching_tt_uris(s))   if s_wild else None
        o_uris  = list(self._matching_tt_uris(obj))  if o_wild else None

        s_fixed = None   if s_wild else self._coerce_tt_read(s)
        o_fixed = None   if o_wild else self._coerce_tt_read(obj)

        if not s_wild and s_fixed is _TT_NOT_FOUND:
            return
        if not o_wild and o_fixed is _TT_NOT_FOUND:
            return

        # Build the Cartesian product of concrete URIs for both positions.
        s_candidates = s_uris  if s_wild  else [s_fixed]
        o_candidates = o_uris  if o_wild  else [o_fixed]

        seen: set = set()
        for s_n in s_candidates:
            for o_n in o_candidates:
                for s_r, p_r, o_r in super().triples((s_n, p, o_n)):
                    if not self._is_encoding_triple(s_r, p_r, o_r):
                        key = (s_r, p_r, o_r)
                        if key not in seen:
                            seen.add(key)
                            yield (self._restore(s_r), p_r, self._restore(o_r))

    def _native_triples_choices(self, triple):
        """Native-backend body of triples_choices() - built directly as a
        SPARQL SELECT with a VALUES clause per list-valued position rather
        than delegating to the store: SPARQLStore.triples_choices() (the
        rdflib base class's own implementation) is an unconditional
        ``raise NotImplementedError("Triples choices currently not
        supported")`` - confirmed live against Oxigraph before this fix.
        A single HTTP round trip regardless of how many choices are given,
        same shape as _native_triples()'s own free-variable/ASK-vs-SELECT
        dispatch.
        """
        from rdflib.term import Variable

        from starlayer.graph.backends.native import http_select, sparql_term
        s, p, o = triple
        q_url, _, hdrs = self._store_http()

        free = []
        values_clauses = []

        def _slot(node, var: str) -> str:
            if node is None:
                free.append(var)
                return f'?{var}'
            if isinstance(node, list):
                free.append(var)
                terms = ' '.join(sparql_term(n) for n in node)
                values_clauses.append(f'VALUES ?{var} {{ {terms} }}')
                return f'?{var}'
            return sparql_term(node)

        pattern = f'{_slot(s, "s")} {_slot(p, "p")} {_slot(o, "o")} .'
        sparql = f'SELECT * WHERE {{ {self._native_scoped(pattern)} {" ".join(values_clauses)} }}'
        vars_, bindings = http_select(q_url, sparql, hdrs)
        for row in bindings:
            yield (
                row.get(Variable('s'), s) if 's' in free else s,
                row.get(Variable('p'), p) if 'p' in free else p,
                row.get(Variable('o'), o) if 'o' in free else o,
            )

    def triples_choices(self, triple, context=None) -> Generator[tuple, None, None]:
        """Iterate triples matching a choices pattern. Filters encoding triples; restores TripleTerms.

        Each position may be None (wildcard), a single node, or a list of nodes.
        TripleTerms not registered in this graph are silently dropped from lists;
        an unregistered single TripleTerm causes the method to yield nothing.
        """
        s, p, o = triple
        if self._is_native:
            yield from self._native_triples_choices((s, p, o))
            return
        s_n, skip_s = self._coerce_choices(s)
        o_n, skip_o = self._coerce_choices(o)
        if skip_s or skip_o:
            return
        for s_r, p_r, o_r in super().triples_choices((s_n, p, o_n), context=context):
            if not self._is_encoding_triple(s_r, p_r, o_r):
                yield (self._restore(s_r), p_r, self._restore(o_r))

    def __contains__(self, triple):
        """Test triple membership. Returns False if a TripleTerm in the pattern is not registered."""
        s, p, obj = triple
        if self._is_native:
            return any(True for _ in self._native_triples((s, p, obj)))
        s_n, o_n = self._coerce_tt_read(s), self._coerce_tt_read(obj)
        if s_n is _TT_NOT_FOUND or o_n is _TT_NOT_FOUND:
            return False
        return super().__contains__((s_n, p, o_n))

    def _native_len(self) -> int:
        """COUNT(*) via one SPARQL SELECT, rather than __len__ falling
        through to `self.triples((None, None, None))` and fetching + Python-
        counting every triple over HTTP - the store already supports this
        efficiently (plain SPARQLStore.__len__ already does a COUNT(*) for a
        non-native graph; StarLayerGraph's own __len__ override just never
        used it for native).
        """
        from rdflib.term import Variable

        from starlayer.graph.backends.native import http_select
        q_url, _, hdrs = self._store_http()
        sparql = f'SELECT (COUNT(*) AS ?c) WHERE {{ {self._native_scoped("?s ?p ?o .")} }}'
        _vars, bindings = http_select(q_url, sparql, hdrs)
        if not bindings:
            return 0
        return int(str(bindings[0][Variable('c')]))

    def __len__(self):
        """Count of visible (non-encoding) triples."""
        if self._is_native:
            return self._native_len()
        return sum(1 for _ in self.triples((None, None, None)))

    # ------------------------------------------------------------------
    # RDF 1.2-specific additions
    # ------------------------------------------------------------------

    def _native_reifiers(self, TT, predicate, object):
        """Native-backend body of reifiers() - uses self.triples() (which
        dispatches through _native_triples()) rather than the rdf-1.1 path's
        super().triples() + _tt_registry lookup, neither of which mean
        anything for a native backend (no tt:HASH encoding, no local
        registry of what's in the live store).
        """
        if TT is not None:
            tt_reifiers = {r for r, _, _ in self.triples((None, RDF_REIFIES, TT))}
        else:
            tt_reifiers = None

        if predicate is not None or object is not None:
            prop_reifiers = {s for s, _, _ in self.triples((None, predicate, object))}
        else:
            prop_reifiers = None

        if tt_reifiers is not None and prop_reifiers is not None:
            candidates = tt_reifiers & prop_reifiers
        elif tt_reifiers is not None:
            candidates = tt_reifiers
        elif prop_reifiers is not None:
            all_reifiers = {r for r, _, _ in self.triples((None, RDF_REIFIES, None))}
            candidates = prop_reifiers & all_reifiers
        else:
            candidates = {r for r, _, _ in self.triples((None, RDF_REIFIES, None))}

        yield from candidates

    def add_reifier_annotation(self, predicate, obj, name=None) -> IdentifiedNode:
        """Create a reifier node and add one annotation property to it.

        Returns the reifier node itself - a ``URIRef`` if ``name`` was
        given, otherwise a fresh ``BNode`` - so it can be passed straight
        into ``add_reification()`` (see below).

        The node is not yet a reifier until add_reification() is called.

            r = g.add_reifier_annotation(EX.confidence, Literal("0.9"), name=EX.stmt1)
            g.add_reification(r, (EX.bob, EX.knows, EX.carol))

            # or inline:
            g.add_reification(
                g.add_reifier_annotation(EX.reported, EX.NYTimes),
                triple_term
            )
        """
        reifier = URIRef(name) if name is not None else BNode()
        self.add((reifier, predicate, obj))
        return reifier

    def add_reification(self, reifier, triple_term) -> StarLayerGraph:
        """Add reifier rdf:reifies triple_term, making the node an official
        reifier. Returns this graph, matching every other mutating method
        on this class (add()/remove()/addN()/etc) - added 2026-10-04, this
        used to return None, the one mutating method that didn't support
        chaining."""
        tt = triple_term if isinstance(triple_term, TripleTerm) else TripleTerm(*triple_term)
        if self._is_native:
            # self.add() (-> _native_add()) writes tt using the backend's
            # real <<( )>> syntax. The rdf-1.1 path below instead interns tt
            # to its tt:HASH encoding (super().add() bypasses backend
            # dispatch entirely, correct only for that encoding) - using it
            # here for native would write raw rdf:subject/predicate/object
            # fragments straight into a live RDF-1.2 endpoint instead of a
            # real triple term. Confirmed live: a second StarLayerGraph
            # object (same store, no shared in-process state) read back
            # nothing but the fragments via this path before this fix.
            self.add((reifier, RDF_REIFIES, tt))
            return self
        tt_uri = self._intern_tt(tt)
        super().add((reifier, RDF_REIFIES, tt_uri))
        self._on_mutated()
        return self

    def reifiers(self, TT=None, predicate=None, object=None) -> Generator[IdentifiedNode, None, None]:
        """Yield reifier nodes matching the given filters.

        TT        -- only reifiers that rdf:reifies this triple term
        predicate -- only reifiers that have (reifier, predicate, ?) in the graph
        object    -- only reifiers that have (reifier, ?, object) in the graph

        Filters combine: reifiers(TT=t, predicate=p, object=o) returns
        reifiers that reify t AND have (reifier, p, o) in the graph.
        """
        if self._is_native:
            yield from self._native_reifiers(TT, predicate, object)
            return
        # Step 1 — candidate reifiers from TT filter (fast path via rdf:reifies index)
        if TT is not None:
            tt_uri = self._coerce_tt_read(TT)
            if tt_uri is None or tt_uri is _TT_NOT_FOUND:
                return
            tt_reifiers = {r for r, _, _ in super().triples((None, RDF_REIFIES, tt_uri))}
        else:
            tt_reifiers = None  # no TT filter

        # Step 2 — candidate reifiers from predicate/object filter
        if predicate is not None or object is not None:
            prop_reifiers = {s for s, _, _ in super().triples((None, predicate, object))
                             if not str(s).startswith(TT_NS)}
        else:
            prop_reifiers = None  # no property filter

        # Step 3 — intersect whichever filters are active
        if tt_reifiers is not None and prop_reifiers is not None:
            candidates = tt_reifiers & prop_reifiers
        elif tt_reifiers is not None:
            candidates = tt_reifiers
        elif prop_reifiers is not None:
            all_reifiers = {r for r, _, _ in super().triples((None, RDF_REIFIES, None))}
            candidates = prop_reifiers & all_reifiers
        else:
            candidates = {r for r, _, _ in super().triples((None, RDF_REIFIES, None))}

        yield from candidates

    def reifications(self, s=None, p=None, o=None) -> Generator[TripleTerm, None, None]:
        """Yield TripleTerms that have at least one reifier and match the s/p/o pattern.

            g.reifications()                 # all reified triple terms
            g.reifications(p=EX.knows)       # reified TTs with that predicate
        """
        if self._is_native:
            seen = set()
            for _, _, tt in self.triples((None, RDF_REIFIES, None)):
                if not isinstance(tt, TripleTerm) or tt in seen:
                    continue
                if s is not None and tt.subject != s:
                    continue
                if p is not None and tt.predicate != p:
                    continue
                if o is not None and tt.object != o:
                    continue
                seen.add(tt)
                yield tt
            return
        for tt in self.triple_terms(subject=s, predicate=p, object=o):
            tt_uri = self._coerce_tt_read(tt)
            if tt_uri and tt_uri is not _TT_NOT_FOUND:
                if any(True for _ in super().triples((None, RDF_REIFIES, tt_uri))):
                    yield tt

    def reifier_annotations(self, TT) -> Generator[tuple, None, None]:
        """Yield (reifier, predicate, value) annotation triples for all reifiers of TT.

        Excludes the rdf:reifies triple itself.
        """
        if self._is_native:
            for reifier, _, _ in self.triples((None, RDF_REIFIES, TT)):
                for _, pred, val in self.triples((reifier, None, None)):
                    if pred != RDF_REIFIES:
                        yield reifier, pred, val
            return
        tt_uri = self._coerce_tt_read(TT)
        if tt_uri is None or tt_uri is _TT_NOT_FOUND:
            return
        for reifier, _, _ in super().triples((None, RDF_REIFIES, tt_uri)):
            for _, pred, val in super().triples((reifier, None, None)):
                if pred != RDF_REIFIES:
                    yield reifier, pred, self._restore(val)

    def reified_triples(self, reifier) -> Generator[TripleTerm, None, None]:
        """Yield the TripleTerms reified by the given reifier node."""
        if self._is_native:
            for _, _, o in self.triples((reifier, RDF_REIFIES, None)):
                if isinstance(o, TripleTerm):
                    yield o
            return
        for _, _, o in super().triples((reifier, RDF_REIFIES, None)):
            if isinstance(o, URIRef) and str(o).startswith(TT_NS):
                tt = self._tt_nodes.get(o)
                if tt is not None:
                    tt._namespace_manager = self.namespace_manager
                    yield tt

    def triple_terms(self, subject=None, predicate=None, object=None) -> Generator[TripleTerm, None, None]:
        """Yield all TripleTerms registered in this graph, with optional filters.

        Any combination of subject, predicate, object narrows the results:
            g.triple_terms()                        # all triple terms
            g.triple_terms(predicate=EX.knows)      # all TTs with that predicate
            g.triple_terms(EX.bob, EX.knows, None)  # any TT with that s and p
        """
        if self._is_native:
            # No local registry for native (no tt:HASH encoding at all) -
            # scan every triple in the graph for a triple-term-valued
            # object instead. O(graph size), same complexity class as the
            # rdf-1.1 path's _tt_nodes scan (also every triple term ever
            # seen, just from a local dict instead of a live fetch).
            seen = set()
            for _, _, tt in self.triples((None, None, None)):
                if not isinstance(tt, TripleTerm) or tt in seen:
                    continue
                if subject   is not None and tt.subject   != subject:   continue
                if predicate is not None and tt.predicate != predicate: continue
                if object    is not None and tt.object    != object:    continue
                seen.add(tt)
                yield tt
            return
        for tt in self._tt_nodes.values():
            if subject   is not None and tt.subject   != subject:   continue
            if predicate is not None and tt.predicate != predicate: continue
            if object    is not None and tt.object    != object:    continue
            tt._namespace_manager = self.namespace_manager
            yield tt

    def has_triple_term(self, subject, predicate, object) -> bool:
        """Return True if a TripleTerm with these exact components exists in the graph."""
        if self._is_native:
            tt = TripleTerm(subject, predicate, object)
            return any(True for _ in self.triples((None, None, tt)))
        key = TripleTerm(subject, predicate, object)._key()
        return key in self._tt_registry

    def qname_term(self, node) -> str:
        """Prefixed n3 form of any term - URIRef, BNode, Literal, TripleTerm,
        or DirLangString.

        Unlike the inherited qname(), which only accepts a URI and raises on
        anything else, this dispatches on whatever it's given: a caller
        iterating over triples() often doesn't know in advance whether a
        given position holds a plain node or a TripleTerm, and qname_term()
        does the right thing either way without an isinstance check.
        """
        return node.n3(self.namespace_manager)

    def remove_reification(self, reifier, triple_term=None) -> StarLayerGraph:
        """Remove the rdf:reifies triple(s) for the given reifier, and
        return this graph - matching add_reification() and every other
        mutating method on this class (added 2026-10-04, this used to
        return None, the same asymmetry add_reification() had before it).

        With triple_term=None (default), removes every rdf:reifies triple
        the reifier has. Pass a specific triple_term (a TripleTerm, or a
        plain (s, p, o) tuple) to unlink only that one reifier<->triple
        pair, leaving any other triple(s) the same reifier reifies - and
        all of its annotation triples - untouched. Delegates to remove()
        (rather than duplicating its native/non-native and TripleTerm
        encoding handling here), so a triple_term that isn't registered in
        this graph is a safe no-op, same as remove() everywhere else.
        """
        return self.remove((reifier, RDF_REIFIES, triple_term))

    def parse(self, source=None, publicID=None, format=None,
              location=None, file=None, data=None, **kwargs) -> StarLayerGraph:
        """Parse RDF data into the graph.

        format='turtle12'  — Turtle 1.2 with <<( )>>, {| |}, ~ reifier syntax
        format='nt12'      — N-Triples 1.2 with <<( )>> triple terms
        format='nq12'      — N-Quads 1.2
        format='trig12'    — TriG 1.2
        format='trix12'    — TriX 1.2 XML
        format='rdfxml12'  — RDF/XML 1.2 with rdf:parseType="Triple" and
                             rdf:annotation/rdf:annotationNodeID (RDF 1.2 XML Syntax)
        format='manchester' (alias 'omn') — OWL 2 Manchester Syntax; see
                             starlayer.graph.parsers.manchester_parser's module
                             docstring for the supported subset
        format='n3'/'n3-12'/'text/n3' — aliased straight to 'turtle12'.
                             Only the plain-triples subset N3 shares with
                             Turtle is supported, not real N3 — a formula
                             ('{ }'), a '=>' rule, or a '?x' variable raises
                             Turtle12SyntaxError, since those aren't Turtle
                             syntax at all. The input must be valid
                             Turtle/Turtle 1.2.

        'nq12'/'trig12'/'trix12' above, and the bare (RDF 1.1) 'nquads'/
        'trig'/'trix' handled by the fallback below, all name quad-shaped
        (multi-graph-capable) formats being parsed into a single graph.
        A document resolving to at most one distinct graph - including the
        trivial case of everything being in the default graph - parses
        normally (any explicit graph name is simply dropped). A document
        genuinely spanning two or more distinct graphs raises
        MultipleGraphsError instead of silently flattening them together -
        use StarLayerDataset.parse() to keep each graph separate.

        All other formats delegate to rdflib (no triple-term support) -
        except bare 'nquads'/'trig'/'trix', which this project still routes
        through the single-vs-multiple-graph check above (plain rdflib
        delegation would otherwise silently yield zero triples the moment
        any named graph appears at all, even just one).
        """
        if format in ('n3', 'n3-12', 'text/n3'):
            format = 'turtle12'
        if format in ('turtle12', 'longturtle12', 'nt12', 'nq12', 'trig12', 'trix12', 'rdfxml12', 'manchester', 'omn'):
            text = _read_source_text(source=source, file=file, location=location, data=data)

            if format in ('turtle12', 'longturtle12'):
                from starlayer.graph.parsers.turtle_parser import (
                    StarLayerTurtleParser,
                    _skolemize_encoding,
                )
                # Seed relative-IRI resolution (including a bare "<>") from
                # publicID, falling back to location's own resolved file://
                # IRI when publicID isn't given - matching the convention
                # rdflib's own parsers follow (publicID defaults to the
                # source's own IRI). Previously nothing was passed here, so
                # a document with no @base of its own (the common case) had
                # no working relative-IRI resolution regardless of publicID -
                # see StarLayerTurtleParser.parse()'s base parameter.
                effective_base = publicID
                if effective_base is None and location is not None:
                    from pathlib import Path
                    effective_base = Path(location).resolve().as_uri()
                raw = StarLayerTurtleParser().parse(text, base=effective_base)
                processed = _skolemize_encoding(raw)
                for prefix, ns in processed.namespaces():
                    self.bind(prefix, ns)
                if self._is_native:
                    # _skolemize_encoding's output is the rdf-1.1 backend's
                    # own tt:HASH on-disk encoding - correct to write
                    # verbatim via super().add() below, but wrong for the
                    # native backend, which needs real TripleTerm objects
                    # routed through self.add() (-> _native_add()) so they
                    # get written using the backend's real <<( )>> syntax,
                    # not the flat encoding-triple fragments.
                    from starlayer.graph.parsers.turtle_parser import (
                        decode_tt_encoded_triples,
                    )
                    self._native_add_many(list(decode_tt_encoded_triples(processed)))
                else:
                    if self._needs_bnode_skolemization:
                        # Each triple here goes to the store via its own
                        # separate super().add() call (no batching, unlike
                        # _native_add_many()) - so even without a
                        # BNode-hostile store, a real blank node repeated
                        # across several of these triples wouldn't reliably
                        # keep its shared identity once each call becomes a
                        # separate SPARQL Update request. Skolemizing (a
                        # pure function of the BNode's own label) sidesteps
                        # that entirely: the same Python BNode object always
                        # maps to the same URI, correctly recurring across
                        # calls, not just within one.
                        from starlayer.graph.backends.native import skolemize_bnode
                        processed = [
                            (
                                skolemize_bnode(s) if isinstance(s, BNode) else s,
                                p,
                                skolemize_bnode(o) if isinstance(o, BNode) else o,
                            )
                            for s, p, o in processed
                        ]
                    for triple in processed:
                        super().add(triple)
                    self._build_registry_from_store()
                    self._on_mutated()

                from starlayer.graph.model.conformance import (
                    check_version_conformance_for_graphs,
                )
                check_version_conformance_for_graphs(
                    getattr(raw, '_declared_version', None), [self], context='Turtle document',
                )

            elif format in ('nt12', 'nq12'):
                from starlayer.graph.parsers.ntriples12 import extract_version_directive
                if format == 'nt12':
                    from starlayer.graph.parsers.ntriples12 import parse_ntriples12
                    triples = parse_ntriples12(text)
                else:
                    from starlayer.graph.parsers.ntriples12 import parse_nquads12
                    quads = parse_nquads12(text)
                    _check_single_graph({g for _s, _p, _o, g in quads}, format='nq12')
                    # at most one distinct graph, per the check above - drop
                    # the (uniform) graph component
                    triples = [(s, p, o) for s, p, o, _g in quads]
                if self._is_native:
                    self._native_add_many(list(triples))
                else:
                    for triple in triples:
                        self.add(triple)

                from starlayer.graph.model.conformance import (
                    check_version_conformance_for_graphs,
                )
                check_version_conformance_for_graphs(
                    extract_version_directive(text), [self], context='N-Triples/N-Quads document',
                )

            elif format == 'trig12':
                from starlayer.graph.parsers.trig12 import (
                    extract_version_directive as _trig_version,
                )
                from starlayer.graph.parsers.trig12 import parse_trig12_named
                named = parse_trig12_named(text)
                # exclude prefix/VERSION-only chunks (no actual triples) -
                # e.g. a leading chunk before the first GRAPH block that
                # has only PREFIX/VERSION directives still shows up as a
                # (None, [], namespaces) entry here, but names no graph
                _check_single_graph(
                    {gid for gid, chunk_triples, _ns in named if chunk_triples}, format='trig12',
                )
                # at most one distinct graph, per the check above - flatten
                # the (single) graph's chunks together
                triples = [t for _gid, chunk_triples, _ns in named for t in chunk_triples]
                if self._is_native:
                    # Same rationale as the turtle12/longturtle12 branch
                    # above - parse_trig12_named() returns the rdf-1.1
                    # backend's own tt:HASH encoding, which needs decoding
                    # back into real TripleTerm objects before self.add()
                    # can write them using the native backend's real
                    # <<( )>> syntax.
                    from starlayer.graph.parsers.turtle_parser import (
                        decode_tt_encoded_triples,
                    )
                    skolemized = Graph()
                    for triple in triples:
                        skolemized.add(triple)
                    self._native_add_many(list(decode_tt_encoded_triples(skolemized)))
                else:
                    for triple in triples:
                        super().add(triple)
                    self._build_registry_from_store()
                    self._on_mutated()

                from starlayer.graph.model.conformance import (
                    check_version_conformance_for_graphs,
                )
                check_version_conformance_for_graphs(_trig_version(text), [self], context='TriG document')

            elif format == 'trix12':
                from starlayer.graph.parsers.trix12 import parse_trix12_named
                named = parse_trix12_named(text)
                _check_single_graph({gid for gid, _triples in named}, format='trix12')
                # at most one distinct graph, per the check above - flatten
                # the (single) graph's chunks together
                triples = [t for _gid, chunk_triples in named for t in chunk_triples]
                if self._is_native:
                    self._native_add_many(list(triples))
                else:
                    for triple in triples:
                        self.add(triple)

            elif format == 'rdfxml12':
                from starlayer.graph.parsers.rdfxml12 import (
                    extract_version_directive as _rx_version,
                )
                from starlayer.graph.parsers.rdfxml12 import parse_rdfxml12
                triples = parse_rdfxml12(text)
                if self._is_native:
                    self._native_add_many(list(triples))
                else:
                    for triple in triples:
                        self.add(triple)

                from starlayer.graph.model.conformance import (
                    check_version_conformance_for_graphs,
                )
                check_version_conformance_for_graphs(_rx_version(text), [self], context='RDF/XML document')

            elif format in ('manchester', 'omn'):
                from starlayer.graph.parsers.manchester_parser import parse_manchester
                effective_base = publicID
                if effective_base is None and location is not None:
                    from pathlib import Path
                    effective_base = Path(location).resolve().as_uri()
                triples = parse_manchester(text, base=effective_base)
                if self._is_native:
                    self._native_add_many(list(triples))
                else:
                    for triple in triples:
                        self.add(triple)

            return self
        if format in ('nquads', 'trig', 'trix'):
            # Plain rdflib delegation (what every other format below still
            # gets) would silently yield zero triples the moment any named
            # graph appears at all in one of these - a non-context-aware
            # Graph's own parser plugins can't place quads anywhere - so
            # this project routes through a real Dataset first instead,
            # purely to see the per-graph structure before deciding whether
            # to flatten (at most one distinct graph) or raise (two or
            # more) - the same rule nq12/trig12/trix12 enforce above.
            text = _read_source_text(source=source, file=file, location=location, data=data)
            from rdflib import Dataset
            ds = Dataset()
            ds.parse(data=text, format=format)
            non_empty = [ctx for ctx in ds.graphs() if len(ctx) > 0]
            _check_single_graph({ctx.identifier for ctx in non_empty}, format=format)
            for ctx in non_empty:
                for triple in ctx:
                    self.add(triple)
            return self
        return super().parse(source=source, publicID=publicID, format=format,
                             location=location, file=file, data=data, **kwargs)

    def query(self, query_object, processor='sparql', result='sparql',
              initNs=None, initBindings=None, use_store_provided=True,
              entailment=None, infer: str = 'changed',
              engine: str = 'hermit', timeout=_OWL_DL_TIMEOUT_DEFAULT, **kwargs) -> Result:
        """Execute a SPARQL query. Triple-term patterns are rewritten to SPARQL 1.1.

        The rewritten query runs against a plain Graph view of the same store so
        that encoding triples (rdf:subject/predicate/object on tt: URIRefs) are
        visible to the SPARQL engine. TripleTerm/tuple values in ``initBindings``
        are encoded to their internal tt:HASH URIRef first, the same way every
        other read path in this class resolves triple terms before matching
        against the store. Results are post-processed to restore tt:HASH
        URIRefs back to TripleTerm objects.

        For the native rdf-1.2 backend the query is routed through
        starlayer.graph.backends.native.native_query, which uses the endpoint's
        own triple-term syntax.

        entailment -- ``None`` (default, plain simple entailment),
            ``ENTAILMENT.RDF`` (query-time RDF entailment rewrite, no data
            copy - see ``starlayer.sparql.entailment_rdf``; not available
            against the native backend), ``ENTAILMENT.RDFS`` (query-time
            RDFS rewrite, no data copy - see
            ``starlayer.sparql.entailment_rdfs``; not available against the
            native backend), ``ENTAILMENT["OWL-RDF-Based"]`` (queries the
            live union of ``self`` and a small cached delta of just its
            newly-entailed triples - see ``infer(mode="delta")`` and the
            ``infer`` parameter below), ``ENTAILMENT["OWL-Direct"]`` (OWL 2
            DL's counterpart to ``ENTAILMENT["OWL-RDF-Based"]`` - the
            SPARQL Entailment Regimes spec's own name for OWL-Direct-
            Semantics-backed querying: same live-union-with-a-cached-delta
            design, but the delta comes from
            ``infer(profile=ENTAILMENT["OWL-Direct"], engine=...,
            mode="delta")`` - see the ``engine`` parameter below and
            ``infer()``'s own docstring for what each engine actually
            guarantees. **Read this before reaching for it**: genuine
            tableau DL reasoning is routinely orders of magnitude slower
            than ``owlrl``'s forward-chaining - an empirical ~20-individual
            constraint-satisfaction example (``docs/guides/
            05e-owl-dl-reasoning.ipynb`` section 4) took several seconds
            per ``infer()`` call, and a ~30-individual version of the same
            problem didn't finish within 60 seconds. ``infer="changed"``
            bounds how *often* this cost is paid (once per mutation, same
            protection ``ENTAILMENT["OWL-RDF-Based"]`` gets), not how
            *expensive* any single recomputation is - unlike
            ``ENTAILMENT["OWL-RDF-Based"]``, which is always fast
            regardless. For a latency-sensitive caller, materialize once
            ahead of time via ``infer(profile=ENTAILMENT["OWL-Direct"],
            mode="in-place"/"full")`` instead and query the result
            plainly; reserve ``entailment=ENTAILMENT["OWL-Direct"]`` for
            when live freshness is genuinely worth this cost. Raises
            ``starlayer.graph.graph.owl_dl.InconsistentOntologyError``
            uncaught if ``self``'s data is logically inconsistent, unlike
            ``ENTAILMENT["OWL-RDF-Based"]``'s partial/silent consistency
            checking - same contract
            ``infer(profile=ENTAILMENT["OWL-Direct"])`` already has
            directly), or ``"native"`` (only legal with
            ``backend='rdf-1.2'`` - a self-documenting label for "this
            endpoint is expected to handle entailment itself"; changes no
            behavior on that path, since ``native_query()`` already sends
            text straight through unmodified regardless of this value -
            see ``docs/fuseki-reasoning-setup.md`` for actually
            configuring an endpoint that makes it meaningful). A per-call
            choice, not a graph-level setting - the same graph can be
            queried with different (or no) entailment on different calls.
        infer -- only consulted when ``entailment=ENTAILMENT["OWL-RDF-Based"]``
            or ``entailment=ENTAILMENT["OWL-Direct"]``; ignored otherwise.
            Controls reuse of ``self``'s cached entailment delta
            (``self._owl_rl_cache`` for ``ENTAILMENT["OWL-RDF-Based"]``;
            ``self._owl_dl_cache[engine]`` for ``ENTAILMENT["OWL-Direct"]``,
            keyed per engine so switching ``engine=`` between calls
            doesn't invalidate the other engine's cached slot) against
            ``self._mutation_generation``
            (bumped by ``_on_mutated()`` on every real edit to ``self`` -
            see ``VALID_INFER_MODES``): ``"changed"`` (default) recomputes
            only if ``self`` was edited since the cache was last computed;
            ``"always"`` ignores the cache and always recomputes;
            ``"cached"`` reuses whatever is cached if anything is, computing
            only when there's no cache yet. When ``self`` is non-native and
            has no triple terms, ``self``'s own data is always queried live
            regardless of this setting - only the entailed delta is subject
            to it. When ``self`` is native-backed or has triple terms, a
            snapshot of ``self``'s own data is refreshed on this same
            cadence too (see the ``ENTAILMENT["OWL-RDF-Based"]`` branch's
            own comment for why).
        engine -- only meaningful when ``entailment=ENTAILMENT["OWL-Direct"]``;
            passing a non-default value with any other ``entailment=``
            raises ``ValueError`` (fail loudly rather than let a caller
            believe it silently did something for a different regime).
            ``"hermit"`` (default) or ``"rustdl"`` - identical choice and
            tradeoffs as ``infer(profile=ENTAILMENT["OWL-Direct"],
            engine=...)``'s own parameter; see that method's docstring
            rather than repeating it here.
        timeout -- only meaningful when ``entailment=ENTAILMENT["OWL-Direct"]``;
            same validation and identical meaning as
            ``infer(profile=ENTAILMENT["OWL-Direct"], timeout=...)``'s own
            parameter (wall-clock budget in seconds for the underlying
            reasoning call, default ``_timeout.DEFAULT_TIMEOUT_SECONDS``
            (120s), ``None`` disables it) - see that method's docstring
            rather than repeating it here.
        """
        if entailment not in VALID_ENTAILMENTS:
            raise NotImplementedError(
                f"entailment must be one of {sorted(e for e in VALID_ENTAILMENTS if e)}, "
                f"got {entailment!r}."
            )
        if entailment != ENTAILMENT["OWL-Direct"] and engine != 'hermit':
            raise ValueError(
                f"engine={engine!r} is only meaningful for entailment=ENTAILMENT['OWL-Direct'] "
                f"(got entailment={entailment!r}) - omit engine= otherwise."
            )
        if entailment != ENTAILMENT["OWL-Direct"] and timeout != _OWL_DL_TIMEOUT_DEFAULT:
            raise ValueError(
                f"timeout={timeout!r} is only meaningful for entailment=ENTAILMENT['OWL-Direct'] "
                f"(got entailment={entailment!r}) - omit timeout= otherwise."
            )
        if entailment == 'native' and not self._is_native:
            raise NotImplementedError(
                "entailment='native' requires backend='rdf-1.2' - it delegates entailment "
                "to the endpoint itself, and the default backend has no endpoint to delegate "
                "to. Use entailment=ENTAILMENT.RDFS or ENTAILMENT['OWL-RDF-Based'] instead."
            )
        if entailment == ENTAILMENT["OWL-RDF-Based"]:
            if infer not in VALID_INFER_MODES:
                raise ValueError(f"infer must be one of {sorted(VALID_INFER_MODES)}, got {infer!r}")
            # Fast path (self is non-native and has no triple terms): self's
            # own data can be queried live (a zero-copy store view) unioned
            # with a small cached delta, since there's nothing a triple term
            # could encode differently between the two. Fallback path
            # (native backend, or self has triple terms): a live store view
            # of self isn't representation-safe to union with delta - self's
            # own tt:HASH-encoded triple-term data and delta's decomposed
            # (owlrl-compatible) reification-fragment encoding are two
            # different things - so both sides of the union come from the
            # same _decompose() call instead, refreshed together on the same
            # infer=-governed cadence as delta (matching today's shipped
            # cost profile: one full read of self per cache recompute, not
            # per query call). See Phase D of the entailment-regime plan for
            # the full reasoning.
            fast_path = not self._is_native and not self._tt_registry
            cached = self._owl_rl_cache
            stale = cached is None or (infer == 'changed' and cached[1] != self._mutation_generation)
            if infer == 'always' or stale:
                if fast_path:
                    delta = self.infer(profile=ENTAILMENT["OWL-RDF-Based"], mode='delta')
                else:
                    self_view, delta = self._infer_before_and_delta(frozenset({ENTAILMENT["OWL-RDF-Based"]}))
                    self._owl_rl_snapshot_cache = self_view
                self._owl_rl_cache = (delta, self._mutation_generation)
            else:
                delta = cached[0]
                if not fast_path:
                    self_view = self._owl_rl_snapshot_cache
            if fast_path:
                self_view = Graph(store=self.store, identifier=self.identifier)

            union = _UnionForQuery([self_view, delta])
            effective_ns = initNs if initNs else dict(self.namespaces())
            prepared = query_object
            if isinstance(query_object, str):
                from starlayer.graph.query.query_cache import prepare_query_cached
                prepared = prepare_query_cached(
                    self._prepared_query_cache, query_object, effective_ns, kwargs.get('base'),
                    entailment=None,
                )
            init_bindings = self._encode_init_bindings(initBindings) if fast_path else initBindings
            r = union.query(
                prepared, processor=processor, result=result,
                initNs=initNs, initBindings=init_bindings,
                use_store_provided=use_store_provided, **kwargs,
            )
            if r.type == 'SELECT':
                restore_select_bindings(r, self._restore)
            elif r.type == 'CONSTRUCT':
                from starlayer.graph.model.encoding import inject_missing_tt_encoding
                inject_missing_tt_encoding(r.graph, self._restore)
                r.graph = StarLayerGraph.from_rdflib(r.graph)
            return r

        if entailment == ENTAILMENT["OWL-Direct"]:
            if infer not in VALID_INFER_MODES:
                raise ValueError(f"infer must be one of {sorted(VALID_INFER_MODES)}, got {infer!r}")
            # Same fast-path/fallback-path split as
            # entailment=ENTAILMENT["OWL-RDF-Based"] above (see that
            # branch's own comment for the full reasoning) - the only real
            # difference is which cache dict is read/written (keyed by
            # engine here, since HermiT's and RustDL's delta genuinely
            # differ for the same graph - see self._owl_dl_cache's own
            # comment in __init__) and which underlying call computes
            # delta (ENTAILMENT["OWL-Direct"] instead of
            # ENTAILMENT["OWL-RDF-Based"], carrying engine= through
            # either way).
            fast_path = not self._is_native and not self._tt_registry
            cached = self._owl_dl_cache.get(engine)
            stale = cached is None or (infer == 'changed' and cached[1] != self._mutation_generation)
            if infer == 'always' or stale:
                if fast_path:
                    delta = self.infer(profile=ENTAILMENT["OWL-Direct"], mode='delta', engine=engine, timeout=timeout)
                else:
                    self_view, delta = self._before_and_delta_for(frozenset({ENTAILMENT["OWL-Direct"]}), engine, timeout)
                    self._owl_dl_snapshot_cache[engine] = self_view
                self._owl_dl_cache[engine] = (delta, self._mutation_generation)
            else:
                delta = cached[0]
                if not fast_path:
                    self_view = self._owl_dl_snapshot_cache[engine]
            if fast_path:
                self_view = Graph(store=self.store, identifier=self.identifier)

            union = _UnionForQuery([self_view, delta])
            effective_ns = initNs if initNs else dict(self.namespaces())
            prepared = query_object
            if isinstance(query_object, str):
                from starlayer.graph.query.query_cache import prepare_query_cached
                prepared = prepare_query_cached(
                    self._prepared_query_cache, query_object, effective_ns, kwargs.get('base'),
                    entailment=None,
                )
            init_bindings = self._encode_init_bindings(initBindings) if fast_path else initBindings
            r = union.query(
                prepared, processor=processor, result=result,
                initNs=initNs, initBindings=init_bindings,
                use_store_provided=use_store_provided, **kwargs,
            )
            if r.type == 'SELECT':
                restore_select_bindings(r, self._restore)
            elif r.type == 'CONSTRUCT':
                from starlayer.graph.model.encoding import inject_missing_tt_encoding
                inject_missing_tt_encoding(r.graph, self._restore)
                r.graph = StarLayerGraph.from_rdflib(r.graph)
            return r

        if self._is_native:
            if entailment in (ENTAILMENT.RDF, ENTAILMENT.RDFS):
                raise NotImplementedError(
                    f"entailment={entailment!r} query-time rewriting is not wired into the "
                    "native (backend='rdf-1.2') query path yet - it only rewrites the default "
                    "(backend='rdf-1.1') in-memory/encoded path today. Use "
                    "entailment=ENTAILMENT['OWL-RDF-Based'] for a materialized closure "
                    "instead, which works regardless of backend."
                )
            from starlayer.graph.backends.native import native_query
            return native_query(
                self.store, self._backend, query_object, processor=processor, result=result,
                initNs=initNs, initBindings=initBindings,
                use_store_provided=use_store_provided, **kwargs,
            )

        # Rewrite SPARQL 1.2 TT patterns to SPARQL 1.1 encoding triple patterns
        # and parse the result, then let the SPARQL engine handle all matching
        # and joining. Cached (prepare_query_cached) on (query text, effective
        # namespaces, base) so repeated calls with the same query text and only
        # initBindings differing - exactly how pySHACL evaluates a SHACL-AF
        # rule/constraint once per focus node - don't redo the rewrite+parse
        # every time. The only post-processing step is _restore(), which
        # converts any tt:HASH URIRef that appears in a result row back into a
        # TripleTerm object.
        raw = Graph(store=self.store, identifier=self.identifier)
        for prefix, ns in self.namespaces():
            raw.bind(prefix, ns)
        pending_recipes = None
        pending_filters = None
        pending_pv = None
        from starlayer.graph.query.query_cache import store_accepts_prepared_query
        remote_only_store = not store_accepts_prepared_query(self.store)
        if isinstance(query_object, str):
            # Parses via starlayer.sparql's real grammar (prepare_query_12),
            # then lowers the 1.2 algebra to a plain SPARQL 1.1 one and
            # hands back an already-executable Query object - cached on
            # (query text, effective namespaces, base) so repeated calls
            # with the same query text don't redo the parse+lower work (see
            # query_cache.py's own module docstring for why that matters -
            # the pySHACL per-focus-node evaluation pattern). Correct for
            # a remote-only store too: falls through to the generalized
            # handling below, which serializes the resulting Query object
            # back to text (and strips any custom-function dependency the
            # remote engine wouldn't understand) before it ever reaches
            # that store.
            from starlayer.graph.query.query_cache import prepare_query_cached
            effective_ns = initNs if initNs else dict(self.namespaces())
            query_object = prepare_query_cached(
                self._prepared_query_cache, query_object, effective_ns, kwargs.get('base'),
                entailment=entailment,
            )

        # Generalized remote-store handling for a pre-built Query object -
        # whether it came from the string-parsing branch above, or was
        # handed to this method directly by a caller (e.g. starlayer.sparql's
        # own rdf11_to_query, or starlayer.graph.query.sparql_api.prepareQuery).
        # Some store implementations (rdflib's own SPARQLStore/
        # SPARQLUpdateStore, used for remote endpoints like Fuseki) only
        # accept a plain query string, not a pre-parsed Query object -
        # confirmed via real Fuseki testing (AssertionError in
        # sparqlstore.py) - so a string-only store would crash outright on
        # a non-str query_object without this. decompose_for_remote()
        # itself needs no changes to support this: it only inspects
        # query_object.algebra by structure/known-IRI matching, indifferent
        # to which pipeline produced the object (confirmed: the
        # custom-function IRIs starlayer.sparql's own lower_rdf11.py
        # produces - TT_HASH_FN etc. - are the literal same URIs
        # starlayer.graph's own query/custom_functions.py registers, both
        # deriving from starlayer.graph.model.encoding.TT_NS/DIRLANG_NS). Only SELECT gets the
        # decompose treatment (decompose_for_remote's own scope, see its
        # docstring); CONSTRUCT/ASK/DESCRIBE still get turned into text so
        # they at least reach the remote store, just without custom
        # function support there yet - a known, narrower gap than before
        # (nothing worked here at all previously), not a regression.
        #
        # Serializes via starlayer.sparql's own _AlgebraTranslator11, not
        # plain rdflib's translateAlgebra - confirmed (starlayer.sparql's
        # own CLAUDE.md, and reproduced directly via a real Fuseki HTTP 400)
        # that plain translateAlgebra has *zero* ConstructQuery handling at
        # all; _AlgebraTranslator11 is plain _AlgebraTranslator (already
        # patched here via algebra_translator_patches.py) plus exactly that
        # gap filled in, built for exactly this purpose - see its own
        # module docstring in lower_rdf11.py.
        if pending_recipes is None and not isinstance(query_object, str) and remote_only_store:
            from starlayer.sparql.lower_rdf11 import _AlgebraTranslator11
            recipes, filters = [], []
            if query_object.algebra.name == 'SelectQuery':
                from starlayer.graph.query.remote_decompose import decompose_for_remote
                original_pv = list(query_object.algebra.p.PV)
                recipes, filters = decompose_for_remote(query_object)
            else:
                # decompose_for_remote is SelectQuery-only (its own scope,
                # see its docstring) - a ConstructQuery/AskQuery/
                # DescribeQuery whose template or pattern still depends on
                # a custom function (e.g. a CONSTRUCT template minting a
                # fresh triple term - confirmed via a real Fuseki run: the
                # BIND computing the term's hash silently leaves it
                # unbound, and CONSTRUCT's own rule for a template triple
                # with an unbound term drops it - no error, no data) has no
                # decomposition support yet. Fail loudly instead of
                # silently sending an unusable query and getting back
                # incomplete/wrong results.
                from starlayer.graph.query.remote_decompose import (
                    contains_custom_function_call,
                )
                if contains_custom_function_call(query_object.algebra):
                    raise NotImplementedError(
                        f"{query_object.algebra.name} depends on a starlayer.graph custom SPARQL "
                        "function (e.g. constructing a fresh triple term or dirLangString) "
                        "and cannot run against this remote store yet - only SELECT is "
                        "supported for this case so far. See remote_decompose.py."
                    )
            query_object = _AlgebraTranslator11(query_object).translateAlgebra()
            if recipes or filters:
                pending_recipes = recipes
                pending_filters = filters
                pending_pv = original_pv

        init_bindings = self._encode_init_bindings(initBindings)
        r = raw.query(query_object, processor=processor, result=result,
                      initNs=initNs, initBindings=init_bindings,
                      use_store_provided=use_store_provided, **kwargs)
        if pending_recipes is not None:
            from starlayer.graph.query.remote_decompose import (
                evaluate_recipes_locally,
                row_passes_filters,
            )
            new_bindings = []
            for row in r.bindings:
                merged = evaluate_recipes_locally(pending_recipes, row, raw)
                if not row_passes_filters(pending_filters, merged, raw):
                    continue
                new_bindings.append({var: merged.get(var) for var in pending_pv})
            r.bindings = new_bindings
            r.vars = pending_pv
        if r.type == 'SELECT':
            restore_select_bindings(r, self._restore)
        elif r.type == 'CONSTRUCT':
            from starlayer.graph.model.encoding import inject_missing_tt_encoding
            inject_missing_tt_encoding(r.graph, self._restore)
            r.graph = StarLayerGraph.from_rdflib(r.graph)
        return r

    def update(self, update_object, processor='sparql',
              initNs=None, initBindings=None, use_store_provided=True, **kwargs) -> None:
        """Execute a SPARQL UPDATE.

        For the native rdf-1.2 backend the update is forwarded to the endpoint
        via HTTP unchanged (see starlayer.graph.backends.native.native_update).

        Otherwise, SPARQL 1.2 text is parsed via starlayer.sparql's real
        grammar (prepare_update_12), then lowered to a plain SPARQL 1.1
        algebra (tt:HASH encoding) and serialized back to real SPARQL 1.1
        Update text - every shape (triple-term WHERE patterns, ground
        triple terms in INSERT/DELETE DATA, triple terms in INSERT/DELETE
        templates) is handled natively by that lowering, no post-processing
        needed here.

        Text, not a pre-parsed ``Update`` object: ``rdflib.Graph.update()``
        hands off to ``self.store.update()`` first when the store defines
        one (``use_store_provided``, true by default) - fine for the
        default in-memory store, whose generic SPARQL Update processor
        accepts either, but ``SPARQLUpdateStore.update()`` (a remote
        Oxigraph/Fuseki endpoint, say) hard-``assert``s on a plain string,
        since all it can do is POST text over HTTP. Confirmed live: handing
        it the lowered ``Update`` object instead raised ``AssertionError``
        for *any* update text against a remote store in this (default)
        backend mode - untested before, since the only existing live
        coverage of ``StarLayerGraph.update()`` against a remote store used
        the native backend, a different code path entirely (see
        ``tests/integration/test_oxigraph_backend.py::TestOxigraphGraphUpdate``).
        """
        if self._is_native:
            from starlayer.graph.backends.native import native_update
            native_update(self.store, self._backend, update_object)
            self._on_mutated()
            return None
        if isinstance(update_object, str):
            from starlayer.sparql.lower_rdf11 import rdf11_update_to_sparql11_text, update_to_rdf11
            from starlayer.sparql.parse12 import prepare_update_12
            prepared_12 = prepare_update_12(update_object, base=kwargs.get('base'), initNs=initNs)
            rdf_graph, root = update_to_rdf11(prepared_12)
            update_object = rdf11_update_to_sparql11_text(rdf_graph, root)
        raw = Graph(store=self.store, identifier=self.identifier)
        for prefix, ns in self.namespaces():
            raw.bind(prefix, ns)
        raw.update(update_object, processor=processor,
                   initNs=initNs, initBindings=initBindings,
                   use_store_provided=use_store_provided)
        self._build_registry_from_store()
        self._on_mutated()
        return None

    def serialize(self, destination=None, format='turtle12', **kwargs) -> str | bytes | StarLayerGraph:
        """Serialize the graph.

        format='turtle12'     — Turtle 1.2 with <<( )>> triple terms (default)
        format='longturtle12' — Turtle 1.2, one triple per line (no grouping)
        format='nt12'         — N-Triples 1.2 with <<( )>> triple terms
        format='nq12'         — N-Quads 1.2 (graph name from self.identifier)
        format='trig12'       — TriG 1.2 (GRAPH block wrapper around Turtle 1.2)
        format='trix12'       — TriX 1.2 XML (<graph> block with <triple> elements)
        format='manchester' (alias 'omn') — OWL 2 Manchester Syntax; see
                             starlayer.graph.serializers.manchester's module
                             docstring for the supported subset and known
                             round-tripping limitations
        format='n3'/'n3-12'/'text/n3' — aliased straight to 'turtle12'; only
                             the plain-triples subset N3 shares with Turtle
                             is supported, not real N3 (formulas, '=>' rules,
                             '?x' variables) - see parse()'s own note.
        All other formats (e.g. 'turtle', 'xml') delegate to rdflib using the
        internal tt:HASH encoding — triple terms appear as opaque URIRefs.
        """
        if format in ('n3', 'n3-12', 'text/n3'):
            format = 'turtle12'
        _RDF12_FORMATS = {'turtle12', 'longturtle12', 'nt12', 'nq12', 'trig12', 'trix12', 'rdfxml12', 'manchester', 'omn'}
        if format in _RDF12_FORMATS:
            if format == 'turtle12':
                from starlayer.graph.serializers.turtle12 import serialize_turtle12
                text = serialize_turtle12(self)
            elif format == 'longturtle12':
                from starlayer.graph.serializers.turtle12 import serialize_longturtle12
                text = serialize_longturtle12(self)
            elif format == 'nt12':
                from starlayer.graph.serializers.ntriples12 import serialize_ntriples12
                text = serialize_ntriples12(self)
            elif format == 'nq12':
                from starlayer.graph.serializers.ntriples12 import serialize_nquads12
                text = serialize_nquads12(self)
            elif format == 'trig12':
                from starlayer.graph.serializers.trig12 import serialize_trig12
                text = serialize_trig12(self)
            elif format == 'trix12':
                from starlayer.graph.serializers.trix12 import serialize_trix12
                text = serialize_trix12(self)
            elif format == 'rdfxml12':
                from starlayer.graph.serializers.rdfxml12 import serialize_rdfxml12
                text = serialize_rdfxml12(self)
            elif format in ('manchester', 'omn'):
                from starlayer.graph.serializers.manchester import serialize_manchester
                text = serialize_manchester(self)
            if destination is not None:
                with open(destination, 'w', encoding='utf-8') as f:
                    f.write(text)
                # self, not the destination path - matches rdflib's own
                # Graph.serialize() contract (returns self when writing to a
                # destination, the text only when destination is None) -
                # fixed 2026-10-04, this used to return the path instead.
                return self
            return text
        # For 1.1 formats: de-skolemize internal URIRefs to blank nodes so
        # rdflib's serializer produces clean output without exposing tt:/rr: URIs.
        deskolemized = self._deskolemize_to_graph()
        if format in ('nquads', 'trix'):
            # Unlike TrigSerializer (which falls back to treating a
            # non-context-aware store as its own single context - see
            # rdflib.plugins.serializers.trig.TrigSerializer.__init__), the
            # NQuads/TriX serializer plugins just raise "...only makes
            # sense for context-aware stores" for one. Added 2026-10-04 so
            # all six dataset formats behave consistently on serialize()
            # (matching the consistent parse() rule added the same day):
            # wrap the de-skolemized graph as the one context of a real
            # Dataset, giving these two formats the same single-graph
            # fallback trig already gets for free.
            from rdflib import Dataset
            ds = Dataset()
            ctx = ds.graph(deskolemized.identifier)
            for triple in deskolemized:
                ctx.add(triple)
            for prefix, ns in deskolemized.namespaces():
                ds.bind(prefix, ns)
            result = ds.serialize(destination=destination, format=format, **kwargs)
        else:
            result = deskolemized.serialize(destination=destination, format=format, **kwargs)
        # self, not the throwaway de-skolemized Graph - same rdflib-matching
        # contract as above; fixed 2026-10-04, this used to return that
        # unrelated internal Graph instead of self when destination was given.
        return self if destination is not None else result

    def _deskolemize_to_graph(self) -> Graph:
        """Return a plain rdflib.Graph with internal tt: URIRefs replaced by
        BNodes. Anonymous reifiers are already ordinary BNodes (see
        starlayer.graph.parsers.turtle_parser._skolemize_encoding) and need no
        substitution here.

        Used by non-RDF12 serializers (format='turtle', 'xml', etc, via
        serialize()) so triple terms appear as blank-node reifications
        rather than opaque content-addressed URIRefs.

        The output graph is constructed with `identifier=self.identifier`
        (both branches below) - a real bug until fixed 2026-10-04: a bare
        `Graph()` defaults to a fresh random BNode identifier, so
        `serialize(format='trig')` on a StarLayerGraph with a real URIRef
        identifier was silently emitting a *different*, randomly-generated
        graph name instead of the caller's own - confirmed against plain
        rdflib.Graph(identifier=...).serialize(format='trig'), which gets
        this right, so StarLayer's own wrapping was the regression, not an
        rdflib limitation.

        Native branch: `raw = Graph(store=self.store, identifier=self.identifier)`
        below (a *plain* rdflib.Graph wrapping the same store, deliberately
        bypassing StarLayerGraph.triples()) is exactly wrong for native -
        it hits SPARQLStore.triples()'s own SPARQL JSON parsing, which (per
        starlayer.graph.backends.native's own module docstring) rdflib 7.x cannot
        parse a "type":"triple" binding from at all. Uses self.triples()
        (the native-dispatching, TripleTerm-restoring public method) plus
        _unfold_native_triple_terms() instead, matching how
        StarLayerGraph.isomorphic() already handles this same asymmetry.
        """
        from starlayer.graph.model.encoding import TT_NS

        if self._is_native:
            out = Graph(identifier=self.identifier)
            for prefix, ns in self.namespaces():
                out.bind(prefix, ns)
            for s, p, o in _unfold_native_triple_terms(self):
                out.add((s, p, o))
            return out

        _INTERNAL_NS = (TT_NS, SL_NS)

        bnode_map: dict = {}

        def _sub(node):
            if isinstance(node, URIRef):
                s = str(node)
                if s.startswith(TT_NS):
                    if node not in bnode_map:
                        bnode_map[node] = BNode()
                    return bnode_map[node]
            return node

        raw = Graph(store=self.store, identifier=self.identifier)
        out = Graph(identifier=self.identifier)
        for prefix, ns in self.namespaces():
            if not str(ns).startswith(_INTERNAL_NS):
                out.bind(prefix, ns)
        for s, p, o in raw:
            out.add((_sub(s), _sub(p), _sub(o)))
        return out

    def print(self, format: str = 'turtle12', out=None) -> None:
        """Print the graph to stdout. Defaults to turtle12 so TripleTerms display correctly."""
        import sys
        print(self.serialize(format=format), file=out or sys.stdout, flush=True)

    def cbd(self, resource, *, target_graph=None, include_reifications=True) -> StarLayerGraph:
        """Concise Bounded Description. Defaults target_graph to a new StarLayerGraph.

        Raises TypeError if target_graph is a plain rdflib.Graph — it cannot store
        TripleTerms that may appear in the CBD results.
        """
        if target_graph is None:
            target_graph = StarLayerGraph()
        elif not isinstance(target_graph, StarLayerGraph):
            raise TypeError(
                f"cbd() target_graph must be a StarLayerGraph, not {type(target_graph).__name__}. "
                "A plain rdflib.Graph cannot store TripleTerms."
            )
        return super().cbd(resource, target_graph=target_graph, include_reifications=include_reifications)

    def skolemize(self, new_graph=None, bnode=None, authority=None, basepath=None) -> StarLayerGraph:
        """Convert blank nodes to skolem IRIs. Defaults new_graph to a new StarLayerGraph.

        Without this override, rdflib's own inherited skolemize() hardcodes a
        plain rdflib.Graph() as the default target - confirmed a real bug,
        same class as cbd()'s own (see that method's docstring): it crashes
        with AssertionError the moment self contains a real TripleTerm, since
        plain Graph.add() rejects it as "not an rdflib term".

        Raises TypeError if new_graph is a plain rdflib.Graph — it cannot store
        TripleTerms that may appear in self.
        """
        if new_graph is None:
            new_graph = StarLayerGraph()
        elif not isinstance(new_graph, StarLayerGraph):
            raise TypeError(
                f"skolemize() new_graph must be a StarLayerGraph, not {type(new_graph).__name__}. "
                "A plain rdflib.Graph cannot store TripleTerms."
            )
        return super().skolemize(new_graph=new_graph, bnode=bnode, authority=authority, basepath=basepath)

    def de_skolemize(self, new_graph=None, uriref=None) -> StarLayerGraph:
        """Convert skolem IRIs back to blank nodes. Defaults new_graph to a new StarLayerGraph.

        Same bug class and same fix as skolemize() above - see its docstring.
        """
        if new_graph is None:
            new_graph = StarLayerGraph()
        elif not isinstance(new_graph, StarLayerGraph):
            raise TypeError(
                f"de_skolemize() new_graph must be a StarLayerGraph, not {type(new_graph).__name__}. "
                "A plain rdflib.Graph cannot store TripleTerms."
            )
        return super().de_skolemize(new_graph=new_graph, uriref=uriref)

    def isomorphic(self, other) -> bool:
        """Graph isomorphism, aware of TripleTerms.

        Overridden because the inherited rdflib.Graph.isomorphic() is (a) a
        crude approximation — see that method's own docstring: "only an
        approximation ... very well could be a false positive" — and (b)
        blind to BNodes embedded inside a TripleTerm's content-address,
        which would otherwise compare as different, unrelated ground terms
        across separately parsed graphs that are actually the same shape
        (e.g. <<( _:x :p :o )>> vs <<( _:other :p :o )>>, both otherwise
        identical). Delegates to rdflib.compare's real canonical-labeling
        algorithm after unfolding each graph's TripleTerms back to native
        BNode-based reification (_unfold_tt_encoding), which mirrors the
        parser's own intermediate form before content-address skolemization
        (see turtle_parser._skolemize_encoding) — so a BNode nested inside a
        triple term is treated as relabelable, the same as any other BNode,
        rather than baked into an opaque tt:HASH URIRef.

        other need not be a StarLayerGraph — the unfold works directly off
        raw triples, degrading to a no-op (plain rdflib isomorphism) for a
        graph with no tt: content at all.
        """
        from rdflib.compare import isomorphic as _rdflib_isomorphic
        return _rdflib_isomorphic(_unfold_tt_encoding(self), _unfold_tt_encoding(other))

    @staticmethod
    def _resolve_owlrl_semantics(regimes: frozenset):
        """Import owlrl and resolve `regimes` (infer()'s own "which
        ruleset(s)" choice, a frozenset of one or more ENTAILMENT.* regime
        IRIs - see entailment_regimes.py) to the owlrl semantics class it
        names. Shared by _infer_before_and_delta() and infer()'s own
        mode="in-place" branch, so both draw from one place for what
        counts as a valid combination.

        ENTAILMENT.RDFS **alone** uses a locally defined subclass that
        suppresses owlrl's own RDFSClosure.RDFS_Semantics.one_time_rules()
        (2026-10-08, found via a real downstream regression, not assumed)
        - that specific method implements a "hidden sameAs" rule: for
        every pair of literals *anywhere* in the graph that compare equal
        by Python value despite different lexical form/datatype
        (confirmed live: Literal(True) and Literal(1), since Python's own
        `1 == True`), it duplicates every triple using one to also use the
        other, across any unrelated subjects/predicates. This is exactly
        the wrinkle pySHACL's own CustomRDFSSemantics
        (pyshacl/inference/custom_rdfs_closure.py) overrides the same
        method to avoid, with the same one-line reasoning in its own
        source comment: "breaks some SHACL validation tests." That
        suppression isn't imported from pyshacl here, to avoid a layering
        violation (this is starlayer.graph's own general-purpose RDFS
        reasoning, not SHACL-specific plumbing, and pyshacl is an optional
        dependency of a different, downstream package) - a small local
        equivalent instead, applied for *every* ENTAILMENT.RDFS-alone
        consumer (sh:entailment, inference=, and any direct
        infer(profile=ENTAILMENT.RDFS) caller), not just a pySHACL-compat
        shim.

        **The combined RDFS+OWL-RL regime does NOT need this override -
        confirmed by reading owlrl's own source, not assumed by analogy.**
        owlrl.RDFS_OWLRL_Semantics.one_time_rules() is a completely
        different method body (full_binding_triples plus
        OWLRL_Semantics.one_time_rules(self)) that never calls the
        literal-comparison logic above at all - stock owlrl already
        rewrote this method for the combined class, for unrelated reasons,
        and it was never exposed to the hidden-sameAs bug in the first
        place. Confirmed directly against pySHACL's own
        CustomRDFSOWLRLSemantics too: despite the "Custom" name, its own
        one_time_rules() is copied verbatim from stock
        RDFS_OWLRL_Semantics's, not overridden to a no-op the way
        CustomRDFSSemantics's is - pySHACL itself only ever needed the
        suppression for the RDFS-alone case. An earlier version of this
        fix wrongly no-op'd the combined class's one_time_rules() too, by
        analogy rather than by checking - caught immediately via
        test_matches_owlrl_run_directly, which failed with dozens of
        missing legitimate OWL-RL axioms (e.g. xsd:byte rdf:type
        owl:Thing) once that override silently ate them.
        """
        try:
            import owlrl
        except ImportError as exc:
            raise ImportError(
                "StarLayerGraph.infer() requires the optional 'owlrl' dependency - "
                "install via `pip install starlayer.graph[reasoning]` (or `pip install owlrl` directly)."
            ) from exc

        class _NoHiddenSameAsRDFSSemantics(owlrl.RDFSClosure.RDFS_Semantics):
            def one_time_rules(self) -> None:
                pass

        profiles = {
            frozenset({ENTAILMENT.RDFS}): _NoHiddenSameAsRDFSSemantics,
            frozenset({ENTAILMENT["OWL-RDF-Based"]}): owlrl.OWLRL_Semantics,
            # Genuinely distinct from ENTAILMENT["OWL-RDF-Based"] alone, not
            # an alias - confirmed live: OWLRL_Semantics.rules() never calls
            # into RDFS_Semantics.rules(), so that regime alone omits e.g.
            # universal rdfs:Resource typing and several rdfs:Datatype-
            # related entailments that RDFS_OWLRL_Semantics's combined rule
            # set adds - declaring both regimes together gets this combined
            # class, matching sh:entailment's own "declare more than one,
            # combine into one pass" model. Plain, unmodified owlrl class -
            # see this method's own docstring for why the hidden-sameAs
            # override doesn't apply here.
            frozenset({ENTAILMENT.RDFS, ENTAILMENT["OWL-RDF-Based"]}): owlrl.RDFS_OWLRL_Semantics,
        }
        semantics = profiles.get(regimes)
        if semantics is None:
            raise ValueError(
                f"Unsupported entailment regime combination {sorted(regimes)!r}; "
                f"expected one of {[sorted(k) for k in profiles]}"
            )
        return semantics

    def _infer_before_and_delta(self, regimes: frozenset):
        """Run entailment against self exactly once, returning both the
        original data (decomposed - see starlayer.graph.compare._decompose())
        and just the newly-entailed triples, as two separate plain
        rdflib.Graph objects. Shared by infer() (mode="full" is their
        union, mode="delta" is just the second one) and by query()'s
        entailment=ENTAILMENT["OWL-RDF-Based"] fallback path (see that
        branch's own comment for why it needs both views, not just the
        delta, for graphs where a live store view of self isn't
        representation-safe to union with a separately-computed delta).

        Safe to diff by plain triple membership (no BNode-identity surprises
        - see infer()'s own docstring on why this differs from comparing two
        *separate* _decompose() calls): ``before`` and ``expanded`` share the
        exact same triple/BNode objects up to the point ``expanded`` is
        mutated, since ``expanded`` is built by re-adding ``before``'s own
        triples verbatim, not by decomposing self a second time.
        """
        semantics = self._resolve_owlrl_semantics(regimes)
        import owlrl

        from starlayer.graph.compare import _decompose
        before = _decompose(self)
        expanded = Graph()
        for t in before:
            expanded.add(t)
        owlrl.DeductiveClosure(semantics).expand(expanded)
        before_set = set(before)
        delta = Graph()
        for t in expanded:
            if t not in before_set:
                delta.add(t)
        return before, delta

    def _before_and_delta_for(self, regimes: frozenset, engine: str = 'hermit', timeout=_OWL_DL_TIMEOUT_DEFAULT):
        """Dispatch to the right reasoning engine for `regimes` (a
        frozenset of one or more ENTAILMENT.* regime IRIs). The
        owlrl-backed combinations (RDFS/OWL-RDF-Based/both together) go
        through _infer_before_and_delta() above; {ENTAILMENT["OWL-Direct"]}
        goes through one of two genuinely different tableau-DL bridges -
        owl_dl.py (HermiT, via owlready2, engine="hermit", the default) or
        owl_dl_rustdl.py (RustDL, engine="rustdl") - chosen by `engine`,
        which is otherwise meaningless (anything but OWL-Direct never even
        looks at it). `timeout` is likewise only meaningful for
        OWL-Direct - see infer()'s own docstring; `None` unambiguously
        means "disable the timeout" here (not "use the engine's own
        default" - the default *is* `_OWL_DL_TIMEOUT_DEFAULT`, a real
        value, not a sentinel needing translation).
        """
        if regimes == frozenset({ENTAILMENT["OWL-Direct"]}):
            if engine == 'hermit':
                from starlayer.graph.graph.owl_dl import classify_owl_dl
                return classify_owl_dl(self, timeout=timeout)
            if engine == 'rustdl':
                from starlayer.graph.graph.owl_dl_rustdl import classify_owl_dl_rustdl
                return classify_owl_dl_rustdl(self, timeout=timeout)
            raise ValueError(f"Unsupported engine {engine!r}; expected one of ['hermit', 'rustdl']")
        if regimes == frozenset({ENTAILMENT.RDF}):
            return self._infer_rdf_before_and_delta()
        return self._infer_before_and_delta(regimes)

    def _infer_rdf_before_and_delta(self):
        """Compute RDF entailment (RDF 1.2 Semantics) natively - no
        ``owlrl``/reasoner dependency at all, unlike every other regime
        this class supports, since this one rule is small enough to just
        implement directly:

        - **rdfD2**: for every distinct predicate ``aaa`` used anywhere in
          self, entail ``aaa rdf:type rdf:Property``.
        - **RDF axiomatic triples**: a small fixed set
          (``rdf:type``/``subject``/``predicate``/``object``/``reifies``/
          ``first``/``rest``/``value`` ``rdf:type rdf:Property``;
          ``rdf:nil rdf:type rdf:List``; ``rdf:_N rdf:type rdf:Property``
          for each container index ``N`` actually used) - only
          instantiated for terms genuinely present in self, never the
          full (infinite, for ``rdf:_N``) schema unconditionally.

        **Deliberately deferred, not implemented here**: rdfD1/rdfD1a
        (datatype literal value-space well-typing - e.g. asserting a
        blank node typed by a literal's own datatype IRI). Lower
        practical value for SHACL validation than the two rules above,
        and a materially different kind of check (datatype value-space
        membership, not plain graph-pattern matching) - a real v1 scope
        reduction, not an oversight. Revisit if a real caller needs it.

        Returns ``(before, delta)`` in the same two-value shape
        ``_infer_before_and_delta()``/the OWL-DL bridges return, so
        ``infer()``'s ``mode=`` dispatch can treat every regime
        uniformly - callers conventionally discard ``before`` (see every
        ``_before, delta = self._before_and_delta_for(...)`` call site),
        so this builds ``delta`` directly against ``self`` rather than a
        separate copy; no external reasoner is invoked here, so there's
        no triple-term crash risk ``_decompose()`` exists to avoid for
        the owlrl-backed regimes, and nothing needs decomposing first.
        """
        delta = Graph()

        def _maybe_add_property_type(term) -> None:
            candidate = (term, RDF.type, RDF.Property)
            if candidate not in self:
                delta.add(candidate)

        seen_predicates: set = set()
        all_terms: set = set()
        for s, p, o in self:
            all_terms.add(s)
            all_terms.add(p)
            all_terms.add(o)
            if p not in seen_predicates:
                seen_predicates.add(p)
                _maybe_add_property_type(p)

        for term in (
            RDF.type, RDF.subject, RDF.predicate, RDF.object, RDF_REIFIES,
            RDF.first, RDF.rest, RDF.value,
        ):
            if term in all_terms:
                _maybe_add_property_type(term)
        if RDF.nil in all_terms:
            candidate = (RDF.nil, RDF.type, RDF.List)
            if candidate not in self:
                delta.add(candidate)
        _rdf_ns = str(RDF)
        for term in all_terms:
            if isinstance(term, URIRef) and str(term).startswith(_rdf_ns + '_'):
                if str(term)[len(_rdf_ns) + 1:].isdigit():
                    _maybe_add_property_type(term)

        return self, delta

    def infer(self, profile=ENTAILMENT.RDFS, *, mode: str = 'full', target_graph=None,
              engine: str = 'hermit', timeout=_OWL_DL_TIMEOUT_DEFAULT) -> StarLayerGraph:
        """Materialize an RDFS/OWL-RL entailment closure - by default into a
        NEW graph, never mutating self (mode="in-place" is the deliberate
        exception - see below). Requires the optional ``owlrl`` dependency
        (``pip install starlayer.graph[reasoning]``).

        profile -- one real entailment regime IRI (``ENTAILMENT.RDF``,
            ``ENTAILMENT.RDFS``, ``ENTAILMENT["OWL-RDF-Based"]``,
            ``ENTAILMENT["OWL-Direct"]``) or an iterable of more than one
            to combine them into a single
            pass (e.g. ``{ENTAILMENT.RDFS, ENTAILMENT["OWL-RDF-Based"]}``
            - genuinely more than ``ENTAILMENT["OWL-RDF-Based"]`` alone:
            e.g. universal rdfs:Resource typing and several
            rdfs:Datatype-related entailments are only present when RDFS's
            own rules run alongside OWL-RL's, confirmed live against owlrl
            directly - see _resolve_owlrl_semantics()). See
            ``starlayer.graph.graph.entailment_regimes``'s own module
            docstring for what each IRI means and which combinations are
            actually supported. ``ENTAILMENT["OWL-Direct"]`` alone selects
            full OWL 2 DL reasoning - a genuinely different computational
            model, tableau-based rather than forward-chaining rules, so it
            can derive disjunctive entailments owlrl structurally cannot,
            e.g. C subClassOf (A or B), not-A(x) |= B(x). Raises
            owl_dl.InconsistentOntologyError, not a silent triple, if
            self's data is logically inconsistent - unlike the owlrl-backed
            regimes, whose consistency checking is partial and never
            raises. See `engine` below for which actual reasoner runs this.
            ``ENTAILMENT.RDF`` alone is implemented natively (no ``owlrl``
            dependency, no reasoner at all) - just rdfD2 (every predicate
            used is entailed ``rdf:type rdf:Property``) plus the small
            fixed set of RDF axiomatic triples actually relevant to self's
            data. Datatype literal value-space well-typing (rdfD1/rdfD1a)
            is a deliberate v1 scope reduction, not built - see
            ``_infer_rdf_before_and_delta()``'s own docstring.
        engine -- only meaningful for profile=ENTAILMENT["OWL-Direct"] (any
            other profile combined with a non-default engine raises
            ValueError - fail loudly rather than let a caller believe it
            silently did something for an owlrl-backed profile). Picks
            which of two
            genuinely different reasoners runs the tableau reasoning
            above - neither is a strict replacement for the other, so this
            is a real tradeoff to make per call, not an implementation
            detail:
            - "hermit" (default) - owlready2 + Java HermiT. Sound *and*
              complete for all of OWL 2 DL (SROIQ) - the strongest
              guarantee either engine offers. Needs the optional
              `starlayer.graph[hermit]` extra (`owlready2`) AND a real Java
              runtime reachable on PATH (owlready2 bundles HermiT as a
              Java program) - see owl_dl.py's own module docstring for
              both actionable RuntimeErrors this raises if either is
              missing.
            - "rustdl" - a pure-Rust reasoner (no JVM at all). Needs only
              the optional `starlayer.graph[rustdl]` extra (`rustdl`) - see
              owl_dl_rustdl.py's own module docstring for the actionable
              RuntimeError this raises if it's missing. Sound, but only
              empirically near-complete on full SROIQ, not provably
              complete (RustDL's own docs: complete by construction only
              on the EL/Horn fragment) - a real, permanent gap against
              "hermit"'s guarantee, not a temporary bug. Concretely: it
              correctly derives disjunctive *class* entailments (confirmed
              live), but its property-assertion materialization is
              documented as a "sound under-approximation (no
              anonymous-witness or disjunctive-derived edges)" - this
              project no longer has a live, re-verifiable example of that
              specific behavior (the one previously used for it is now a
              confirmed hang instead, caught pre-flight - see
              owl_dl_rustdl.py's own module docstring, points 2 and 4, and
              `CLAUDE.md`'s "Tracking rustdl's own evolving capabilities"
              section). Also raises `rustdl.UnsupportedAxiomError` outright
              (not silently) for `HasKey:` axioms, role chains longer than
              2, and one specific confirmed-hang idiom detected pre-flight
              - all three real constructs, not hypothetical.
        timeout -- only meaningful for profile=ENTAILMENT["OWL-Direct"]
            (same ValueError contract as engine= above for any other
            profile). Wall-clock
            budget in seconds for the actual reasoner call, shared by both
            engines - defense-in-depth against a hang *neither* engine has
            a known, structurally-detectable pattern for yet (RustDL's one
            *known* hang pattern is already caught separately, fast and
            pre-flight - see `engine=` above; this timeout is the backstop
            for everything else). Default `_timeout.DEFAULT_TIMEOUT_SECONDS`
            (120s); pass `None` to disable entirely (wait indefinitely -
            the pre-this-feature behavior). Implemented as a real
            subprocess/process-group kill, not a cooperative
            cancellation - see `starlayer.graph/graph/_timeout.py`'s own
            module docstring for why that's the only mechanism that
            reliably works against an opaque, uninterruptible reasoner
            call (a JVM subprocess for "hermit", an in-process native
            PyO3 call for "rustdl") - a raised
            `_timeout.ReasoningTimeoutError` is guaranteed to leave no
            orphaned JVM/native process still running behind it.
        mode -- all three ultimately reach the same closure (self's own data
            plus everything entailed from it) - this chooses where that ends
            up and how much of it comes back as a distinct value. "full"
            (default) returns a NEW graph with the original triples plus
            everything newly entailed. "delta" returns a NEW graph with only
            the newly-entailed triples, none of the originals - the smaller
            artifact query()'s entailment=ENTAILMENT["OWL-RDF-Based"] caches and queries as a
            live union with self, rather than caching a full closure copy.
            "in-place" adds just the newly-entailed triples into self
            directly (self already has the originals) and returns self -
            works for any self, including native and triple-term-bearing
            ones (see the triple-term-fidelity paragraph below for the one
            narrow caveat it still doesn't avoid). target_graph must not be
            given together with it (raises ValueError - mutating self has no
            separate destination). See VALID_INFER_RETURN_MODES.
        target_graph -- only meaningful for mode="full"/"delta"; defaults
            to a new StarLayerGraph, or if given, entailed triples are added
            to it (never cleared first) — must be a StarLayerGraph, not a
            plain rdflib.Graph, same restriction as cbd() and for the same
            reason: consistency with the rest of this class's API.

        Any triple term in self is decomposed into its synthetic
        blank-node reification form (the same one rdfc10_hash()/
        isomorphic() use — see starlayer.graph.compare._decompose()) purely
        so owlrl can run without crashing: its RDFS closure asserts "x
        rdf:type rdfs:Resource" for every term seen anywhere in a triple,
        including subject position, and a triple term is never legal there
        under RDF 1.2 — confirmed live, owlrl crashes with this class's own
        "triple terms are not permitted in subject position" guard
        otherwise (see add()). That decomposition never reaches the
        returned graph for mode="full"/"delta", though: self's own
        triples are copied in as-is (real TripleTerm objects intact, for a
        non-native self), and only the *newly-entailed* portion (mode=
        "delta"'s content, also included in mode="full") can still
        contain a decomposed reification fragment instead of a real
        TripleTerm - and only for a derived fact that isn't itself
        expressible with one. That's not a gap this implementation chooses
        to leave open; it's structural: a rule like rdfs4a/4b that types
        *every* term as rdfs:Resource inherently wants to put a triple term
        in subject position, which RDF 1.2 never permits for any triple,
        entailed or asserted - there is no legal real-TripleTerm form of
        that fact to recover. Nothing rewires the delta's synthetic
        blank node back to the real triple term self's own copied-in
        triples use, either - they're unrelated objects in the output
        graph, not the same node re-described two ways.

        owlrl has no truth maintenance: retracting a fact from self later
        does not retract anything this call already entailed from it.
        Re-run infer() from the original facts after any edit, rather than
        trying to patch a previous call's output.

        For a native (backend='rdf-1.2') self, reading "self's own data"
        (via plain iteration, same as _decompose()/for t in self) is scoped
        to self.identifier — GRAPH <self.identifier> { ... } — unless
        self.identifier is exactly rdflib.graph.DATASET_DEFAULT_GRAPH_ID
        (see _native_scoped()). This is unrelated to query()/update(), which
        send text straight through unscoped. A native StarLayerGraph
        constructed with no explicit identifier= now defaults to
        DATASET_DEFAULT_GRAPH_ID automatically (see __init__), so the
        common case already agrees with query()/update() by construction.
        The one remaining case this doesn't cover: a caller who explicitly
        passes a *different*, non-default identifier= that has no matching
        named graph on the endpoint - infer() then correctly sees an empty
        graph, same as any SPARQL query would against a real but
        currently-empty named graph. That's expected behavior for a named
        graph with no data yet, not a footgun - nothing to work around.

        mode="in-place" only ever adds the delta into self directly - never
        a re-decomposed copy of self's own data - so it can't crash the way
        calling owlrl.DeductiveClosure(...).expand(self) directly would (the
        crash this whole decomposition step exists to avoid in the first
        place). It inherits the same narrow leftover caveat as mode=
        "full"/"delta" above, with one difference worth being explicit
        about: for those two, a stray decomposed reification fragment lands
        in a disposable copy; for mode="in-place", it lands directly in the
        graph you're still working with, since there's no separate copy to
        contain it.
        """
        if mode not in VALID_INFER_RETURN_MODES:
            raise ValueError(f"mode must be one of {sorted(VALID_INFER_RETURN_MODES)}, got {mode!r}")
        # str check, not URIRef - URIRef is itself a str subclass, and a
        # bare non-URIRef str (e.g. a leftover old 'rdfs' string keyword)
        # must also be treated as one scalar value, not iterated character
        # by character - iterating it silently produces a nonsensical
        # regime set ({'r', 'd', 'f', 's'}) instead of a clear rejection.
        regimes = frozenset({profile}) if isinstance(profile, str) else frozenset(profile)
        if not regimes:
            raise ValueError("profile must name at least one entailment regime IRI.")
        unsupported = regimes - SUPPORTED_REGIMES
        if unsupported:
            message = (
                f"Unsupported entailment regime(s) {sorted(unsupported)!r} - "
                f"expected a combination of {sorted(SUPPORTED_REGIMES)!r}."
            )
            if ENTAILMENT.D in unsupported:
                message += (
                    " ENTAILMENT.D (D-Entailment) is a recognized regime IRI "
                    "but not implemented; see docs/future_enhancements.md."
                )
            raise ValueError(message)
        if regimes != frozenset({ENTAILMENT["OWL-Direct"]}) and engine != 'hermit':
            raise ValueError(
                f"engine={engine!r} is only meaningful for profile=ENTAILMENT['OWL-Direct'] "
                f"(got profile={sorted(regimes)!r}) - omit engine= for owlrl-backed profiles."
            )
        if regimes != frozenset({ENTAILMENT["OWL-Direct"]}) and timeout != _OWL_DL_TIMEOUT_DEFAULT:
            raise ValueError(
                f"timeout={timeout!r} is only meaningful for profile=ENTAILMENT['OWL-Direct'] "
                f"(got profile={sorted(regimes)!r}) - omit timeout= for owlrl-backed profiles."
            )

        if mode == 'in-place':
            if target_graph is not None:
                raise ValueError(
                    "target_graph is meaningless with mode='in-place' - it mutates self directly."
                )
            # Adds only the delta - self's own triples are already there,
            # untouched (_infer_before_and_delta reasons over a decomposed
            # *copy*, never self itself), so this can't crash on a triple
            # term the way calling owlrl.DeductiveClosure(...).expand(self)
            # directly would. delta's own content is always plain terms (no
            # real TripleTerm ever appears in it - see
            # _infer_before_and_delta's own docstring), so both add() and
            # _native_add_many() below accept it unconditionally.
            _before, delta = self._before_and_delta_for(regimes, engine, timeout)
            if self._is_native:
                self._native_add_many(list(delta))
            else:
                for t in delta:
                    self.add(t)
            self._on_mutated()
            return self

        if target_graph is None:
            target_graph = StarLayerGraph()
            for prefix, ns in self.namespaces():
                target_graph.bind(prefix, ns)
        elif not isinstance(target_graph, StarLayerGraph):
            raise TypeError(
                f"infer() target_graph must be a StarLayerGraph, not {type(target_graph).__name__}. "
                "A plain rdflib.Graph cannot store TripleTerms."
            )

        _before, delta = self._before_and_delta_for(regimes, engine, timeout)
        if mode == 'full':
            # self's own triples, not _before - _before is decomposed (a
            # synthetic reification fragment stands in for any triple term)
            # purely so owlrl could run without crashing; nothing requires
            # keeping the *output* in that form too. Reading self directly
            # restores real TripleTerm objects for a non-native self (see
            # triples()) - the decomposed form only still leaks through in
            # `delta`, for a newly-entailed fact that isn't itself
            # expressible with a real triple term (see below).
            for t in self:
                target_graph.add(t)
        for t in delta:
            target_graph.add(t)
        return target_graph

    def derive_shape(self, template_shape=None, *, ignored_properties=None,
                      use_default_ignored_properties: bool = True) -> StarLayerGraph:
        """Infer a SHACL shape from self's own data - one ``sh:NodeShape``
        per distinct ``rdf:type`` found (the simplest option: derive shapes
        from classes, never per-node or heuristic clustering), optionally
        reconciled against an existing template shape. Returns a
        ``StarLayerGraph`` (a real, standalone shapes graph) - wrapped via
        ``from_rdflib()`` for consistency with every other graph-returning
        method on this class, even though a derived shapes graph has no
        triple-term content of its own today.

        template_shape -- if omitted, every returned NodeShape is built
            fresh from self's own data. If given (any Graph, including a
            StarLayerGraph with genuine RDF 1.2 content), its own
            constraints are validated against self and, wherever a
            principled data-driven fix exists (cardinality, datatype,
            class, node kind including ``sh:TripleTerm``, numeric-range
            bounds, string length, ``sh:languageIn``, additive ``sh:in``
            widening), recomputed from the *true* current data rather than
            patched around a single violating value; constraint types with
            no generic fix (``sh:pattern``, cross-property comparisons like
            ``sh:equals``/``sh:lessThan``) are dropped with an ``rdfs:comment``
            note; opaque ``sh:sparql``-based/custom constraint components are
            left untouched, also with a note, since there's no way to know
            whether a failure there is a real data problem or a genuinely
            important check. Any predicate observed in self with no
            matching ``sh:property`` on the relevant shape, and any class
            present in self with no shape at all, get freshly-derived
            additions - "extend any new properties" generalized to the
            whole graph.
        ignored_properties -- extra predicates to exclude from every
            derived ``sh:NodeShape``'s candidate-property scan (union'd
            into ``sh:ignoredProperties``, alongside the resolved default
            list below and, unconditionally, ``rdf:type`` itself - required
            for any closed shape to conform, since ``sh:closed`` doesn't
            exempt ``rdf:type`` automatically). A template's own existing
            ``sh:ignoredProperties`` is always carried forward too.
        use_default_ignored_properties -- when true (default), also
            excludes ``shape_derivation.DEFAULT_IGNORED_PROPERTIES``
            (``rdfs:label``/``comment``, ``dcterms:created``/``modified``) -
            pass False to opt out of that built-in list entirely and rely
            only on ``ignored_properties=``.

        Every returned shape is closed (``sh:closed true``) and is
        self-checked to conform against self before being returned (a real
        assertion, not just documentation - see ``shape_derivation.py``).
        Goes through ``starlayer.shacl`` for all SHACL semantics, never bare
        ``pyshacl`` directly - self or template_shape may contain genuine
        RDF 1.2 content (triple terms) that only starlayer.shacl understands.
        """
        from starlayer.graph.graph.shape_derivation import derive_shape
        result = derive_shape(
            self, template_shape,
            ignored_properties=ignored_properties,
            use_default_ignored_properties=use_default_ignored_properties,
        )
        return StarLayerGraph.from_rdflib(result)

    @classmethod
    def from_rdflib(cls, source_graph) -> StarLayerGraph:
        """Wrap a plain rdflib.Graph (e.g., from StarLayerTurtleParser).

        Namespace bindings, triples, and the TripleTerm registry are all
        copied from the source graph.  If the source uses the intermediate
        BNode TT encoding (with sl:TripleTerm type markers), it is converted
        to content-addressed tt: URIRefs before copying.

        source_graph may also be a Dataset/ConjunctiveGraph: triples are read
        via its own ``.triples((None, None, None))``, which - like iterating
        the dataset directly - honors whatever ``default_union`` it was
        constructed with (rdflib default: False), so only its default graph
        is copied unless the caller explicitly opted into a unioned view.
        Named graphs are never selected implicitly; use
        ``dataset.get_context(identifier)`` first for a specific one.
        """
        from starlayer.graph.parsers.turtle_parser import _skolemize_encoding
        processed = _skolemize_encoding(source_graph)
        g = cls()
        for prefix, ns in processed.namespaces():
            g.bind(prefix, ns)
        for triple in processed:
            super(StarLayerGraph, g).add(triple)
        g._build_registry_from_store()
        return g
