"""Registers starlayergraph's own custom SPARQL extension functions with rdflib's
global function registry, as an import-time side effect.

These are the functions the SPARQL 1.2 -> 1.1 lowering (starsparql's
``lower_rdf11.py``, driven from ``prepare_query_12``/``prepare_update_12``)
compiles ``TRIPLE()``/triple-term-construction, ``SUBJECT()``/``PREDICATE()``/
``OBJECT()`` accessors, and ``STRLANGDIR()`` down to - real ``Function``
algebra nodes evaluated by rdflib's own evaluator at query-execution time,
not text. Every one of them needs a registered Python implementation to
actually run against, or rdflib's own SPARQL error semantics (an unbound/
unknown function leaves its BIND target unbound, and a FILTER using one
excludes the row) silently produce wrong results instead of a real error.

Extracted from the old, now-retired ``sparql12_to_11.py`` text-rewriter
(which historically both rewrote query text *and* registered these
functions as an unrelated import-time side effect) into its own module so
the registration survives independent of that rewriter's removal. Imported
eagerly from ``starlayergraph/__init__.py`` alongside this project's other
eager compatibility patches, so registration always happens regardless of
which pipeline a caller uses.

``starlayergraph.query.remote_decompose`` imports the three function-IRI
constants below (``TT_HASH_FN``, ``_TT_ACCESSOR_FN``, ``DIRLANG_CONSTRUCT_FN``)
to recognize when a query still depends on one of these functions after
decomposition - the literal same URIs ``starsparql.lower_rdf11``
produces, both deriving from ``starlayergraph.model.encoding.TT_NS``/
``DIRLANG_NS``.
"""

from __future__ import annotations

TT_NS_PREFIX = "https://github.com/hidden-graph/starlayergraph/ns/tt#"
DIRLANG_NS_PREFIX = "https://github.com/hidden-graph/starlayergraph/ns/dirlang#"

# SPARQL-callable function computing the same content-addressed tt:HASH URIRef
# that StarLayerGraph._intern_tt() assigns on write. Used to BIND a triple-term
# variable that a CONSTRUCT template needs but that has no existing WHERE-clause
# match to bind it from (i.e. the template is minting a triple term that was
# never previously used as a value anywhere in the graph).
TT_HASH_FN = f"<{TT_NS_PREFIX}fn/hash>"


def _register_tt_hash_function() -> None:
    from rdflib import BNode, URIRef
    from rdflib.plugins.sparql.operators import register_custom_function
    from rdflib.plugins.sparql.sparql import SPARQLError

    from starlayergraph.model.encoding import TT_NS, tt_hash, term_key, remember_tt_hash

    def _tt_hash_fn(s, p, o):
        # RDF 1.2 (17.4.6, TRIPLE()): a triple term's subject must be an
        # IRI or blank node, predicate an IRI - never a Literal in either
        # position (object has no such restriction). Confirmed via a real
        # W3C test (triple-on-literals): TRIPLE(?subject, ?predicate,
        # ?object) with a VALUES row binding ?subject/?predicate to a
        # Literal is expected to leave ?triple *unbound* for that row, not
        # silently construct an invalid triple term - SPARQLError
        # specifically (not ValueError) is what makes that happen: it's
        # the one exception type evalExtend's own error handling catches
        # and turns into "this BIND target stays unbound", instead of
        # aborting the whole query.
        if not isinstance(s, (URIRef, BNode)):
            raise SPARQLError(f"TRIPLE(): subject must be an IRI or blank node, not {s!r}")
        if not isinstance(p, URIRef):
            raise SPARQLError(f"TRIPLE(): predicate must be an IRI, not {p!r}")
        # A triple term is internally represented as a plain TT_NS-prefixed
        # URIRef (the whole point of the encoding) - so the isinstance
        # checks above alone don't catch "subject/predicate is *itself* a
        # triple term", which RDF 1.2 forbids just as much as a Literal
        # there (triple terms are only ever legal in object position).
        # Confirmed via a real W3C test (triple-on-triple-terms): a VALUES
        # row binding ?subject to a ground <<( )>> value must also leave
        # ?triple unbound, not silently construct a nested-in-subject-
        # position triple term - which would crash downstream anyway (see
        # TripleTerm.__init__'s own, separate guard against exactly this).
        if str(s).startswith(TT_NS):
            raise SPARQLError("TRIPLE(): subject must not itself be a triple term")
        if str(p).startswith(TT_NS):
            raise SPARQLError("TRIPLE(): predicate must not itself be a triple term")
        uri = URIRef(TT_NS + tt_hash(term_key(s), term_key(p), term_key(o)))
        # s/p/o here are rdflib's own already-resolved terms - remembering
        # them lets StarLayerGraph._restore() reconstruct a proper
        # TripleTerm for a value that was computed but never written to
        # any graph. See starlayergraph.model.encoding's _TT_HASH_MEMO docstring.
        remember_tt_hash(uri, s, p, o)
        return uri

    register_custom_function(URIRef(TT_HASH_FN[1:-1]), _tt_hash_fn, override=True)


# Deliberate import-time side effect: this mutates rdflib's *global*
# CUSTOM_EVALS/function registry the moment this module is imported, not on
# first use. override=True is intentional too - re-importing this module (or
# a reload) re-registers idempotently under the same TT_HASH_FN URI rather
# than raising on a duplicate registration, since it's always the same
# function. The tradeoff: nothing else in the process may register a
# different function at this exact URI and expect it to stick - acceptable
# here since TT_NS/DIRLANG_NS are starlayergraph's own namespaces, not shared with
# any other library.
_register_tt_hash_function()

# SPARQL-callable functions computing SUBJECT()/PREDICATE()/OBJECT() of a
# triple-term value (its tt:HASH URIRef). Registered as `raw=True` custom
# functions (rdflib passes the already-evaluated Expr plus the live
# evaluation Context, giving access to ctx.graph for a real store lookup -
# confirmed via rdflib's own operators.Function/register_custom_function:
# raw functions receive (e, ctx), e.expr already holds evaluated arguments,
# and default_cast's own raw=True builtins use e.expr[0] as a plain already-
# resolved term the same way).
_TT_ACCESSOR_FN = {
    'SUBJECT':   f"<{TT_NS_PREFIX}fn/subject>",
    'PREDICATE': f"<{TT_NS_PREFIX}fn/predicate>",
    'OBJECT':    f"<{TT_NS_PREFIX}fn/object>",
}


def _register_tt_accessor_functions() -> None:
    from rdflib import URIRef
    from rdflib.namespace import RDF
    from rdflib.plugins.sparql.operators import register_custom_function
    from rdflib.plugins.sparql.sparql import SPARQLError

    from starlayergraph.model.encoding import TT_NS, lookup_tt_hash
    from starlayergraph.model.triple import TripleTerm

    def _make_accessor(label: str, index: int, pred):
        def _accessor(e, ctx):
            if len(e.expr) != 1:
                raise SPARQLError(f"{label}() requires exactly 1 argument")
            uri = e.expr[0]
            # A triple term bound via an ordinary graph-pattern match (e.g.
            # `?r rdf:reifies ?tt .`) arrives here as a native TripleTerm
            # object, not a tt: URIRef - StarLayerGraph.triples() always
            # restores tt: URIs to TripleTerm objects as part of its own
            # ordinary result iteration (see StarLayerGraph._restore()), not
            # only at final query-result time, so this is the common case
            # for a pattern-matched (as opposed to freshly-constructed or
            # dereferenced-by-URI) triple term. Its own subject/predicate/
            # object attributes are already the answer - no lookup or graph
            # dereference needed at all.
            if isinstance(uri, TripleTerm):
                return (uri.subject, uri.predicate, uri.object)[index]
            if not (isinstance(uri, URIRef) and str(uri).startswith(TT_NS)):
                raise SPARQLError(f"{label}(): argument is not a triple term")
            remembered = lookup_tt_hash(uri)
            if remembered is not None:
                return remembered[index]
            # ctx.graph, not always a plain QueryContext: evalFilter (unlike
            # evalExtend) always calls .eval() with a FrozenBindings
            # (ctx.forget(...)), which has no .graph of its own - only its
            # own .ctx attribute (FrozenBindings.__init__ stashes the real
            # QueryContext there) does.
            graph = getattr(ctx, "graph", None) or getattr(getattr(ctx, "ctx", None), "graph", None)
            if graph is None:
                raise SPARQLError(f"{label}(): no graph available in this evaluation context")
            value = graph.value(uri, pred)
            if value is None:
                raise SPARQLError(f"{label}(): {uri!r} is not a known triple term")
            return value

        return _accessor

    for name, index, pred in (
        ('SUBJECT', 0, RDF.subject),
        ('PREDICATE', 1, RDF.predicate),
        ('OBJECT', 2, RDF.object),
    ):
        register_custom_function(
            URIRef(_TT_ACCESSOR_FN[name][1:-1]), _make_accessor(name, index, pred),
            override=True, raw=True,
        )


_register_tt_accessor_functions()

# STRLANGDIR is a SPARQL-callable function (registered like TT_HASH_FN) rather
# than a pure STRDT/IRI/CONCAT/LCASE expression: a plain expression can't
# validate its direction argument at all - it would silently build a
# well-formed-looking but wrong Literal, with no diagnostic. Registering a
# real function lets it validate at construction time and raise SPARQLError
# for a bad direction like "sideways" - which rdflib's evaluator (evalExtend,
# for BIND/SELECT-projection expressions) specifically catches and treats as
# "leave the variable unbound for this solution", the same "type error in an
# expression" semantics a real SPARQL 1.2 engine uses (confirmed directly
# against live Fuseki 5.5.0 and Oxigraph 0.5.9 2026-07-16: an invalid
# direction there doesn't abort the query or drop the row, it just leaves
# that one binding's variable missing).
DIRLANG_CONSTRUCT_FN = f"<{DIRLANG_NS_PREFIX}fn/construct>"


def _register_dirlang_construct_function() -> None:
    from rdflib import URIRef, Literal
    from rdflib.plugins.sparql.operators import register_custom_function
    from rdflib.plugins.sparql.sparql import SPARQLError

    from starlayergraph.model.encoding import encode_dirlang_datatype

    def _dirlang_construct_fn(lex, lang, direction):
        lang_str = str(lang).lower()
        dir_str = str(direction).lower()
        if dir_str not in ('ltr', 'rtl'):
            # SPARQLError specifically (not ValueError): this is what
            # rdflib's evaluator recognizes as a SPARQL expression type
            # error and converts to "unbound", matching native engines -
            # see the module-level comment above DIRLANG_CONSTRUCT_FN.
            raise SPARQLError(f'STRLANGDIR: direction must be "ltr" or "rtl", got {dir_str!r}')
        return Literal(str(lex), datatype=encode_dirlang_datatype(lang_str, dir_str))

    register_custom_function(URIRef(DIRLANG_CONSTRUCT_FN[1:-1]), _dirlang_construct_fn, override=True)


# Same deliberate import-time global-registry mutation as
# _register_tt_hash_function() above, and the same reasoning applies.
_register_dirlang_construct_function()
