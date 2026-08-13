"""
starlayergraph.backends.native

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
    check_native_version_conformance(text) → None (may emit RDF12ConformanceWarning)
    native_query(store, backend, query_object, ...) → rdflib.query.Result
    native_update(store, backend, update_object)    → None

The endpoint (e.g. Apache Jena Fuseki 5.5+, Oxigraph) speaks SPARQL 1.2
natively - triple-term syntax (<<( s p o )>>), TRIPLE()/isTRIPLE(), and the
base-direction functions (LANGDIR/hasLANGDIR/STRLANGDIR/LANG/hasLANG) are all
sent straight through with no rewriting, confirmed 2026-07-16 against live
Fuseki 5.5.0 and Oxigraph 0.5.9. This is a different code path from the
default rdf-1.1 backend's SPARQL 1.2 handling (starsparql's
parse_update_12/update_to_rdf11/rdf11_update_to_sparql11_text pipeline,
see native_update() below), which never runs for a native-backend
query/update - see native_query()/native_update() below, and
StarLayerGraph._native_add()/_native_triples() for the write/read-triples
paths (those stay graph-scoped, using a specific GRAPH <identifier> clause,
so they aren't shared with StarLayerDataset the way query/update are).
"""

from __future__ import annotations

import re

import requests
from rdflib import URIRef, Literal, BNode
from rdflib.namespace import XSD
from rdflib.query import Result
from rdflib.term import Variable

from starlayergraph.model.encoding import BN_NS
from starlayergraph.model.triple import TripleTerm
from starlayergraph.model.dirlangstring import DirLangString


# ---------------------------------------------------------------------------
# Term serialization
# ---------------------------------------------------------------------------

def sparql_term(node, skolemize_bnodes: bool = True) -> str:
    """Serialize an RDF node to its SPARQL inline string.

    TripleTerms are rendered as <<( s p o )>>. A DirLangString is rendered as
    the real "text"@lang--dir lexical form - unlike TripleTerm's tt:HASH
    encoding, the native RDF 1.2 endpoint understands this syntax directly, so
    no internal encoding is involved here at all. All other nodes use
    rdflib's .n3() which produces correct SPARQL syntax - except BNode, which
    by default is skolemized to a stable BN_NS URI first (see
    skolemize_bnode()'s docstring for why: a blank node's own SPARQL syntax
    label is *not* enough to keep its identity across separate HTTP
    requests).

    skolemize_bnodes=False renders a real, unskolemized blank node instead -
    only safe when every triple that might share this exact BNode object is
    going out together in the *same* HTTP request (see
    StarLayerGraph._native_add_many(), the only caller that passes this),
    since that's the one case SPARQL 1.1 Update's per-request blank-node
    scoping doesn't bite - and it avoids skolemize_bnode()'s own cost (the
    endpoint no longer recognizing it as a real blank node for ORDER BY /
    isBLANK()) for exactly the triples that don't need to pay it.
    """
    if isinstance(node, TripleTerm):
        s = sparql_term(node.subject, skolemize_bnodes)
        p = sparql_term(node.predicate, skolemize_bnodes)
        o = sparql_term(node.object, skolemize_bnodes)
        return f'<<( {s} {p} {o} )>>'
    if isinstance(node, DirLangString):
        escaped = node.value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"@{node.language}--{node.direction}'
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
    Confirmed empirically against live Oxigraph: ``g.add((b, :r, :o1));
    g.add((b, :r, :o2))`` for one Python BNode produced two different
    store-side blank nodes, and a query joining on the shared subject
    returned nothing. Skolemizing to a URI sidesteps request-scoping
    entirely - a URI means the same thing in every request, exactly like
    this project's existing RR_NS scheme skolemizes anonymous reifiers for
    the same underlying reason (see encoding.py's module docstring).
    Reversed by deskolemize_bnode() on every read path.
    """
    return URIRef(BN_NS + str(node))


def deskolemize_bnode(node):
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
        # Confirmed 2026-07-16 against live Fuseki 5.5.0 and Oxigraph 0.5.9
        # (both agree independently): the SPARQL 1.2 JSON Results key is
        # "its:dir", mirroring the its:dir attribute RDF/XML 1.2 also uses -
        # not "direction", which was an earlier unverified guess. Returned
        # directly as a DirLangString rather than the internal dirlang:
        # Literal encoding, since native-backend results never round-trip
        # through StarLayerGraph._restore() - same as how a "triple" binding
        # below returns a TripleTerm directly.
        direction = term_dict.get('its:dir')
        if lang and direction:
            from starlayergraph.model.dirlangstring import DirLangString
            return DirLangString(term_dict['value'], lang, direction)
        if lang:
            return Literal(term_dict['value'], lang=lang)
        if dtype:
            literal = Literal(term_dict['value'], datatype=URIRef(dtype))
            if dtype == str(XSD.decimal):
                # Confirmed against live Oxigraph 0.5.x specifically (not
                # Fuseki/Jena-ARQ, which already returns the canonical form):
                # a whole-number xsd:decimal computed by Oxigraph's own
                # SPARQL engine (CEIL/FLOOR/ROUND/division, or simply stored
                # and read back) comes back lexically as e.g. "4"/"123"
                # rather than XSD 1.1's mandatory canonical "4.0"/"123.0"
                # (a decimal point with at least one digit each side) - see
                # docs/rdflib-upstream-issues.md Issue 2, the same defect
                # this project's own operator_patches.py already works
                # around for rdflib's *internal* evaluator. Reuses that same
                # helper here for the native backend's *results* specifically
                # - this corrects Oxigraph's own output formatting on the
                # way into a Python Literal, not the query or stored data
                # sent to it, so it doesn't conflict with this module's
                # otherwise-zero-rewriting design (see module docstring).
                # A no-op for any lexical form that already has a "." (every
                # other engine, and Oxigraph itself for non-whole-number
                # results).
                from starlayergraph.query.operator_patches import _canonicalize_decimal_lexical_form

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
            # A conformant engine should never produce this (RDF 1.2: a
            # triple term's own subject may never itself be a triple term -
            # TripleTerm.__init__ enforces the same rule this library uses
            # internally). Confirmed reproducible against live Fuseki 5.5.0
            # specifically: TRIPLE(?subject, ...) fails to validate a
            # triple-term-valued `subject` argument the way it already
            # validates `predicate` (see docs/fuseki-upstream-issues.md
            # Issue 1) - so a native backend can genuinely hand this back as
            # a query *result*, not just reject it as malformed input.
            # Re-raised (not swallowed - this is a real data problem, not
            # something safe to silently paper over) as a clear, single
            # error identifying the actual cause, instead of propagating
            # TripleTerm's own bare ValueError: that failure happens before
            # any of TripleTerm's __slots__ are assigned, so anything that
            # tries to repr() the half-constructed instance afterward
            # (pytest's own traceback formatting, notably) hits a *second*,
            # unrelated AttributeError on top of the first, obscuring what
            # actually went wrong.
            #
            # Not just the nested-triple-term case: TripleTerm.__init__ also
            # rejects a Literal-valued subject/predicate (the fuller RDF 1.2
            # rule, ttSubject ::= iri | BlankNode, verb ::= iri) - confirmed
            # via the same live Fuseki bug that a Literal-valued `subject`
            # argument to TRIPLE() is accepted just as wrongly as a
            # triple-term-valued one.
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
    store.kwargs['headers'] rather than exposing a raw auth tuple. Raises
    RuntimeError if the store does not expose HTTP endpoints (e.g. in-memory
    stores). Shared by StarLayerGraph and StarLayerDataset - a dataset's
    per-context StarLayerGraphs all share the same underlying store (see
    StarLayerDataset.get_context()), so there is exactly one store to resolve
    per dataset, same as for a single graph.
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
    """Run the same RDF12ConformanceWarning check the in-memory backend's
    rewrite pipeline runs, for a native (rdf-1.2) backend's raw SPARQL text.

    The native backend sends text straight through to a real endpoint via
    HTTP with zero rewriting (see this module's docstring) - correct, since
    Fuseki/Oxigraph understand VERSION natively (confirmed live 2026-07-17:
    both execute a VERSION-declared query normally regardless of a
    conformance mismatch, HTTP 200). But neither surfaces any warning back
    to the caller for a mismatch - confirmed the same day, sending VERSION
    "1.2-basic" plus a <<( )>> pattern to both got a normal 200 response
    with no signal anywhere in it. Without this check, a native-backend
    graph or dataset would silently never emit RDF12ConformanceWarning at
    all, while the default in-memory backend does for the identical query -
    an inconsistency between backends this project otherwise takes care to
    avoid (see tests/integration/test_cross_backend_parity.py). Only the
    *warning* is replicated here, never the VERSION-stripping - the native
    endpoint needs to see the directive itself, unlike rdflib's SPARQL 1.1
    parser.
    """
    from starlayergraph.query.version_directive import strip_version_directive
    from starlayergraph.model.conformance import check_version_conformance

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
    )


def native_query(store, backend: str, query_object, processor='sparql', result='sparql',
                 initNs=None, initBindings=None, use_store_provided=True, **kwargs):
    """Execute a SPARQL query directly against a native-backend HTTP store.

    Shared by StarLayerGraph._native_query()-equivalent dispatch and
    StarLayerDataset's - a native-backed dataset's contexts all share one
    store, and this function sends its query text straight through with no
    per-graph scoping of its own (scoping comes entirely from whatever GRAPH
    clauses the query text itself contains), so the exact same HTTP call is
    correct whether it originated from a single StarLayerGraph or a
    StarLayerDataset spanning many named graphs.
    """
    q_url, _, hdrs = resolve_store_http(store, backend)
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
        r.askAnswer = http_ask(q_url, sparql, hdrs)
        return r

    if query_type in ('CONSTRUCT', 'DESCRIBE'):
        from rdflib.query import Result as RDFResult
        from starlayergraph.graph.starlayer_graph import StarLayerGraph
        body, _ = http_construct(q_url, sparql, hdrs)
        g = StarLayerGraph()
        g.parse(data=body.decode('utf-8'), format='turtle12')
        # Reverse skolemize_bnode(): a CONSTRUCT template can echo back a
        # stored triple containing one of our own BN_NS URIs (a blank node
        # we skolemized on write - see skolemize_bnode()'s docstring), which
        # the Turtle parser above has no way to recognize as anything but an
        # ordinary URIRef.
        deskolemized = StarLayerGraph()
        for s, p, o in g.triples((None, None, None)):
            deskolemized.add((deskolemize_bnode(s), p, deskolemize_bnode(o)))
        r = RDFResult('CONSTRUCT')
        r.graph = deskolemized
        return r

    vars_, bindings = http_select(q_url, sparql, hdrs)
    return build_result(vars_, bindings)


def native_update(store, backend: str, update_object) -> None:
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
    dataset-level SPARQL. Confirmed via real Oxigraph and Fuseki testing: a
    plain ``INSERT DATA { GRAPH <uri> {...} }`` with no triple terms at all
    got a 400 from both. Going straight over HTTP sidesteps rdflib's
    dispatch (and this bug) entirely, for both backends.
    """
    _, u_url, hdrs = resolve_store_http(store, backend)
    text = update_object
    if backend == 'rdf-1.2':
        if isinstance(text, str):
            check_native_version_conformance(text)
    else:
        # A remote rdf-1.1 endpoint has no notion of SPARQL 1.2 triple-term
        # syntax, so text containing it must become plain SPARQL 1.1 first.
        # Goes through the same real grammar/algebra pipeline as everywhere
        # else in this project (starsparql's prepare_update_12 ->
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
            from starsparql.parse12 import prepare_update_12
            from starsparql.lower_rdf11 import update_to_rdf11, rdf11_update_to_sparql11_text
            prepared_12 = prepare_update_12(text)
            rdf_graph, root = update_to_rdf11(prepared_12)
            text = rdf11_update_to_sparql11_text(rdf_graph, root)
    http_update(u_url, text, hdrs)
