"""Private module (renamed from ``grammar12.py`` 2026-10-06 - no external
caller needs this directly; only ``parse12.py`` calls ``install()``, at
import time, plus two test ``conftest.py`` files that force it early for
test-ordering reasons).

New pyparsing productions for SPARQL 1.2 triple-term syntax
(``<<( s p o )>>`` / ``TRIPLE(s, p, o)``), spliced into rdflib's own real
SPARQL grammar (``rdflib.plugins.sparql.parser``) in place.

This is deliberately *not* a text-rewrite-then-reparse approach (the
approach `starlayer.graph`'s ``sparql12_to_11.py`` uses, for its own good
reasons) — it extends rdflib's actual pyparsing grammar the same way rdflib
extends itself: a ``Comp``/``Param``-built production with a parse action
that constructs an algebra-tree node directly during parsing.

The extension point: the grammar rules that need to accept a triple term
— ``GraphTerm``, ``VarOrTerm``, ``GraphNode``, ``GraphNodePath`` — are
plain ``pyparsing.MatchFirst`` objects with a public ``.append(expr)``
method.
Because pyparsing composes grammar rules by object reference (every rule
that transitively depends on ``GraphTerm``, e.g. ``TriplesSameSubject``,
holds a reference to the *same* object, not a copy), appending a new
alternative to it in place makes the addition visible to every rule built on
top of it, without forking rdflib's grammar module or touching the installed
package on disk.
"""

from __future__ import annotations

import re

from pyparsing import CaselessKeyword as Keyword
from pyparsing import (
    Forward,
    Group,
    Literal,
    Optional,
    ParseResults,
    Regex,
    Suppress,
    ZeroOrMore,
)
from rdflib import BNode, URIRef, Variable
from rdflib import Literal as RDFTermLiteral
from rdflib.namespace import RDF
from rdflib.plugins.sparql.parser import (
    BLANK_NODE_LABEL,
    NIL,
    A,
    BlankNode,
    BlankNodePropertyList,
    BlankNodePropertyListPath,
    BuiltInCall,
    DataBlockValue,
    Expression,
    GraphNode,
    GraphNodePath,
    GraphTerm,
    PrimaryExpression,
    String,
    TriplesNode,
    TriplesNodePath,
    TriplesSameSubject,
    TriplesSameSubjectPath,
    Var,
    VarOrTerm,
    Verb,
    VerbPath,
    VerbSimple,
    iri,
)
from rdflib.plugins.sparql.parserutils import Comp, CompValue, Param

from .triple_term import TripleTermNode
from .vocab import encode_dirlang_datatype

# RDF 1.2's "a triple term's subject is never a Literal, and never itself a
# nested triple term (nesting is only legal in object position)" rule turns
# out to hold only when the ground triple term is used as an EXPRESSION
# VALUE (BIND/FILTER/VALUES) — not when it's used in ordinary TERM/pattern
# position. Real, contrasting W3C tests confirm this, not mere symmetry:
# `tripleterm-subject-03`
# (`BIND( <<( <<(:s :p :o )>> :q :z )>> AS ?X )`, nested ground triple term
# as subject) and `bindbnode-tripleterm` (`BIND(<<( [] ?p ?o )>> AS ?t)`,
# anonymous `[]` as subject) must both be REJECTED — but
# `nested-tripleterm-02`/`compound-tripleterm-subject` (the identical
# shapes, in ordinary triple-pattern position, e.g.
# `<<( <<(?S :p :o )>> :r :z )>> :q 1 .`) and `bnode-tripleterm-03`
# (`<<([] :p [] )>> :q :z .`) are POSITIVE tests requiring exactly what the
# BIND versions reject. One shared grammar object can't enforce two
# different rules depending on where it's spliced in, so this is built as
# two genuinely separate pairs of `Comp` objects below, each with its own
# subject grammar, rather than reusing one.
#
# Deliberately built from rdflib's *primitive* term productions (Var/iri/
# BlankNode) rather than referencing GraphTerm/VarOrTerm directly: those two
# objects are exactly what install() (below) mutates in place to add the new
# triple-term alternative, so referencing them here would make a triple term
# legal in its own subject slot too, once install() runs — independent
# primitives avoid that.
# `a` (the standard SPARQL/Turtle shorthand for rdf:type) must be legal
# here too, not just Var | iri: per the W3C fixture
# `triple-on-triple-terms` (`<<(:x a :z)>>`, `a` as a triple term's own
# predicate) - `a` is a dedicated token (`A`, matched and mapped to
# rdf:type by rdflib's own grammar) spliced into ordinary Verb/VerbSimple
# productions elsewhere, never part of plain `iri` itself, so a triple
# term's own restricted predicate grammar needs it explicitly.
_TripleTermPredicate = Var | iri | A

# Forward-declared so the object position (and, for the permissive/pattern
# variant, the subject position too) can itself be a (possibly nested)
# triple term — filled in below once TripleTermExpr/TripleTermCall exist,
# the same declare-then-fill-in pattern rdflib's own grammar uses for Path/
# TriplesNode.
TripleTermObject = Forward()

# TERM/pattern-position subject: any BlankNode form (rdflib's own
# BLANK_NODE_LABEL-or-ANON alias) or a nested triple term, both legal per
# the positive tests cited above.
_TripleTermSubjectPattern = Var | iri | BlankNode | TripleTermObject

# EXPRESSION/value-position subject: BLANK_NODE_LABEL only (the `_:x` form —
# excludes anonymous `[]`) and never a nested triple term, per the
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

    Args:
        tokens: The pyparsing ``ParseResults`` for one matched TripleTerm
            production; ``tokens[0]`` is the just-built ``CompValue``.

    Returns:
        The promoted, validated ``TripleTermNode``.
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
# spec 17.4.6 — needed, not merely permitted by the grammar text, per the
# W3C positive test `expr-tripleterm-04`:
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
# model: regenerate SPARQL 1.2 text and hand off to starlayer.graph, never
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
# names exist in stock SPARQL 1.1 (plain rdflib parses `LANG(?x)` fine via
# its own Builtin_LANG, but raises a ParseException on all four of these)
# - genuinely new grammar, same shape as the triple-term
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
# notion of the "--dir" suffix, and it doesn't just fail to capture it:
# matched against "nl--ltr", LANGTAG's regex consumes only "nl" (a lone "-"
# can't start a new `-[a-zA-Z0-9]+` group, since the very next character is
# a second "-", not alphanumeric), so RDFLiteral itself *succeeds* with
# "a"@nl as its value, leaving "--ltr" as unconsumed trailing text. That
# failure surfaces far away from where it actually happened - at the
# outermost SelectQuery rule, not locally at the literal - because
# pyparsing's MatchFirst doesn't backtrack into an alternative that already
# succeeded once parsing has moved past it; true in plain, unmodified
# rdflib, with zero involvement from this project's own grammar work
# (`BIND("a"@nl--ltr AS ?a)` alone fails the same way). Fixing this means
# the new production must be tried *before* plain RDFLiteral, not merely
# added as a further alternative - same lesson as the annotation-shorthand
# forms below (see install()'s own comment).
#
# Represented as an ordinary rdflib Literal using this project's own
# dirlang: datatype encoding (vocab.encode_dirlang_datatype), not lang= -
# `Literal(text, lang="nl--ltr")` raises outright even with
# normalize=False (that flag only skips *value* canonicalization, not the
# separate lang-tag *validation* rdflib's Literal constructor always runs).
# Deliberately this project's *own* encoding (own namespace under vocab.SALG),
# not starlayer.graph's identically-shaped one, despite starlayer.graph already
# having established the exact same trick: reusing starlayer.graph's would mean
# every encoded query containing a dirLangString literal is only safely
# storable in a plain rdflib.Graph, never a real StarLayerGraph, since
# StarLayerGraph.value()/.triples() unconditionally decodes any literal
# tagged with *its own* dirlang: datatype back into a real DirLangString
# object - which this project's from_rdf.py decoder has no branch for and
# crashes on. Being a plain Literal (not a new CompValue/node type the way
# TripleTermNode is) still means to_rdf.py's existing _LEAF_TERM_TYPES
# branch needs zero new code either way - only serialize12.py needs a
# branch, to turn this project's own dirlang: datatype back into real
# "text"@lang--dir syntax on the way out.
#
# Direction restricted to exactly "ltr"/"rtl" (not a general identifier) -
# RDF 1.2 Concepts sec 3.4 requires exactly one of those two, lowercase
# only, no case-insensitive matching - matching the same restriction
# starlayer.graph's own Turtle parser already enforces (its own W3C test
# suite fixture nt-ttl12-langdir-bad-2).
def _langdir_literal_action(tokens):
    node = tokens[0]
    text = str(node["string"])
    # Language tags compare ASCII case-insensitively (RDF 1.2 Concepts); data
    # is stored lower-cased, so a pattern or FILTER constant must be too.
    lang = str(node["lang"]).lower()
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
# The mechanism this relies on: rdflib's own expandTriples (the parse
# action already bound to TriplesSameSubjectPath/TriplesSameSubject)
# flattens whatever token stream
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
# then fails at the *statement* level instead. Appending (tried last) lets
# the ordinary alternative win and fail later; inserting at position 0
# (tried first) fixes it, and ordinary triples with no annotation suffix at
# all still parse correctly either way, since these new productions simply
# fail to match (no `~`/`{|`) and pyparsing falls through to the ordinary
# alternative normally.
# Annotations: `o ~ r`, `o {| p v ; ... |}`, `o ~ r {| ... |}` and any
# repetition of those after ONE OBJECT of a property list (spec rules
# Object ::= GraphNode Annotation, Annotation ::= (Reifier | AnnotationBlock)*,
# and the Path twins). Redesigned 2026-10-26 (#93): the earlier production
# matched one whole `s p o suffix` statement, so an annotation could not
# be followed by `,` or `;`, could not follow `a`, a bracketed list, a
# collection or another annotation block, and could not nest.
#
# Mechanism. rdflib's ObjectList/ObjectListPath alias the shared GraphNode
# object, so they cannot be edited in place. install() instead replaces the
# alternatives of the four consumers of a property list (TriplesSameSubject,
# TriplesSameSubjectPath, BlankNodePropertyList, BlankNodePropertyListPath)
# with copies built from `_ObjectAnn`, an object plus its annotation
# suffixes. An annotated object is parsed to an `_Annotated` marker (not
# a list, so rdflib's own bracket-list handling never sees it);
# `_expand_triples12` is rdflib's expandTriples plus one branch: after the
# object has been emitted, the marker adds `r rdf:reifies <<( s p o )>>` and
# the annotation triples, where s and p are the subject and predicate of
# the `;` / `,` list the object belongs to. A `{| |}` block is expanded by
# the same function with the reifier as its subject, so blocks nest.
_RDF_REIFIES = URIRef(str(RDF) + "reifies")


def _make_triple_term(s, p, o) -> TripleTermNode:
    """Build the TripleTermNode for (s, p, o): the canonical RDF 1.2 triple
    term (not starlayer.graph's internal ``tt:HASH`` encoding, which is
    private to its in-memory backend and means nothing to another engine).
    A plain CompValue would not survive rdflib's algebra pass (unhashable,
    unorderable; see triple_term.py). Only the ``rdf:reifies`` meaning is
    kept, not the shorthand syntax.
    """
    return TripleTermNode("TripleTerm", subject=s, predicate=p, object=o)


class _Annotated:
    """An object together with its annotation suffixes, as parsed.

    ``suffixes`` is a list of ``(reifier_or_None, block_tokens_or_None)``.
    """

    __slots__ = ("obj", "suffixes")

    def __init__(self, obj, suffixes):
        self.obj = obj
        self.suffixes = suffixes


def _simple_predicate(p):
    """The IRI, ``a`` or variable a predicate token stands for.

    A path-position predicate is wrapped in ``PathAlternative`` /
    ``PathSequence`` / ``PathElt`` nodes even when it is a single IRI (the
    prefixed name is not resolved yet at parse time), so unwrap the
    one-child wrappers. An annotation reifies one triple, so a real
    property path (``^:p``, ``:p/:q``, ``:p*``, ``!:p``) is rejected.
    """
    while isinstance(p, CompValue):
        if p.name in ("PathAlternative", "PathSequence") and len(p.part) == 1:
            p = p.part[0]
        elif p.name == "PathElt" and not dict.get(p, "mod"):
            p = p.part
        elif p.name in ("pname", "iri", "Var"):
            return p
        else:
            break
    if isinstance(p, (URIRef, Variable)):
        return p
    raise ValueError(
        "starlayer.sparql: a reifier or annotation needs a single IRI or variable as its predicate, not a property path"
    )


def _annotation_triples(s, p, o, suffixes) -> list:
    tt = _make_triple_term(s, _simple_predicate(p), o)
    out: list = []
    for reifier, block in suffixes:
        r = reifier if reifier is not None else BNode()
        out += [r, _RDF_REIFIES, tt]
        if block:
            out += _expand_triples12([r] + block)
    return out


def _expand_triples12(terms) -> list:
    """rdflib's ``expandTriples`` (``,`` / ``;`` / bracket-list expansion)
    with annotated objects: see the comment above ``_Annotated``."""
    last_subject, last_predicate = None, None
    res: list = []
    n = len(terms)
    for i, t in enumerate(terms):
        annotated = None
        if isinstance(t, _Annotated):
            annotated, t = t, t.obj
            subj, pred = last_subject, last_predicate
        if t == ",":
            res.extend([last_subject, last_predicate])
        elif t == ";":
            if i + 1 == n or terms[i + 1] == ";" or terms[i + 1] == ".":
                continue
            res.append(last_subject)
        elif isinstance(t, list):
            if (len(res) % 3) == 2:
                res.append(t[0])
            if len(t) > 1:
                res += t
            if i + 1 < n and terms[i + 1] not in [".", ",", ";"]:
                last_subject, last_predicate = t[0], None
                res.append(t[0])
        elif isinstance(t, ParseResults):
            res += t.as_list()
        elif t != ".":
            res.append(t)
            if (len(res) % 3) == 1:
                last_subject = t
            elif (len(res) % 3) == 2:
                last_predicate = t
        if annotated is not None:
            obj = t[0] if isinstance(t, list) else t
            res += _annotation_triples(subj, pred, obj, annotated.suffixes)
    return res


def _expand_bnode_triples12(terms) -> list:
    return [_expand_triples12([BNode()] + terms.as_list()[0])]


# Reifier ::= '~' VarOrReifierId?  (a literal or `()` is not allowed).
_VarOrReifierId = Var | iri | BlankNode


def _build_annotated_object(property_list_not_empty_for_block):
    """One ``Object Annotation`` production; the argument is a Forward for
    the matching property list (path or no path) used inside ``{| |}``."""
    block = Suppress("{|") + Group(property_list_not_empty_for_block) + Suppress("|}")
    tilde = Suppress("~") + Optional(_VarOrReifierId, default=None) + Optional(block, default=None)
    tilde.add_parse_action(lambda t: [(t[0], t[1].as_list() if t[1] is not None else None)])
    bare = block.copy()
    bare.add_parse_action(lambda t: [(None, t[0].as_list())])
    return tilde | bare


def _annotated_object_action(tokens):
    if len(tokens) == 1:
        return None
    return [_Annotated(tokens[0], list(tokens[1:]))]


def _build_property_list(verb, node, object_ann):
    object_list = object_ann + ZeroOrMore("," + object_ann)
    return verb + object_list + ZeroOrMore(";" + Optional(verb + object_list))


_PropertyListNotEmptyAnn = Forward()
_PropertyListPathNotEmptyAnn = Forward()

_ObjectAnn = GraphNode + ZeroOrMore(_build_annotated_object(_PropertyListNotEmptyAnn))
_ObjectAnn.add_parse_action(_annotated_object_action)
_ObjectPathAnn = GraphNodePath + ZeroOrMore(_build_annotated_object(_PropertyListPathNotEmptyAnn))
_ObjectPathAnn.add_parse_action(_annotated_object_action)

_PropertyListNotEmptyAnn <<= _build_property_list(Verb, GraphNode, _ObjectAnn)
_PropertyListPathNotEmptyAnn <<= _build_property_list(VerbPath | VerbSimple, GraphNodePath, _ObjectPathAnn)

# The consumers' alternatives, rebuilt (see the comment above _Annotated).
_TSS_ALTERNATIVES = [
    VarOrTerm + _PropertyListNotEmptyAnn,
    TriplesNode + Optional(_PropertyListNotEmptyAnn),
]
_TSSP_ALTERNATIVES = [
    VarOrTerm + _PropertyListPathNotEmptyAnn,
    TriplesNodePath + Optional(_PropertyListPathNotEmptyAnn),
]
_BNPL_BODY = Suppress("[") + _PropertyListNotEmptyAnn + Suppress("]")
_BNPLP_BODY = Suppress("[") + _PropertyListPathNotEmptyAnn + Suppress("]")


def _install_annotated_objects() -> None:
    """Point rdflib's four property-list consumers at the annotation-aware
    productions above. Assignment, not append, so it is idempotent and does
    not depend on whether pyparsing already streamlined the originals."""
    TriplesSameSubject.exprs[:] = _TSS_ALTERNATIVES
    TriplesSameSubject.set_parse_action(_expand_triples12)
    TriplesSameSubject.streamlined = False
    TriplesSameSubjectPath.exprs[:] = _TSSP_ALTERNATIVES
    TriplesSameSubjectPath.set_parse_action(_expand_triples12)
    TriplesSameSubjectPath.streamlined = False
    BlankNodePropertyList.expr = _BNPL_BODY
    BlankNodePropertyList.set_parse_action(_expand_bnode_triples12)
    BlankNodePropertyList.streamlined = False
    BlankNodePropertyListPath.expr = _BNPLP_BODY
    BlankNodePropertyListPath.set_parse_action(_expand_bnode_triples12)
    BlankNodePropertyListPath.streamlined = False


def _expand_value(t):
    """A reifier-term slot's token is a plain RDF term or the nested list
    ``[value, *extra_triples]`` that ``expandBNodeTriples`` produces; return
    ``(value, extra_triples)``."""
    if isinstance(t, list):
        return t[0], list(t)
    return t, []


_ReifierTermValue = Forward()

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
# list) — per rdflib's own expandTriples source.
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
# (_TripleTermPredicate, Var | iri) — needed per the W3C negative test
# `bnode-predicate-anonreifier` (`<<?s [] ?o>> ?p2 ?o2 .`, an anonymous
# blank node predicate, must be rejected; a predicate is never legal as a
# blank node in RDF's data model).
#
# Subject and object use _ReifierTermValue (below), not plain VarOrTerm —
# deliberately MORE permissive than the ground triple term's own
# _TripleTermSubjectExpr (which excludes ANON `[]`; per the W3C *positive*
# test `subject-tripleterm` that `<<[] ?R :z ~ :iri>>`, an anonymous
# blank-node subject, IS legal for this reifier-reference form
# specifically) — and, since _ReifierTermValue also carries a nested
# reifier-shorthand-term alternative, lets a reifier-shorthand term's own
# subject/object be *another* reifier-shorthand term or a nested ground
# triple term (the latter already reachable via VarOrTerm, which
# install() mutates to include TripleTermExpr/TripleTermCall). Needed for
# real W3C test data not reachable with plain VarOrTerm:
# `nested-reifier-02`/`nested-anonreifier-*`
# (`<<:a :q <<:s :p ?O ~ :iri>> ~ _:bnode>> :r :z .` — the outer term's
# object is another reifier-shorthand term) and `subject-tripleterm`'s
# second half (`<< <<(:x ?R :z )>> :p <<:a :b [] >> ~ _:bnode >> :q ...` —
# the outer term's subject is a nested *ground* triple term).
#
# NOT GraphNode: GraphNode includes TriplesNode, and TriplesNode.expr is
# the SAME shared object install() splices these two reifier-shorthand
# productions into (see their own installation comment) as `Collection |
# BlankNodePropertyList | ...`, so referencing GraphNode here would pull
# in a bare Collection/BlankNodePropertyList (`(...)`/`[ p o ]`) too —
# siblings that don't belong in this specific slot, per the W3C negative
# tests `quoted-list-subject-*`/`quoted-list-object-*`/
# `quoted-list-predicate-*` (`<<?s :p ("abc") >> :q 123 .` — a Collection
# as a reifier-shorthand term's own object — must be rejected). Built as a
# narrower, dedicated Forward here instead, admitting only plain terms
# (via VarOrTerm, itself already carrying ground triple terms) and nested
# reifier-shorthand terms specifically — nothing TriplesNode itself would
# add.
#
# A match here comes back as either a plain term (VarOrTerm/ground triple
# term) or the special nested-list shape a reifier-shorthand match
# produces (see _annotation_reifier_term below) — `_expand_value` already
# knows how to unwrap either uniformly (see `_annotation_block_action`'s
# use of it for the exact same contract), reused here rather than
# inventing a second unwrapping convention.
# (_ReifierTermValue itself is declared earlier, above the annotation machinery
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
    + Optional(_VarOrReifierId, default=None)
    + Suppress(">>")
)


def _annotation_reifier_term_explicit_action(tokens):
    s, p, o, r = tokens[0], tokens[1], tokens[2], tokens[3]
    # a bare `~` (Reifier ::= '~' VarOrReifierId?) names a fresh reifier, like the unmarked form
    return [_annotation_reifier_term(s, p, o, r if r is not None else BNode())]


_AnnotationReifierTermExplicit.add_parse_action(_annotation_reifier_term_explicit_action)

# ~NIL guard: VarOrTerm's own grammar (rdflib's parser.py) is
# `Var | iri | RDFLiteral | NumericLiteral | BooleanLiteral | BlankNode |
# NIL | TripleTerm` - it includes NIL (the bare `()` empty-collection
# token, rdf:nil), unlike the real spec's ReifiedTripleSubject/
# ReifiedTripleObject productions (SPARQL 1.2 Query grammar rules
# [117]/[118]), which enumerate exactly the same list *minus* NIL (and
# minus Collection, already excluded below by using VarOrTerm instead of
# GraphNode - see the long comment above this production). Per the
# vendored grammar snapshot
# (tests/graph/vendor/spec_snapshots/sparql12-query.txt) - neither
# production lists NIL as an alternative. Without this guard,
# `<< _:b ex:x () >>` parsed successfully via VarOrTerm's NIL branch -
# the W3C NegativeSyntaxTest fixture `list-anonreifier-01` (whose own text
# carries a "TODO: See if this should be throwing an error" comment) is
# answered by this grammar citation: yes, it should.
_ReifierTermValue <<= (
    (~NIL + VarOrTerm) | _AnnotationReifierTermExplicit | _AnnotationReifierTermAnon
)


def _annotation_reifier_term(s_raw, p, o_raw, r) -> list:
    s, s_extra = _expand_value(s_raw)
    o, o_extra = _expand_value(o_raw)
    return _annotation_reifier_term_resolved(s, p, o, r) + s_extra + o_extra


def _annotation_reifier_term_resolved(s, p, o, r) -> list:
    """Build the reification triple ``(r, rdf:reifies, tt)`` for one
    resolved (s, p, o, r) reifier-shorthand term.

    ``r`` must appear only once, as the first element of the single
    embedded triple below, not as a separately prepended copy — rdflib's
    own ``expandTriples()`` (its ``isinstance(t, list)`` branch) uses
    ``t[0]`` both as the value slotted into an enclosing triple's object
    position (via a plain ``res.append(t[0])``) and, separately, folds the
    whole of ``t`` (``t[0]`` included) back in as one or more new
    self-contained triples of its own — duplicating ``r`` as a standalone
    ``t[0]`` ahead of its real first triple breaks that contract.

    Args:
        s: The base triple's resolved subject.
        p: The base triple's resolved predicate.
        o: The base triple's resolved object.
        r: The reifier term naming this triple term.

    Returns:
        The flat ``[r, rdf:reifies, tt]`` triple, ready to splice into the
        enclosing triple list.
    """
    tt = _make_triple_term(s, p, o)
    return [r, _RDF_REIFIES, tt]


_ANNOTATION_TERM_FORMS = (
    _AnnotationReifierTermExplicit,
    _AnnotationReifierTermAnon,
)

def _fix_rdflib_lexical_gaps() -> None:
    """Repair three lexical defects in rdflib's own SPARQL terminals, in place and idempotently.

    All three reproduce against plain ``rdflib.plugins.sparql.prepareQuery`` with no starlayer involved
    (see ``docs/upstream-issues/rdflib-upstream-issues.md`` items 19 to 21):

    * ``-1.5``: ``DECIMAL_NEGATIVE`` negates through ``Literal(-literal, ...)``, which raises "Not a number".
    * ``"a\\'b"`` / ``'a\\"b'``: ECHAR (spec [160]) allows ``\\"`` and ``\\'`` in either quote style; the
      string regexes allowed only the one matching the quote.
    * ``:a\\-b``: ``PN_LOCAL_ESC`` (spec [173]) keeps its backslash in the local name, giving an invalid IRI.
    """
    from rdflib.plugins.sparql import parser as sparql_parser

    if getattr(sparql_parser.DECIMAL_NEGATIVE, "_starlayer_lexical_fix", False):
        return

    sparql_parser.DECIMAL_NEGATIVE.set_parse_action(
        lambda x: RDFTermLiteral("-" + str(x[0]), datatype=x[0].datatype)
    )
    sparql_parser.DECIMAL_NEGATIVE._starlayer_lexical_fix = True

    for terminal, quote_escape in ((sparql_parser.STRING_LITERAL1, "['ntbrf\\\\]"), (sparql_parser.STRING_LITERAL2, '["ntbrf\\\\]')):
        widened = terminal.pattern.replace(quote_escape, "[tbnrf\"'\\\\]")
        if widened != terminal.pattern:
            terminal.pattern = widened
            terminal.re = re.compile(widened, re.U)
            terminal.re_match = terminal.re.match

    sparql_parser.PN_LOCAL.add_parse_action(
        lambda t: re.sub(r"\\([_~.\-!$&\"'()*+,;=/?#@%])", r"\1", t[0])
    )


def _already_installed() -> bool:
    """State-based idempotency check - is TripleTermCallValue actually
    present in PrimaryExpression.exprs right now - rather than trusting a
    module-level boolean set once and never re-checked.

    Necessary, not just extra caution: pyparsing's own
    ParseExpression.streamline() (rdflib.plugins.sparql.parser's grammar
    objects are streamlined the first time they're actually used to parse
    something) collapses a MatchFirst with exactly 2 children by splicing
    a nested MatchFirst's own .exprs directly into the parent, *replacing*
    self.exprs outright, not appending to it - per pyparsing's own source
    (ParseExpression.streamline). PrimaryExpression starts with exactly 2
    children in stock rdflib, so it's exactly this kind of 2-child
    MatchFirst: under certain import/collection orderings this streamline
    pass can run *after* install() has already appended this module's own
    productions into PrimaryExpression.exprs, resetting it back to a
    flattened, pristine-rdflib list with every production this module
    installed missing - on the *same* Python object (not a duplicate
    import or module reload), which a module-level `_INSTALLED = True`
    flag set once at import time has no way to detect and never re-runs
    install() to recover from. A boolean flag can only ever be as
    trustworthy as the assumption that nothing else ever resets the
    objects it's guarding - false here, so this checks the live objects
    directly instead.
    """
    return TripleTermCallValue in PrimaryExpression.exprs


def _append_once(rule, production) -> None:
    """Append ``production`` to ``rule``'s alternatives unless it's
    already there (by identity, same mechanics as ``_already_installed``'s
    own ``in`` check). Makes every mutation ``install()`` performs
    idempotent individually, not just gated behind one top-level
    ``_already_installed()`` check - see ``install()``'s own docstring for
    why that distinction matters for ``force=True`` specifically.
    """
    if production not in rule.exprs:
        rule.append(production)


def _insert_once(rule, index, production) -> None:
    """``_append_once``'s counterpart for the front-inserted productions
    (``LangDirLiteral``, the annotation-shorthand forms) - same
    already-there check, ``exprs.insert(index, ...)`` instead of
    ``.append()``.
    """
    if production not in rule.exprs:
        rule.exprs.insert(index, production)


def install(force: bool = False) -> None:
    """Splice the new productions into rdflib's own grammar objects, in
    place, via pyparsing's public ``MatchFirst.append()``. Idempotent - safe
    to call more than once (e.g. from multiple import sites), and - see
    ``_already_installed``'s own docstring - safe to call again after
    something *else* has reset the grammar objects this already installed
    into, which a simple call-once boolean flag is not.

    ``force=True`` skips the ``_already_installed()`` short-circuit and
    re-runs every mutation - used by ``parse12.py``'s own parse-failure
    retry path as a last-resort recovery, for the residual corruption case
    ``_already_installed()`` itself doesn't reliably catch.

    Every individual mutation below goes through ``_append_once``/
    ``_insert_once`` rather than a bare ``.append()``/``.exprs.insert()``,
    so "re-runs every mutation" means "re-verifies every production is
    present," not "duplicates whatever's already there." This matters
    because these are shared, global, process-wide pyparsing grammar
    objects, and ``parse12.py``'s retry path calls ``install(force=True)``
    on every ``ParseBaseException`` - which every W3C *negative*-syntax
    test triggers *by design*, not just in the rare real-corruption case
    this was written for. An unconditional ``.append()`` on every forced
    reinstall would bloat these objects on every single negative-syntax
    test in a run, and since they're referenced recursively throughout the
    whole SPARQL grammar, parse cost for every later query would compound
    combinatorially as a function of how many prior negative-syntax tests
    had already run in the same process (see ``graph/CLAUDE.md`` for the
    measured before/after numbers).
    """
    _fix_rdflib_lexical_gaps()
    if not force and _already_installed():
        return
    for rule in (GraphTerm, VarOrTerm, GraphNode, GraphNodePath):
        _append_once(rule, TripleTermExpr)
        _append_once(rule, TripleTermCall)
        # Must be tried *before* plain RDFLiteral (already one of this
        # rule's own alternatives, transitively via GraphTerm) - see
        # LangDirLiteral's own comment for why appending wouldn't work
        # (RDFLiteral partially matches "nl" out of "nl--ltr" and
        # *succeeds*, so MatchFirst never backtracks to try a later
        # alternative at all).
        _insert_once(rule, 0, LangDirLiteral)
    # Expression position: a triple term usable directly as a PrimaryExpression
    # value (BIND(<<(...)>> AS ?x)), and the four accessor builtins usable
    # anywhere BuiltInCall is (BIND/FILTER/SELECT (... AS ?x)/GROUP BY/etc.,
    # per PrimaryExpression/Constraint/GroupCondition all referencing
    # BuiltInCall — see rdflib's parser.py). Uses the *Value variants
    # (restricted subject grammar) — see _TripleTermSubjectExpr's own
    # comment for why this must be a different pair of objects from the
    # ones spliced into GraphTerm/VarOrTerm/GraphNode/GraphNodePath above.
    _append_once(PrimaryExpression, TripleTermExprValue)
    _append_once(PrimaryExpression, TripleTermCallValue)
    _insert_once(PrimaryExpression, 0, LangDirLiteral)
    # VALUES { <<(:s :p :o)>> ... } — a ground triple term used as a data
    # block value. Self-contained (no side-effect triples, unlike the
    # annotation forms below), so a plain .append() is enough — same as
    # every other DataBlockValue alternative (iri/RDFLiteral/etc). Also
    # uses the *Value variants — a VALUES row is a ground value, not a
    # pattern, treated the same as expression position (see
    # TripleTermExprValue's own comment on the lack of direct test
    # evidence for this specific position).
    _append_once(DataBlockValue, TripleTermExprValue)
    _append_once(DataBlockValue, TripleTermCallValue)
    _insert_once(DataBlockValue, 0, LangDirLiteral)
    _append_once(BuiltInCall, Builtin_isTRIPLE)
    _append_once(BuiltInCall, Builtin_SUBJECT)
    _append_once(BuiltInCall, Builtin_PREDICATE)
    _append_once(BuiltInCall, Builtin_OBJECT)
    _append_once(BuiltInCall, Builtin_LANGDIR)
    _append_once(BuiltInCall, Builtin_hasLANGDIR)
    _append_once(BuiltInCall, Builtin_hasLANG)
    _append_once(BuiltInCall, Builtin_STRLANGDIR)

    # Annotations and reifiers after an object: replace the property-list
    # alternatives of the four consumers (see the comment above `_Annotated`).
    _install_annotated_objects()

    # `<<s p o>>`/`<<s p o ~ r>>` reifier-reference terms: appended (order
    # vs Collection/BlankNodePropertyList doesn't matter — disjoint leading
    # tokens; order between the two new forms themselves doesn't matter
    # either, see their own comment) to TriplesNode/TriplesNodePath's
    # underlying MatchFirst (`.expr`, since both are pyparsing `Forward`
    # wrappers, not MatchFirst objects themselves —
    # `TriplesNode.expr`/`TriplesNodePath.expr` are real MatchFirst objects
    # with a public `.append()`). This single splice
    # point is what makes the new forms usable everywhere TriplesNode(Path)
    # already is: GraphNode/GraphNodePath (ordinary object position, inside
    # `[...]`, inside `(...)`), and TriplesSameSubject(Path)'s own
    # `TriplesNode(Path) + PropertyList(Path)` alternative (a bare `<<s p o>>
    # .` statement, PropertyList empty) — see the forms' own comment.
    for rule in (TriplesNode, TriplesNodePath):
        for form in _ANNOTATION_TERM_FORMS:
            _append_once(rule.expr, form)
