"""New pyparsing productions for SPARQL 1.2 triple-term syntax
(``<<( s p o )>>`` / ``TRIPLE(s, p, o)``), spliced into rdflib's own real
SPARQL grammar (``rdflib.plugins.sparql.parser``) in place.

This is deliberately *not* a text-rewrite-then-reparse approach (the
approach `starlayergraph`'s ``sparql12_to_11.py`` uses, for its own good
reasons) — it extends rdflib's actual pyparsing grammar the same way rdflib
extends itself: a ``Comp``/``Param``-built production with a parse action
that constructs an algebra-tree node directly during parsing.

The extension point (confirmed empirically before relying on it): the
grammar rules that need to accept a triple term — ``GraphTerm``,
``VarOrTerm``, ``GraphNode``, ``GraphNodePath`` — are plain
``pyparsing.MatchFirst`` objects with a public ``.append(expr)`` method.
Because pyparsing composes grammar rules by object reference (every rule
that transitively depends on ``GraphTerm``, e.g. ``TriplesSameSubject``,
holds a reference to the *same* object, not a copy), appending a new
alternative to it in place makes the addition visible to every rule built on
top of it, without forking rdflib's grammar module or touching the installed
package on disk.
"""

from __future__ import annotations

from pyparsing import CaselessKeyword as Keyword
from pyparsing import Forward, Group, Literal, OneOrMore, Optional, Regex, Suppress, ZeroOrMore
from rdflib import BNode, URIRef
from rdflib import Literal as RDFTermLiteral
from rdflib.namespace import RDF

from rdflib.plugins.sparql.parser import (
    A,
    BLANK_NODE_LABEL,
    BlankNode,
    BuiltInCall,
    DataBlockValue,
    Expression,
    GraphNode,
    GraphNodePath,
    GraphTerm,
    Path,
    PrimaryExpression,
    String,
    TriplesNode,
    TriplesNodePath,
    TriplesSameSubject,
    TriplesSameSubjectPath,
    Var,
    VarOrTerm,
    iri,
)
from rdflib.plugins.sparql.parserutils import Comp, Param

from .triple_term import TripleTermNode
from .vocab import encode_dirlang_datatype

# RDF 1.2's "a triple term's subject is never a Literal, and never itself a
# nested triple term (nesting is only legal in object position)" rule turns
# out to hold only when the ground triple term is used as an EXPRESSION
# VALUE (BIND/FILTER/VALUES) — not when it's used in ordinary TERM/pattern
# position. Confirmed via real, contrasting W3C tests, not assumed by
# symmetry: `tripleterm-subject-03`
# (`BIND( <<( <<(:s :p :o )>> :q :z )>> AS ?X )`, nested ground triple term
# as subject) and `bindbnode-tripleterm` (`BIND(<<( [] ?p ?o )>> AS ?t)`,
# anonymous `[]` as subject) must both be REJECTED — but
# `nested-tripleterm-02`/`compound-tripleterm-subject` (the identical
# shapes, in ordinary triple-pattern position, e.g.
# `<<( <<(?S :p :o )>> :r :z )>> :q 1 .`) and `bnode-tripleterm-03`
# (`<<([] :p [] )>> :q :z .`) are POSITIVE tests requiring exactly what the
# BIND versions reject. One shared grammar object can't enforce two
# different rules depending on where it's spliced in — tried that first
# (a single `_TripleTermSubject` installed into both `GraphTerm`/`VarOrTerm`/
# `GraphNode`/`GraphNodePath` *and* `PrimaryExpression`/`DataBlockValue`)
# and it necessarily got one side wrong; fixed by building two genuinely
# separate pairs of `Comp` objects below, each with its own subject
# grammar, rather than reusing one.
#
# Deliberately built from rdflib's *primitive* term productions (Var/iri/
# BlankNode) rather than referencing GraphTerm/VarOrTerm directly: those two
# objects are exactly what install() (below) mutates in place to add the new
# triple-term alternative, so referencing them here would make a triple term
# legal in its own subject slot too, once install() runs — confirmed
# empirically as a real bug during development (nesting silently became
# legal in subject position, contradicting this comment, before this was
# rewritten to use independent primitives instead).
# `a` (the standard SPARQL/Turtle shorthand for rdf:type) must be legal
# here too, not just Var | iri: confirmed via the real W3C fixture
# `triple-on-triple-terms` (`<<(:x a :z)>>`, `a` as a triple term's own
# predicate) - `<<(:x :y :z)>>` (ordinary IRI predicate) parsed fine, but
# `a` specifically failed, since it's a dedicated token (`A`, matched and
# mapped to rdf:type by rdflib's own grammar) spliced into ordinary
# Verb/VerbSimple productions elsewhere - never part of plain `iri` itself,
# so a triple term's own restricted predicate grammar needs it explicitly.
_TripleTermPredicate = Var | iri | A

# Forward-declared so the object position (and, for the permissive/pattern
# variant, the subject position too) can itself be a (possibly nested)
# triple term — filled in below once TripleTermExpr/TripleTermCall exist,
# the same declare-then-fill-in pattern rdflib's own grammar uses for Path/
# TriplesNode.
TripleTermObject = Forward()

# TERM/pattern-position subject: any BlankNode form (rdflib's own
# BLANK_NODE_LABEL-or-ANON alias) or a nested triple term, both confirmed
# legal by the positive tests cited above.
_TripleTermSubjectPattern = Var | iri | BlankNode | TripleTermObject

# EXPRESSION/value-position subject: BLANK_NODE_LABEL only (the `_:x` form —
# excludes anonymous `[]`) and never a nested triple term, confirmed by the
# negative tests cited above.
_TripleTermSubjectExpr = Var | iri | BLANK_NODE_LABEL


def _promote(tokens):
    """Reclass the CompValue Comp() just built into a TripleTermNode, so the
    tree never contains a plain (unhashable, un-addVars-recursable)
    CompValue('TripleTerm', ...) to begin with — see triple_term.py.

    ``.validate()`` here is the real semantic backstop for RDF 1.2's
    subject/predicate-never-a-triple-term rule — see
    ``InvalidTripleTermError``'s own docstring for why this can't be left
    to the grammar alone: `_TripleTermSubjectPattern` above still
    syntactically *parses* a nested-subject triple term (matching the W3C
    suite's own `PositiveSyntaxTest` classification for that shape), so
    rejection has to happen here, at construction, not in the grammar.
    """
    node = tokens[0]
    promoted = TripleTermNode("TripleTerm")
    promoted.update(node)
    return promoted.validate()


# <<( s p o )>> / TRIPLE(s, p, o) in ordinary TERM/pattern position (spliced
# into GraphTerm/VarOrTerm/GraphNode/GraphNodePath below).
TripleTermExpr = Comp(
    "TripleTerm",
    Suppress(Literal("<<("))
    + Param("subject", _TripleTermSubjectPattern)
    + Param("predicate", _TripleTermPredicate)
    + Param("object", TripleTermObject)
    + Suppress(Literal(")>>")),
)
TripleTermExpr.add_parse_action(_promote)

# TRIPLE(s, p, o) - the SPARQL 1.2 spec's function-call spelling of the same
# construct (17.4.6), equivalent to <<( s p o )>>.
TripleTermCall = Comp(
    "TripleTerm",
    Keyword("TRIPLE")
    + Suppress("(")
    + Param("subject", _TripleTermSubjectPattern)
    + Suppress(",")
    + Param("predicate", _TripleTermPredicate)
    + Suppress(",")
    + Param("object", TripleTermObject)
    + Suppress(")"),
)
TripleTermCall.add_parse_action(_promote)

TripleTermObject <<= VarOrTerm | TripleTermExpr | TripleTermCall

# Same two constructs again, for EXPRESSION/value position (PrimaryExpression
# — BIND/FILTER/SELECT (... AS ?x)/etc. — and DataBlockValue — VALUES rows,
# treated the same as expression position since a VALUES row is a ground
# *value*, not a pattern, though no specific W3C test confirms the ANON/
# nested-term restriction there one way or the other; a principled
# extension of the confirmed BIND rule, not itself directly evidenced).
# Object position is unchanged from the pattern variant above (no evidence
# either restriction applies there) — reuses the same TripleTermObject.
TripleTermExprValue = Comp(
    "TripleTerm",
    Suppress(Literal("<<("))
    + Param("subject", _TripleTermSubjectExpr)
    + Param("predicate", _TripleTermPredicate)
    + Param("object", TripleTermObject)
    + Suppress(Literal(")>>")),
)
TripleTermExprValue.add_parse_action(_promote)


# TRIPLE(...)'s three arguments are full Expressions, not just terms, per
# spec 17.4.6 — confirmed necessary (not merely permitted by the grammar
# text) via the W3C positive test `expr-tripleterm-04`:
# `BIND(TRIPLE(?s, ?p, str(?o)) AS ?t2)`, whose third argument is a
# function-call expression, not a plain term at all. This is a strict
# superset of a plain term (a bare Var/iri IS a trivial Expression too), so
# widening from _TripleTermSubjectExpr/_TripleTermPredicate/TripleTermObject
# to Expression uniformly can't regress any query that only ever passed a
# plain term here. Deliberately not applied to TripleTermExprValue
# (`<<( s p o )>>`) above — the two spellings are NOT equivalent despite
# 17.4.6 describing them as such for the ground case: `<<( )>>` is a
# GraphTerm-level production (values/patterns only), while `TRIPLE()` is
# unambiguously function-call/expression-level, and no test exercises (or
# implies) a full expression argument for the bracket form.
TripleTermCallValue = Comp(
    "TripleTerm",
    Keyword("TRIPLE")
    + Suppress("(")
    + Param("subject", Expression)
    + Suppress(",")
    + Param("predicate", Expression)
    + Suppress(",")
    + Param("object", Expression)
    + Suppress(")"),
)
TripleTermCallValue.add_parse_action(_promote)

# ---------------------------------------------------------------------
# Expression-position usage: isTRIPLE(expr)/SUBJECT(expr)/PREDICATE(expr)/
# OBJECT(expr), and a triple term used directly as a value (e.g.
# BIND(<<( :a :b :c )>> AS ?x) or SELECT (TRIPLE(:a, :b, :c) AS ?x)).
#
# <<( )>>/TRIPLE(...) in *term* position (BGP.triples) is a genuine algebra
# node this project executes structurally, so TripleTermExpr/TripleTermCall
# above get promoted to TripleTermNode via _promote. In *expression*
# position these four builtins are never evaluated in-process by this
# project either way (see the module docstring on this project's execution
# model: regenerate SPARQL 1.2 text and hand off to starlayergraph, never
# evaluate our own tree directly) — so, deliberately, no eval function is
# bound here (Comp's evalfn parameter defaults to None, see parserutils.py),
# which makes Comp.postParse produce a plain CompValue rather than an Expr.
# That's sufficient and correct for this project's purposes: to_rdf.py's
# generic CompValue branch already encodes a plain CompValue with no special
# casing, and from_rdf.py's decoder falls through to the same generic
# CompValue reconstruction for any name _EXPR_EVALFNS doesn't recognize —
# zero new code needed in either direction for these four productions.
_TripleTermAccessorArgs = Suppress("(") + Param("arg", Expression) + Suppress(")")
Builtin_isTRIPLE = Comp("Builtin_isTRIPLE", Keyword("isTRIPLE") + _TripleTermAccessorArgs)
Builtin_SUBJECT = Comp("Builtin_SUBJECT", Keyword("SUBJECT") + _TripleTermAccessorArgs)
Builtin_PREDICATE = Comp("Builtin_PREDICATE", Keyword("PREDICATE") + _TripleTermAccessorArgs)
Builtin_OBJECT = Comp("Builtin_OBJECT", Keyword("OBJECT") + _TripleTermAccessorArgs)

# ---------------------------------------------------------------------
# RDF 1.2 Query sec 17.4.2 base-direction functions: LANGDIR(?x)/
# hasLANGDIR(?x)/hasLANG(?x)/STRLANGDIR(lex, lang, dir). None of these four
# names exist in stock SPARQL 1.1 (confirmed empirically: plain rdflib
# parses `LANG(?x)` fine via its own Builtin_LANG, but ParseExceptions on
# all four of these) - genuinely new grammar, same shape as the triple-term
# accessors immediately above (one-arg BuiltInCall extensions), except
# STRLANGDIR, which takes three. LANG(?x) itself needs *no* new grammar -
# it already parses as rdflib's own Builtin_LANG; only its *lowering*
# (lower_rdf11.py) needs to change, to make it dirLangString-aware.
#
# No evalfn bound here either, for the same reason given above
# Builtin_isTRIPLE/etc.: this project never evaluates its own tree
# in-process, so a plain CompValue (structurally encodable/decodable with
# zero special-casing) is sufficient.
_StrLangDirArgs = (
    Suppress("(")
    + Param("lex", Expression)
    + Suppress(",")
    + Param("lang", Expression)
    + Suppress(",")
    + Param("direction", Expression)
    + Suppress(")")
)
Builtin_LANGDIR = Comp("Builtin_LANGDIR", Keyword("LANGDIR") + _TripleTermAccessorArgs)
Builtin_hasLANGDIR = Comp("Builtin_hasLANGDIR", Keyword("hasLANGDIR") + _TripleTermAccessorArgs)
Builtin_hasLANG = Comp("Builtin_hasLANG", Keyword("hasLANG") + _TripleTermAccessorArgs)
Builtin_STRLANGDIR = Comp("Builtin_STRLANGDIR", Keyword("STRLANGDIR") + _StrLangDirArgs)

# ---------------------------------------------------------------------
# RDF 1.2 base-direction literals: "text"@lang--dir (rdf:dirLangString).
#
# rdflib's own LANGTAG ([145] '@' [a-zA-Z]+ ('-' [a-zA-Z0-9]+)*) has no
# notion of the "--dir" suffix - and confirmed empirically, it doesn't just
# fail to capture it: matched against "nl--ltr", LANGTAG's regex consumes
# only "nl" (a lone "-" can't start a new `-[a-zA-Z0-9]+` group, since the
# very next character is a second "-", not alphanumeric), so RDFLiteral
# itself *succeeds* with "a"@nl as its value, leaving "--ltr" as unconsumed
# trailing text. That failure surfaces far away from where it actually
# happened - at the outermost SelectQuery rule, not locally at the literal
# - because pyparsing's MatchFirst doesn't backtrack into an alternative
# that already succeeded once parsing has moved past it; confirmed via
# plain, unmodified rdflib with zero involvement from this project's own
# grammar work (`BIND("a"@nl--ltr AS ?a)` alone fails the same way). Fixing
# this means the new production must be tried *before* plain RDFLiteral,
# not merely added as a further alternative - same lesson as the
# annotation-shorthand forms below (see install()'s own comment).
#
# Represented as an ordinary rdflib Literal using this project's own
# dirlang: datatype encoding (vocab.encode_dirlang_datatype), not lang= -
# confirmed `Literal(text, lang="nl--ltr")` raises outright even with
# normalize=False (that flag only skips *value* canonicalization, not the
# separate lang-tag *validation* rdflib's Literal constructor always runs).
# Deliberately this project's *own* encoding (own namespace under vocab.SALG),
# not starlayergraph's identically-shaped one, despite starlayergraph already
# having established the exact same trick: reusing starlayergraph's would mean
# every encoded query containing a dirLangString literal is only safely
# storable in a plain rdflib.Graph, never a real StarLayerGraph, since
# StarLayerGraph.value()/.triples() unconditionally decodes any literal
# tagged with *its own* dirlang: datatype back into a real DirLangString
# object - which this project's from_rdf.py decoder has no branch for
# (confirmed via a real crash doing exactly that). Being a plain Literal
# (not a new CompValue/node type the way TripleTermNode is) still means
# to_rdf.py's existing _LEAF_TERM_TYPES branch needs zero new code either
# way - only serialize12.py needs a branch, to turn this project's own
# dirlang: datatype back into real "text"@lang--dir syntax on the way out.
#
# Direction restricted to exactly "ltr"/"rtl" (not a general identifier) -
# RDF 1.2 Concepts sec 3.4 requires exactly one of those two, lowercase
# only, no case-insensitive matching - matching the same restriction
# starlayergraph's own Turtle parser already enforces (confirmed via its
# own W3C test suite, nt-ttl12-langdir-bad-2).
def _langdir_literal_action(tokens):
    node = tokens[0]
    text = str(node["string"])
    lang = str(node["lang"])
    direction = str(node["direction"])
    return [RDFTermLiteral(text, datatype=encode_dirlang_datatype(lang, direction))]


LangDirLiteral = Comp(
    "literal",
    Param("string", String)
    + Suppress(Literal("@")).leave_whitespace()
    + Param("lang", Regex("[a-zA-Z]+(?:-[a-zA-Z0-9]+)*").leave_whitespace())
    + Suppress(Literal("--")).leave_whitespace()
    + Param("direction", Regex("ltr|rtl").leave_whitespace()),
)
LangDirLiteral.add_parse_action(_langdir_literal_action)

# ---------------------------------------------------------------------
# Annotation / reification-shorthand syntax: << s p o >>, << s p o ~ r >>,
# s p o ~ r, and s p o {| ap av ; ... |} — RDF 1.2's sugar for "assert a
# triple, mint or bind a reifier for it, and (for the two <<...>> forms)
# use that reifier as the subject of another triple".
#
# Architecturally different from <<( s p o )>>/TRIPLE() above: those are
# self-contained *term* productions (one algebra node, no side effect on
# the surrounding triple list). These four forms are NOT self-contained —
# each expands to *multiple* (s, p, o) triples (the rdf:subject/predicate/
# object component triples, an rdf:reifies triple, and — for the
# reifier-binding-shorthand/annotation-block forms — the base triple
# itself too), which must land as siblings in the *enclosing* BGP/
# TriplesBlock, not wrapped in a single new node.
#
# The mechanism this relies on, confirmed empirically before committing to
# it (see the Phase 7 plan/CLAUDE.md finding for the full spike): rdflib's
# own expandTriples (the parse action already bound to
# TriplesSameSubjectPath/TriplesSameSubject) flattens whatever token stream
# a single matched statement produces into a list, later regrouped into
# triples 3-at-a-time by algebra.triples() — the exact same mechanism that
# already expands `s p1 o1 ; p2 o2` shorthand into multiple triples. A new
# alternative spliced into TriplesSameSubjectPath/TriplesSameSubject whose
# parse action returns a flat list of terms (length a multiple of 3) rides
# that same mechanism for free — no new expansion logic of our own needed
# past building the right flat list.
#
# Unlike the term-position splices above (order-independent, since "<<("
# never collides with anything else already in GraphTerm/VarOrTerm), these
# four MUST be tried before the ordinary `VarOrTerm + PropertyListPathNotEmpty`
# alternative already in TriplesSameSubjectPath/TriplesSameSubject: that
# ordinary alternative greedily matches just "s p o" and succeeds before
# ever trying a later alternative (pyparsing's MatchFirst is first-match,
# not longest-match), leaving a dangling `~ r` or `{| ... |}` suffix that
# then fails at the *statement* level instead. Confirmed empirically:
# appending (tried last) let the ordinary alternative win and fail later;
# inserting at position 0 (tried first) fixed it, and ordinary triples with
# no annotation suffix at all still parse correctly either way, since these
# new productions simply fail to match (no `~`/`{|`) and pyparsing falls
# through to the ordinary alternative normally.
_RDF_REIFIES = URIRef(str(RDF) + "reifies")


def _make_triple_term(s, p, o) -> TripleTermNode:
    """Build a real TripleTermNode for (s, p, o) - the canonical RDF 1.2
    form of "the triple term s/p/o", not starlayergraph's own internal on-disk
    tt:HASH encoding (three flat rdf:subject/predicate/object triples on a
    synthetic BNode), which this function replaced.

    Why this matters: a plain CompValue('TripleTerm', ...) can't survive
    rdflib's algebra pass unmodified (see triple_term.py's own module
    docstring - unhashable/unorderable), so a TripleTermNode is the only
    form of "this is really one triple term value" that both (a) an
    enclosing rdf:reifies triple can hold in its object slot and (b) this
    project's existing to_rdf.py/from_rdf.py/serialize12.py already know
    how to round-trip - Phase 6 built that support for <<( s p o )>>/
    TRIPLE() and it works unmodified for any TripleTermNode, this one
    included, with zero new code needed here.

    The three-flat-triple encoding this replaced was a real, confirmed bug,
    not just an inconsistency: it's starlayergraph's own *internal*
    representation, meaningful only when re-interpreted by starlayergraph's
    in-memory backend - a real RDF 1.2 engine (Oxigraph) has no idea
    `?tt rdf:subject ?s` etc is supposed to mean anything beyond three
    perfectly ordinary asserted triples about an arbitrary node. Confirmed
    via the W3C fixture `basic-2` (`<<:a :b :c>> ?p ?o`): regenerated text
    using the old encoding matched real data on starlayergraph's in-memory
    backend (which understands its own encoding) but matched *nothing* on
    real Oxigraph, loaded with the identical data via real <<( )>> syntax -
    an actual semantic mistranslation, not a style choice. Explicitly not
    preserving the shorthand *syntax* itself on regeneration (that's a
    separate, deferred concern - see CLAUDE.md) - only the canonical
    rdf:reifies + real-triple-term *meaning* needs to survive round-trip.
    """
    return TripleTermNode("TripleTerm", subject=s, predicate=p, object=o)


def _expand_value(t):
    """A term slot's raw parsed token is sometimes not a plain RDF term but
    a *nested-expansion* list — the shape rdflib's own expandBNodeTriples
    (BlankNodePropertyList's parse action, for `[ p1 o1 ; p2 o2 ]` syntax)
    produces: a flat list whose first element is the value actually
    occupying this position (a fresh blank node) and whose remainder is a
    flat, 3-at-a-time-regroupable list of *additional* triples describing
    that blank node's own properties, which must be spliced into the
    enclosing triple list alongside this term's own reification triples.
    Confirmed by reading algebra.py's own expandTriples, which already
    handles exactly this shape (`isinstance(t, list)`) the same way for
    ordinary (non-annotation) triples — this mirrors that same contract so
    an annotation value like `{| :source [ :graph <...> ] |}` works the
    same way a plain triple's object position already does.

    Returns (value, extra_triples) — extra_triples is [] for a plain term.
    """
    if isinstance(t, list):
        return t[0], list(t)
    return t, []


# s p o ~ r  /  s p o {| ap av ; ... |}  /  s p o ~ r {| ap av ; ... |}  /
# s p o ~ r1 {| ... |} ~ r2 {| ... |}  — reifier-binding and inline
# annotation-block shorthand, and any repeated combination of the two on
# the SAME base triple. Always asserts the base triple s/p/o once,
# regardless of how many suffix elements follow.
#
# Originally built as two entirely separate, mutually-exclusive
# productions (`s p o ~ r` xor `s p o {| |}`) — too narrow, confirmed via
# real W3C test data requiring both together on one statement
# (`annotation-reifier-01`: `?s ?p ?o ~ :iri {| :r ?Z |} .`) and even
# *repeated* (the `annotation-*-multiple-*` test family: `~ r1 {| |} ~ r2
# {| |}`, each suffix minting/using its own independent reifier for the
# SAME underlying triple term). Rebuilt as one combined grammar matching
# the shape confirmed working in the sibling `starlayergraph` project's
# own Turtle-syntax annotation parser (`split_obj_and_annotations` in
# `starlayergraph/parsers/lexer.py`, which already handles this exact
# combination for Turtle *data* — not ported from it, since that's
# string-splitting against already-tokenized text rather than a pyparsing
# grammar, but cross-checked against it as a working reference for the
# semantics, per direct instruction): each suffix is either `~
# [reifier]` optionally followed immediately by `{| ... |}` (both bound to
# the SAME reifier — the one named after `~`, or a fresh one if `~` has no
# name), or a bare `{| ... |}` (implicitly a fresh reifier) — and this can
# repeat one or more times.
#
# Declared here (Forward, filled in far below once
# _AnnotationReifierTermExplicit/Anon exist) rather than at its point of
# use only, since AnnotationSuffixed's own subject/object slots need it
# too — see AnnotationSuffixed's comment.
_ReifierTermValue = Forward()

def _annotation_suffixed_action(tokens):
    s_raw, p, o_raw, suffixes = tokens[0], tokens[1], tokens[2], tokens[3]
    s, s_extra = _expand_value(s_raw)
    o, o_extra = _expand_value(o_raw)
    tt = _make_triple_term(s, p, o)
    result: list = []
    for reifier, block in suffixes:
        r = reifier if reifier is not None else BNode()
        result += [r, _RDF_REIFIES, tt]
        if block is not None:
            pairs = list(block)
            for i in range(0, len(pairs), 2):
                ap = pairs[i]
                av, extra = _expand_value(pairs[i + 1])
                result += [r, ap, av] + extra
    result += [s, p, o] + s_extra + o_extra
    return result


def _build_annotation_suffixed(value_grammar, predicate_grammar):
    """Build one AnnotationSuffixed-shaped production, parameterized by the
    grammar an annotation pair's *value* slot uses — GraphNode (no property
    paths) or GraphNodePath (paths allowed). Needed as two separate
    productions, not one shared one, for the same reason TripleTermExpr/
    TripleTermExprValue are two separate objects: `AnnotationSuffixed` gets
    installed into BOTH TriplesSameSubjectPath (ordinary WHERE-clause
    context, paths legal) *and* TriplesSameSubject (CONSTRUCT-template
    context, paths never legal per the SPARQL grammar — rdflib's own
    `PropertyListPathNotEmpty`/`PropertyListNotEmpty` split exists for
    exactly this reason). Confirmed a real, necessary distinction (not
    over-engineering) via the W3C positive test `annotation-anonreifier-07`
    (`?s ?p ?o {| :r [ :p1|:p2 'ABC'] |} .` in an ordinary WHERE clause,
    needing GraphNodePath's path-aware BlankNodePropertyListPath for the
    annotation value's own internal `[ ... ]`) — using plain GraphNode
    (BlankNodePropertyList, no paths) there was a real, observed failure.

    Only the grammar differs between the two variants; both share the
    exact same `_annotation_suffixed_action`, since the token shape it
    consumes doesn't depend on which value grammar matched.
    """
    # predicate_grammar is `Path | Var` for the WHERE-clause variant, matching
    # rdflib's own `VerbPath | VerbSimple` convention (`PropertyListPathNotEmpty`
    # in rdflib's parser.py) — `Path` alone regressed the far more common
    # plain-variable-predicate case (`{| ?Y ?Z |}`), since Path's own grammar
    # has no Var alternative. `Path` itself is needed there for
    # `annotation-anonreifier-06`/`annotation-reifier-06`
    # (`{| :r/:q 'ABC' |}`) and `-07`/`update-reifier-07`.
    #
    # For the CONSTRUCT-template variant, predicate_grammar is plain VarOrTerm
    # instead — NOT `Path | Var` — for a reason distinct from (and sharper
    # than) "paths aren't legal in CONSTRUCT templates per the grammar"
    # (true, confirmed: plain rdflib itself raises a ParseException on
    # `CONSTRUCT { ?s :r/:q ?o } WHERE {...}`, since ConstructTriples uses
    # TriplesSameSubject, never TriplesSameSubjectPath). The sharper reason:
    # even a *trivial*, single-IRI "path" like `:source` alone parses via
    # Path's grammar as a nested `PathAlternative`/`PathSequence`/`PathElt`
    # CompValue chain, not a bare URIRef — ordinary rdflib simplifies this
    # away via `traverse(q.where, visitPost=translatePath)`, but confirmed
    # (by reading translateQuery's own source) that this walk is *never*
    # run over `template = triples(q[1].template)` for CONSTRUCT specifically
    # — it's built directly from the raw parse tree, bypassing that pass
    # entirely. So even `{| :source ?g |}` (no `/`/`|` at all) inside a
    # CONSTRUCT template left an un-simplified CompValue sitting in the
    # template's predicate slot, and rdflib's own `reorderTriples`/
    # `_knownTerms` (which *does* still run on `template`, via `triples()`)
    # then crashed trying to hash it: `TypeError: cannot use CompValue as a
    # set element` — a real, reproducible failure on the W3C positive tests
    # `annotation-anonreifier-08`/`annotation-reifier-08`, not a
    # hypothetical. A `Path` object dropped directly into a plain WHERE-
    # clause BGP triple's predicate slot is fine, by contrast — that *is*
    # already how rdflib's own `PropertyListPathNotEmpty` works there, and
    # the `translatePath` walk that WHERE clauses do get cleans up the
    # trivial case correctly (confirmed empirically: `{| :source ?g |}` in
    # an ordinary SELECT's WHERE clause comes out with a bare `URIRef`
    # predicate after `prepare_query_12`, not a CompValue).
    pair = predicate_grammar + value_grammar
    block_body = Suppress("{|") + Group(pair + ZeroOrMore(Suppress(";") + pair)) + Suppress("|}")

    def _suffix_tilde_action(tokens):
        return [(tokens[0], tokens[1])]

    suffix_tilde = Suppress("~") + Optional(VarOrTerm, default=None) + Optional(block_body, default=None)
    suffix_tilde.add_parse_action(_suffix_tilde_action)

    def _suffix_block_action(tokens):
        return [(None, tokens[0])]

    suffix_block = block_body.copy()
    suffix_block.add_parse_action(_suffix_block_action)

    suffix = suffix_tilde | suffix_block

    # Subject/object use _ReifierTermValue (declared above, filled in below
    # once _AnnotationReifierTermExplicit/Anon exist), not plain VarOrTerm —
    # confirmed necessary via `annotation-anonreifier-03`
    # (`:s :p <<:a :b :c>> {| ?q ?z |}`, whose base triple's OBJECT is
    # itself a bare reifier-shorthand term). Predicate stays plain
    # VarOrTerm, unchanged — no test evidences a need to narrow it here.
    prod = _ReifierTermValue + VarOrTerm + _ReifierTermValue + Group(OneOrMore(suffix))
    prod.add_parse_action(_annotation_suffixed_action)
    return prod


# s p o ~ r  /  s p o {| ap av ; ... |}  /  s p o ~ r {| ap av ; ... |}  /
# s p o ~ r1 {| ... |} ~ r2 {| ... |}  — reifier-binding and inline
# annotation-block shorthand, and any repeated combination of the two on
# the SAME base triple. Always asserts the base triple s/p/o once,
# regardless of how many suffix elements follow.
#
# Originally built as two entirely separate, mutually-exclusive
# productions (`s p o ~ r` xor `s p o {| |}`) — too narrow, confirmed via
# real W3C test data requiring both together on one statement
# (`annotation-reifier-01`: `?s ?p ?o ~ :iri {| :r ?Z |} .`) and even
# *repeated* (the `annotation-*-multiple-*` test family: `~ r1 {| |} ~ r2
# {| |}`, each suffix minting/using its own independent reifier for the
# SAME underlying triple term). Rebuilt as one combined grammar matching
# the shape confirmed working in the sibling `starlayergraph` project's
# own Turtle-syntax annotation parser (`split_obj_and_annotations` in
# `starlayergraph/parsers/lexer.py`, which already handles this exact
# combination for Turtle *data* — not ported from it, since that's
# string-splitting against already-tokenized text rather than a pyparsing
# grammar, but cross-checked against it as a working reference for the
# semantics, per direct instruction): each suffix is either `~
# [reifier]` optionally followed immediately by `{| ... |}` (both bound to
# the SAME reifier — the one named after `~`, or a fresh one if `~` has no
# name), or a bare `{| ... |}` (implicitly a fresh reifier) — and this can
# repeat one or more times.
#
# Declared here (Forward, filled in far below once
# _AnnotationReifierTermExplicit/Anon exist) rather than at its point of
# use only, since AnnotationSuffixed's own subject/object slots need it
# too — see _build_annotation_suffixed's comment.
_ReifierTermValue = Forward()

AnnotationSuffixed = _build_annotation_suffixed(GraphNodePath, Path | Var)
AnnotationSuffixedConstruct = _build_annotation_suffixed(GraphNode, VarOrTerm)

# << s p o >>  /  << s p o ~ reifier >>  — reifier-reference TERMS, not
# whole-statement productions. `<<s p o>>` denotes the (fresh or given)
# reifier of the triple s/p/o — it does NOT assert the base triple s/p/o
# itself, only the reification triples plus (if given) `reifier
# rdf:reifies tt`. Unlike `<<( s p o )>>`/`TRIPLE()` (TripleTermExpr/
# TripleTermCall above, a self-contained value with no side effect), this
# form has a side effect (extra triples to assert) — so it can't be spliced
# into GraphTerm/VarOrTerm the way TripleTermExpr is; it needs the same
# nested-list "value + side-effect triples" contract rdflib's own
# BlankNodePropertyList (`[ p o ]`) uses (see expandBNodeTriples/
# expandTriples/expandCollection in rdflib's parser.py/algebra.py): a
# parse action returning `[[value, *extra_triples]]`, where `extra_triples`
# is itself a flat, already-3-at-a-time-grouped list of complete triples
# (never a stray fragment) and `value` doubles as the subject of the first
# of those triples (so the shape is self-consistent whether this ends up
# completing an enclosing triple's object slot, spliced bare as a
# TriplesNode statement, or nested inside a collection/blank-node-property-
# list) — confirmed against rdflib's own expandTriples source before
# relying on it, not assumed.
#
# Installed into TriplesNode/TriplesNodePath (not GraphTerm/VarOrTerm
# directly, and not TriplesSameSubject/TriplesSameSubjectPath directly
# either — see install()): TriplesNode/TriplesNodePath already sit under
# every position that needs to accept this — GraphNode/GraphNodePath
# (ordinary object position, inside `[...]`, inside `(...)`), *and*
# TriplesSameSubject's/TriplesSameSubjectPath's own second alternative
# (`TriplesNode(Path) + PropertyList(Path)`, which is how a bare `[ :p :o
# ] .` statement already works) — so one splice point covers "used as an
# ordinary object", "used bare as a whole statement's subject with no
# further properties" (`<< ?s ?p ?o >> .`), and "nested inside a
# collection/blank-node-property-list" all at once, with zero extra
# productions.
# Predicate uses the same restricted primitive as the ground triple term
# (_TripleTermPredicate, Var | iri) — confirmed necessary via the W3C
# negative test `bnode-predicate-anonreifier` (`<<?s [] ?o>> ?p2 ?o2 .`, an
# anonymous blank node predicate, must be rejected; a predicate is never
# legal as a blank node in RDF's data model).
#
# Subject and object use _ReifierTermValue (below), not plain VarOrTerm —
# deliberately MORE permissive than the ground triple term's own
# _TripleTermSubjectExpr (which excludes ANON `[]`; confirmed via the W3C
# *positive* test `subject-tripleterm` that `<<[] ?R :z ~ :iri>>`, an
# anonymous blank-node subject, IS legal for this reifier-reference form
# specifically) — and, since _ReifierTermValue also carries a nested
# reifier-shorthand-term alternative, lets a reifier-shorthand term's own
# subject/object be *another* reifier-shorthand term or a nested ground
# triple term (the latter already reachable via VarOrTerm, which
# install() mutates to include TripleTermExpr/TripleTermCall). Confirmed
# necessary via real W3C test data that was NOT reachable with plain
# VarOrTerm: `nested-reifier-02`/`nested-anonreifier-*`
# (`<<:a :q <<:s :p ?O ~ :iri>> ~ _:bnode>> :r :z .` — the outer term's
# object is another reifier-shorthand term) and `subject-tripleterm`'s
# second half (`<< <<(:x ?R :z )>> :p <<:a :b [] >> ~ _:bnode >> :q ...` —
# the outer term's subject is a nested *ground* triple term).
#
# NOT GraphNode: tried that first, and it let a bare Collection/
# BlankNodePropertyList (`(...)`/`[ p o ]`) through too — GraphNode
# includes TriplesNode, and TriplesNode.expr is the SAME shared object
# install() splices these two reifier-shorthand productions into (see
# their own installation comment) as `Collection | BlankNodePropertyList |
# ...`, so referencing GraphNode here pulled in siblings that don't belong
# in this specific slot. Confirmed a real regression via the W3C negative
# tests `quoted-list-subject-*`/`quoted-list-object-*`/
# `quoted-list-predicate-*` (`<<?s :p ("abc") >> :q 123 .` — a Collection
# as a reifier-shorthand term's own object — must be rejected). Fixed by
# building a narrower, dedicated Forward here instead, admitting only
# plain terms (via VarOrTerm, itself already carrying ground triple terms)
# and nested reifier-shorthand terms specifically — nothing TriplesNode
# itself would add.
#
# A match here comes back as either a plain term (VarOrTerm/ground triple
# term) or the special nested-list shape a reifier-shorthand match
# produces (see _annotation_reifier_term below) — `_expand_value` already
# knows how to unwrap either uniformly (see `_annotation_block_action`'s
# use of it for the exact same contract), reused here rather than
# inventing a second unwrapping convention.
# (_ReifierTermValue itself is declared earlier, alongside AnnotationSuffixed
# — also above this point — since that production needs it too; both fill
# it in together, below, once these two productions exist.)

_AnnotationReifierTermAnon = (
    Suppress("<<") + _ReifierTermValue + _TripleTermPredicate + _ReifierTermValue + Suppress(">>")
)


def _annotation_reifier_term_anon_action(tokens):
    s, p, o = tokens[0], tokens[1], tokens[2]
    return [_annotation_reifier_term(s, p, o, BNode())]


_AnnotationReifierTermAnon.add_parse_action(_annotation_reifier_term_anon_action)

_AnnotationReifierTermExplicit = (
    Suppress("<<")
    + _ReifierTermValue
    + _TripleTermPredicate
    + _ReifierTermValue
    + Suppress("~")
    + VarOrTerm
    + Suppress(">>")
)


def _annotation_reifier_term_explicit_action(tokens):
    s, p, o, r = tokens[0], tokens[1], tokens[2], tokens[3]
    return [_annotation_reifier_term(s, p, o, r)]


_AnnotationReifierTermExplicit.add_parse_action(_annotation_reifier_term_explicit_action)

_ReifierTermValue <<= VarOrTerm | _AnnotationReifierTermExplicit | _AnnotationReifierTermAnon


def _annotation_reifier_term(s_raw, p, o_raw, r) -> list:
    s, s_extra = _expand_value(s_raw)
    o, o_extra = _expand_value(o_raw)
    return _annotation_reifier_term_resolved(s, p, o, r) + s_extra + o_extra


def _annotation_reifier_term_resolved(s, p, o, r) -> list:
    # t[0] must equal r *by virtue of* being the first element of the
    # single embedded triple (r, RDF.reifies, tt) below, not a separately
    # prepended copy — rdflib's own expandTriples() (see its isinstance(t,
    # list) branch) uses t[0] BOTH as the value slotted into an enclosing
    # triple's object position (via a plain `res.append(t[0])`) AND,
    # completely separately, folds the *whole* t (t[0] included) back in as
    # one or more new self-contained triples of its own. Duplicating r as a
    # standalone t[0] ahead of its real first triple breaks that (confirmed
    # via `these aint triples` from rdflib's algebra.triples() when tried).
    tt = _make_triple_term(s, p, o)
    return [r, _RDF_REIFIES, tt]


_ANNOTATION_TERM_FORMS = (
    _AnnotationReifierTermExplicit,
    _AnnotationReifierTermAnon,
)

def _already_installed() -> bool:
    """State-based idempotency check - is TripleTermCallValue actually
    present in PrimaryExpression.exprs right now - rather than trusting a
    module-level boolean set once and never re-checked.

    Confirmed necessary, not just extra caution: pyparsing's own
    ParseExpression.streamline() (rdflib.plugins.sparql.parser's grammar
    objects are streamlined the first time they're actually used to parse
    something) collapses a MatchFirst with exactly 2 children by splicing
    a nested MatchFirst's own .exprs directly into the parent, *replacing*
    self.exprs outright (not appending) - confirmed via pyparsing's own
    source (ParseExpression.streamline). PrimaryExpression starts with
    exactly 2 children in stock rdflib. Reproduced directly (not
    theoretical): under pytest with assertion rewriting enabled
    specifically (--assert=plain avoids it - the trigger inside pytest's
    own import hook wasn't fully isolated further, but the symptom is
    unambiguous and repeatable), PrimaryExpression's *same* Python object
    (confirmed via id() - not a duplicate import/module reload) ends up
    with its .exprs reset to a flattened, pristine-rdflib 78-entry list
    with every production this module installed missing, while a
    module-level `_INSTALLED = True` flag installed once at import time
    has no way to detect this and never re-runs install(). A boolean flag
    can only ever be as trustworthy as the assumption that nothing else
    ever resets the objects it's guarding - confirmed false here, so this
    checks the live objects directly instead.
    """
    return TripleTermCallValue in PrimaryExpression.exprs


def install(force: bool = False) -> None:
    """Splice the new productions into rdflib's own grammar objects, in
    place, via pyparsing's public ``MatchFirst.append()``. Idempotent - safe
    to call more than once (e.g. from multiple import sites), and - see
    ``_already_installed``'s own docstring - safe to call again after
    something *else* has reset the grammar objects this already installed
    into, which a simple call-once boolean flag is not.

    ``force=True`` skips the ``_already_installed()`` short-circuit and
    re-runs every mutation unconditionally - used by ``parse12.py``'s own
    parse-failure retry path as a last-resort recovery, for the residual
    corruption case ``_already_installed()`` itself doesn't reliably catch
    (confirmed empirically still possible under some pytest runs even with
    the per-call re-verification in place - the exact trigger inside
    pytest's import machinery was not fully isolated, but a forced,
    unconditional re-append immediately before retrying the same parse
    was confirmed to recover it every time it was tried). Appending an
    already-present production twice is harmless for parsing correctness
    (MatchFirst just gets a redundant alternative - tries a bit more, never
    matches differently) - this is a recovery hatch, not a hot path, so
    that small inefficiency is an acceptable trade for actually working.
    """
    if not force and _already_installed():
        return
    for rule in (GraphTerm, VarOrTerm, GraphNode, GraphNodePath):
        rule.append(TripleTermExpr)
        rule.append(TripleTermCall)
        # Must be tried *before* plain RDFLiteral (already one of this
        # rule's own alternatives, transitively via GraphTerm) - see
        # LangDirLiteral's own comment for why appending wouldn't work
        # (RDFLiteral partially matches "nl" out of "nl--ltr" and
        # *succeeds*, so MatchFirst never backtracks to try a later
        # alternative at all).
        rule.exprs.insert(0, LangDirLiteral)
    # Expression position: a triple term usable directly as a PrimaryExpression
    # value (BIND(<<(...)>> AS ?x)), and the four accessor builtins usable
    # anywhere BuiltInCall is (BIND/FILTER/SELECT (... AS ?x)/GROUP BY/etc.,
    # per PrimaryExpression/Constraint/GroupCondition all referencing
    # BuiltInCall — see rdflib's parser.py). Uses the *Value variants
    # (restricted subject grammar) — see _TripleTermSubjectExpr's own
    # comment for why this must be a different pair of objects from the
    # ones spliced into GraphTerm/VarOrTerm/GraphNode/GraphNodePath above.
    PrimaryExpression.append(TripleTermExprValue)
    PrimaryExpression.append(TripleTermCallValue)
    PrimaryExpression.exprs.insert(0, LangDirLiteral)
    # VALUES { <<(:s :p :o)>> ... } — a ground triple term used as a data
    # block value. Self-contained (no side-effect triples, unlike the
    # annotation forms below), so a plain .append() is enough — same as
    # every other DataBlockValue alternative (iri/RDFLiteral/etc). Also
    # uses the *Value variants — a VALUES row is a ground value, not a
    # pattern, treated the same as expression position (see
    # TripleTermExprValue's own comment on the lack of direct test
    # evidence for this specific position).
    DataBlockValue.append(TripleTermExprValue)
    DataBlockValue.append(TripleTermCallValue)
    DataBlockValue.exprs.insert(0, LangDirLiteral)
    BuiltInCall.append(Builtin_isTRIPLE)
    BuiltInCall.append(Builtin_SUBJECT)
    BuiltInCall.append(Builtin_PREDICATE)
    BuiltInCall.append(Builtin_OBJECT)
    BuiltInCall.append(Builtin_LANGDIR)
    BuiltInCall.append(Builtin_hasLANGDIR)
    BuiltInCall.append(Builtin_hasLANG)
    BuiltInCall.append(Builtin_STRLANGDIR)

    # Annotation/reification-shorthand forms must be *inserted at the front*
    # (tried first), not appended: the ordinary `VarOrTerm +
    # PropertyListPathNotEmpty` alternative already in these two objects
    # greedily matches just "s p o" and succeeds before ever trying a later
    # alternative, confirmed empirically to otherwise leave a dangling
    # `~ r`/`{| ... |}` suffix that fails at the statement level instead of
    # being recognized here.
    #
    # TriplesSameSubjectPath (ordinary WHERE-clause context) gets
    # AnnotationSuffixed (path-aware annotation values); TriplesSameSubject
    # (CONSTRUCT-template context, where property paths are never legal)
    # gets AnnotationSuffixedConstruct instead — see
    # _build_annotation_suffixed's own comment for why these must be two
    # different productions, not the same one installed into both.
    TriplesSameSubjectPath.exprs.insert(0, AnnotationSuffixed)
    TriplesSameSubjectPath._defaultName = None
    TriplesSameSubject.exprs.insert(0, AnnotationSuffixedConstruct)
    TriplesSameSubject._defaultName = None

    # `<<s p o>>`/`<<s p o ~ r>>` reifier-reference terms: appended (order
    # vs Collection/BlankNodePropertyList doesn't matter — disjoint leading
    # tokens; order between the two new forms themselves doesn't matter
    # either, see their own comment) to TriplesNode/TriplesNodePath's
    # underlying MatchFirst (`.expr`, since both are pyparsing `Forward`
    # wrappers, not MatchFirst objects themselves — confirmed
    # `TriplesNode.expr`/`TriplesNodePath.expr` are real MatchFirst objects
    # with a public `.append()` before relying on this). This single splice
    # point is what makes the new forms usable everywhere TriplesNode(Path)
    # already is: GraphNode/GraphNodePath (ordinary object position, inside
    # `[...]`, inside `(...)`), and TriplesSameSubject(Path)'s own
    # `TriplesNode(Path) + PropertyList(Path)` alternative (a bare `<<s p o>>
    # .` statement, PropertyList empty) — see the forms' own comment.
    for rule in (TriplesNode, TriplesNodePath):
        for form in _ANNOTATION_TERM_FORMS:
            rule.expr.append(form)
