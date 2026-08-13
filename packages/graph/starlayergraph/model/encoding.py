"""
starlayergraph.model.encoding

Shared constants and hash function for the starlayergraph internal graph encoding.

Triple terms    → content-addressed URIRefs under TT_NS (same content = same URI)
Anon reifiers   → sequential URIRefs under RR_NS (each {| |} block is distinct)
DirLangString   → a Literal whose datatype URI under DIRLANG_NS packs the real
                  language tag and base direction (see decode_dirlang_datatype)
"""

import hashlib
from collections import OrderedDict

from rdflib import Literal, URIRef
from rdflib.namespace import RDF, XSD

TT_NS      = 'https://github.com/hidden-graph/starlayergraph/ns/tt#'       # triple-term content-addressed URIs
RR_NS      = 'https://github.com/hidden-graph/starlayergraph/ns/rr#'       # anonymous reifier URIs
DIRLANG_NS = 'https://github.com/hidden-graph/starlayergraph/ns/dirlang#'  # dirLangString datatype encoding
BN_NS      = 'https://github.com/hidden-graph/starlayergraph/ns/bn#'       # native-backend blank-node skolemization

# Predicates used in the internal TripleTerm URIRef encoding - shared by
# StarLayerGraph and StarLayerDataset's _is_encoding_triple() checks and by
# restore_select_bindings() below.
ENCODING_PREDS = frozenset({RDF.subject, RDF.predicate, RDF.object})


def term_key(term) -> str:
    """Canonical string form of an RDF term/pre-resolved URI string, for use
    as one of tt_hash's three inputs.

    NOT the same as plain str(term) - confirmed a real, reproducible bug via
    a W3C SPARQL 1.2 test (triple-on-str-literals): str(Literal) always
    returns just the lexical form, dropping BOTH the language tag and the
    datatype entirely (str(Literal("c")) == str(Literal("c", lang="nl")) ==
    str(Literal("c", datatype=<dirlang-uri>)) == "c"), so three genuinely
    different triple-term object values all hashed to the *same* tt:HASH
    URI - not just a comparison false-positive, a real content-addressing
    collision that silently overwrote _TT_HASH_MEMO's remembered (s,p,o)
    for that URI with whichever of the three was computed last, corrupting
    the other two. `.n3()` includes the datatype/language, correctly
    distinguishing them - safe to switch to uniformly (not just for
    Literals) per tt_hash's own docstring ("safe to change without a
    migration story"). Passing through an already-string value unchanged
    supports the common "already resolved to a tt: URI string" case every
    caller also needs (a nested triple term's own hash, computed via plain
    string concatenation, e.g. TT_NS + local_hash - not an rdflib term at
    all). Checked via `isinstance(term, Node)`, NOT `isinstance(term, str)`:
    URIRef/BNode/Literal are ALL str subclasses in rdflib, so a bare
    `isinstance(term, str)` check would catch them too and skip `.n3()`
    entirely, reintroducing the exact bug this function exists to fix.
    """
    from rdflib.term import Node
    if isinstance(term, Node):
        return term.n3()
    return str(term)


def tt_hash(s_str: str, p_str: str, o_str: str) -> str:
    """Return a 16-hex-char content-addressed ID for a triple term.

    Inputs are the canonical string representations of the resolved nodes
    (full URIs, bnode IDs, or literal N3 strings).  Nested triple terms
    contribute their full TT_NS URI as the s/o string, so nesting is
    reflected in the hash.

    16 hex chars = 64 bits, keeping birthday-bound collision risk negligible
    even for graphs with heavy reification (an 8-char/32-bit prefix becomes
    non-negligible around ~65,000 distinct triple terms in one process - a
    plausible count for this library's primary use case). Safe to change
    without a migration story: the hash is recomputed fresh from content on
    every intern, never persisted as a stable external identifier - every
    RDF 1.2 serializer emits <<( )>> syntax, never a raw tt:HASH URI.
    """
    return hashlib.sha256(
        f'{s_str}\x00{p_str}\x00{o_str}'.encode()
    ).hexdigest()[:16]


# Process-wide memo: tt:HASH URIRef -> (s, p, o) components, populated by the
# registered TT_HASH_FN SPARQL function (starlayergraph.query.custom_functions)
# whenever it computes a hash for a fully-ground TRIPLE()/<<( )>> value used
# as a plain expression (SELECT projection, BIND, FILTER) rather than a
# graph-pattern term - a value that, like a literal IRI, is constructed on
# the spot and never needs to have been written to any graph. Since it was
# never written, no StarLayerGraph's own _tt_nodes registry has it, so
# StarLayerGraph._restore() falls back to this memo to still reconstruct a
# proper TripleTerm instead of leaking the raw internal URIRef to the caller.
#
# Sharing this across every graph and query in the process is correct, not a
# leak: tt_hash is a pure, deterministic function of (s, p, o), so what a
# given hash "means" doesn't depend on which graph is asking - the same
# (s, p, o) always hashes to the same URI everywhere, and a graph that has
# never seen that URI still means the same thing by it as one that has.
#
# Bounded LRU rather than a plain dict, though: correctness of *what a hash
# means* doesn't bound how much memory remembering every hash ever computed
# costs. A long-running process issuing many distinct ground TRIPLE()/
# <<( )>> queries would otherwise grow this dict forever. Capped size with
# oldest-first eviction trades "a very old, likely-no-longer-relevant ground
# value might need re-computing/re-remembering via TT_HASH_FN if looked up
# again" for bounded memory - re-computation is just re-running the pure
# hash function, so eviction has no correctness cost, only a cache-miss cost.
_TT_HASH_MEMO_MAXSIZE = 100_000
_TT_HASH_MEMO: OrderedDict = OrderedDict()


def remember_tt_hash(uri: URIRef, s, p, o) -> None:
    """Record that *uri* is the content-addressed hash of triple term (s, p, o)."""
    _TT_HASH_MEMO[uri] = (s, p, o)
    _TT_HASH_MEMO.move_to_end(uri)
    if len(_TT_HASH_MEMO) > _TT_HASH_MEMO_MAXSIZE:
        _TT_HASH_MEMO.popitem(last=False)


def lookup_tt_hash(uri: URIRef):
    """Return the (s, p, o) remembered for *uri* via remember_tt_hash(), or None."""
    value = _TT_HASH_MEMO.get(uri)
    if value is not None:
        _TT_HASH_MEMO.move_to_end(uri)
    return value


def encode_dirlang_datatype(language: str, direction: str) -> URIRef:
    """Return the internal datatype URIRef encoding (language, direction).

    rdflib.Literal(text, lang="en--rtl") raises ValueError - rdflib's langtag
    validator (_is_valid_langtag) has no notion of the RDF 1.2 "--dir" suffix
    and rejects it outright. Validation only fires for the lang= keyword, not
    datatype=, so packing (language, direction) into a synthetic datatype URI
    sidesteps the check entirely while staying self-describing: the URI's
    local name is exactly the real "lang--dir" lexical suffix (RDF 1.2
    Concepts sec 3.4), so decoding is a plain string split, no lookup table.
    """
    return URIRef(f'{DIRLANG_NS}{language}--{direction}')


def decode_dirlang_datatype(datatype) -> tuple[str, str] | None:
    """Return (language, direction) if datatype is a starlayergraph dirlang encoding.

    Returns None for any other datatype (including plain rdf:langString, which
    never reaches here since it's represented via Literal's native lang=).
    """
    s = str(datatype)
    if not s.startswith(DIRLANG_NS):
        return None
    suffix = s[len(DIRLANG_NS):]
    language, sep, direction = suffix.rpartition('--')
    if not sep:
        return None
    return language, direction


_CANONICALIZABLE_NUMERIC_DATATYPES = frozenset({XSD.decimal, XSD.double, XSD.float})


def _canonicalize_numeric_literal(literal: Literal) -> Literal:
    """Reformat a decimal/double/float-typed Literal's lexical form to its
    XSD canonical form. A no-op for anything already canonical, or for any
    other datatype.

    decimal: canonical form requires a decimal point with at least one
    digit on each side (e.g. "42.0", not "42").
    double/float: reformats through Python's own float parsing/repr, which
    - for the ordinary (non-extreme-magnitude) range this is actually used
    for in practice - already produces XSD's own "at least one digit each
    side of a required decimal point" convention (e.g. "123e0" -> "123.0",
    "1.5E2" -> "150.0"); not a full implementation of XSD 1.1's exact
    canonical-form algorithm for every possible magnitude (e.g. very
    large/small values render with Python's "1e+30"-style exponent rather
    than XSD's "1.0E30"), which is a level of fidelity nothing in this
    codebase currently needs.
    """
    dt = literal.datatype
    lex = str(literal)
    if dt == XSD.decimal:
        if "." not in lex:
            return Literal(f"{lex}.0", datatype=dt)
        return literal
    if dt in (XSD.double, XSD.float):
        try:
            val = float(lex)
        except ValueError:
            return literal
        canonical = repr(val)
        if "e" in canonical:
            canonical = canonical.replace("e", "E").replace("E+", "E")
        elif "." not in canonical:
            canonical += ".0"
        if canonical == lex:
            return literal
        return Literal(canonical, datatype=dt)
    return literal


def canonicalize_query_result_value(node):
    """Canonicalize a numeric-XSD-typed Literal's lexical form for a SPARQL
    query *result* value specifically - recurses into a TripleTerm's own
    subject/object components. Deliberately applied only here, at the
    SELECT-result boundary (see restore_select_bindings below) - not
    anywhere data is read verbatim (plain .triples()/_restore() on their
    own): Turtle/N-Triples parsing (parsers.syntax.coerce_object()/
    turtle_parser._to_node()) deliberately preserves a literal's exact
    lexical form as written, since RDF 1.2's own term-equality rules
    require it - see coerce_object()'s own docstring and
    tests/unit/test_syntax.py::TestCoerceObject, both explicit about this
    for the same "123e0" value that motivates this function. A query
    *result*, though, is expected to match what a real conformant engine's
    own query results look like - confirmed via the W3C SPARQL 1.2
    eval-triple-terms/op-2 fixture, whose own expected result canonicalizes
    "123e0" to "123.0" - the same convention already applied to the native
    (Oxigraph) backend's own results (see
    starlayergraph/backends/native.py::_parse_json_term), extended here to the
    in-memory backend's query results specifically.
    """
    from starlayergraph.model.triple import TripleTerm

    if isinstance(node, TripleTerm):
        new_subject = canonicalize_query_result_value(node.subject)
        new_object = canonicalize_query_result_value(node.object)
        if new_subject is node.subject and new_object is node.object:
            # Nothing actually needed canonicalizing - return the original
            # object unchanged rather than an equal-but-fresh one, so its
            # _namespace_manager (set by StarLayerGraph._restore(), used
            # for prefixed-name rendering in .n3()/__str__()) survives.
            # Confirmed a real regression when first tried: rebuilding
            # unconditionally dropped it even when no literal inside needed
            # reformatting, breaking TestQ6::test_tt_str_uses_prefixed_names.
            return node
        result = TripleTerm(new_subject, node.predicate, new_object)
        result._namespace_manager = node._namespace_manager
        return result
    if isinstance(node, Literal) and node.datatype in _CANONICALIZABLE_NUMERIC_DATATYPES:
        return _canonicalize_numeric_literal(node)
    return node


def restore_select_bindings(r, restore_fn) -> None:
    """Post-process a SPARQL SELECT rdflib.query.Result in place: drop rows
    that are purely internal encoding infrastructure, and restore any
    tt:HASH URIRef/dirlang: Literal in the surviving rows to its public
    TripleTerm/DirLangString form via restore_fn - then canonicalize any
    numeric literal's lexical form (see canonicalize_query_result_value)
    now that it's a real value rather than an opaque tt:HASH URI.

    Shared by StarLayerGraph.query() (restore_fn=self._restore, which looks
    up a single graph's own registry) and StarLayerDataset.query()
    (restore_fn=self._restore_any, which searches every cached graph's
    registry) - the row-filtering and restoration shape is identical between
    the two; only how a tt:HASH URIRef gets resolved back to a TripleTerm
    differs, which is exactly what restore_fn parameterizes.

    A row is dropped when it contains both a TT_NS-prefixed URIRef and one of
    the rdf:subject/predicate/object encoding predicates as *values* - such a
    row exists only because a query pattern incidentally matched the raw
    encoding triples (e.g. an unconstrained ``?s ?p ?o``), not because the
    user asked about them.
    """
    r.bindings = [
        {var: canonicalize_query_result_value(restore_fn(row.get(var))) if row.get(var) is not None else None
         for var in r.vars}
        for row in r.bindings
        if not (any(isinstance(v, URIRef) and str(v).startswith(TT_NS)
                    for v in row.values())
                and ENCODING_PREDS.intersection(row.values()))
    ]


def _reencode_tt(tt, out_graph) -> URIRef:
    """Emit tt's rdf:subject/predicate/object encoding triples into
    out_graph (recursively for any nested TripleTerm component) and return
    its content-addressed URI - the write-side mirror of
    StarLayerGraph._intern_tt(), but writing to an arbitrary graph rather
    than `self`, and given an already-fully-resolved TripleTerm (no nested
    tt:HASH URIRefs left to look up) rather than one that might still
    contain them. See inject_missing_tt_encoding()'s docstring for why this
    exists.
    """
    from starlayergraph.model.triple import TripleTerm
    s_n = _reencode_tt(tt.subject, out_graph) if isinstance(tt.subject, TripleTerm) else tt.subject
    o_n = _reencode_tt(tt.object, out_graph) if isinstance(tt.object, TripleTerm) else tt.object
    uri = URIRef(TT_NS + tt_hash(term_key(s_n), term_key(tt.predicate), term_key(o_n)))
    out_graph.add((uri, RDF.subject, s_n))
    out_graph.add((uri, RDF.predicate, tt.predicate))
    out_graph.add((uri, RDF.object, o_n))
    return uri


def inject_missing_tt_encoding(graph, restore_fn) -> None:
    """Scan a freshly-built CONSTRUCT result graph for any tt:HASH URIRef
    that appears with no rdf:subject/predicate/object encoding triples of
    its own already in `graph`, and - wherever `restore_fn` (the querying
    graph/dataset's own ``_restore``/``_restore_any``) can still resolve it
    - inject those triples so the value survives being wrapped in
    ``StarLayerGraph.from_rdflib()`` afterwards.

    Why this is needed: a CONSTRUCT template can embed a tt:HASH URIRef that
    was never freshly computed by this query at all - just read straight off
    an existing WHERE-clause binding, e.g. ``BIND(<<(?s ?p ?o)>> AS ?t)``
    where ``?o`` itself already held a *nested* triple-term value from the
    graph being queried. Such a value is only "known" via the *querying*
    graph's own ``_tt_nodes`` registry (built when that data was originally
    parsed) - the plain rdflib Graph rdflib's SPARQL engine hands back for a
    CONSTRUCT result has no rdf:subject/predicate/object triples for it at
    all (those were never re-derived, since nothing re-interned it), so
    ``StarLayerGraph.from_rdflib()``'s registry-building pass
    (``_build_registry_from_store()``) has nothing to find, and the raw
    tt:HASH URIRef leaks straight through to callers instead of the
    TripleTerm it's supposed to mean. Confirmed via the W3C SPARQL 1.2
    eval-triple-terms/expr-1 fixture, whose CONSTRUCT template does exactly
    this. Called on `graph` *before* ``StarLayerGraph.from_rdflib(graph)``,
    from both ``StarLayerGraph.query()`` and ``StarLayerDataset.query()``.
    """
    from starlayergraph.model.triple import TripleTerm

    already_encoded = {s for s, _p, _o in graph.triples((None, RDF.subject, None))}
    candidates = {
        term for s, p, o in graph for term in (s, o)
        if isinstance(term, URIRef) and str(term).startswith(TT_NS)
    }
    for uri in candidates:
        if uri in already_encoded:
            continue
        restored = restore_fn(uri)
        if isinstance(restored, TripleTerm):
            _reencode_tt(restored, graph)
