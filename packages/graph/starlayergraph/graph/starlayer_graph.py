"""
starlayergraph.graph.starlayer_graph

StarLayerGraph — rdflib.Graph subclass with RDF 1.2 triple-term support.

A plain Python 3-tuple in any node position is treated as an inline TripleTerm.
All rdflib.Graph methods work identically; core traversal methods are extended
to accept and return TripleTerm objects while hiding the internal encoding.

Encoding: triple terms are stored as content-addressed URIRefs under TT_NS
(same triple content always maps to the same URI). The rdf:subject/predicate/object
triples that define the encoding are hidden from callers.
"""


from rdflib import BNode, Graph, Literal, URIRef
from rdflib.graph import DATASET_DEFAULT_GRAPH_ID
from rdflib.namespace import RDF

from starlayergraph.model.dirlangstring import (
    DirLangString,
    decode_dirlangstring,
    encode_dirlangstring,
)
from starlayergraph.model.encoding import ENCODING_PREDS as _ENCODING_PREDS
from starlayergraph.model.encoding import (
    TT_NS,
    lookup_tt_hash,
    restore_select_bindings,
    term_key,
    tt_hash,
)
from starlayergraph.model.triple import TripleTerm

SL_NS           = 'https://github.com/hidden-graph/starlayergraph/ns#'
SL_TRIPLE_TERM  = URIRef(SL_NS + 'TripleTerm')   # kept for export / backward compat
SL_REIFICATION  = URIRef(SL_NS + 'Reification')  # kept for export / backward compat
RDF_REIFIES     = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')

# Valid backend mode identifiers
VALID_BACKENDS = frozenset({'rdf-1.1', 'rdf-1.2'})

# rdf:TripleTerm type URI — emitted by the JSON-LD 1.2 serializer; treated as
# internal encoding so it is never surfaced through triples() / __len__ etc.
_RDF_TRIPLE_TERM = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#TripleTerm'

# Unbound reference to Graph.triples — used to bypass our override safely
_raw_triples = Graph.triples


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
        super().__init__(*args, **kwargs)
        self._backend = backend
        self._tt_registry: dict = {}   # canonical (s_key, p, o_key) -> URIRef (rdf-1.1 only)
        self._tt_nodes: dict = {}      # URIRef -> TripleTerm (rdf-1.1 only)
        self._invalidate_callback = None  # set by StarLayerDataset to clear raw query cache
        self._prepared_query_cache: dict = {}  # see starlayergraph.query.query_cache.prepare_query_cached

    @property
    def _is_native(self) -> bool:
        """True when using the native RDF 1.2 backend (no tt:HASH encoding)."""
        return self._backend == 'rdf-1.2'

    # ------------------------------------------------------------------
    # Native backend (rdf-1.2)
    # ------------------------------------------------------------------

    def _store_http(self) -> tuple:
        """Return (query_url, update_url, extra_headers) from the backing store.

        Raises RuntimeError if the store does not expose HTTP endpoints
        (e.g. in-memory stores). See starlayergraph.backends.native.resolve_store_http()
        - shared with StarLayerDataset's own native-backend dispatch, since a
        dataset's contexts all share the same underlying store.
        """
        from starlayergraph.backends.native import resolve_store_http
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
        from starlayergraph.backends.native import http_update, sparql_term
        from starlayergraph.model.triple import TripleTerm as _TT
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
        from starlayergraph.backends.native import http_update, sparql_term
        from starlayergraph.model.triple import TripleTerm as _TT

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
        if self._invalidate_callback:
            self._invalidate_callback()

    def _native_triples(self, triple):
        from starlayergraph.backends.native import http_ask, http_select, sparql_term
        q_url, _, hdrs = self._store_http()
        s, p, o = triple

        free = []
        def _slot(node, var: str) -> str:
            if node is None:
                free.append(var)
                return f'?{var}'
            return sparql_term(node)

        s_str = _slot(s, 's')
        p_str = _slot(p, 'p')
        o_str = _slot(o, 'o')
        pattern = f'{s_str} {p_str} {o_str} .'

        if not free:
            sparql = f'ASK {{ {self._native_scoped(pattern)} }}'
            if http_ask(q_url, sparql, hdrs):
                yield (s, p, o)
            return

        sel = ' '.join(f'?{v}' for v in free)
        sparql = f'SELECT {sel} WHERE {{ {self._native_scoped(pattern)} }}'
        vars_, bindings = http_select(q_url, sparql, hdrs)
        from rdflib.term import Variable
        for row in bindings:
            yield (
                row.get(Variable('s'), s) if 's' in free else s,
                row.get(Variable('p'), p) if 'p' in free else p,
                row.get(Variable('o'), o) if 'o' in free else o,
            )

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
                # anywhere (see starlayergraph.model.encoding's TT_HASH_FN memo).
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

    def open(self, configuration, create: bool = False):
        """Open a persistent store and rebuild the TripleTerm registry.

        Delegates to rdflib's Graph.open() then scans the store for any
        existing tt:HASH encoding triples so TripleTerms are immediately
        usable without a separate rebuild call.

        The store backend (e.g. Sleepycat, rdflib-sqlalchemy) is not a
        StarLayer dependency — install and configure it separately, then
        pass store='StoreName' to the constructor before calling open().

        Example::

            sg = StarLayerGraph(store='Sleepycat')
            sg.open('/path/to/db', create=True)
        """
        result = super().open(configuration, create)
        if not self._is_native:
            self._build_registry_from_store()
        return result

    def close(self, commit_pending_transaction: bool = False):
        """Close the underlying store, optionally committing pending writes."""
        self.store.close(commit_pending_transaction=commit_pending_transaction)

    # ------------------------------------------------------------------
    # Overridden rdflib.Graph methods
    # ------------------------------------------------------------------

    def add(self, triple):
        """Add a triple. A TripleTerm (or plain 3-tuple) in the object position is
        converted to its internal encoding automatically.

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
            if self._invalidate_callback:
                self._invalidate_callback()
            return
        super().add((self._coerce_tt(s), p, self._coerce_tt(obj)))
        if self._invalidate_callback:
            self._invalidate_callback()

    def addN(self, quads):
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
        if self._invalidate_callback:
            self._invalidate_callback()
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
        from starlayergraph.backends.native import http_update, sparql_term
        from starlayergraph.model.triple import TripleTerm as _TT
        _, u_url, hdrs = self._store_http()

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

    def remove(self, triple):
        """Remove a triple. Returns immediately if a TripleTerm in the pattern is not registered."""
        s, p, obj = triple
        if self._is_native:
            self._native_remove(s, p, obj)
            if self._invalidate_callback:
                self._invalidate_callback()
            return
        s_n, o_n = self._coerce_tt_read(s), self._coerce_tt_read(obj)
        if s_n is _TT_NOT_FOUND or o_n is _TT_NOT_FOUND:
            return
        super().remove((s_n, p, o_n))
        if self._invalidate_callback:
            self._invalidate_callback()

    def triples(self, triple):
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

        from starlayergraph.backends.native import http_select, sparql_term
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

    def triples_choices(self, triple, context=None):
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

        from starlayergraph.backends.native import http_select
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

    def add_reifier_annotation(self, predicate, obj, name=None):
        """Create a reifier node and add one annotation property to it.

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

    def add_reification(self, reifier, triple_term):
        """Add reifier rdf:reifies triple_term, making the node an official reifier."""
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
            return
        tt_uri = self._intern_tt(tt)
        super().add((reifier, RDF_REIFIES, tt_uri))

    def reifiers(self, TT=None, predicate=None, object=None):
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

    def reifications(self, s=None, p=None, o=None):
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

    def reifier_annotations(self, TT):
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

    def reified_triples(self, reifier):
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
                    yield tt

    def triple_terms(self, subject=None, predicate=None, object=None):
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
            yield tt

    def has_triple_term(self, subject, predicate, object):
        """Return True if a TripleTerm with these exact components exists in the graph."""
        if self._is_native:
            tt = TripleTerm(subject, predicate, object)
            return any(True for _ in self.triples((None, None, tt)))
        key = TripleTerm(subject, predicate, object)._key()
        return key in self._tt_registry

    def remove_reification(self, reifier):
        """Remove the rdf:reifies triple(s) for the given reifier."""
        if self._is_native:
            self.remove((reifier, RDF_REIFIES, None))
            return
        super().remove((reifier, RDF_REIFIES, None))

    def parse(self, source=None, publicID=None, format=None,
              location=None, file=None, data=None, **kwargs):
        """Parse RDF data into the graph.

        format='turtle12'  — Turtle 1.2 with <<( )>>, {| |}, ~ reifier syntax
        format='nt12'      — N-Triples 1.2 with <<( )>> triple terms
        format='nq12'      — N-Quads 1.2 (all named graphs merged into this graph)
        format='trig12'    — TriG 1.2 (all named graphs merged into this graph)
        format='trix12'    — TriX 1.2 XML (all named graphs merged into this graph)
        format='rdfxml12'  — RDF/XML 1.2 with rdf:parseType="Triple" and
                             rdf:annotation/rdf:annotationNodeID (RDF 1.2 XML Syntax)
        All other formats delegate to rdflib (no triple-term support).
        """
        if format in ('n3', 'n3-12', 'text/n3'):
            format = 'turtle12'
        if format in ('turtle12', 'longturtle12', 'nt12', 'nq12', 'trig12', 'trix12', 'rdfxml12', 'jsonld12'):
            text = _read_source_text(source=source, file=file, location=location, data=data)

            if format in ('turtle12', 'longturtle12'):
                from starlayergraph.parsers.turtle_parser import (
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
                    from starlayergraph.parsers.turtle_parser import (
                        decode_tt_encoded_triples,
                    )
                    self._native_add_many(list(decode_tt_encoded_triples(processed)))
                else:
                    for triple in processed:
                        super().add(triple)
                    self._build_registry_from_store()

                from starlayergraph.model.conformance import (
                    check_version_conformance_for_graphs,
                )
                check_version_conformance_for_graphs(
                    getattr(raw, '_declared_version', None), [self], context='Turtle document',
                )

            elif format in ('nt12', 'nq12'):
                from starlayergraph.parsers.ntriples12 import extract_version_directive
                if format == 'nt12':
                    from starlayergraph.parsers.ntriples12 import parse_ntriples12
                    triples = parse_ntriples12(text)
                else:
                    from starlayergraph.parsers.ntriples12 import parse_nquads12
                    # merge all named graphs: drop the graph component
                    triples = [(s, p, o) for s, p, o, _g in parse_nquads12(text)]
                if self._is_native:
                    self._native_add_many(list(triples))
                else:
                    for triple in triples:
                        self.add(triple)

                from starlayergraph.model.conformance import (
                    check_version_conformance_for_graphs,
                )
                check_version_conformance_for_graphs(
                    extract_version_directive(text), [self], context='N-Triples/N-Quads document',
                )

            elif format == 'trig12':
                from starlayergraph.parsers.trig12 import (
                    extract_version_directive as _trig_version,
                )
                from starlayergraph.parsers.trig12 import parse_trig12
                if self._is_native:
                    # Same rationale as the turtle12/longturtle12 branch
                    # above - parse_trig12() returns the rdf-1.1 backend's
                    # own tt:HASH encoding, which needs decoding back into
                    # real TripleTerm objects before self.add() can write
                    # them using the native backend's real <<( )>> syntax.
                    from starlayergraph.parsers.turtle_parser import (
                        decode_tt_encoded_triples,
                    )
                    skolemized = Graph()
                    for triple in parse_trig12(text):
                        skolemized.add(triple)
                    self._native_add_many(list(decode_tt_encoded_triples(skolemized)))
                else:
                    for triple in parse_trig12(text):
                        super().add(triple)
                    self._build_registry_from_store()

                from starlayergraph.model.conformance import (
                    check_version_conformance_for_graphs,
                )
                check_version_conformance_for_graphs(_trig_version(text), [self], context='TriG document')

            elif format == 'trix12':
                from starlayergraph.parsers.trix12 import parse_trix12
                triples = parse_trix12(text)
                if self._is_native:
                    self._native_add_many(list(triples))
                else:
                    for triple in triples:
                        self.add(triple)

            elif format == 'rdfxml12':
                from starlayergraph.parsers.rdfxml12 import (
                    extract_version_directive as _rx_version,
                )
                from starlayergraph.parsers.rdfxml12 import parse_rdfxml12
                triples = parse_rdfxml12(text)
                if self._is_native:
                    self._native_add_many(list(triples))
                else:
                    for triple in triples:
                        self.add(triple)

                from starlayergraph.model.conformance import (
                    check_version_conformance_for_graphs,
                )
                check_version_conformance_for_graphs(_rx_version(text), [self], context='RDF/XML document')

            elif format == 'jsonld12':
                if self._is_native:
                    # super().parse() below writes straight into self's own
                    # store via a bypassed rdflib-internal ConjunctiveGraph
                    # wrapper (rdflib's json-ld parser's own sink, not
                    # StarLayerGraph.add()) - fine for the rdf-1.1 backend,
                    # whose on-disk format *is* this tt:HASH encoding, but
                    # wrong here: it would write the raw rdf:subject/
                    # predicate/object encoding fragments directly into the
                    # live native store instead of the real <<( )>> syntax
                    # _native_add_many() produces, and _build_registry_from_
                    # store() is a no-op for a native backend (see its own
                    # docstring), so those fragments would never be
                    # reconstructed - they'd leak into every later read.
                    # Parsing into a throwaway plain Graph first and decoding
                    # it exactly like the trig12 branch above avoids that.
                    from starlayergraph.parsers.turtle_parser import (
                        decode_tt_encoded_triples,
                    )
                    temp = Graph()
                    temp.parse(data=text, format='json-ld')
                    # rdf:type rdf:TripleTerm marker triples (see
                    # starlayergraph/serializers/jsonld12.py's own docstring for
                    # this shape) aren't part of decode_tt_encoded_triples()'s
                    # contract the way turtle12/trig12's own intermediate
                    # sl:TripleTerm markers are (those are stripped by
                    # _skolemize_encoding before decode_tt_encoded_triples
                    # ever sees them) - left in place, decode_tt_encoded_
                    # triples() would yield them as ordinary data with a
                    # *reconstructed TripleTerm* as subject, which
                    # _native_add_many() then correctly rejects (triple terms
                    # aren't permitted in subject position).
                    for tt_uri in list(temp.subjects(RDF.type, URIRef(_RDF_TRIPLE_TERM))):
                        temp.remove((tt_uri, RDF.type, URIRef(_RDF_TRIPLE_TERM)))
                    self._native_add_many(list(decode_tt_encoded_triples(temp)))
                else:
                    # Delegate to rdflib's JSON-LD parser (handles @context
                    # expansion); the tt: encoding triples and rdf:type
                    # rdf:TripleTerm markers are loaded into the store, then
                    # _build_registry_from_store rebuilds the TripleTerm
                    # registry.  rdf:type rdf:TripleTerm is filtered by
                    # _is_encoding_triple so it never surfaces to callers.
                    super().parse(data=text, format='json-ld')
                    self._build_registry_from_store()

            return self
        return super().parse(source=source, publicID=publicID, format=format,
                             location=location, file=file, data=data, **kwargs)

    def query(self, query_object, processor='sparql', result='sparql',
              initNs=None, initBindings=None, use_store_provided=True, **kwargs):
        """Execute a SPARQL query. Triple-term patterns are rewritten to SPARQL 1.1.

        The rewritten query runs against a plain Graph view of the same store so
        that encoding triples (rdf:subject/predicate/object on tt: URIRefs) are
        visible to the SPARQL engine. TripleTerm/tuple values in ``initBindings``
        are encoded to their internal tt:HASH URIRef first, the same way every
        other read path in this class resolves triple terms before matching
        against the store. Results are post-processed to restore tt:HASH
        URIRefs back to TripleTerm objects.

        For the native rdf-1.2 backend the query is routed through
        starlayergraph.backends.native.native_query, which uses the endpoint's
        own triple-term syntax.
        """
        if self._is_native:
            from starlayergraph.backends.native import native_query
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
        from starlayergraph.query.query_cache import store_accepts_prepared_query
        remote_only_store = not store_accepts_prepared_query(self.store)
        if isinstance(query_object, str):
            # Parses via starsparql's real grammar (prepare_query_12),
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
            from starlayergraph.query.query_cache import prepare_query_cached
            effective_ns = initNs if initNs else dict(self.namespaces())
            query_object = prepare_query_cached(
                self._prepared_query_cache, query_object, effective_ns, kwargs.get('base')
            )

        # Generalized remote-store handling for a pre-built Query object -
        # whether it came from the string-parsing branch above, or was
        # handed to this method directly by a caller (e.g. starsparql's
        # own rdf11_to_query, or starlayergraph.query.sparql_api.prepareQuery).
        # Some store implementations (rdflib's own SPARQLStore/
        # SPARQLUpdateStore, used for remote endpoints like Fuseki) only
        # accept a plain query string, not a pre-parsed Query object -
        # confirmed via real Fuseki testing (AssertionError in
        # sparqlstore.py) - so a string-only store would crash outright on
        # a non-str query_object without this. decompose_for_remote()
        # itself needs no changes to support this: it only inspects
        # query_object.algebra by structure/known-IRI matching, indifferent
        # to which pipeline produced the object (confirmed: the
        # custom-function IRIs starsparql's own lower_rdf11.py
        # produces - TT_HASH_FN etc. - are the literal same URIs
        # starlayergraph's own query/custom_functions.py registers, both
        # deriving from starlayergraph.model.encoding.TT_NS/DIRLANG_NS). Only SELECT gets the
        # decompose treatment (decompose_for_remote's own scope, see its
        # docstring); CONSTRUCT/ASK/DESCRIBE still get turned into text so
        # they at least reach the remote store, just without custom
        # function support there yet - a known, narrower gap than before
        # (nothing worked here at all previously), not a regression.
        #
        # Serializes via starsparql's own _AlgebraTranslator11, not
        # plain rdflib's translateAlgebra - confirmed (starsparql's
        # own CLAUDE.md, and reproduced directly via a real Fuseki HTTP 400)
        # that plain translateAlgebra has *zero* ConstructQuery handling at
        # all; _AlgebraTranslator11 is plain _AlgebraTranslator (already
        # patched here via algebra_translator_patches.py) plus exactly that
        # gap filled in, built for exactly this purpose - see its own
        # module docstring in lower_rdf11.py.
        if pending_recipes is None and not isinstance(query_object, str) and remote_only_store:
            from starsparql.lower_rdf11 import _AlgebraTranslator11
            recipes, filters = [], []
            if query_object.algebra.name == 'SelectQuery':
                from starlayergraph.query.remote_decompose import decompose_for_remote
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
                from starlayergraph.query.remote_decompose import (
                    contains_custom_function_call,
                )
                if contains_custom_function_call(query_object.algebra):
                    raise NotImplementedError(
                        f"{query_object.algebra.name} depends on a starlayergraph custom SPARQL "
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
            from starlayergraph.query.remote_decompose import (
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
            from starlayergraph.model.encoding import inject_missing_tt_encoding
            inject_missing_tt_encoding(r.graph, self._restore)
            r.graph = StarLayerGraph.from_rdflib(r.graph)
        return r

    def update(self, update_object, processor='sparql',
              initNs=None, initBindings=None, use_store_provided=True, **kwargs):
        """Execute a SPARQL UPDATE.

        For the native rdf-1.2 backend the update is forwarded to the endpoint
        via HTTP unchanged (see starlayergraph.backends.native.native_update).

        Otherwise, SPARQL 1.2 text is parsed via starsparql's real
        grammar (prepare_update_12), then lowered to a plain SPARQL 1.1
        algebra (tt:HASH encoding) and handed to rdflib as an
        already-executable Update object - every shape (triple-term WHERE
        patterns, ground triple terms in INSERT/DELETE DATA, triple terms
        in INSERT/DELETE templates) is handled natively by that lowering,
        no post-processing needed here.
        """
        if self._is_native:
            from starlayergraph.backends.native import native_update
            native_update(self.store, self._backend, update_object)
            return None
        if isinstance(update_object, str):
            from starsparql.lower_rdf11 import rdf11_to_update, update_to_rdf11
            from starsparql.parse12 import prepare_update_12
            prepared_12 = prepare_update_12(update_object, base=kwargs.get('base'), initNs=initNs)
            rdf_graph, root = update_to_rdf11(prepared_12)
            update_object = rdf11_to_update(rdf_graph, root)
        raw = Graph(store=self.store, identifier=self.identifier)
        for prefix, ns in self.namespaces():
            raw.bind(prefix, ns)
        raw.update(update_object, processor=processor,
                   initNs=initNs, initBindings=initBindings,
                   use_store_provided=use_store_provided)
        self._build_registry_from_store()
        return None

    def serialize(self, destination=None, format='turtle12', **kwargs):
        """Serialize the graph.

        format='turtle12'     — Turtle 1.2 with <<( )>> triple terms (default)
        format='longturtle12' — Turtle 1.2, one triple per line (no grouping)
        format='nt12'         — N-Triples 1.2 with <<( )>> triple terms
        format='nq12'         — N-Quads 1.2 (graph name from self.identifier)
        format='trig12'       — TriG 1.2 (GRAPH block wrapper around Turtle 1.2)
        format='trix12'       — TriX 1.2 XML (<graph> block with <triple> elements)
        All other formats (e.g. 'turtle', 'xml') delegate to rdflib using the
        internal tt:HASH encoding — triple terms appear as opaque URIRefs.
        """
        _RDF12_FORMATS = {'turtle12', 'longturtle12', 'nt12', 'nq12', 'trig12', 'trix12', 'rdfxml12', 'jsonld12'}
        if format in _RDF12_FORMATS:
            if format == 'turtle12':
                from starlayergraph.serializers.turtle12 import serialize_turtle12
                text = serialize_turtle12(self)
            elif format == 'longturtle12':
                from starlayergraph.serializers.turtle12 import serialize_longturtle12
                text = serialize_longturtle12(self)
            elif format == 'nt12':
                from starlayergraph.serializers.ntriples12 import serialize_ntriples12
                text = serialize_ntriples12(self)
            elif format == 'nq12':
                from starlayergraph.serializers.ntriples12 import serialize_nquads12
                text = serialize_nquads12(self)
            elif format == 'trig12':
                from starlayergraph.serializers.trig12 import serialize_trig12
                text = serialize_trig12(self)
            elif format == 'trix12':
                from starlayergraph.serializers.trix12 import serialize_trix12
                text = serialize_trix12(self)
            elif format == 'rdfxml12':
                from starlayergraph.serializers.rdfxml12 import serialize_rdfxml12
                text = serialize_rdfxml12(self)
            elif format == 'jsonld12':
                from starlayergraph.serializers.jsonld12 import serialize_jsonld12
                text = serialize_jsonld12(self)
            if destination is not None:
                with open(destination, 'w', encoding='utf-8') as f:
                    f.write(text)
                return destination
            return text
        # For 1.1 formats: de-skolemize internal URIRefs to blank nodes so
        # rdflib's serializer produces clean output without exposing tt:/rr: URIs.
        return self._deskolemize_to_graph().serialize(destination=destination, format=format, **kwargs)

    def _deskolemize_to_graph(self) -> Graph:
        """Return a plain rdflib.Graph with internal tt:/rr: URIRefs (or, for
        a native backend, real TripleTerm values and rr: URIRefs) replaced
        by BNodes.

        Used by non-RDF12 serializers (format='turtle', 'xml', etc, via
        serialize()) so triple terms appear as blank-node reifications
        rather than opaque content-addressed URIRefs.

        Native branch: `raw = Graph(store=self.store, identifier=self.identifier)`
        below (a *plain* rdflib.Graph wrapping the same store, deliberately
        bypassing StarLayerGraph.triples()) is exactly wrong for native -
        it hits SPARQLStore.triples()'s own SPARQL JSON parsing, which (per
        starlayergraph.backends.native's own module docstring) rdflib 7.x cannot
        parse a "type":"triple" binding from at all. Uses self.triples()
        (the native-dispatching, TripleTerm-restoring public method) plus
        _unfold_native_triple_terms() instead, matching how
        StarLayerGraph.isomorphic() already handles this same asymmetry.
        """
        from starlayergraph.model.encoding import RR_NS, TT_NS

        if self._is_native:
            rr_map: dict = {}

            def _sub_rr(node):
                if isinstance(node, URIRef) and str(node).startswith(RR_NS):
                    if node not in rr_map:
                        rr_map[node] = BNode()
                    return rr_map[node]
                return node

            out = Graph()
            for prefix, ns in self.namespaces():
                if not str(ns).startswith(RR_NS):
                    out.bind(prefix, ns)
            for s, p, o in _unfold_native_triple_terms(self):
                out.add((_sub_rr(s), p, _sub_rr(o)))
            return out

        _INTERNAL_NS = (TT_NS, RR_NS, SL_NS)

        bnode_map: dict = {}

        def _sub(node):
            if isinstance(node, URIRef):
                s = str(node)
                if s.startswith(TT_NS) or s.startswith(RR_NS):
                    if node not in bnode_map:
                        bnode_map[node] = BNode()
                    return bnode_map[node]
            return node

        raw = Graph(store=self.store, identifier=self.identifier)
        out = Graph()
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

    def cbd(self, resource, *, target_graph=None, include_reifications=True):
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

    @classmethod
    def from_rdflib(cls, source_graph):
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
        from starlayergraph.parsers.turtle_parser import _skolemize_encoding
        processed = _skolemize_encoding(source_graph)
        g = cls()
        for prefix, ns in processed.namespaces():
            g.bind(prefix, ns)
        for triple in processed:
            super(StarLayerGraph, g).add(triple)
        g._build_registry_from_store()
        return g
