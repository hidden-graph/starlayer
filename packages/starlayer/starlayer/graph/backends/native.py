"""
starlayer.graph.backends.native

HTTP-level utilities for the native RDF 1.2 backend.

rdflib 7.x does not handle "type":"triple" in SPARQL JSON results, so these
functions bypass rdflib's SPARQL stack and talk directly to SPARQL endpoints
via HTTP.

Public API, shared by StarLayerGraph and StarLayerDataset (a native-backed
dataset's per-context graphs all share one store, so there is exactly one
underlying endpoint per dataset, same as for a single graph — see
resolve_store_http()):
    sparql_term(node)                     → SPARQL inline string
    http_select(url, sparql, auth)        → (vars, bindings)
    http_construct(url, sparql, auth)     → (body_bytes, content_type)
    http_update(url, sparql, auth)        → None
    http_ask(url, sparql, auth)           → bool
    build_result(vars_, bindings)         → rdflib.query.Result
    resolve_store_http(store, backend)    → (query_url, update_url, extra_headers)
    check_native_version_conformance(text) → None (may emit SPARQL12ConformanceWarning)
    native_query(store, backend, query_object, ...) → rdflib.query.Result
    native_update(store, backend, update_object)    → None

The endpoint (e.g. Apache Jena Fuseki 5.5+, Oxigraph) speaks SPARQL 1.2
natively - triple-term syntax (<<( s p o )>>), TRIPLE()/isTRIPLE(), and the
base-direction functions (LANGDIR/hasLANGDIR/STRLANGDIR/LANG/hasLANG) are all
sent straight through with no rewriting. This is a different code path from the
default rdf-1.1 backend's SPARQL 1.2 handling (starlayer.sparql's
parse_update_12/update_to_rdf11/rdf11_update_to_sparql11_text pipeline,
see native_update() below), which never runs for a native-backend
query/update - see native_query()/native_update() below, and
StarLayerGraph._native_add()/_native_triples() for the write/read-triples
paths (those stay graph-scoped, using a specific GRAPH <identifier> clause,
so they aren't shared with StarLayerDataset the way query/update are).
"""

from __future__ import annotations

import re
from typing import Any

import requests
from rdflib import BNode, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.query import Result
from rdflib.term import Node, Variable

from starlayer.graph.model.dirlangstring import DirLangString
from starlayer.graph.model.encoding import BN_NS, decode_dirlang_datatype
from starlayer.graph.model.triple import TripleTerm

# ---------------------------------------------------------------------------
# Term serialization
# ---------------------------------------------------------------------------

def sparql_term(node, skolemize_bnodes: bool = True) -> str:
    """Serialize an RDF node to its SPARQL inline string.

    TripleTerms are rendered as <<( s p o )>>. A DirLangString is rendered as
    the real "text"@lang--dir lexical form - unlike TripleTerm's tt:HASH
    encoding, the native RDF 1.2 endpoint understands this syntax directly,
    so no internal encoding is involved here at all.

    A plain Literal whose datatype is starlayer.graph's own internal
    dirlang: encoding (not yet unwrapped to a real DirLangString object)
    gets the identical treatment, not just an already-converted
    DirLangString instance: StarLayerGraph's dirLangString -> DirLangString
    conversion happens lazily on *read* (inside StarLayerGraph._restore()),
    so the native-backend write path (_native_add()/_native_add_many())
    hands this function a raw Literal whose .datatype is still the internal
    dirlang: encoding, never yet unwrapped. Without this check, such a value
    would be sent as a bare "text"^^<the internal dirlang: URI> typed
    literal - syntactically valid SPARQL, but *semantically wrong*: the
    endpoint would store a literal with some unrelated custom datatype
    instead of a real rdf:dirLangString, so its own
    LANG()/LANGDIR()/hasLANG()/hasLANGDIR() would then correctly (from the
    endpoint's own perspective) report no language/direction at all.

    All other nodes use rdflib's .n3(), which produces correct SPARQL syntax
    - except BNode, which by default is skolemized to a stable BN_NS URI
    first (see skolemize_bnode()'s docstring for why: a blank node's own
    SPARQL syntax label is *not* enough to keep its identity across
    separate HTTP requests).

    Args:
        node: The RDF term to serialize - a TripleTerm, DirLangString, or
            any rdflib term.
        skolemize_bnodes: If False, render a real, unskolemized blank node
            instead. Only safe when every triple that might share this
            exact BNode object is going out together in the *same* HTTP
            request (see StarLayerGraph._native_add_many(), the only
            caller that passes this) - the one case SPARQL 1.1 Update's
            per-request blank-node scoping doesn't bite - which also avoids
            skolemize_bnode()'s own cost (the endpoint no longer
            recognizing it as a real blank node for ORDER BY / isBLANK())
            for exactly the triples that don't need to pay it.

    Returns:
        node's SPARQL inline string form.
    """
    if isinstance(node, TripleTerm):
        s = sparql_term(node.subject, skolemize_bnodes)
        p = sparql_term(node.predicate, skolemize_bnodes)
        o = sparql_term(node.object, skolemize_bnodes)
        return f'<<( {s} {p} {o} )>>'
    if isinstance(node, tuple) and len(node) == 3:
        # A plain 3-tuple means a triple term everywhere else in the public
        # API (StarLayerGraph.add()'s own docstring); the non-native path
        # coerces it via _coerce_tt() - this is the native equivalent.
        s, p, o = (sparql_term(x, skolemize_bnodes) for x in node)
        return f'<<( {s} {p} {o} )>>'
    if isinstance(node, DirLangString):
        escaped = node.value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"@{node.language}--{node.direction}'
    if isinstance(node, Literal) and node.datatype:
        decoded = decode_dirlang_datatype(node.datatype)
        if decoded is not None:
            language, direction = decoded
            escaped = str(node).replace('\\', '\\\\').replace('"', '\\"')
            return f'"{escaped}"@{language}--{direction}'
    if isinstance(node, BNode) and skolemize_bnodes:
        return skolemize_bnode(node).n3()
    return node.n3()


# ---------------------------------------------------------------------------
# Blank-node skolemization (native backend only)
# ---------------------------------------------------------------------------

def skolemize_bnode(node: BNode) -> URIRef:
    """Map a blank node to a stable URI for the wire, deterministically from
    its own internal label - no registry needed, since a BNode's label is
    already a stable, globally-unique-within-process string and every write
    involving "the same" blank node is always the same Python BNode object
    (or an equal one carrying the same label).

    Why this exists at all: StarLayerGraph._native_add() issues one SPARQL
    Update request per triple (see its own docstring), and SPARQL 1.1 Update
    scopes blank-node labels to the single request they appear in - reusing
    a label like ``_:b`` across two separate INSERT requests does *not*
    refer to the same node on the far side, it mints two unrelated ones.
    Skolemizing to a URI sidesteps this request-scoping entirely - a URI
    means the same thing in every request.

    This is also what makes an anonymous reifier's own BNode identity (see
    starlayer.graph.parsers.turtle_parser._skolemize_encoding - anonymous
    reifiers are ordinary BNodes, not a separate skolemization scheme of
    their own) survive a native-backend round trip for free: it's just
    another BNode as far as this function is concerned.

    Reversed by deskolemize_bnode() on every read path.

    Args:
        node: The blank node to skolemize.

    Returns:
        A stable URIRef under BN_NS encoding node's label.
    """
    return URIRef(BN_NS + str(node))


def deskolemize_bnode(node: Node | TripleTerm) -> Node | TripleTerm:
    """Reverse skolemize_bnode(): a BN_NS URIRef becomes the BNode with the
    same label back; any other value passes through unchanged. Recurses into
    a TripleTerm's own subject/object so a blank node nested inside one
    (e.g. ``<<( _:b :r :o )>>``) is restored too."""
    if isinstance(node, TripleTerm):
        return TripleTerm(deskolemize_bnode(node.subject), node.predicate, deskolemize_bnode(node.object))
    if isinstance(node, URIRef) and str(node).startswith(BN_NS):
        return BNode(str(node)[len(BN_NS):])
    return node


# ---------------------------------------------------------------------------
# JSON result parsing
# ---------------------------------------------------------------------------

def _parse_json_term(term_dict: dict):
    """Convert a SPARQL JSON binding term to an rdflib node, DirLangString, or TripleTerm."""
    t = term_dict['type']
    if t == 'uri':
        value = term_dict['value']
        # Reverse skolemize_bnode(): a binding that resolves to one of our
        # own BN_NS URIs is a blank node we wrote, not a real URI - see
        # skolemize_bnode()'s docstring for why writes go out this way.
        if value.startswith(BN_NS):
            return BNode(value[len(BN_NS):])
        return URIRef(value)
    if t == 'bnode':
        return BNode(term_dict['value'])
    if t in ('literal', 'typed-literal'):
        lang  = term_dict.get('xml:lang')
        dtype = term_dict.get('datatype')
        # SPARQL 1.2 JSON Results' base-direction key is "its:dir", matching
        # RDF/XML 1.2's own attribute name. Returned directly as a
        # DirLangString rather than the internal dirlang: Literal encoding,
        # since native-backend results never round-trip through
        # StarLayerGraph._restore() - same as how a "triple" binding below
        # returns a TripleTerm directly.
        direction = term_dict.get('its:dir')
        if lang and direction:
            from starlayer.graph.model.dirlangstring import DirLangString
            return DirLangString(term_dict['value'], lang, direction)
        if lang:
            return Literal(term_dict['value'], lang=lang)
        if dtype:
            literal = Literal(term_dict['value'], datatype=URIRef(dtype))
            if dtype == str(XSD.decimal):
                # Corrects a canonicalization defect in Oxigraph's own
                # decimal output: a whole-number xsd:decimal result (from
                # CEIL/FLOOR/ROUND/division, or simply stored and read back)
                # comes back lexically as e.g. "4"/"123" rather than XSD
                # 1.1's canonical "4.0"/"123.0" (a decimal point with at
                # least one digit each side) - the same whole-number
                # trailing-".0" defect this project's own
                # operator_patches.py already works around for rdflib's
                # internal evaluator, reused here for the native backend's
                # *results* specifically. This corrects Oxigraph's own
                # output formatting on the way into a Python Literal, not
                # the query or stored data sent to it, so it doesn't
                # conflict with this module's otherwise-zero-rewriting
                # design (see module docstring). A no-op for any lexical
                # form that already has a "." (every other engine, and
                # Oxigraph itself for non-whole-number results).
                from starlayer.graph.query.operator_patches import (
                    _canonicalize_decimal_lexical_form,
                )

                literal = _canonicalize_decimal_lexical_form(literal)
            return literal
        return Literal(term_dict['value'])
    if t == 'triple':
        v = term_dict['value']
        s = _parse_json_term(v['subject'])
        p = _parse_json_term(v['predicate'])
        o = _parse_json_term(v['object'])
        try:
            return TripleTerm(s, p, o)
        except ValueError as e:
            # RDF 1.2 forbids a triple term's own subject/predicate from
            # itself being a triple term or a Literal (ttSubject ::= iri |
            # BlankNode, verb ::= iri) - TripleTerm.__init__ enforces this,
            # but a native engine can still hand back a triple-term-shaped
            # result that violates it, so this is a real data problem
            # arriving over the wire, not just malformed input to reject up
            # front. Re-raised (not swallowed) as a clear, single error
            # identifying the actual cause, instead of propagating
            # TripleTerm's own bare ValueError: that failure happens before
            # any of TripleTerm's __slots__ are assigned, so anything that
            # tries to repr() the half-constructed instance afterward
            # (pytest's own traceback formatting, notably) hits a *second*,
            # unrelated AttributeError on top of the first, obscuring what
            # actually went wrong.
            raise ValueError(
                f'native backend returned a triple term with an invalid RDF 1.2 subject or '
                f'predicate (subject={s!r}, predicate={p!r}, object={o!r}) - {e}. This '
                f'indicates a spec-conformance bug in the native SPARQL engine, not in this '
                f'library.'
            ) from e
    raise ValueError(f'Unknown SPARQL JSON term type: {t!r}')


def _parse_bindings(data: dict) -> tuple[list[Variable], list[dict]]:
    """Parse the bindings section of a SPARQL JSON SELECT response."""
    vars_ = [Variable(v) for v in data['head']['vars']]
    bindings = []
    for row in data['results']['bindings']:
        binding = {}
        for v in vars_:
            raw = row.get(str(v))   # str(Variable('o')) == 'o', not '?o'
            if raw is not None:
                binding[v] = _parse_json_term(raw)
        bindings.append(binding)
    return vars_, bindings


# ---------------------------------------------------------------------------
# HTTP execution
# ---------------------------------------------------------------------------

def http_select(query_url: str, sparql: str, extra_headers: dict | None = None) -> tuple[list, list]:
    """Execute a SPARQL SELECT and return (vars, bindings).

    Handles "type":"triple" in results — converting them to TripleTerm objects.
    """
    headers = {
        'Content-Type': 'application/sparql-query',
        'Accept': 'application/sparql-results+json',
    }
    if extra_headers:
        headers.update(extra_headers)
    resp = requests.post(query_url, data=sparql.encode('utf-8'), headers=headers, timeout=30)
    resp.raise_for_status()
    return _parse_bindings(resp.json())


def http_construct(query_url: str, sparql: str, extra_headers: dict | None = None) -> tuple[bytes, str]:
    """Execute a SPARQL CONSTRUCT or DESCRIBE and return (body_bytes, content_type).

    Requests Turtle, which the endpoint supports and which
    StarLayerGraph.parse() handles natively including triple-term syntax.
    """
    headers = {
        'Content-Type': 'application/sparql-query',
        'Accept': 'text/turtle',
    }
    if extra_headers:
        headers.update(extra_headers)
    resp = requests.post(query_url, data=sparql.encode('utf-8'), headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.content, resp.headers.get('Content-Type', 'text/turtle')


def http_update(update_url: str, sparql: str, extra_headers: dict | None = None) -> None:
    """Execute a SPARQL UPDATE against the endpoint."""
    headers = {'Content-Type': 'application/sparql-update'}
    if extra_headers:
        headers.update(extra_headers)
    resp = requests.post(update_url, data=sparql.encode('utf-8'), headers=headers, timeout=30)
    resp.raise_for_status()


def http_ask(query_url: str, sparql: str, extra_headers: dict | None = None) -> bool:
    """Execute a SPARQL ASK and return the boolean result."""
    headers = {
        'Content-Type': 'application/sparql-query',
        'Accept': 'application/sparql-results+json',
    }
    if extra_headers:
        headers.update(extra_headers)
    resp = requests.post(query_url, data=sparql.encode('utf-8'), headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json().get('boolean', False)


def build_result(vars_: list, bindings: list) -> Result:
    """Construct an rdflib Result object from pre-parsed SELECT data."""
    r = Result('SELECT')
    r.vars = vars_
    r.bindings = bindings
    return r


# ---------------------------------------------------------------------------
# Store resolution and dataset/graph-shared dispatch
# ---------------------------------------------------------------------------

def resolve_store_http(store, backend: str) -> tuple:
    """Return (query_url, update_url, extra_headers) from a native-backend store.

    SPARQLUpdateStore pre-encodes credentials as an Authorization header in
    store.kwargs['headers'] rather than exposing a raw auth tuple. Shared by
    StarLayerGraph and StarLayerDataset - a dataset's per-context
    StarLayerGraphs all share the same underlying store (see
    StarLayerDataset.get_context()), so there is exactly one store to
    resolve per dataset, same as for a single graph.

    Args:
        store: The native-backend store to resolve HTTP endpoints from.
        backend: The backend identifier, used only for the error message.

    Returns:
        A (query_url, update_url, extra_headers) tuple.

    Raises:
        RuntimeError: If store does not expose HTTP endpoints (e.g. an
            in-memory store).
    """
    q = getattr(store, 'query_endpoint', None)
    u = getattr(store, 'update_endpoint', None)
    if not q or not u:
        raise RuntimeError(
            f"backend={backend!r} requires a store with query_endpoint "
            f"and update_endpoint (e.g. SPARQLUpdateStore); "
            f"got {type(store).__name__}"
        )
    extra_headers = getattr(store, 'kwargs', {}).get('headers', {})
    return q, u, extra_headers


def check_native_version_conformance(text: str) -> None:
    """Run the same SPARQL12ConformanceWarning check the in-memory backend's
    rewrite pipeline runs, for a native (rdf-1.2) backend's raw SPARQL text.

    The native backend sends text straight through to a real endpoint via
    HTTP with zero rewriting (see this module's docstring) - correct, since
    Fuseki/Oxigraph both understand VERSION natively and execute a
    VERSION-declared query normally regardless of a conformance mismatch.
    But neither surfaces any warning back to the caller for a mismatch -
    both just return a normal 200 response with no signal anywhere in it.
    Without this check, a native-backend graph or dataset would silently
    never emit SPARQL12ConformanceWarning at all, while the default
    in-memory backend does for the identical query - an inconsistency
    between backends this project otherwise takes care to avoid (see
    tests/integration/test_cross_backend_parity.py). Only the *warning* is
    replicated here, never the VERSION-stripping - the native endpoint
    needs to see the directive itself, unlike rdflib's SPARQL 1.1 parser.

    Args:
        text: The raw SPARQL query or update text to check.
    """
    from starlayer.graph.model.conformance import (
        SPARQL12ConformanceWarning,
        check_version_conformance,
    )
    from starlayer.graph.query.version_directive import strip_version_directive

    _, declared_version = strip_version_directive(text)
    if declared_version is None:
        return
    check_version_conformance(
        declared_version,
        uses_triple_term=bool(
            "<<(" in text or re.search(r'<<[^(]|\{\|', text) or '~' in text
        ),
        uses_dirlangstring='--' in text,
        context='SPARQL query',
        warning_class=SPARQL12ConformanceWarning,
    )


def _in_process(store) -> bool:
    """True when ``store`` is an in-process Oxigraph (``oxrdflib``'s
    ``OxigraphStore``) rather than a remote HTTP endpoint. See
    ``native_oxigraph.py``."""
    return type(store).__name__ == 'OxigraphStore' and hasattr(type(store), '_inner')


def new_graph_like(store, backend: str):
    """A new, empty ``StarLayerGraph`` of the same kind as one backed by
    ``store`` - the "derived graphs are created like their source" rule.

    An in-process Oxigraph source gets a fresh, independent in-process
    Oxigraph (a new path-less ``pyoxigraph.Store``) with the same
    representation; anything else - the default in-memory store, a remote
    HTTP endpoint (a new remote database can't be minted from here), SQLAlchemy,
    etc. - gets an ordinary in-memory ``StarLayerGraph``, exactly as before.
    """
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph

    if _in_process(store):
        import pyoxigraph
        from oxrdflib import OxigraphStore
        return StarLayerGraph(store=OxigraphStore(store=pyoxigraph.Store()), backend=backend)
    return StarLayerGraph()


def execute_select(store, backend: str, sparql: str) -> tuple[list, list]:
    """Run a SPARQL SELECT against a native-backend store - remote HTTP or
    in-process Oxigraph - returning (vars, bindings) either way."""
    if _in_process(store):
        from starlayer.graph.backends.native_oxigraph import ox_select
        return ox_select(store, sparql)
    q_url, _, hdrs = resolve_store_http(store, backend)
    return http_select(q_url, sparql, hdrs)


def execute_ask(store, backend: str, sparql: str) -> bool:
    """Run a SPARQL ASK against a native-backend store (HTTP or in-process)."""
    if _in_process(store):
        from starlayer.graph.backends.native_oxigraph import ox_ask
        return ox_ask(store, sparql)
    q_url, _, hdrs = resolve_store_http(store, backend)
    return http_ask(q_url, sparql, hdrs)


def execute_update(store, backend: str, sparql: str) -> None:
    """Run a SPARQL UPDATE against a native-backend store (HTTP or in-process)."""
    if _in_process(store):
        from starlayer.graph.backends.native_oxigraph import ox_update
        ox_update(store, sparql)
        return
    _, u_url, hdrs = resolve_store_http(store, backend)
    http_update(u_url, sparql, hdrs)


def execute_construct(store, backend: str, sparql: str):
    """Run a SPARQL CONSTRUCT/DESCRIBE against a native-backend store (HTTP or
    in-process), returning a deskolemized StarLayerGraph of the results."""
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph

    if _in_process(store):
        from starlayer.graph.backends.native_oxigraph import ox_construct
        # Results are created like the source (in-process Oxigraph in, Oxigraph
        # out) and loaded in one batch, not one INSERT per triple.
        g = new_graph_like(store, backend)
        triples = list(ox_construct(store, sparql))
        if g._is_native:
            g._native_add_many(triples)
        else:
            for t in triples:
                g.add(t)
        return g
    q_url, _, hdrs = resolve_store_http(store, backend)
    body, _ = http_construct(q_url, sparql, hdrs)
    g = StarLayerGraph()
    g.parse(data=body.decode('utf-8'), format='turtle12')
    # Reverse skolemize_bnode(): a CONSTRUCT template can echo back a stored
    # triple containing one of our own BN_NS URIs (a blank node we skolemized
    # on write - see skolemize_bnode()'s docstring), which the Turtle parser
    # has no way to recognize as anything but an ordinary URIRef.
    deskolemized = StarLayerGraph()
    for s, p, o in g.triples((None, None, None)):
        deskolemized.add((deskolemize_bnode(s), p, deskolemize_bnode(o)))
    return deskolemized


def native_query(store, backend: str, query_object: Any, processor: str = 'sparql',
                 result: str = 'sparql', initNs: dict | None = None,
                 initBindings: dict | None = None, use_store_provided: bool = True,
                 **kwargs):
    """Execute a SPARQL query directly against a native-backend HTTP store.

    Shared by StarLayerGraph._native_query()-equivalent dispatch and
    StarLayerDataset's - a native-backed dataset's contexts all share one
    store, and this function sends its query text straight through with no
    per-graph scoping of its own (scoping comes entirely from whatever GRAPH
    clauses the query text itself contains), so the exact same HTTP call is
    correct whether it originated from a single StarLayerGraph or a
    StarLayerDataset spanning many named graphs.

    Args:
        store: The native-backend store to resolve HTTP endpoints from
            (see resolve_store_http()).
        backend: The backend identifier (e.g. 'rdf-1.2'), passed through
            to resolve_store_http() for its error message only.
        query_object: The SPARQL query text.
        processor: Unused by this function; accepted for interface parity
            with rdflib's own Graph.query().
        result: Unused by this function; accepted for interface parity
            with rdflib's own Graph.query().
        initNs: Unused by this function; accepted for interface parity
            with rdflib's own Graph.query().
        initBindings: Unused by this function; accepted for interface
            parity with rdflib's own Graph.query().
        use_store_provided: Unused by this function; accepted for
            interface parity with rdflib's own Graph.query().
        **kwargs: Unused; accepted for interface parity with rdflib's own
            Graph.query().

    Returns:
        An rdflib.query.Result - ASK (askAnswer set), CONSTRUCT/DESCRIBE
        (graph set, blank nodes deskolemized), or SELECT (vars/bindings
        set).
    """
    if isinstance(query_object, str):
        check_native_version_conformance(query_object)

    sparql = query_object

    # Detect query type by searching for the keyword — startswith() fails when
    # PREFIX declarations appear before ASK / CONSTRUCT / DESCRIBE.
    _qt = re.search(r'\b(ASK|CONSTRUCT|DESCRIBE)\b', sparql, re.IGNORECASE)
    query_type = _qt.group(1).upper() if _qt else 'SELECT'

    if query_type == 'ASK':
        from rdflib.query import Result as RDFResult
        r = RDFResult('ASK')
        r.askAnswer = execute_ask(store, backend, sparql)
        return r

    if query_type in ('CONSTRUCT', 'DESCRIBE'):
        from rdflib.query import Result as RDFResult

        deskolemized = execute_construct(store, backend, sparql)
        r = RDFResult('CONSTRUCT')
        r.graph = deskolemized
        return r

    vars_, bindings = execute_select(store, backend, sparql)
    return build_result(vars_, bindings)


def native_update(store, backend: str, update_object: Any) -> None:
    """Execute a SPARQL UPDATE directly against a native-backend HTTP store,
    bypassing rdflib's own store dispatch entirely.

    Needed not just for the rdf-1.2 backend (which understands the update
    text unmodified) but also for any *rdf-1.1* dataset backed by a remote
    store: rdflib's ``Dataset(store=...).update()`` always wraps the whole
    update text in an extra ``GRAPH <urn:x-rdflib:default> { }`` block
    (``SPARQLStore._is_contextual()`` doesn't recognize ``Dataset``'s
    default-graph sentinel as exempt - it's a URIRef, which subclasses str,
    and only the literal string ``"__UNION__"`` is special-cased), which
    nests illegally around any update that already has its own
    ``GRAPH <uri> { }`` clause - the normal way to target a named graph from
    dataset-level SPARQL. Both Oxigraph and Fuseki reject the resulting
    double-nested GRAPH clause outright (HTTP 400), even for a plain
    ``INSERT DATA { GRAPH <uri> {...} }`` with no triple terms involved at
    all. Going straight over HTTP sidesteps rdflib's dispatch (and this
    bug) entirely, for both backends.

    Args:
        store: The native-backend store to resolve HTTP endpoints from
            (see resolve_store_http()).
        backend: The backend identifier - 'rdf-1.2' sends update_object
            straight through unmodified; any other value is treated as a
            remote rdf-1.1 endpoint and update_object is first lowered to
            plain SPARQL 1.1 text.
        update_object: The SPARQL UPDATE text to execute.
    """
    text = update_object
    if backend == 'rdf-1.2':
        if isinstance(text, str):
            check_native_version_conformance(text)
    else:
        # A remote rdf-1.1 endpoint has no notion of SPARQL 1.2 triple-term
        # syntax, so text containing it must become plain SPARQL 1.1 first.
        # Goes through the same real grammar/algebra pipeline as everywhere
        # else in this project (starlayer.sparql's prepare_update_12 ->
        # update_to_rdf11), then all the way to genuine text via
        # rdf11_update_to_sparql11_text - needed specifically here (unlike
        # StarLayerGraph/StarLayerDataset's own local-store update path,
        # which hands the lowered Update *object* straight to rdflib)
        # because this function POSTs raw text directly over HTTP, bypassing
        # rdflib's store dispatch entirely (see this function's own
        # docstring for why). Text with no SPARQL 1.2 syntax at all still
        # round-trips correctly through this - it's just a plain SPARQL 1.1
        # update by the time it comes back out.
        if isinstance(text, str):
            from starlayer.graph.query.version_directive import (
                contains_triple_term,
                strip_version_directive,
            )
            from starlayer.sparql.lower_rdf11 import (
                rdf11_update_to_sparql11_text,
                update_to_rdf11,
            )
            from starlayer.sparql.parse12 import prepare_update_12
            stripped_text, declared_version = strip_version_directive(text)
            prepared_12 = prepare_update_12(stripped_text)
            if declared_version is not None:
                from starlayer.graph.model.conformance import (
                    SPARQL12ConformanceWarning,
                    check_version_conformance,
                )
                check_version_conformance(
                    declared_version,
                    uses_triple_term=contains_triple_term(prepared_12.algebra),
                    uses_dirlangstring='--' in stripped_text,
                    context='SPARQL update',
                    warning_class=SPARQL12ConformanceWarning,
                )
            rdf_graph, root = update_to_rdf11(prepared_12)
            text = rdf11_update_to_sparql11_text(rdf_graph, root)
    execute_update(store, backend, text)
