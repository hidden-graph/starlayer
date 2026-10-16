"""
starlayer.graph.backends.native_pyoxigraph

Embedded-engine transport for the native RDF 1.2 backend (backend='rdf-1.2').

Kept separate from native.py - whose HTTP functions remain unchanged - the
same way owl_dl_rustdl.py is kept separate from owl_dl.py: this is an
independently-optional dependency (the pyoxigraph pip package, not installed
by default - see the `oxigraph-embedded` extra), imported lazily, never at
native.py's module level.

Unlike the HTTP transport (which talks to a *server*, e.g. a running
`oxigraph serve` process), this talks directly to an in-process
pyoxigraph.Store - the identical Oxigraph Rust engine, with no HTTP
round-trip at all. It is also, deliberately, NOT built on top of oxrdflib
(the existing third-party rdflib Store adapter for pyoxigraph): oxrdflib's
own term converter (_converter.py's to_ox()/from_ox()) has no case for a
triple-term-valued term at all - one direction raises ValueError, the other
returns a bare, unusable tuple - so going through it would lose RDF 1.2
triple-term fidelity entirely, which is the whole point of this transport.
pyoxigraph's own Store.query()/.update() already understand real RDF 1.2
syntax (<<( s p o )>>, "text"@lang--dir) natively - confirmed live - so this
module only needs to convert pyoxigraph's *native result objects*
(NamedNode/BlankNode/Literal/Triple) to StarLayer's model, not text at all.

Public API, mirrored 1:1 against native.py's HTTP equivalents so native.py's
execute_select()/execute_update()/execute_ask()/execute_construct() can
dispatch to either transport uniformly:
    EmbeddedOxigraphStore            - rdflib Store shim wrapping a real
                                        pyoxigraph.Store
    embedded_oxigraph_store(path)    → EmbeddedOxigraphStore
    _ox_select(store, sparql)        → (vars, bindings)
    _ox_ask(store, sparql)           → bool
    _ox_update(store, sparql)        → None
    _ox_construct(store, sparql)     → iterator of (s, p, o) triples
"""

from __future__ import annotations

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.store import Store
from rdflib.term import Variable

from starlayer.graph.backends.native import deskolemize_bnode
from starlayer.graph.model.dirlangstring import DirLangString
from starlayer.graph.model.encoding import BN_NS
from starlayer.graph.model.triple import TripleTerm


class EmbeddedOxigraphStore(Store):
    """Minimal rdflib Store shim wrapping a real pyoxigraph.Store.

    Exists only because rdflib.Graph.__init__ requires store= to be either a
    plugin-name string or an actual rdflib.store.Store subclass instance -
    confirmed live that a bare pyoxigraph.Store() object fails that check
    outright (PluginException: No plugin registered for (, <class
    'rdflib.store.Store'>)). This class is never meant to be driven through
    rdflib's own Store protocol (triples()/add()/remove()/__len__()) - a
    StarLayerGraph constructed with backend='rdf-1.2' never calls those; it
    dispatches every read/write through native.py's execute_*() functions
    instead (see starlayer_graph.py's _is_native-gated methods), which reach
    into this shim's own _ox_store attribute directly. Each protocol method
    below raises loudly rather than silently doing nothing or the wrong
    thing, in case that bypass is ever accidentally violated.

    Two groups of methods are deliberate exceptions, genuinely invoked in
    normal use rather than bypassed:

    - close(): StarLayerGraph.close()/StarLayerDataset.close() call
      self.store.close(...) unconditionally, not gated on _is_native.
      Confirmed live that pyoxigraph's RocksDB storage holds its
      single-writer lock for the Store object's own lifetime, released only
      when the object is actually dropped (there is no Store.close() in
      pyoxigraph itself, only flush()) - so close() must drop the reference
      (self._ox_store = None), not just no-op, or a later attempt to reopen
      the same on-disk path raises OSError: ... LOCK: Resource temporarily
      unavailable.
    - bind()/namespace()/prefix()/namespaces(): StarLayerGraph.bind() has no
      _is_native-gated override at all - it always goes through
      self.namespace_manager.bind(), which always delegates to these four
      Store methods (confirmed by reading rdflib's own
      NamespaceManager.bind() directly). The base Store class's own versions
      are silent no-ops, which would make every g.bind(prefix, ns) call
      vanish - confirmed live via a stale ns1:/ns2: auto-generated-prefix
      serialize() before this was added. Implemented below as a plain pair
      of dicts, mirroring rdflib's own in-memory Memory store.
    """

    # pyoxigraph.Store is a genuine multi-named-graph quad store (context-
    # aware, graph-aware) - rdflib.graph.ConjunctiveGraph.__init__ (which
    # StarLayerDataset ultimately subclasses) asserts store.context_aware
    # at construction time, so this must be True for
    # StarLayerDataset(store=embedded_oxigraph_store(), backend='rdf-1.2')
    # to construct at all, even though _is_native=True means nothing in
    # this class's own dispatch path ever calls a real context/graph-aware
    # Store-protocol method on this shim (every native-backend read/write
    # goes through native.py's execute_*() functions instead - see the
    # class docstring above).
    context_aware = True
    graph_aware = True
    formula_aware = False
    transaction_aware = True

    def __init__(self, ox_store) -> None:
        super().__init__()
        self._ox_store = ox_store
        self.__namespace: dict = {}
        self.__prefix: dict = {}

    def close(self, commit_pending_transaction: bool = False) -> None:
        """Drop the pyoxigraph.Store reference so its RocksDB lock actually
        releases (see class docstring) - flush()-ing first if there's
        anything to commit, matching commit_pending_transaction's meaning
        for every other Store.close()."""
        if self._ox_store is not None:
            if commit_pending_transaction:
                self._ox_store.flush()
            self._ox_store = None

    # ------------------------------------------------------------------
    # Namespace bindings - a real implementation, not a bypassed one
    # ------------------------------------------------------------------
    # Unlike triples()/add()/remove()/__len__() below, StarLayerGraph.bind()
    # (inherited unmodified from rdflib.Graph - no _is_native-gated override
    # exists for it) always goes through self.namespace_manager.bind(),
    # which always delegates storage to self.store.bind()/.namespace()/
    # .prefix() (confirmed by reading rdflib.namespace.NamespaceManager.bind()
    # directly) - every native-backend StarLayerGraph, embedded or not,
    # relies on this. The base rdflib.store.Store class's own
    # bind()/namespace()/prefix()/namespaces() are all silent no-ops, which
    # would make every g.bind(prefix, ns) call silently vanish - confirmed
    # live: serialize() fell back to auto-generated ns1:/ns2: prefixes
    # instead of the real ones before this was added. Implementation
    # mirrors rdflib's own in-memory Memory store (the same logic every
    # other backend not needing real server-side namespace persistence
    # already uses) - a plain pair of dicts, nothing pyoxigraph-specific.

    def bind(self, prefix: str, namespace, override: bool = True) -> None:
        bound_namespace = self.__namespace.get(prefix)
        bound_prefix = self.__prefix.get(namespace) or (
            self.__prefix.get(bound_namespace) if bound_namespace is not None else None
        )
        if override:
            if bound_prefix is not None:
                del self.__namespace[bound_prefix]
            if bound_namespace is not None:
                del self.__prefix[bound_namespace]
            self.__prefix[namespace] = prefix
            self.__namespace[prefix] = namespace
        else:
            self.__prefix[bound_namespace if bound_namespace is not None else namespace] = (
                bound_prefix if bound_prefix is not None else prefix
            )
            self.__namespace[bound_prefix if bound_prefix is not None else prefix] = (
                bound_namespace if bound_namespace is not None else namespace
            )

    def namespace(self, prefix: str):
        return self.__namespace.get(prefix, None)

    def prefix(self, namespace):
        return self.__prefix.get(namespace, None)

    def namespaces(self):
        yield from self.__namespace.items()

    def triples(self, triple_pattern, context=None):
        raise NotImplementedError(
            "EmbeddedOxigraphStore.triples() should never be called directly - "
            "StarLayerGraph(backend='rdf-1.2') dispatches reads through "
            "native.py's execute_select()/execute_construct() instead."
        )

    def add(self, triple, context=None, quoted: bool = False) -> None:
        raise NotImplementedError(
            "EmbeddedOxigraphStore.add() should never be called directly - "
            "StarLayerGraph(backend='rdf-1.2') dispatches writes through "
            "native.py's execute_update() instead."
        )

    def remove(self, triple_pattern, context=None) -> None:
        raise NotImplementedError(
            "EmbeddedOxigraphStore.remove() should never be called directly - "
            "StarLayerGraph(backend='rdf-1.2') dispatches removals through "
            "native.py's execute_update() instead."
        )

    def __len__(self, context=None) -> int:
        raise NotImplementedError(
            "EmbeddedOxigraphStore.__len__() should never be called directly - "
            "StarLayerGraph(backend='rdf-1.2') dispatches length queries through "
            "native.py's execute_select() instead."
        )


def embedded_oxigraph_store(path=None) -> EmbeddedOxigraphStore:
    """Construct an embedded, in-process Oxigraph store for use as
    StarLayerGraph(store=..., backend='rdf-1.2')'s store= - real native RDF
    1.2 triple-term storage, no tt:HASH encoding, no HTTP.

    Args:
        path: Directory to persist to. Omit (or pass None) for an ephemeral,
            in-memory-only store (pyoxigraph's own Store(path=None)
            semantics - data is never written to disk and is discarded once
            the store is garbage collected).

    Returns:
        An EmbeddedOxigraphStore ready to pass as StarLayerGraph(store=...).

    Raises:
        ImportError: If the optional pyoxigraph dependency isn't installed.
    """
    try:
        import pyoxigraph
    except ImportError as exc:
        raise ImportError(
            "The embedded Oxigraph backend requires the optional 'pyoxigraph' "
            "dependency - install it with `pip install starlayer.graph[oxigraph-embedded]` "
            "(or `pip install pyoxigraph` directly), then retry."
        ) from exc
    return EmbeddedOxigraphStore(pyoxigraph.Store(path))


# ---------------------------------------------------------------------------
# Native-object result parsing (no JSON/text round-trip at all)
# ---------------------------------------------------------------------------

def _parse_ox_term(term):
    """Convert a native pyoxigraph term object to an rdflib node,
    DirLangString, or TripleTerm.

    Mirrors native.py's _parse_json_term(), but simpler: pyoxigraph hands
    back real typed objects directly (no "type" dict dispatch, no
    its:dir-key JSON parsing - a direction-tagged literal already carries a
    real .direction attribute).
    """
    import pyoxigraph as ox

    if term is None:
        return None
    if isinstance(term, ox.NamedNode):
        value = term.value
        # Reverse skolemize_bnode() - see that function's docstring for why
        # a stored write goes out this way.
        if value.startswith(BN_NS):
            return BNode(value[len(BN_NS):])
        return URIRef(value)
    if isinstance(term, ox.BlankNode):
        return BNode(term.value)
    if isinstance(term, ox.Literal):
        if term.language and term.direction is not None:
            return DirLangString(term.value, term.language, str(term.direction))
        if term.language:
            return Literal(term.value, lang=term.language)
        dtype_iri = term.datatype.value
        # pyoxigraph always reports an explicit xsd:string datatype for a
        # plain literal (confirmed live) - rdflib's own Literal.__eq__
        # treats a simple literal and its ^^xsd:string equivalent as
        # *different* terms (a known, documented rdflib divergence - see
        # packages/starlayer/starlayer/graph/CLAUDE.md's
        # "plain-string-same" entry), so collapsing back to a plain
        # Literal(value) here - matching _parse_json_term()'s own behavior
        # for a binding with no datatype key at all - is required for
        # embedded/HTTP parity, not a style choice.
        if dtype_iri == str(XSD.string):
            return Literal(term.value)
        literal = Literal(term.value, datatype=URIRef(dtype_iri))
        if dtype_iri == str(XSD.decimal):
            # Same Oxigraph-engine whole-number xsd:decimal canonicalization
            # defect native.py's _parse_json_term() already works around for
            # the HTTP transport - confirmed live this reproduces identically
            # through the embedded Store.query() API, since it's a property
            # of the underlying engine, not of JSON serialization.
            from starlayer.graph.query.operator_patches import (
                _canonicalize_decimal_lexical_form,
            )

            literal = _canonicalize_decimal_lexical_form(literal)
        return literal
    if isinstance(term, ox.Triple):
        s = _parse_ox_term(term.subject)
        p = _parse_ox_term(term.predicate)
        o = _parse_ox_term(term.object)
        try:
            return TripleTerm(s, p, o)
        except ValueError as e:
            # Same re-raise rationale as native.py's _parse_json_term(): a
            # non-conformant triple term reaching this point is a real data
            # problem from the engine, not malformed input to reject up
            # front, and TripleTerm's own bare ValueError fires before
            # __slots__ are assigned, so a later repr() attempt would
            # otherwise hit a second, unrelated AttributeError.
            raise ValueError(
                f'embedded native backend returned a triple term with an invalid RDF 1.2 '
                f'subject or predicate (subject={s!r}, predicate={p!r}, object={o!r}) - {e}. '
                f'This indicates a spec-conformance bug in the native SPARQL engine, not in '
                f'this library.'
            ) from e
    raise ValueError(f'Unknown pyoxigraph term type: {type(term).__name__!r}')


# ---------------------------------------------------------------------------
# Embedded execution
# ---------------------------------------------------------------------------

def _ox_select(store, sparql: str) -> tuple[list, list]:
    """Execute a SPARQL SELECT against an embedded pyoxigraph store and
    return (vars, bindings) in the same shape native.py's http_select()
    produces."""
    solutions = store._ox_store.query(sparql)
    native_vars = solutions.variables
    vars_ = [Variable(v.value) for v in native_vars]
    bindings = []
    for sol in solutions:
        binding = {}
        for rdf_var, native_var in zip(vars_, native_vars):
            raw = sol[native_var]
            if raw is not None:
                binding[rdf_var] = _parse_ox_term(raw)
        bindings.append(binding)
    return vars_, bindings


def _ox_ask(store, sparql: str) -> bool:
    """Execute a SPARQL ASK against an embedded pyoxigraph store."""
    return bool(store._ox_store.query(sparql))


def _ox_update(store, sparql: str) -> None:
    """Execute a SPARQL UPDATE against an embedded pyoxigraph store."""
    store._ox_store.update(sparql)


def _ox_construct(store, sparql: str):
    """Execute a SPARQL CONSTRUCT/DESCRIBE against an embedded pyoxigraph
    store, yielding already-deskolemized (s, p, o) triples - no Turtle
    serialize/re-parse round-trip at all, unlike the HTTP transport, since
    pyoxigraph's own QueryTriples result already carries real Triple
    objects."""
    for t in store._ox_store.query(sparql):
        s = deskolemize_bnode(_parse_ox_term(t.subject))
        p = _parse_ox_term(t.predicate)
        o = deskolemize_bnode(_parse_ox_term(t.object))
        yield s, p, o
