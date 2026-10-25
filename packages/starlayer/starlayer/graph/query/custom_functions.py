"""Registers starlayer.graph's own custom SPARQL extension functions with rdflib's
global function registry, as an import-time side effect.

These are the functions the SPARQL 1.2 -> 1.1 lowering (starlayer.sparql's
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
eagerly from ``starlayer.graph/__init__.py`` alongside this project's other
eager compatibility patches, so registration always happens regardless of
which pipeline a caller uses.

``starlayer.graph.query.remote_decompose`` imports the three function-IRI
constants below (``TT_HASH_FN``, ``_TT_ACCESSOR_FN``, ``DIRLANG_CONSTRUCT_FN``)
to recognize when a query still depends on one of these functions after
decomposition - the literal same URIs ``starlayer.sparql.lower_rdf11``
produces, both deriving from ``starlayer.graph.model.encoding.TT_NS``/
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

    from starlayer.graph.model.encoding import (
        TT_NS,
        remember_tt_hash,
        term_key,
        tt_hash,
    )

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
        # any graph. See starlayer.graph.model.encoding's _TT_HASH_MEMO docstring.
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
# here since TT_NS/DIRLANG_NS are starlayer.graph's own namespaces, not shared with
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
    from rdflib.plugins.sparql.operators import register_custom_function
    from rdflib.plugins.sparql.sparql import SPARQLError

    from starlayer.graph.model.encoding import (
        TT_NS,
        TT_OBJECT,
        TT_PREDICATE,
        TT_SUBJECT,
        lookup_tt_hash,
    )
    from starlayer.graph.model.triple import TripleTerm

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
        ('SUBJECT', 0, TT_SUBJECT),
        ('PREDICATE', 1, TT_PREDICATE),
        ('OBJECT', 2, TT_OBJECT),
    ):
        register_custom_function(
            URIRef(_TT_ACCESSOR_FN[name][1:-1]), _make_accessor(name, index, pred),
            override=True, raw=True,
        )


_register_tt_accessor_functions()

# The lowered form of isTRIPLE(x): a dedicated function, because the old STRSTARTS(STR(x), TT_NS) test cannot be used any
# more now that a user-written STR(<triple term>) is an error (GitHub issue #74), and a function IRI survives the lowered
# query's trip through RDF and text unchanged, which an extra flag on the STR node did not.
TT_IS_TRIPLE_TERM_FN = f"<{TT_NS_PREFIX}fn/isTripleTerm>"


def _register_tt_is_triple_term_function() -> None:
    from rdflib import Literal, URIRef
    from rdflib.plugins.sparql.operators import register_custom_function

    from starlayer.graph.model.encoding import TT_NS
    from starlayer.graph.model.triple import TripleTerm

    def _is_triple_term(e, ctx):
        term = e.expr[0]
        return Literal(
            isinstance(term, TripleTerm) or (isinstance(term, URIRef) and str(term).startswith(TT_NS))
        )

    register_custom_function(URIRef(TT_IS_TRIPLE_TERM_FN[1:-1]), _is_triple_term, override=True, raw=True)


_register_tt_is_triple_term_function()

# STRLANGDIR is a SPARQL-callable function (registered like TT_HASH_FN) rather
# than a pure STRDT/IRI/CONCAT/LCASE expression: a plain expression can't
# validate its direction argument at all - it would silently build a
# well-formed-looking but wrong Literal, with no diagnostic. Registering a
# real function lets it validate at construction time and raise SPARQLError
# for a bad direction like "sideways" - which rdflib's evaluator (evalExtend,
# for BIND/SELECT-projection expressions) specifically catches and treats as
# "leave the variable unbound for this solution", the same "type error in an
# expression" semantics live Fuseki and Oxigraph both use: an invalid
# direction there doesn't abort the query or drop the row, it just leaves
# that one binding's variable missing.
DIRLANG_CONSTRUCT_FN = f"<{DIRLANG_NS_PREFIX}fn/construct>"


def _register_dirlang_construct_function() -> None:
    from rdflib import Literal, URIRef
    from rdflib.plugins.sparql.operators import register_custom_function, string
    from rdflib.plugins.sparql.sparql import SPARQLError

    from starlayer.graph.model.encoding import encode_dirlang_datatype

    def _dirlang_construct_fn(lex, lang, direction):
        # operators.string() applies the same validation stock rdflib's own
        # Builtin_STRLANG applies to its analogous lexicalForm argument -
        # raises for a non-literal (e.g. STRLANGDIR(<http://example/x>,
        # ...), an error per RDF 1.2 Query sec 17.4.2.17's own example
        # table) or a literal with some other, unrelated datatype. A bare
        # str(lex) coercion would silently accept any term here instead.
        lexical = str(string(lex))
        # .lower() matches stock rdflib's own Builtin_STRLANG (the
        # non-direction-aware sibling function) exactly - its source does
        # the same "lang=str(expr.arg2).lower())" - kept unchanged here.
        lang_str = str(lang).lower()
        # langTag MUST NOT be an empty string (17.4.2.17's own normative
        # text, per its example table: STRLANGDIR("abc", "", "ltr") ->
        # error). An empty language tag must be rejected here with a
        # SPARQLError rather than silently building a Literal that would
        # only fail later, with an unrelated, un-SPARQL-error-shaped
        # ValueError, the first time something (e.g.
        # StarLayerGraph._restore()) tried to decode it back into a real
        # DirLangString - instead of leaving the binding unbound the way a
        # SPARQLError does.
        if not lang_str:
            raise SPARQLError("STRLANGDIR: language tag must not be empty")
        # baseDirection MUST be exactly "ltr" or "rtl", case-sensitively
        # (same example table: STRLANGDIR("abc", "en", "LTR") -> error) -
        # must be compared against ('ltr', 'rtl') without lowercasing
        # first, or "LTR"/"Ltr"/"rTl" etc. would incorrectly pass.
        dir_str = str(direction)
        if dir_str not in ('ltr', 'rtl'):
            # SPARQLError specifically (not ValueError): this is what
            # rdflib's evaluator recognizes as a SPARQL expression type
            # error and converts to "unbound", matching native engines -
            # see the module-level comment above DIRLANG_CONSTRUCT_FN.
            raise SPARQLError(f'STRLANGDIR: direction must be "ltr" or "rtl", got {dir_str!r}')
        return Literal(lexical, datatype=encode_dirlang_datatype(lang_str, dir_str))

    register_custom_function(URIRef(DIRLANG_CONSTRUCT_FN[1:-1]), _dirlang_construct_fn, override=True)


# Same deliberate import-time global-registry mutation as
# _register_tt_hash_function() above, and the same reasoning applies.
_register_dirlang_construct_function()

# RDF 1.2 Query sec 17.4.3 ("Functions on Strings") extends every function
# in this family to accept a dirLangString as a "string literal" (alongside
# plain xsd:string and langString), with its own argument-compatibility and
# result-kind-propagation rules. rdflib's own stock evalfns reject this
# outright: every one of them calls operators.string(), which raises
# SPARQLError for any literal whose .datatype is set and isn't xsd:string -
# and a dirLangString value is internally stored with exactly that kind of
# non-standard datatype (see starlayer.graph.model.encoding.DIRLANG_NS),
# so STRLEN/SUBSTR/UCASE/LCASE/STRSTARTS/STRENDS/CONTAINS/STRBEFORE/
# STRAFTER/CONCAT/REGEX/REPLACE/ENCODE_FOR_URI all silently produced an
# unbound result for any query touching a direction-tagged literal, found
# via a retrospective check of the W3C SPARQL 1.2 suite's own lang-basedir/
# category (none of those 14 functions were fetched/exercised by this
# project's test suite before now - see download_w3c_sparql12_tests.py's
# own CATEGORIES list).
#
# langMATCHES is deliberately excluded: its own signature (17.4.2.11) types
# both arguments as plain xsd:string only, not "string literal" - nobody
# legitimately passes a dirLangString as a language tag/range, so rdflib's
# existing behavior already matches the spec as-is.
#
# Design: reuse rdflib's own stock evalfn for the actual string-processing
# logic (regex matching, substring arithmetic, case-folding, URI-encoding)
# rather than reimplementing it - each wrapper classifies its "string
# literal" argument(s) into (lexical, language, direction) via
# decode_dirlang_datatype(), strips tagging down to a bare Literal(lexical)
# (which trivially passes operators.string()'s own xsd:string-or-nothing
# gate), calls the real rdflib function with a small shim object standing
# in for its usual Expr, then re-wraps the bare string result in the
# correct kind per that function's own spec-mandated propagation rule.
def _register_dirlang_string_functions() -> None:
    import re
    from types import SimpleNamespace

    from rdflib import Literal, URIRef
    from rdflib.namespace import XSD
    from rdflib.plugins.sparql import operators as _op
    from rdflib.plugins.sparql.operators import register_custom_function
    from rdflib.plugins.sparql.sparql import SPARQLError

    from starlayer.graph.model.encoding import (
        decode_dirlang_datatype,
        encode_dirlang_datatype,
    )

    def _classify(term, context):
        """Classify term as RDF 1.2 Query sec 17.4.3's own "string literal"
        - a plain xsd:string literal, a langString with a language tag, or
        a dirLangString with both a language tag and base direction.

        Args:
            term: The literal to classify.
            context: Name of the calling SPARQL function, used only to
                label the SPARQLError message on failure.

        Returns:
            A (lexical, language_or_None, direction_or_None) tuple.

        Raises:
            SPARQLError: term is not a literal, or is a literal with some
                other, unrelated datatype.
        """
        if not isinstance(term, Literal):
            raise SPARQLError(f"{context}: not a string literal: {term!r}")
        dirlang = decode_dirlang_datatype(term.datatype) if term.datatype else None
        if dirlang is not None:
            language, direction = dirlang
            return str(term), language, direction
        if term.datatype is not None and term.datatype != XSD.string:
            raise SPARQLError(f"{context}: not a string literal: {term!r}")
        if term.language:
            return str(term), term.language, None
        return str(term), None, None

    def _same_kind(lexical, language, direction):
        """Build a literal "of the same kind" as a (language, direction)
        pair from _classify() - the shared propagation rule SUBSTR/UCASE/
        LCASE/STRBEFORE/STRAFTER/REPLACE all follow.

        Deliberately a *bare* ``Literal(lexical)`` for the plain case, not
        ``Literal(lexical, datatype=XSD.string)`` - rdflib's own term
        equality treats the two as genuinely different terms
        (``Literal("x") != Literal("x", datatype=XSD.string)``), every W3C
        expected-result fixture for this family renders the plain case with
        no "datatype" key at all, and stock rdflib's own Builtin_CONCAT/
        Builtin_STRBEFORE/Builtin_STRAFTER construct their own plain-case
        result the same bare way.

        Args:
            lexical: The result string.
            language: Language tag to propagate, or None for the plain/
                dirLangString-without-language cases.
            direction: Base direction to propagate, or None for the plain/
                langString cases.

        Returns:
            A plain Literal if neither language nor direction is set, a
            langString Literal if only language is set, or a dirLangString
            Literal if both are set.
        """
        if direction is not None:
            return Literal(lexical, datatype=encode_dirlang_datatype(language, direction))
        if language is not None:
            return Literal(lexical, lang=language)
        return Literal(lexical)

    def _compatible(parts1, parts2):
        """RDF 1.2 Query sec 17.4.3's own argument-compatibility table for
        STRSTARTS/STRENDS/CONTAINS/STRBEFORE/STRAFTER."""
        _, lang1, dir1 = parts1
        _, lang2, dir2 = parts2
        if lang2 is None and dir2 is None:
            return True  # arg2 is a plain xsd:string - always compatible
        if dir1 is not None and dir2 is not None:
            return lang1 == lang2 and dir1 == dir2
        if dir1 is None and dir2 is None:
            return lang1 == lang2
        return False

    def _call_stock(evalfn, **kwargs):
        # ctx is unused by every one of the stock evalfns reused below
        # (confirmed by reading each one's source) - None is safe.
        return evalfn(SimpleNamespace(**kwargs), None)

    def _strlen(arg):
        lexical, _, _ = _classify(arg, "STRLEN")
        return Literal(len(lexical))

    def _substr(arg, start, length=None):
        lexical, language, direction = _classify(arg, "SUBSTR")
        result = _call_stock(_op.Builtin_SUBSTR, arg=Literal(lexical), start=start, length=length)
        return _same_kind(str(result), language, direction)

    def _ucase(arg):
        lexical, language, direction = _classify(arg, "UCASE")
        return _same_kind(lexical.upper(), language, direction)

    def _lcase(arg):
        lexical, language, direction = _classify(arg, "LCASE")
        return _same_kind(lexical.lower(), language, direction)

    def _strstarts(arg1, arg2):
        parts1 = _classify(arg1, "STRSTARTS")
        parts2 = _classify(arg2, "STRSTARTS")
        if not _compatible(parts1, parts2):
            raise SPARQLError("STRSTARTS: arguments are not argument-compatible")
        return Literal(parts1[0].startswith(parts2[0]))

    def _strends(arg1, arg2):
        parts1 = _classify(arg1, "STRENDS")
        parts2 = _classify(arg2, "STRENDS")
        if not _compatible(parts1, parts2):
            raise SPARQLError("STRENDS: arguments are not argument-compatible")
        return Literal(parts1[0].endswith(parts2[0]))

    def _contains(arg1, arg2):
        parts1 = _classify(arg1, "CONTAINS")
        parts2 = _classify(arg2, "CONTAINS")
        if not _compatible(parts1, parts2):
            raise SPARQLError("CONTAINS: arguments are not argument-compatible")
        return Literal(parts2[0] in parts1[0])

    def _strbefore(arg1, arg2):
        parts1 = _classify(arg1, "STRBEFORE")
        parts2 = _classify(arg2, "STRBEFORE")
        if not _compatible(parts1, parts2):
            raise SPARQLError("STRBEFORE: arguments are not argument-compatible")
        lexical1, language1, direction1 = parts1
        i = lexical1.find(parts2[0])
        if i == -1:
            # Spec's own explicit exception to "same kind as arg1" - a
            # non-match always returns a plain empty literal, regardless of
            # either argument's own kind (matches stock rdflib's own
            # Builtin_STRBEFORE no-match case, bare "Literal('')").
            return Literal("")
        return _same_kind(lexical1[:i], language1, direction1)

    def _strafter(arg1, arg2):
        parts1 = _classify(arg1, "STRAFTER")
        parts2 = _classify(arg2, "STRAFTER")
        if not _compatible(parts1, parts2):
            raise SPARQLError("STRAFTER: arguments are not argument-compatible")
        lexical1, language1, direction1 = parts1
        lexical2 = parts2[0]
        i = lexical1.find(lexical2)
        if i == -1:
            return Literal("")
        return _same_kind(lexical1[i + len(lexical2) :], language1, direction1)

    def _concat(*args):
        # errata-query-4 (quoted in the vendored spec snapshot): CONCAT()
        # with zero arguments is "" (xsd:string, per the spec's own prose -
        # but rendered bare, no "datatype" key, in every W3C expected-
        # result fixture, same as the "otherwise" branch below); with
        # exactly one argument the result is that argument's own value,
        # unchanged - both handled by the general rule below without a
        # special case, except that the loop needs at least one element to
        # classify.
        if not args:
            return Literal("")
        parts = [_classify(a, "CONCAT") for a in args]
        lexical = "".join(p[0] for p in parts)
        languages = {p[1] for p in parts}
        directions = {p[2] for p in parts}
        if len(languages) == 1 and len(directions) == 1 and None not in directions:
            return Literal(lexical, datatype=encode_dirlang_datatype(languages.pop(), directions.pop()))
        if len(languages) == 1 and directions == {None}:
            language = next(iter(languages))
            if language is None:
                return Literal(lexical)
            return Literal(lexical, lang=language)
        return Literal(lexical)

    def _regex(text, pattern, flags=None):
        lexical, _, _ = _classify(text, "REGEX")
        return _call_stock(_op.Builtin_REGEX, text=Literal(lexical), pattern=pattern, flags=flags)

    def _replace(arg, pattern, replacement, flags=None):
        # Not routed through _call_stock(operators.Builtin_REPLACE, ...)
        # like the other functions here: stock rdflib's own Builtin_REPLACE
        # has a real, independent bug (not specific to dirLangString at
        # all) - it calls "re.sub(str(pattern), replacement, text, cFlag)",
        # but re.sub()'s fourth positional parameter is "count", not
        # "flags", so a REPLACE(..., "i")-style flags argument is silently
        # misinterpreted as a replacement-count limit instead of enabling
        # case-insensitive matching (a Python DeprecationWarning fires
        # right at this call, "'count' is passed as positional argument",
        # and the replacement doesn't happen). Reimplemented directly here
        # instead, reusing stock Builtin_REGEX's own (correct) flag-mapping
        # approach via re.sub(..., flags=cFlag) as a keyword.
        lexical, language, direction = _classify(arg, "REPLACE")
        pattern_str = str(_op.string(pattern))
        replacement_str = str(_op.string(replacement))
        replacement_str = re.sub(r"\$([0-9]*)", r"\\\1", replacement_str)
        c_flags = 0
        if flags:
            flag_map = {"i": re.IGNORECASE, "s": re.DOTALL, "m": re.MULTILINE}
            for f in str(flags):
                c_flags |= flag_map.get(f, 0)
        result = re.sub(pattern_str, replacement_str, lexical, flags=c_flags)
        return _same_kind(result, language, direction)

    def _encode_for_uri(arg):
        lexical, _, _ = _classify(arg, "ENCODE_FOR_URI")
        return _call_stock(_op.Builtin_ENCODE_FOR_URI, arg=Literal(lexical))

    for name, fn in (
        ("strlen", _strlen),
        ("substr", _substr),
        ("ucase", _ucase),
        ("lcase", _lcase),
        ("strstarts", _strstarts),
        ("strends", _strends),
        ("contains", _contains),
        ("strbefore", _strbefore),
        ("strafter", _strafter),
        ("concat", _concat),
        ("regex", _regex),
        ("replace", _replace),
        ("encode_for_uri", _encode_for_uri),
    ):
        register_custom_function(URIRef(f"{DIRLANG_NS_PREFIX}fn/{name}"), fn, override=True)


# URIs for starlayer.sparql's lower_rdf11.py to route the corresponding
# stock SPARQL 1.1 builtins through - see that module's own duplicated copy
# of these constants (same cross-package duplication rationale as
# TT_HASH_FN/DIRLANG_CONSTRUCT_FN above) for which Builtin_* each one
# replaces.
DIRLANG_STRING_FN = {
    name: f"<{DIRLANG_NS_PREFIX}fn/{name}>"
    for name in (
        "strlen", "substr", "ucase", "lcase", "strstarts", "strends",
        "contains", "strbefore", "strafter", "concat", "regex", "replace",
        "encode_for_uri",
    )
}

# Same deliberate import-time global-registry mutation as
# _register_tt_hash_function() above, and the same reasoning applies.
_register_dirlang_string_functions()
