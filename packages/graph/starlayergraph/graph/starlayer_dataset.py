"""
starlayergraph.graph.starlayer_dataset

StarLayerDataset — an RDF 1.2 dataset where every named-graph context is a
StarLayerGraph with full triple-term support.

Terminology: "RDF dataset" is the term used by RDF 1.2, SPARQL, TriG, and
N-Quads.  rdflib models this as ``Dataset`` (default graph is an explicit,
independent graph, not a union of named graphs).

Typical usage::

    from starlayergraph.graph import StarLayerDataset

    ds = StarLayerDataset()
    ds.parse("knowledge_base.trig", format="trig12")

    g1 = ds.get_context(URIRef("http://example.org/graph1"))
    # g1 is a StarLayerGraph — all TripleTerm API available
    for tt in g1.triple_terms():
        print(tt)

    for s, p, o, g in ds.quads():
        print(s, p, o, "in", g.identifier)

    ds.serialize("out.trig", format="trig12")
"""

from __future__ import annotations

import weakref

from rdflib import BNode, Dataset, Graph, URIRef
from rdflib.graph import DATASET_DEFAULT_GRAPH_ID

from starlayergraph.graph.starlayer_graph import (
    VALID_BACKENDS,
    StarLayerGraph,
    _raw_triples,
    _read_source_text,
)
from starlayergraph.model.encoding import ENCODING_PREDS as _ENCODING_PREDS
from starlayergraph.model.encoding import TT_NS, lookup_tt_hash, restore_select_bindings
from starlayergraph.model.triple import TripleTerm

_raw_graph_add = Graph.add


class StarLayerDataset(Dataset):
    """An RDF dataset where every named-graph context is a StarLayerGraph.

    All RDF 1.2 triple-term handling (encoding, filtering, restoration) is
    delegated to per-context StarLayerGraph instances.  The shared store holds
    the tt: URIRef encoding triples; each StarLayerGraph's registry maps those
    back to TripleTerm objects.

    The default graph is an explicit, independent graph (``default_union=False``
    per the RDF dataset spec and rdflib 7 default).  Pass
    ``default_union=True`` to make the default graph a union of all named graphs.

    Public API additions vs Dataset:
        parse(format='trig12')      — load TriG 1.2 with triple-term support
        parse(format='nq12')        — load N-Quads 1.2 with triple-term support
        serialize(format='trig12')  — emit TriG 1.2 with triple-term support
        serialize(format='nq12')    — emit N-Quads 1.2 with triple-term support
        get_context(identifier)     — returns StarLayerGraph (not plain Graph)
        contexts()                  — yields StarLayerGraph instances
        quads()                     — yields (s, p, o, StarLayerGraph) with
                                      TripleTerms restored; encoding triples filtered
    """

    def __init__(self, *args, backend: str = 'rdf-1.1', **kwargs):
        if backend not in VALID_BACKENDS:
            raise ValueError(f"backend must be one of {sorted(VALID_BACKENDS)}, got {backend!r}")
        super().__init__(*args, **kwargs)
        self._backend = backend
        self._sg_cache: dict[str, StarLayerGraph] = {}
        self._raw_execution_graph: Dataset | None = None
        self._prepared_query_cache: dict = {}  # see starlayergraph.query.query_cache.prepare_query_cached

    # ------------------------------------------------------------------
    # Persistent store lifecycle
    # ------------------------------------------------------------------

    def open(self, configuration, create: bool = False):
        """Open a persistent store and rebuild all per-context TripleTerm registries.

        The store backend is not a StarLayer dependency — install and configure
        it separately, then pass store='StoreName' to the constructor.

        Example::

            ds = StarLayerDataset(store='Sleepycat')
            ds.open('/path/to/db', create=True)
        """
        result = super().open(configuration, create)
        self._sg_cache.clear()
        self._raw_execution_graph = None
        for ctx in super(Dataset, self).contexts():
            self.get_context(ctx.identifier)
        return result

    def close(self, commit_pending_transaction: bool = False):
        """Close the underlying store, optionally committing pending writes."""
        self.store.close(commit_pending_transaction=commit_pending_transaction)

    # ------------------------------------------------------------------
    # Context access
    # ------------------------------------------------------------------

    def _register_sg(self, sg: StarLayerGraph) -> StarLayerGraph:
        """Cache a StarLayerGraph context and wire its invalidation callback.

        The callback uses a weakref so the dataset is not kept alive by its
        own contexts.
        """
        ds_ref = weakref.ref(self)

        def _invalidate():
            ds = ds_ref()
            if ds is not None:
                ds._raw_execution_graph = None

        sg._invalidate_callback = _invalidate
        self._sg_cache[str(sg.identifier)] = sg
        return sg

    def get_context(self, identifier, quoted: bool = False, base=None) -> StarLayerGraph:
        """Return the StarLayerGraph for the named graph with the given identifier.

        If the graph was populated via parse(), its TripleTerm registry is
        already current.  If the context was added through other means, the
        registry is rebuilt on first access.
        """
        key = str(identifier)
        if key not in self._sg_cache:
            sg = StarLayerGraph(
                store=self.store,
                identifier=identifier,
                namespace_manager=self.namespace_manager,
                backend=self._backend,
            )
            sg._build_registry_from_store()
            self._register_sg(sg)
        return self._sg_cache[key]

    def contexts(self, triple=None):
        """Yield a StarLayerGraph for every named graph in this dataset."""
        for ctx in super(Dataset, self).contexts(triple):
            yield self.get_context(ctx.identifier)

    # ------------------------------------------------------------------
    # Quad iteration with TripleTerm restoration
    # ------------------------------------------------------------------

    def _is_encoding_triple(self, s, p, o) -> bool:
        return (
            isinstance(s, URIRef)
            and str(s).startswith(TT_NS)
            and p in _ENCODING_PREDS
        )

    def quads(self, triple=(None, None, None)):
        """Yield (s, p, o, StarLayerGraph) with encoding triples filtered out
        and tt:HASH URIRefs restored to TripleTerm objects."""
        # Bypass Dataset.quads() (which yields bare URIRef graph identifiers)
        # and call the grandparent implementation directly so the 4th element
        # is a Graph object with .identifier.
        for s_r, p_r, o_r, g in super(Dataset, self).quads(triple):
            if self._is_encoding_triple(s_r, p_r, o_r):
                continue
            sg = self.get_context(g.identifier)
            yield sg._restore(s_r), p_r, sg._restore(o_r), sg

    def triples(self, triple=(None, None, None)):
        """Yield (s, p, o), scoped by ``self.default_union`` like rdflib's own Dataset.

        default_union=False (the default): only the default graph's own triples,
        matching this dataset's declared default-graph-isolation semantics.
        default_union=True: the union of every graph, default and named alike.
        The same triple may appear more than once if it exists in multiple graphs.

        Encoding triples are filtered; TripleTerms are restored either way.
        """
        if self.default_union:
            for s, p, o, _g in self.quads(triple):
                yield s, p, o
        else:
            default_graph = self.get_context(self.default_graph.identifier)
            yield from default_graph.triples(triple)

    # ------------------------------------------------------------------
    # Add/remove with TripleTerm-aware encoding
    #
    # rdflib's own Dataset has no override for any of these three at all -
    # confirmed a real, previously-undiscovered gap (not just an
    # asymmetry with triples()/quads() for its own sake): calling
    # .add()/.remove()/`+=`/`-=` directly on a bare StarLayerDataset (no
    # WITH/USING clause naming a specific graph, so SPARQL Update's own
    # Modify operation reads/writes through ctx.graph = the Dataset itself
    # - confirmed via tracing a real evalModify call) previously fell
    # through to plain rdflib Dataset.add/remove/addN, which write a raw
    # TripleTerm Python object directly into the underlying store with no
    # translation to this library's own tt:HASH encoding - silently
    # failing to match anything on a later read or a subsequent remove()
    # of the exact same value, with no error at all. triples()/quads()
    # above already delegate to a real per-context StarLayerGraph for
    # reads; these three do the same for writes.
    # ------------------------------------------------------------------

    def add(self, triple) -> StarLayerDataset:
        """Add a triple to the default graph, with TripleTerm-aware
        encoding - see this section's own module-level comment for why
        this override exists at all."""
        default_graph = self.get_context(self.default_graph.identifier)
        default_graph.add(triple)
        return self

    def remove(self, triple) -> StarLayerDataset:
        """Remove a triple from the default graph, with TripleTerm-aware
        encoding - see this section's own module-level comment for why
        this override exists at all. Found via a real SPARQL Update
        (Modify DELETE of a non-ground triple-term pattern): the WHERE
        clause matched correctly, but nothing was actually removed -
        traced down to this exact gap, not a bug in the query/update
        translation that produced the Modify operation."""
        default_graph = self.get_context(self.default_graph.identifier)
        default_graph.remove(triple)
        return self

    def addN(self, quads) -> None:
        """Add multiple quads, each routed to its own target graph's real
        StarLayerGraph context for TripleTerm-aware encoding - see this
        section's own module-level comment. rdflib's own ``Graph.__iadd__``
        (``+=``) calls this with every quad's graph element set to the
        same graph object being added to (confirmed by reading its
        source) - grouped by identifier here regardless, matching
        ``StarLayerGraph.addN``'s own general handling of a heterogeneous
        quads iterable, so this is correct for a direct multi-graph
        ``addN`` call too, not just the ``+=`` case.
        """
        by_graph: dict = {}
        for s, p, o, c in quads:
            identifier = c.identifier if isinstance(c, Graph) else c
            by_graph.setdefault(identifier, []).append((s, p, o))
        for identifier, triples in by_graph.items():
            sg = self.get_context(identifier)
            sg.addN((s, p, o, sg) for s, p, o in triples)

    # ------------------------------------------------------------------
    # Internal parse helpers
    # ------------------------------------------------------------------

    def _read_source(self, source, publicID, location, file, data) -> str:
        """Resolve any of the rdflib source arguments to a text string.

        publicID is accepted (matching every rdflib parse()-style signature
        in this codebase) but unused, same as before this was factored out
        - see _read_source_text(), shared with StarLayerGraph.parse().
        """
        return _read_source_text(source=source, file=file, location=location, data=data)

    def _load_context(self, identifier, namespaces=()) -> StarLayerGraph:
        """Create (or update) a StarLayerGraph context and register its namespaces."""
        sg = StarLayerGraph(
            store=self.store,
            identifier=identifier,
            namespace_manager=self.namespace_manager,
            backend=self._backend,
        )
        for prefix, ns in namespaces:
            sg.bind(prefix, ns)
            self.bind(prefix, ns)
        return sg

    # ------------------------------------------------------------------
    # Parse / Serialize
    # ------------------------------------------------------------------

    def parse(
        self,
        source=None,
        publicID=None,
        format=None,
        location=None,
        file=None,
        data=None,
        **kwargs,
    ) -> StarLayerDataset:
        """Parse RDF data into named-graph contexts.

        format='turtle12' — Turtle 1.2; triples go into the default graph as a StarLayerGraph.
        format='trig12'   — TriG 1.2; each GRAPH block becomes a StarLayerGraph.
                            Plain Turtle content (no GRAPH blocks) goes into the default graph.
        format='nq12'     — N-Quads 1.2; each distinct graph name becomes a StarLayerGraph.
        format='trix12'   — TriX 1.2 XML; each <graph> block becomes a StarLayerGraph.
        All other formats delegate to rdflib (no triple-term support).
        """
        # turtle12 is Turtle-only (no GRAPH blocks); trig12 is a strict superset,
        # so routing turtle12 through the trig12 path is correct and safe.
        if format == 'turtle12':
            format = 'trig12'

        if format not in ('trig12', 'nq12', 'trix12'):
            return super().parse(
                source=source, publicID=publicID, format=format,
                location=location, file=file, data=data, **kwargs,
            )

        text = self._read_source(source, publicID, location, file, data)

        if format == 'trig12':
            from starlayergraph.parsers.trig12 import (
                extract_version_directive as _trig_version,
            )
            from starlayergraph.parsers.trig12 import parse_trig12_named
            for graph_id, triples, namespaces in parse_trig12_named(text):
                identifier = DATASET_DEFAULT_GRAPH_ID if graph_id is None else graph_id
                sg = self._load_context(identifier, namespaces)
                if sg._is_native:
                    # parse_trig12_named() returns the rdf-1.1 backend's own
                    # tt:HASH encoding (same as parse_trig12(), see
                    # StarLayerGraph.parse()'s trig12 branch) - decode back
                    # into real TripleTerm objects before sg.add() so a
                    # native-backend context gets its real <<( )>> encoding
                    # via _native_add(), not the flat encoding fragments.
                    from starlayergraph.parsers.turtle_parser import (
                        decode_tt_encoded_triples,
                    )
                    skolemized = Graph()
                    for triple in triples:
                        skolemized.add(triple)
                    for triple in decode_tt_encoded_triples(skolemized):
                        sg.add(triple)
                else:
                    for triple in triples:
                        _raw_graph_add(sg, triple)
                    sg._build_registry_from_store()
                self._register_sg(sg)
            self._check_document_version_conformance(_trig_version(text), context='TriG document')

        elif format == 'nq12':
            from collections import defaultdict

            from starlayergraph.parsers.ntriples12 import (
                extract_version_directive as _nq_version,
            )
            from starlayergraph.parsers.ntriples12 import parse_nquads12
            by_graph: dict = defaultdict(list)
            for s, p, o, graph_id in parse_nquads12(text):
                key = graph_id if graph_id is not None else DATASET_DEFAULT_GRAPH_ID
                by_graph[key].append((s, p, o))
            for identifier, triples in by_graph.items():
                sg = self._load_context(identifier)
                for triple in triples:
                    sg.add(triple)
                self._register_sg(sg)
            self._check_document_version_conformance(_nq_version(text), context='N-Quads document')

        elif format == 'trix12':
            from starlayergraph.parsers.trix12 import parse_trix12_named
            for graph_id, triples in parse_trix12_named(text):
                identifier = DATASET_DEFAULT_GRAPH_ID if graph_id is None else graph_id
                sg = self._load_context(identifier)
                for triple in triples:
                    sg.add(triple)
                self._register_sg(sg)

        self._raw_execution_graph = None
        return self

    def _check_document_version_conformance(self, declared_version, *, context: str) -> None:
        """Warn (RDF12ConformanceWarning, never a hard error) if a document-
        level VERSION directive declares "1.2-basic"/"1.1" but any graph in
        this dataset actually uses a triple term or dirLangString.

        The directive applies to the whole document, not per named graph
        (see trig12.py's extract_version_directive()), so this checks the
        union across every context rather than each one independently -
        see check_version_conformance_for_graphs(), shared with
        StarLayerGraph.parse()'s equivalent per-format checks.
        """
        from starlayergraph.model.conformance import (
            check_version_conformance_for_graphs,
        )
        check_version_conformance_for_graphs(declared_version, self.contexts(), context=context)

    # ------------------------------------------------------------------
    # Query / Update with SPARQL-star support
    # ------------------------------------------------------------------

    def _restore_any(self, node):
        """Restore a tt:HASH URIRef to a TripleTerm by searching all cached graph
        registries, falling back to the process-wide TT_HASH_FN memo (see
        starlayergraph.model.encoding's lookup_tt_hash) for a fully-ground
        TRIPLE()/<<( )>> value that was computed but never written to any
        graph - mirrors StarLayerGraph._restore's own fallback, which this
        one lacked (a real, separate gap: confirmed via a W3C test, expr-2,
        that only reaches StarLayerDataset because its data fixture happens
        to be an empty .nq file, routing it through StarLayerDataset._new_graph
        instead of a plain StarLayerGraph - the query itself never touches
        any actual dataset content). Recurses like StarLayerGraph._restore
        does, so a nested triple-term component (itself a tt:HASH URIRef)
        resolves fully rather than leaving an inner URIRef unresolved.
        """
        if not (isinstance(node, URIRef) and str(node).startswith(TT_NS)):
            return node
        for sg in self._sg_cache.values():
            tt = sg._tt_nodes.get(node)
            if tt is not None:
                return TripleTerm(self._restore_any(tt.subject), tt.predicate, self._restore_any(tt.object))
        remembered = lookup_tt_hash(node)
        if remembered is not None:
            s, p, o = remembered
            return TripleTerm(self._restore_any(s), p, self._restore_any(o))
        return node

    def _build_raw_execution_graph(self) -> Dataset:
        """Build (and cache) a plain Dataset containing all raw triples including encoding triples.

        rdflib's Memory store stores the actual StarLayerGraph Python objects as
        context keys.  When the SPARQL engine evaluates GRAPH ?g it calls
        contexts() and then triples() on each returned object — which would
        invoke StarLayerGraph.triples() and filter encoding triples, breaking
        the rewritten SPARQL 1.1 triple-term patterns.  A separate Dataset with
        plain Graph contexts sidesteps this.

        default_union is forwarded from self so a GRAPH-less query pattern
        against this copy sees the same default-graph-is-the-union-of-everything
        semantics self.triples() already honors - omitting it silently dropped
        every named graph from any query with no explicit GRAPH clause,
        regardless of how this dataset was constructed.

        The result is cached and reused until the next parse() or update() call.
        """
        if self._raw_execution_graph is not None:
            return self._raw_execution_graph
        raw = Dataset(default_union=self.default_union)
        for prefix, ns in self.namespaces():
            raw.bind(prefix, ns)
        for sg in self._sg_cache.values():
            raw_ctx = raw.get_context(sg.identifier)
            for t in _raw_triples(sg, (None, None, None)):
                raw_ctx.add(t)
        self._raw_execution_graph = raw
        return raw

    def __len__(self) -> int:
        """Total triple count across the *entire* dataset (default graph +
        every named graph) - matching rdflib's own Dataset.__len__ docstring
        ("Number of triples in the entire conjunctive graph") and this
        class's own behavior for the default in-memory backend, where
        Dataset.__len__ -> self.store.__len__() already sums everything
        (a Memory store has no separate per-context counting concept).

        Native backend needed its own override: SPARQLStore.__len__(context=
        None) (what the inherited Dataset.__len__ calls) queries only the
        endpoint's true default graph - GRAPH-scoped content is invisible to
        it - so plain inheritance would silently undercount any native-
        backed dataset with named-graph content. Confirmed live: 3 triples
        (1 default + 1 each in two named graphs) came back as 1 via
        inheritance, 3 via the UNION query here.
        """
        if self._backend != 'rdf-1.2':
            return super().__len__()
        from rdflib.term import Variable

        from starlayergraph.backends.native import http_select, resolve_store_http
        q_url, _, hdrs = resolve_store_http(self.store, self._backend)
        sparql = 'SELECT (COUNT(*) AS ?c) WHERE { { ?s ?p ?o } UNION { GRAPH ?g { ?s ?p ?o } } }'
        _vars, bindings = http_select(q_url, sparql, hdrs)
        if not bindings:
            return 0
        return int(str(bindings[0][Variable('c')]))

    def query(self, query_object, processor='sparql', result='sparql',
              initNs=None, initBindings=None, use_store_provided=True, **kwargs):
        """Execute a SPARQL query across all named graphs with SPARQL-star support.

        SPARQL 1.2 syntax (``<<( )>>``, ``{| |}``, ``~``, SUBJECT/PREDICATE/
        OBJECT/isTRIPLE) is parsed via starsparql's real grammar and
        lowered to plain SPARQL 1.1 (tt:HASH encoding) before execution.
        SELECT result rows are post-processed to restore tt:HASH URIRefs
        back to TripleTerm objects.

        Rewriting and parsing are cached (``prepare_query_cached``) on
        (query text, effective namespaces, base) - not cleared on
        parse()/update() unlike ``_raw_execution_graph``, since a query's
        parse tree depends only on its own text, not on graph content.

        For the native rdf-1.2 backend the query is routed through
        ``starlayergraph.backends.native.native_query``, same as
        ``StarLayerGraph.query()`` (a native-backed dataset's contexts all
        share one store, so it's the same underlying HTTP operation) -
        ``_build_raw_execution_graph()``'s plain-Graph-copy approach can't
        represent real triple-term-valued bindings (rdflib's SPARQL JSON
        result parsing doesn't understand "type":"triple"; see
        starlayergraph.backends.native's module docstring).
        """
        if self._backend == 'rdf-1.2':
            from starlayergraph.backends.native import native_query
            return native_query(
                self.store, self._backend, query_object, processor=processor, result=result,
                initNs=initNs, initBindings=initBindings,
                use_store_provided=use_store_provided, **kwargs,
            )

        if isinstance(query_object, str):
            # No remote-store dispatch complexity needed here unlike
            # StarLayerGraph: _build_raw_execution_graph() below is
            # *always* a fresh, local, in-memory Dataset copy (no store=
            # argument) regardless of what this dataset's own backing
            # store is, so the resulting Query object can always be handed
            # to it directly.
            from starlayergraph.query.query_cache import prepare_query_cached
            effective_ns = initNs if initNs else dict(self.namespaces())
            query_object = prepare_query_cached(
                self._prepared_query_cache, query_object, effective_ns, kwargs.get('base')
            )
        raw = self._build_raw_execution_graph()
        r = raw.query(query_object, processor=processor, result=result,
                      initNs=initNs, initBindings=initBindings,
                      use_store_provided=use_store_provided, **kwargs)
        if r.type == 'SELECT':
            restore_select_bindings(r, self._restore_any)
        elif r.type == 'CONSTRUCT':
            from starlayergraph.model.encoding import inject_missing_tt_encoding
            inject_missing_tt_encoding(r.graph, self._restore_any)
            r.graph = StarLayerGraph.from_rdflib(r.graph)
        return r

    def update(self, update_object, processor='sparql',
               initNs=None, initBindings=None, use_store_provided=True, **kwargs):
        """Execute a SPARQL UPDATE across named graphs with SPARQL-star support.

        Triple-term patterns in WHERE clauses are rewritten to SPARQL 1.1
        (rdf-1.1 backend only — see below). All cached per-graph registries
        are rebuilt after execution so that newly added triple terms are
        immediately visible.

        Remote-store (Fuseki/Oxigraph) updates bypass rdflib's own
        ``Dataset(store=...).update()`` and are sent over HTTP directly (see
        ``starlayergraph.backends.native.native_update``) — needed for *both*
        backends: rdflib's ``SPARQLStore._is_contextual()`` treats any string
        graph identifier other than the literal ``"__UNION__"`` as needing a
        wrapping ``GRAPH { }`` block, and doesn't special-case ``Dataset``'s
        own ``DATASET_DEFAULT_GRAPH_ID`` sentinel (a ``URIRef``, which
        subclasses ``str``) - so ``Dataset.update()`` always wrapped the
        *entire* update text in an extra ``GRAPH <urn:x-rdflib:default> { }``
        block, which nests illegally around any update that already has its
        own ``GRAPH <uri> { }`` clause (the normal way to target a named graph
        from dataset-level SPARQL). Confirmed via real Oxigraph and Fuseki
        testing: a plain ``INSERT DATA { GRAPH <uri> {...} }`` with no triple
        terms at all got a 400 from both. For the rdf-1.2 backend the update
        text is sent unmodified (the endpoint understands ``<<( )>>``
        natively); for rdf-1.1 it is parsed and lowered to the tt:HASH
        encoding first (native_update itself, via starsparql).
        """
        is_remote_http_store = bool(
            getattr(self.store, 'query_endpoint', None) and getattr(self.store, 'update_endpoint', None)
        )
        if not is_remote_http_store:
            if isinstance(update_object, str):
                from starsparql.lower_rdf11 import rdf11_to_update, update_to_rdf11
                from starsparql.parse12 import prepare_update_12
                prepared_12 = prepare_update_12(update_object, base=kwargs.get('base'), initNs=initNs)
                rdf_graph, root = update_to_rdf11(prepared_12)
                update_object = rdf11_to_update(rdf_graph, root)
            # default_union forwarded from self - same rationale as
            # _build_raw_execution_graph(): a GRAPH-less WHERE clause should
            # see the same default-graph-is-the-union semantics self.triples()
            # honors, not silently match against an empty default graph.
            raw = Dataset(store=self.store, default_union=self.default_union)
            for prefix, ns in self.namespaces():
                raw.bind(prefix, ns)
            raw.update(update_object, processor=processor,
                       initNs=initNs, initBindings=initBindings,
                       use_store_provided=use_store_provided, **kwargs)
        else:
            from starlayergraph.backends.native import native_update
            native_update(self.store, self._backend, update_object)
        for sg in self._sg_cache.values():
            sg._build_registry_from_store()
        self._raw_execution_graph = None
        return None

    def serialize(self, destination=None, format='trig', **kwargs) -> str | None:
        """Serialize this dataset.

        format='trig12'  — TriG 1.2 with GRAPH blocks and <<( )>> triple terms.
        format='nq12'   — N-Quads 1.2 with <<( )>> triple terms; one quad per line.
        format='trix12' — TriX 1.2 XML with <graph> blocks and <tripleTerm> elements.
        All other formats delegate to rdflib.
        """
        if format not in ('trig12', 'nq12', 'trix12'):
            return super().serialize(destination=destination, format=format, **kwargs)

        if format == 'nq12':
            from starlayergraph.serializers.ntriples12 import serialize_nquads12
            has_tt = any(getattr(sg, '_tt_nodes', None) for sg in self.contexts())
            header = 'VERSION "1.2"\n' if has_tt else ''
            lines: list[str] = []
            for sg in self.contexts():
                if len(sg) == 0:
                    continue
                chunk = serialize_nquads12(sg, _include_header=False)
                if chunk.strip():
                    lines.append(chunk.rstrip('\n'))
            text = header + '\n'.join(lines) + ('\n' if lines else '')

        elif format == 'trix12':
            from starlayergraph.serializers.trix12 import serialize_trix12_dataset
            text = serialize_trix12_dataset(self)

        else:  # trig12
            from starlayergraph.serializers.turtle12 import serialize_turtle12

            all_prefix_lines: set[str] = set()
            has_version = False
            graph_entries: list[tuple] = []

            for sg in self.contexts():
                if len(sg) == 0:
                    continue
                turtle_text = serialize_turtle12(sg)
                body_lines = []
                for ln in turtle_text.splitlines():
                    if ln.startswith('@prefix'):
                        all_prefix_lines.add(ln)
                    elif ln.startswith('@version'):
                        has_version = True
                    else:
                        body_lines.append(ln)
                body = '\n'.join(body_lines).strip()
                if body:
                    graph_entries.append((sg.identifier, body))

            blocks: list[str] = []
            if has_version:
                blocks.append('@version "1.2" .')
            if all_prefix_lines:
                blocks.append('\n'.join(sorted(all_prefix_lines)))

            indent = '    '
            for identifier, body in graph_entries:
                if isinstance(identifier, BNode):
                    blocks.append(body)
                else:
                    indented = '\n'.join(
                        indent + ln if ln.strip() else ln
                        for ln in body.splitlines()
                    )
                    blocks.append(f'GRAPH <{identifier}> {{\n{indented}\n}}')

            text = '\n\n'.join(blocks) + '\n'

        if destination is not None:
            with open(destination, 'w', encoding='utf-8') as f:
                f.write(text)
            return destination
        return text
