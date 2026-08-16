"""Lower a SPARQL 1.2 algebra tree (as produced by ``grammar12.py`` /
``parse12.py`` — the only non-standard node type it ever contains is
``TripleTermNode``, see ``triple_term.py``) into a plain SPARQL 1.1 algebra
tree runnable against ``starlayergraph``'s in-memory backend.

This is a **tree** transform, not a text one — it mirrors, at the algebra
level, what ``starlayergraph``'s own ``starlayergraph/query/sparql12_to_11.py``
already does by rewriting SPARQL *text* with regexes/string splicing. Nearly
every bug in that module traced back to the fragility of manipulating SPARQL
syntax as strings (ordering-sensitive BIND/FILTER splicing, join-order
bugs); operating on the decoded algebra tree sidesteps that class of bug
entirely — see the accompanying plan for the full rationale.

Four composable entry points:

- ``lower_algebra_to_rdf11(algebra)`` — the core recursive transform.
- ``query_to_rdf11(query)`` — lower, then encode via the existing,
  unmodified ``to_rdf.query_to_rdf``. Produces a genuine RDF graph for the
  lowered 1.1 algebra, the same representation this project already uses
  for the 1.2 algebra.
- ``rdf11_to_query(graph, root)`` — decode via the existing, unmodified
  ``from_rdf.rdf_to_query``, which already re-runs rdflib's own
  ``_addVars``/``analyse`` and promotes ``Function`` nodes to real,
  evaluable ``Expr``s — the result is a fully executable ``Query`` object,
  nothing further needed. **Prefer this for actual execution** — hand it
  straight to ``StarLayerGraph.query()``/``StarLayerDataset.query()``,
  both of which already special-case a non-``str`` ``query_object`` to
  skip their own text rewriting/parsing entirely (confirmed: both branch
  on ``isinstance(query_object, str)``). No SPARQL 1.1 text needs to
  exist anywhere in this path.
- ``rdf11_to_sparql11_text(graph, root)`` — same decode, then plain
  rdflib ``algebra.translateAlgebra`` (not ``serialize12.
  translate_algebra_12``, since nothing lowered still needs
  ``TripleTermNode``/dirLangString special-casing) to produce real SPARQL
  1.1 *text*. Kept for cases that genuinely need text — debugging, human
  inspection, external tools, a backend that only accepts query strings
  (e.g. a remote ``SPARQLStore``) — not because execution needs it; it
  doesn't. Going through this function and re-parsing its output is
  strictly redundant with ``rdf11_to_query`` for in-memory execution, and
  reintroduces exactly the string-serialization fragility this project's
  tree-based approach exists to avoid (confirmed a real instance of this
  while building it: rdflib's own ``_AlgebraTranslator`` has no branch at
  all for a generic ``Function`` call or for ``ConstructQuery``, both
  patched around here in ``_AlgebraTranslator11``, purely to make this
  *text* path work — none of that is needed for direct execution).

## What actually needs lowering

``TripleTermNode`` is the only non-standard node type
(``triple_term.py``/``grammar12.py``'s docstrings confirm reification
shorthand — ``<<s p o>>``, ``<<s p o ~ r>>``, ``{| |}`` — is fully desugared
at *parse* time into plain ``rdf:reifies`` + ``TripleTermNode`` BGP triples,
so no shorthand form ever reaches the algebra). ``Builtin_isTRIPLE``/
``Builtin_SUBJECT``/``Builtin_PREDICATE``/``Builtin_OBJECT`` are this
project's own bespoke grammar productions (``grammar12.py``) for the
SPARQL 1.2 accessor builtins.

``LANGDIR``/``hasLANGDIR``/``STRLANGDIR``/``hasLANG`` have **no** grammar12
production at all (confirmed: not in ``grammar12.py``'s ``BuiltInCall``
extensions) — a query using them wouldn't parse as anything but an ordinary,
unrecognized SPARQL 1.1 function call, which the generic fallback below
already passes through unchanged. dirLangString *literals*
(``"text"@lang--dir``) need zero lowering either: ``grammar12.py``'s
``LangDirLiteral`` production already builds
``Literal(text, datatype=encode_dirlang_datatype(lang, dir))`` at parse
time — the exact encoded form starlayergraph's in-memory backend expects as-is.

## Term-slot vs. expression-position lowering

A ``TripleTermNode`` reached in **expression position** (a ``Filter``/
``Extend``/etc. ``.expr``, or nested as a function-call argument) always
lowers to an *inline* ``Function(TT_HASH_FN, [s, p, lower(o)])`` call — safe
regardless of groundedness, since a function argument can itself be any
expression including another function call, and ``TT_HASH_FN`` has no
observable side effects.

A ``TripleTermNode`` reached in a **term-slot position** — a BGP triple's
own subject/object, a VALUES row cell, or a CONSTRUCT template triple's
subject/object — cannot host an expression at all (SPARQL only allows a
plain term there), so it needs converting to an actual term:

- Ground, ordinary BGP pattern position: computed **eagerly, in Python**
  (reusing the same ``starlayergraph.model.encoding.tt_hash``/``term_key``
  machinery as the VALUES-row case below) and substituted directly as a
  literal ``tt:`` ``URIRef`` term — no fresh variable, no ``BIND``, no
  runtime ``Function`` call. Deliberately *not* a ``BIND``-wrapped fresh
  variable (unlike the CONSTRUCT-template case below, which looks
  superficially similar): confirmed via a real, reproducible bug (W3C
  fixture ``pattern-4``, "No match" — regressed to a false positive) that
  rdflib's own ``evalExtend`` does not enforce SPARQL's "a ``BIND`` target
  must be previously unbound" rule — it unconditionally overwrites
  (``c.merge({extend.var: e})``, no equality check) rather than raising or
  filtering. A pattern-position triple term's minted variable is *also*
  bound by the BGP's own ordinary triple match (that's the point of
  putting it in the pattern's term slot), so wrapping it in ``BIND`` lets
  the overwrite silently discard the very equality check the match was
  supposed to perform, turning "no such triple term in the data" into a
  false match. Substituting an already-computed constant term sidesteps
  the bug entirely — see ``_lower_pattern_term``'s own docstring.
- Non-ground, ordinary BGP pattern position: decompose into
  ``?ttVar rdf:subject s . ?ttVar rdf:predicate p . ?ttVar rdf:object o .``
  match triples appended to the *same* BGP (recursing into a nested object;
  a nested object that's itself ground recurses into the eager-Python case
  above, not another decomposition).
- VALUES row cell (always ground — a VALUES cell can never be a variable):
  computed eagerly in Python via ``starlayergraph.model.encoding.tt_hash``/
  ``term_key`` (mirroring ``_tt_hash_fn``'s own logic) and substituted as a
  literal ``tt:`` ``URIRef`` — there is no algebra-level expression to
  build at all. Same mechanism as the ground-pattern-position case above.
- CONSTRUCT template triple (ground *by the time the template is
  instantiated*, regardless of whether it's syntactically a ``?var`` —
  every WHERE-clause variable is already bound by then): minted via a
  fresh variable ``BIND``-wrapped around the WHERE-clause root, *plus* the
  template unconditionally also gets its own
  ``?ttVar rdf:subject/predicate/object`` triples appended (see
  ``_lower_construct_query``) — mirrors ``sparql12_to_11.py``'s own
  ``in_construct_template`` branch, checked first and unconditional there
  for the same reason. Safe from the ``evalExtend`` overwrite hazard above
  specifically because this fresh variable is never independently
  pattern-matched anywhere in the WHERE clause — it exists solely to carry
  the ``BIND``'s own value into the template, so there is nothing for the
  overwrite to clobber.

Wrapping a CONSTRUCT-template ground BIND locally, around the WHERE-clause
root, rather than hoisting it to some shared position, is always
join-order-correct by construction (ordinary SPARQL nested-group
evaluation handles it, and a ground ``Function`` call has zero variable
dependencies to worry about) — sidestepping the class of evaluation-order
bug that made the text-based rewriter's own hoisting logic fragile.
"""

from __future__ import annotations

from rdflib import BNode, Literal, URIRef, Variable
from rdflib.graph import Graph
from rdflib.namespace import RDF
from rdflib.plugins.sparql.algebra import (
    ExpressionNotCoveredException,
    _AlgebraTranslator,
)
from rdflib.plugins.sparql.parserutils import CompValue
from rdflib.plugins.sparql.sparql import Prologue, Query, Update

# _AlgebraTranslator11 (below) subclasses plain rdflib's own
# _AlgebraTranslator, adding only two fixes of its own (a Function-node
# rendering branch, a couple of leftover-placeholder cleanups). Four other
# confirmed, real translateAlgebra bugs it relies on - BGP blank-node
# adjacency producing text rdflib's own parser can't re-parse, UNION
# branches mis-nesting when each contains a subquery + BIND, an inverted
# IN/NOT IN list-handling guard that crashes on multi-value lists, and a
# missing "*" on SELECT * WHERE { <fully-ground pattern> } - are fixed by
# starlayergraph's own algebra_translator_patches.py, which monkey-patches
# _AlgebraTranslator in place. Since _AlgebraTranslator11 is a subclass, it
# only inherits those fixes if the patches happen to already be applied by
# the time it runs - previously true only by accident, via some unrelated
# starlayergraph import happening to run first elsewhere in this project. This
# project already hard-requires starlayergraph (see to_rdf._new_starlayer_graph
# and this module's own starlayergraph.model.encoding imports below), so make
# that dependency explicit here too, rather than relying on side effects:
# call the same patch function starlayergraph/__init__.py itself calls eagerly,
# idempotent and safe to call again regardless of whether that's already
# happened.
from starlayergraph.query.algebra_translator_patches import (
    patch_algebra_translator_bugs as _patch_algebra_translator_bugs,
)

from .from_rdf import rdf_to_query, rdf_to_update
from .to_rdf import query_to_rdf, update_to_rdf
from .triple_term import TripleTermNode
from .vocab import decode_dirlang_datatype

_patch_algebra_translator_bugs()

# Mirrors starlayergraph/query/sparql12_to_11.py's own constants exactly (see
# that module for the authoritative definitions/registration). Duplicated
# here rather than imported: this project's dependency direction runs
# starlayergraph -> starsparql (see CLAUDE.md's "Sibling project"
# note), so importing starlayergraph's *query-rewriting* internals from here
# would invert it. starlayergraph.model.encoding (a stable, low-level module,
# already the established import direction for exactly this project) is
# still imported directly, below, for VALUES-row eager hashing.
TT_NS = "https://github.com/hidden-graph/starlayergraph/ns/tt#"
TT_HASH_FN = URIRef(TT_NS + "fn/hash")
_TT_ACCESSOR_FN = {
    "Builtin_SUBJECT": URIRef(TT_NS + "fn/subject"),
    "Builtin_PREDICATE": URIRef(TT_NS + "fn/predicate"),
    "Builtin_OBJECT": URIRef(TT_NS + "fn/object"),
}

# Same duplication rationale as TT_NS/TT_HASH_FN above - mirrors
# starlayergraph/query/sparql12_to_11.py's own DIRLANG_NS_PREFIX/
# DIRLANG_CONSTRUCT_FN exactly, so the URI this module's Function(...) call
# resolves to is the identical custom function starlayergraph already registers
# (register_custom_function is keyed by URI, not by which module happened
# to build the call).
DIRLANG_NS = "https://github.com/hidden-graph/starlayergraph/ns/dirlang#"
DIRLANG_CONSTRUCT_FN = URIRef(DIRLANG_NS + "fn/construct")


class _LowerState:
    """Per-query counter for fresh triple-term variables, plus
    `global_plain_vars` — the whole (pre-lowering) tree's own
    unconditionally-bound plain variables (see
    `_collect_mandatory_plain_vars`), set once by whichever entry point
    starts lowering a given query/Modify-operation, consulted by every
    `_lower_bgp`/`_lower_flat_triples` call reached under it regardless of
    which BGP a triple term's own component variable happens to sit in.
    """

    def __init__(self) -> None:
        self._n = 0
        self.global_plain_vars: set = set()

    def new_var(self) -> Variable:
        self._n += 1
        return Variable(f"__tt11_{self._n}__")


def _is_ground(term) -> bool:
    """True iff `term` contains no Variable and no BlankNode anywhere,
    recursively through nested TripleTermNodes. A blank node counts as
    non-ground here even though it isn't a Variable — matching
    sparql12_to_11.py's own (session-confirmed) fix for the same question:
    a BIND target computed from a triple term containing a blank node must
    still be recomputed per-solution-consistent-skolemization, not hoisted
    as if it were a constant.
    """
    if isinstance(term, TripleTermNode):
        return (
            _is_ground(term["subject"])
            and _is_ground(term["predicate"])
            and _is_ground(term["object"])
        )
    return not isinstance(term, (Variable, BNode))


def _make_function_call(iri: URIRef, args: list) -> CompValue:
    return CompValue("Function", iri=iri, distinct=[], expr=list(args))


def _hash_call(s, p, o, state: _LowerState) -> CompValue:
    # RDF 1.2 forbids a triple term's subject/predicate from itself being a
    # triple term (only object position permits nesting — TripleTermNode's
    # own grammar restricts predicate to Var|iri, subject similarly), so
    # only `o` can ever need recursive expression-position lowering here.
    return _make_function_call(TT_HASH_FN, [s, p, _lower_expr(o, state)])


def _is_triple_term_expr(arg) -> CompValue:
    """``arg``'s value is a triple term — true for *either* representation
    a triple-term-valued expression can hold at evaluation time: a native
    ``TripleTerm`` object (ordinary pattern-matched, or extracted via an
    accessor-function chain — ``STR()`` on one renders it as
    ``"<<( s p o )>>"``, confirmed empirically, never a `tt:`-prefixed
    string) or a `tt:` hash ``URIRef`` (freshly constructed via
    `TT_HASH_FN`, never pattern-matched). Plain `STRSTARTS(STR(x), TT_NS)`
    alone — this project's own earlier version, and still what the sibling
    `starlayergraph` repo's own text-based `isTripleTerm()`/`isTRIPLE()`
    rewriter uses — only recognizes the second form; confirmed as a real,
    reproducible false-negative for the first (a query testing whether an
    ordinarily-pattern-matched value is a triple term always got `false`,
    even when it truly was one).
    """
    str_call = CompValue("Builtin_STR", arg=arg)
    return CompValue(
        "ConditionalOrExpression",
        expr=CompValue("Builtin_STRSTARTS", arg1=str_call, arg2=Literal(TT_NS)),
        other=[CompValue("Builtin_STRSTARTS", arg1=str_call, arg2=Literal("<<"))],
    )


def _dirlang_str_datatype(raw_arg, state: _LowerState) -> CompValue:
    """``STR(DATATYPE(arg))`` - the shared prefix every one of the four
    dirLangString-aware lowerings below tests against ``DIRLANG_NS``.
    Lowers a *fresh* copy of ``raw_arg`` each call (never reuses a
    previously-lowered result across multiple occurrences in the expanded
    tree) - same "no aliasing" invariant every other lowering helper in
    this module already follows (see ``lower_algebra_to_rdf11``'s own
    "does not mutate" docstring); `_lower_expr` is a pure function, so this
    just costs a little redundant work, never correctness.
    """
    return CompValue("Builtin_STR", arg=CompValue("Builtin_DATATYPE", arg=_lower_expr(raw_arg, state)))


def _dirlang_langdir_expr(raw_arg, state: _LowerState) -> CompValue:
    """``LANGDIR(v)`` (RDF 1.2 Query sec 17.4.2) -> the direction suffix of
    v's own dirLangString datatype IRI, or ``""`` for any other value.
    Mirrors ``starlayergraph/query/sparql12_to_11.py::_dirlang_langdir`` exactly
    (same target SPARQL 1.1 shape, built as algebra instead of text).
    """
    starts = CompValue(
        "Builtin_STRSTARTS", arg1=_dirlang_str_datatype(raw_arg, state), arg2=Literal(DIRLANG_NS)
    )
    direction = CompValue(
        "Builtin_STRAFTER", arg1=_dirlang_str_datatype(raw_arg, state), arg2=Literal("--")
    )
    return CompValue("Builtin_IF", arg1=starts, arg2=direction, arg3=Literal(""))


def _dirlang_has_langdir_expr(raw_arg, state: _LowerState) -> CompValue:
    """``hasLANGDIR(v)`` -> true iff v's datatype is a dirLangString IRI.
    Mirrors ``sparql12_to_11.py::_dirlang_has_langdir``.
    """
    return CompValue(
        "Builtin_STRSTARTS", arg1=_dirlang_str_datatype(raw_arg, state), arg2=Literal(DIRLANG_NS)
    )


def _dirlang_lang_expr(raw_arg, state: _LowerState) -> CompValue:
    """Dirlang-aware ``LANG(v)`` -> the language subtag for a dirLangString
    value (extracted from its own encoded datatype IRI), falling back to
    plain SPARQL 1.1 ``LANG(v)`` for anything else. Mirrors
    ``sparql12_to_11.py::_dirlang_lang`` - replaces rdflib's own stock
    ``Builtin_LANG`` node wherever it's reached during lowering (see
    ``_lower_expr``'s dispatch), not a new grammar production - `LANG(?x)`
    is already legal SPARQL 1.1 syntax, only its RDF-1.2-aware *lowering*
    is new.
    """
    starts = CompValue(
        "Builtin_STRSTARTS", arg1=_dirlang_str_datatype(raw_arg, state), arg2=Literal(DIRLANG_NS)
    )
    after = CompValue(
        "Builtin_STRAFTER", arg1=_dirlang_str_datatype(raw_arg, state), arg2=Literal(DIRLANG_NS)
    )
    language = CompValue("Builtin_STRBEFORE", arg1=after, arg2=Literal("--"))
    fallback = CompValue("Builtin_LANG", arg=_lower_expr(raw_arg, state))
    return CompValue("Builtin_IF", arg1=starts, arg2=language, arg3=fallback)


def _dirlang_has_lang_expr(raw_arg, state: _LowerState) -> CompValue:
    """``hasLANG(v)`` -> true iff v is a dirLangString OR an ordinary
    language-tagged literal. Mirrors ``sparql12_to_11.py::_dirlang_has_lang``.
    """
    starts = CompValue(
        "Builtin_STRSTARTS", arg1=_dirlang_str_datatype(raw_arg, state), arg2=Literal(DIRLANG_NS)
    )
    lang_ne_empty = CompValue(
        "RelationalExpression",
        expr=CompValue("Builtin_LANG", arg=_lower_expr(raw_arg, state)),
        op="!=",
        other=Literal(""),
    )
    return CompValue("ConditionalOrExpression", expr=starts, other=[lang_ne_empty])


def _lower_expr(node, state: _LowerState):
    """Lower `node` for EXPRESSION position — a Filter/Extend/etc. `.expr`,
    or any function-call argument. A TripleTermNode inlines as a nested
    Function(TT_HASH_FN, ...) call (safe at any nesting depth/groundedness
    — a function argument can itself be another function call, and
    TT_HASH_FN has no observable side effects). Builtin_isTRIPLE/_SUBJECT/
    _PREDICATE/_OBJECT become their SPARQL-1.1-equivalent shape.
    Builtin_LANGDIR/_hasLANGDIR/_hasLANG lower to the plain SPARQL 1.1
    builtin combination sparql12_to_11.py already produces for these (no
    custom function needed - remote-store-safe as-is); Builtin_STRLANGDIR
    lowers to a Function(DIRLANG_CONSTRUCT_FN, ...) call, same treatment as
    TRIPLE()/TT_HASH_FN. Stock rdflib's own Builtin_LANG is intercepted
    here too and replaced with its dirLangString-aware expansion - no new
    grammar needed for it, only different lowering. Everything else
    recurses structurally, unchanged in shape.
    """
    if isinstance(node, TripleTermNode):
        return _hash_call(node["subject"], node["predicate"], node["object"], state)

    if isinstance(node, CompValue):
        name = node.name
        if name == "Builtin_isTRIPLE":
            arg = _lower_expr(node["arg"], state)
            return _is_triple_term_expr(arg)
        if name in _TT_ACCESSOR_FN:
            arg = _lower_expr(node["arg"], state)
            return _make_function_call(_TT_ACCESSOR_FN[name], [arg])
        if name == "Builtin_LANGDIR":
            return _dirlang_langdir_expr(node["arg"], state)
        if name == "Builtin_hasLANGDIR":
            return _dirlang_has_langdir_expr(node["arg"], state)
        if name == "Builtin_LANG":
            return _dirlang_lang_expr(node["arg"], state)
        if name == "Builtin_hasLANG":
            return _dirlang_has_lang_expr(node["arg"], state)
        if name == "Builtin_STRLANGDIR":
            args = [
                _lower_expr(node["lex"], state),
                _lower_expr(node["lang"], state),
                _lower_expr(node["direction"], state),
            ]
            return _make_function_call(DIRLANG_CONSTRUCT_FN, args)
        if name == "BGP":
            return _lower_bgp(node, state)
        if name == "ConstructQuery":
            return _lower_construct_query(node, state)
        if name == "values":
            return _lower_values(node, state)
        new_node = CompValue(name)
        for key, value in node.items():
            if key in ("_vars", "lazy"):
                continue
            if key in node.__dict__:
                # rdflib's own translateQuery post-processing (e.g.
                # algebra.translateExists, for Builtin_EXISTS/NOTEXISTS's
                # `graph`) fixes up certain keys by assigning a real
                # instance attribute (`n.graph = ...`) - which *shadows*
                # but does not update the underlying dict-stored value
                # `.items()` just yielded here, so `value` can be a stale,
                # untranslated parse-tree fragment even though `node.graph`
                # (attribute access) already returns the correct, translated
                # algebra. Confirmed via `dict.__getitem__(node, "graph")`
                # still returning the raw `GroupGraphPatternSub` on a node
                # whose `.graph` attribute already reads back as `Join` -
                # without this, a `FILTER (NOT) EXISTS { ... }` with more
                # than one triple in its block gets re-encoded with a
                # dead, un-evaluable fragment and crashes at execution time
                # ("What do I do with this CompValue?"). Prefer the
                # attribute whenever both exist.
                value = getattr(node, key)
            new_node[key] = _lower_expr(value, state)
        return new_node

    if isinstance(node, list):
        return [_lower_expr(item, state) for item in node]

    if isinstance(node, tuple):
        return tuple(_lower_expr(item, state) for item in node)

    return node


def _lower_pattern_term(term, extra_constraints: list, already_bound: set, state: _LowerState):
    """Lower `term` for TERM-SLOT position within a BGP — an ordinary
    triple pattern's own subject/object. `extra_constraints` accumulates
    ``("extend", var, expr)``/``("filter", expr)`` tuples the caller
    (`_lower_bgp`) wraps around the whole BGP, outermost-in, once every
    triple has been processed. `already_bound` is the set of `Variable`s
    guaranteed bound *some other way* by the time these constraints run —
    seeded by the caller with every variable that appears as an ordinary
    (non-triple-term) triple position anywhere in the same BGP, and grown
    here as each triple-term component gets its own `Extend` — see
    `_add_single_constraint` for why this matters. Returns the replacement
    term.

    A ground triple term is computed *eagerly, in Python* (reusing
    `_eager_lower_value`, the same mechanism VALUES rows already use) and
    substituted as a literal `tt:` URIRef directly — deliberately **not**
    the ``BIND``-a-fresh-variable approach used elsewhere (expression
    position, CONSTRUCT templates): confirmed via a real, reproducible bug
    (W3C fixture `pattern-4`, "No match" — regressed to a false match)
    that rdflib's own `evalExtend` does not enforce SPARQL's "BIND target
    must be previously unbound" rule at all — it unconditionally
    overwrites (`c.merge({extend.var: e})`, no equality check against the
    existing binding) rather than raising/filtering. Wrapping a *pattern-
    position* ground triple term's own fresh variable in Extend means that
    exact variable is *also* bound by the BGP's own ordinary triple match
    (that's the whole point of putting it in the pattern's term slot) —
    so `BIND` there silently overwrites whatever the BGP actually
    matched, discarding the very equality check the match was supposed to
    perform. Computing the value in Python and substituting a constant
    sidesteps the bug entirely (there's no variable left for anything to
    overwrite) rather than working around a case-by-case symptom of it.
    Safe here specifically because the value is already fully known at
    lowering time; CONSTRUCT-template ground values use the same
    `Extend` approach safely (see `_lower_template_term`) precisely
    because *that* fresh variable is never independently pattern-matched
    anywhere — no overwrite hazard to avoid.

    A **non-ground** triple term cannot be decomposed into
    ``?ttVar rdf:subject s .`` etc. match triples the way an earlier
    version of this function did — confirmed empirically that
    ``StarLayerGraph`` stores a triple term as a native Python
    ``TripleTerm`` object directly (with its own real ``.subject``/
    ``.predicate``/``.object`` attributes), never as decomposed
    ``rdf:subject``/``predicate``/``object`` triples, so there is nothing
    in the store for such a match triple to ever match against — it
    silently matched zero rows regardless of real matching data. Fixed by
    minting a fresh variable for the *whole* triple term (bound the
    ordinary way, by the BGP's own triple match) and pushing
    ``tt:fn/subject``/``predicate``/``object`` accessor-function
    constraints (see `_add_component_constraints`) — the same accessor
    functions expression-position `SUBJECT()`/etc. already lower to,
    extended (in the sibling `starlayergraph` repo, see
    ``_register_tt_accessor_functions``) to accept a native ``TripleTerm``
    object directly, not just a `tt:` hash URIRef, since that's what a
    pattern-matched variable is actually bound to.
    """
    if not isinstance(term, TripleTermNode):
        return term
    if _is_ground(term):
        return _eager_lower_value(term)
    var = state.new_var()
    _add_component_constraints(var, term, extra_constraints, already_bound, state)
    return var


def _add_component_constraints(
    base_expr, term: TripleTermNode, extra_constraints: list, already_bound: set, state: _LowerState
) -> None:
    """Push constraints tying `base_expr` (an expression whose evaluated
    value is expected to be the triple term `term` describes) to each of
    `term`'s own subject/predicate/object components, via the
    ``tt:fn/subject``/``predicate``/``object`` accessor functions.

    Subject/predicate can never themselves be a nested triple term (RDF
    1.2 forbids it — enforced at parse/construction time by
    ``TripleTermNode.validate()``), so only object ever needs to recurse.
    A nested object recurses *here* — chaining another accessor call onto
    `base_expr` — regardless of whether that nested object is itself
    ground: confirmed empirically that ``StarLayerGraph`` always
    represents a nested triple term as a further native ``TripleTerm``
    object, never a `tt:` hash URI, even when fully ground, so there is no
    ordinary BGP pattern slot to substitute an eagerly-computed `tt:` URI
    into the way the top-level (directly pattern-matched) case can.

    Always pushes an explicit ``isTRIPLE(base_expr)`` `Filter` guard first
    — confirmed necessary, not defensive-programming overkill, via a real
    regression (W3C fixture `pattern-10`'s
    ``<<?s ?p <<( ?st ?pt ?ot )>> >>`` branch): without it, a `base_expr`
    that turns out *not* to be a triple term (e.g. an outer triple term's
    object that's an ordinary ground value, not the nested triple term a
    query pattern's shape merely *hints* it might be) makes every
    accessor-function call below raise — which, for whichever component
    happens to be `Extend`-classified rather than `Filter`-classified (see
    `_add_single_constraint`), rdflib's `evalExtend` silently swallows
    into "leave that one variable unbound" rather than rejecting the row,
    exactly the ``evalExtend``-doesn't-enforce-prior-unbound hazard this
    module's other docstrings describe recurring in a new shape. A row
    with only *some* of its triple-term-derived variables ever getting
    bound, instead of being excluded outright, is silently wrong, not
    merely incomplete — this guard makes the rejection explicit and
    unconditional instead of an accident of which components happened to
    need `Filter` anyway.
    """
    extra_constraints.append(("filter", _is_triple_term_expr(base_expr)))
    s, p, o = term["subject"], term["predicate"], term["object"]
    s_expr = _make_function_call(_TT_ACCESSOR_FN["Builtin_SUBJECT"], [base_expr])
    _add_single_constraint(s, s_expr, extra_constraints, already_bound)
    p_expr = _make_function_call(_TT_ACCESSOR_FN["Builtin_PREDICATE"], [base_expr])
    _add_single_constraint(p, p_expr, extra_constraints, already_bound)
    o_expr = _make_function_call(_TT_ACCESSOR_FN["Builtin_OBJECT"], [base_expr])
    if isinstance(o, TripleTermNode):
        _add_component_constraints(o_expr, o, extra_constraints, already_bound, state)
    else:
        _add_single_constraint(o, o_expr, extra_constraints, already_bound)


def _add_single_constraint(value, accessor_expr, extra_constraints: list, already_bound: set) -> None:
    """`value` is either a plain ground term (→ equality `Filter`) or a
    `Variable`. A `Variable` needs `Filter`-equality too, not `Extend`,
    whenever it's already guaranteed bound some other way by the time this
    constraint runs (tracked via `already_bound`) — confirmed as a real,
    reproducible regression via the W3C fixture `pattern-9`
    ("Same variable"), whose query reuses the *same* variable as both a
    triple term's own predicate and the enclosing triple's ordinary
    predicate (``<<?s ?p :o>> ?p ?z``): rdflib's `evalExtend` does not
    enforce "BIND target must be previously unbound" (see this function's
    caller's own docstring for the general form of this rdflib behavior) —
    wrapping `?p` in `Extend` here would silently overwrite whatever the
    ordinary BGP triple `(?bnode, ?p, ?z)` actually matched, discarding
    the equality join the shared variable name was supposed to express,
    and returning a row for every predicate rather than just the matching
    one. `Extend` is only safe for a variable that this triple term is the
    *sole* source of a value for — exactly the set `already_bound` is
    tracking the complement of.
    """
    if isinstance(value, Variable):
        if value in already_bound:
            extra_constraints.append(
                ("filter", CompValue("RelationalExpression", expr=accessor_expr, op="=", other=value))
            )
        else:
            extra_constraints.append(("extend", value, accessor_expr))
            already_bound.add(value)
    else:
        extra_constraints.append(
            ("filter", CompValue("RelationalExpression", expr=accessor_expr, op="=", other=value))
        )


def _wrap_with_constraints(pattern: CompValue, extra_constraints: list) -> CompValue:
    result = pattern
    for kind, *args in extra_constraints:
        if kind == "extend":
            var, expr = args
            result = CompValue("Extend", p=result, expr=expr, var=var)
        else:
            (expr,) = args
            result = CompValue("Filter", p=result, expr=expr)
    return result


def _bgp_plain_vars(triples: list) -> set:
    """Every `Variable` appearing as an ordinary (non-triple-term) subject/
    predicate/object anywhere in `triples` — the seed for `already_bound`
    (see `_add_single_constraint`'s docstring): a variable reused this way
    is guaranteed bound by the BGP's own ordinary matching regardless of
    where any triple-term constraint for it ends up, since BGP triples
    join as one unordered AND, not left-to-right."""
    return {t for s, p, o in triples for t in (s, p, o) if isinstance(t, Variable)}


def _collect_mandatory_plain_vars(node) -> set:
    """Every `Variable` unconditionally bound by an *ordinary* (non-
    triple-term) term position somewhere in `node` — used to seed
    `already_bound` (see `_add_single_constraint`'s docstring) with
    variables bound by a *different part of the same query* than the
    triple-term constraint being lowered, not just the same BGP.

    Confirmed necessary via a real regression (W3C fixture `graphs-1`):
    ``:s :p ?o .`` (one BGP) and ``GRAPH ?g { <<:s :p ?o>> ?q ?z }`` (a
    sibling BGP, joined via `Join`, not the same BGP) share `?o` —
    `_bgp_plain_vars` alone, scoped to one BGP's own triples, can't see
    that it's already bound by the *other* one, so without this, `Extend`
    silently clobbers `?o`'s already-joined value exactly the way
    `_add_single_constraint`'s docstring already documents for the
    same-BGP case.

    Deliberately conservative toward treating *more* variables as
    "already bound" rather than fewer: does not descend into
    `LeftJoin.p2` (OPTIONAL — not guaranteed to contribute a binding),
    `Union`'s own children (only one branch is guaranteed per solution),
    or `Minus.p2` (a negation test, never a binding source). Treating a
    variable bound only in one of those as unconditionally bound would
    risk *incorrectly rejecting* solutions (a `Filter` comparing against
    something that turns out unbound for a given row raises, which
    excludes the row) rather than merely picking a less-efficient
    `Extend` — the failure mode this conservatism avoids is worse than
    the one it risks. Everything else recurses structurally; never
    descends into a `TripleTermNode` (its own nested variables are
    exactly the ones this function must *not* count as plainly bound).
    """
    found: set = set()

    def walk(n) -> None:
        if isinstance(n, TripleTermNode):
            return
        if isinstance(n, CompValue):
            name = n.name
            if name == "BGP":
                found.update(_bgp_plain_vars(n["triples"]))
                return
            if name == "LeftJoin":
                walk(n["p1"])
                return
            if name == "Minus":
                walk(n["p1"])
                return
            if name == "Union":
                return
            if name == "Extend":
                walk(n["p"])
                found.add(n["var"])
                return
            if name == "values":
                for row in n["res"]:
                    found.update(row.keys())
                return
            for value in n.values():
                walk(value)
            return
        if isinstance(n, (list, tuple)):
            for item in n:
                walk(item)

    walk(node)
    return found


def _lower_triples_for_pattern(triples: list, already_bound: set, state: _LowerState) -> tuple[list, list]:
    """Lower a flat (s, p, o) list at ordinary PATTERN position, returning
    ``(new_triples, extra_constraints)`` separately rather than an already-
    wrapped `BGP` — shared by `_lower_bgp` (which immediately wraps the
    result) and the `DeleteWhere`->`Modify` rewrite below (which also needs
    `new_triples` on its own, unwrapped, for reuse as the DELETE template —
    see `_lower_delete_where`'s own docstring for why that reuse is valid).
    """
    extra_constraints: list = []
    new_triples = []
    for s, p, o in triples:
        s2 = _lower_pattern_term(s, extra_constraints, already_bound, state)
        # Predicate position of an ordinary triple pattern is never itself
        # a TripleTermNode (grammar12.py restricts it to Var|iri) — no
        # lowering needed.
        o2 = _lower_pattern_term(o, extra_constraints, already_bound, state)
        new_triples.append((s2, p, o2))
    return new_triples, extra_constraints


def _lower_bgp(node: CompValue, state: _LowerState) -> CompValue:
    already_bound = _bgp_plain_vars(node["triples"]) | state.global_plain_vars
    new_triples, extra_constraints = _lower_triples_for_pattern(node["triples"], already_bound, state)
    bgp = CompValue("BGP", triples=new_triples)
    return _wrap_with_constraints(bgp, extra_constraints)


def _lower_template_term(term, pending_extends: list, extra_template_triples: list, state: _LowerState):
    """Lower `term` for TERM-SLOT position within a CONSTRUCT template.
    Unlike ordinary BGP pattern position, this is unconditional regardless
    of groundedness (every WHERE-clause variable is already bound by the
    time a template is instantiated) — mirrors sparql12_to_11.py's own
    `in_construct_template` branch, checked first and unconditional there
    for the same reason.
    """
    if not isinstance(term, TripleTermNode):
        return term
    s, p, o = term["subject"], term["predicate"], term["object"]
    var = state.new_var()
    pending_extends.append((var, _hash_call(s, p, o, state)))
    # Separately mint the nested object's own term-slot replacement (and,
    # recursively, its own encoding triples) for use in *this* level's
    # rdf:object encoding triple below — a deliberate, cheap duplication
    # against the hash computed via _hash_call's own expression-position
    # inlining above (tt_hash is a pure, cheap function): the encoding
    # triple's object slot needs an actual TERM, not an expression.
    o2 = _lower_template_term(o, pending_extends, extra_template_triples, state)
    extra_template_triples.append((var, RDF.subject, s))
    extra_template_triples.append((var, RDF.predicate, p))
    extra_template_triples.append((var, RDF.object, o2))
    return var


def _lower_construct_query(node: CompValue, state: _LowerState) -> CompValue:
    # node["p"] is always a Project wrapping the WHERE pattern (rdflib's
    # own algebra.py always wraps a CONSTRUCT's WHERE this way, even
    # though — per serialize12.py's own finding — its PV is internal
    # bookkeeping, not a printed variable list; CONSTRUCT has no ORDER
    # BY/etc. that could put something else here). A minted ground bind
    # must wrap the pattern *inside* Project (Project.p), not Project
    # itself from the outside — Extend-outside-Project is structurally
    # backwards (BIND happens before projection, not after) and decodes/
    # re-serializes into a mangled WHERE clause.
    where = _lower_expr(node["p"], state)
    pending_extends: list = []
    extra_template_triples: list = []
    new_template = []
    for s, p, o in node["template"]:
        s2 = _lower_template_term(s, pending_extends, extra_template_triples, state)
        o2 = _lower_template_term(o, pending_extends, extra_template_triples, state)
        new_template.append((s2, p, o2))
    new_template.extend(extra_template_triples)
    inner = where["p"]
    for var, expr in pending_extends:
        inner = CompValue("Extend", p=inner, expr=expr, var=var)
    where["p"] = inner
    # Project.PV must include every freshly minted template variable, not
    # just the ones already in the original (pre-lowering) template —
    # evalConstructQuery fills the template from evalProject's *output*
    # solutions, and evalProject drops any variable not listed in PV.
    # Confirmed as a real, reproducible bug (not just a theoretical
    # concern) once execution stopped round-tripping through SPARQL 1.1
    # text: re-parsing text-serialized output happened to recompute PV
    # fresh from the regenerated CONSTRUCT template each time, silently
    # masking this — executing the decoded Query object directly (see
    # rdf11_to_query) does not, since it reuses the PV this function
    # itself produced. Without this, every ground/minted triple-term
    # template triple silently vanished from CONSTRUCT results.
    where["PV"] = list(where["PV"]) + [var for var, _ in pending_extends]
    result = CompValue("ConstructQuery")
    for key, value in node.items():
        if key in ("_vars", "lazy", "p", "template"):
            continue
        result[key] = value
    result["p"] = where
    result["template"] = new_template
    return result


def _eager_lower_value(val):
    """Eagerly (Python-level, not algebra-level) lower a VALUES row cell —
    also used by `_lower_pattern_term` for a ground triple term reached in
    ordinary BGP pattern position (see its own docstring for why that case
    specifically must not use BIND). A VALUES cell can never be an
    expression (only a ground term or the bare string "UNDEF" — see
    to_rdf.py's _encode_binding_row docstring), so a triple term there
    needs its hash computed directly, mirroring _tt_hash_fn's own
    algorithm, rather than an algebra-level Function call.

    Also calls `remember_tt_hash`, exactly as `_tt_hash_fn` itself does —
    this value is never written to the graph (it's substituted as a
    literal term directly, not asserted), so without this,
    `StarLayerGraph`'s own result-restoration step has no way to turn the
    computed `tt:` URIRef in a result row back into a real `TripleTerm`
    for display, unlike a triple term that came from an ordinary pattern
    match against real data. Confirmed via a real W3C fixture
    (`triple-on-triple-terms`, whose VALUES rows put a ground triple term
    directly in subject/predicate position of another): a result row's
    `?subject`/`?predicate` came back as a bare, unresolved `tt:` URIRef
    instead of the expected `TripleTerm`.
    """
    if not isinstance(val, TripleTermNode):
        return val
    from starlayergraph.model.encoding import TT_NS as _STARLIGHT_TT_NS
    from starlayergraph.model.encoding import remember_tt_hash, term_key, tt_hash

    s = _eager_lower_value(val["subject"])
    p = val["predicate"]
    o = _eager_lower_value(val["object"])
    uri = URIRef(_STARLIGHT_TT_NS + tt_hash(term_key(s), term_key(p), term_key(o)))
    remember_tt_hash(uri, s, p, o)
    return uri


def _lower_values(node: CompValue, state: _LowerState) -> CompValue:
    new_res = []
    for row in node["res"]:
        new_res.append({var: _eager_lower_value(val) for var, val in row.items()})
    new_node = CompValue("values", res=new_res)
    for key, value in node.items():
        if key in ("_vars", "lazy", "res"):
            continue
        new_node[key] = value
    return new_node


# ---------------------------------------------------------------------
# SPARQL Update lowering.
#
# Confirmed empirically (not assumed) the real algebra shape of every
# Update operation before writing any of this:
#
#   InsertData/DeleteData/DeleteWhere -> ['quads', 'triples']  (same shape)
#   Modify                            -> ['delete', 'insert', 'where']
#   Load                              -> ['iri']
#   Clear/Drop/Create                 -> ['graphiri']
#   Add/Move/Copy                     -> ['graph']
#
# Load/Clear/Drop/Create/Add/Move/Copy are pure graph-management operations
# with no triple-pattern/template position at all (a graph reference is
# always a plain IRI, never a term slot a triple term could occupy) - they
# need zero lowering and pass through completely unchanged.
#
# The other three split into two genuinely different lowering rules, not
# one:
#
# - InsertData/DeleteData's own `.triples`/`.quads` are ordinary PATTERN
#   position, the same as a BGP's - reuses `_lower_pattern_term` directly
#   via `_lower_flat_triples_op`/`_lower_flat_triples`, unchanged. Always
#   takes the ground/eager-Python branch (SPARQL's QuadData grammar
#   forbids variables there entirely) - `_lower_flat_triples` asserts this,
#   it doesn't need to handle the non-ground case at all.
# - DeleteWhere is dispatched separately, to `_lower_delete_where`: its own
#   triples list serves as both the match pattern *and* the delete
#   template simultaneously (that's the whole point of the `WHERE`
#   shorthand), which is fine for `_lower_flat_triples_op`'s simple,
#   unchanged path in the ordinary (ground, or plain-variable) case - but a
#   non-ground triple term's own accessor-function constraints (see
#   `_add_component_constraints`) have nowhere to attach on a bare flat
#   triples list: `evalDeleteWhere` (rdflib's own `update.py`) calls
#   `evalBGP` directly on it, with no Filter/Extend wrapping capability at
#   all — confirmed by reading its source, unlike ordinary WHERE-clause
#   evaluation (`_lower_bgp`, which the caller can freely wrap). Fixed, not
#   left as a gap: `_lower_delete_where` rewrites the whole operation into
#   an equivalent `Modify(delete=<template>, insert=None, where=<pattern>)`
#   whenever a non-ground triple term is present, reusing `_lower_bgp`'s
#   own `Filter`/`Extend`-wrapping machinery for the WHERE side and the
#   *same* lowered (variable-substituted) triples list directly as the
#   DELETE template - see that function's own docstring for why that reuse
#   is exactly correct, not just structurally convenient.
# - Modify's `.delete`/`.insert` clauses are TEMPLATE position, the same as
#   CONSTRUCT's - reuses `_lower_template_term` (unconditional minting
#   regardless of groundedness, since every variable here is bound by
#   `.where`'s own solutions by the time the template is instantiated).
#   Unlike CONSTRUCT, no `Project`/`PV` wrapping exists to worry about:
#   `translateUpdate` never wraps a `Modify`'s `.where` in `Project` at all
#   (confirmed via finding #6 - `_addVars`/`analyse` never even run on it),
#   so a minted `Extend` wrapped directly around `.where` is sufficient for
#   its variable to reach the template - no PV list to remember to update.
# ---------------------------------------------------------------------


def _lower_flat_triples(triples: list, state: _LowerState) -> list:
    """Lower a flat (s, p, o) list at ordinary PATTERN position - shared by
    InsertData/DeleteData's own `.triples`, and each graph's triples inside
    `.quads`. SPARQL's `QuadData` grammar forbids variables in InsertData/
    DeleteData entirely, so a non-ground triple term can never actually
    reach this function - only `DeleteWhere` could produce one, and that
    case is handled separately now (see `_lower_delete_where`, which
    rewrites into an equivalent `Modify` instead of using this function at
    all whenever a non-ground triple term is present)."""
    already_bound = _bgp_plain_vars(triples)
    new_triples, extra_constraints = _lower_triples_for_pattern(triples, already_bound, state)
    assert not extra_constraints, (
        "starsparql.lower_rdf11: a non-ground triple term reached "
        "_lower_flat_triples - SPARQL's QuadData grammar should make this "
        "unreachable for InsertData/DeleteData, and DeleteWhere should "
        "have been routed through _lower_delete_where's Modify rewrite "
        "instead before ever calling this function."
    )
    return new_triples


def _lower_quads_map(quads: dict, state: _LowerState) -> dict:
    return {graph: _lower_flat_triples(triples, state) for graph, triples in quads.items()}


def _lower_flat_triples_term_for_insert(term, extra_triples: list):
    """Lower `term` for InsertData's own flat `.triples`/`.quads` TERM-SLOT
    position - unlike `_lower_pattern_term`'s ground branch (which this
    otherwise mirrors: SPARQL's QuadData grammar forbids variables here
    entirely, so eager Python computation is always safe), a ground triple
    term reached here introduces *new* data, not a match against something
    that must already exist - it must persist its own encoding triples
    (rdf:subject/predicate/object onto its tt:HASH URI), not just compute
    the URI and rely on the ephemeral, process-global `remember_tt_hash`
    cache `_eager_lower_value` alone populates. Confirmed via a real gap:
    without this, `has_triple_term()`/`triple_terms()` (which both rebuild
    their registry from the store's own *persisted* encoding triples, not
    that process-global cache) never see a triple term introduced this way
    at all, even though the value it hashes to is written correctly and a
    same-process `.triples()` read (which does consult that cache) appears
    to work. Recurses into a nested object-position triple term the same
    way `_lower_template_term` does, accumulating that nested term's own
    encoding triples too."""
    if not isinstance(term, TripleTermNode):
        return term
    from starlayergraph.model.encoding import TT_NS as _STARLIGHT_TT_NS
    from starlayergraph.model.encoding import remember_tt_hash, term_key, tt_hash

    s = _lower_flat_triples_term_for_insert(term["subject"], extra_triples)
    p = term["predicate"]
    o = _lower_flat_triples_term_for_insert(term["object"], extra_triples)
    uri = URIRef(_STARLIGHT_TT_NS + tt_hash(term_key(s), term_key(p), term_key(o)))
    remember_tt_hash(uri, s, p, o)
    extra_triples.append((uri, RDF.subject, s))
    extra_triples.append((uri, RDF.predicate, p))
    extra_triples.append((uri, RDF.object, o))
    return uri


def _lower_flat_triples_for_insert(triples: list) -> list:
    """`_lower_flat_triples`'s InsertData-specific counterpart - see
    `_lower_flat_triples_term_for_insert` for why InsertData can't reuse
    the shared pattern-position lowering every other flat-triples case
    (DeleteData, DeleteWhere, VALUES rows, ordinary WHERE-clause matching)
    correctly does use."""
    extra_triples: list = []
    new_triples = []
    for s, p, o in triples:
        s2 = _lower_flat_triples_term_for_insert(s, extra_triples)
        o2 = _lower_flat_triples_term_for_insert(o, extra_triples)
        new_triples.append((s2, p, o2))
    new_triples.extend(extra_triples)
    return new_triples


def _lower_flat_triples_op(node: CompValue, state: _LowerState) -> CompValue:
    """InsertData/DeleteData - identical `.triples`/`.quads` shape.
    (`DeleteWhere` shares this shape too, but is dispatched to
    `_lower_delete_where` instead - see `_lower_update_operation`.)

    InsertData is lowered differently from DeleteData here - see
    `_lower_flat_triples_term_for_insert`'s own docstring for why a ground
    triple term being *inserted* needs its encoding triples persisted,
    while one merely being *matched* for deletion (DeleteData can only
    ever remove a reference to something that must already exist) doesn't
    - matching `has_triple_term`'s own tests confirming encoding triples
    deliberately survive a DELETE.
    """
    new_node = CompValue(node.name)
    if node.name == "InsertData":
        new_node["triples"] = _lower_flat_triples_for_insert(node["triples"])
        new_node["quads"] = {
            graph: _lower_flat_triples_for_insert(triples) for graph, triples in node["quads"].items()
        }
    else:
        new_node["triples"] = _lower_flat_triples(node["triples"], state)
        new_node["quads"] = _lower_quads_map(node["quads"], state)
    return new_node


def _contains_nonground_triple_term(triples: list) -> bool:
    return any(
        (isinstance(t, TripleTermNode) and not _is_ground(t)) for s, p, o in triples for t in (s, o)
    )


def _lower_delete_where(node: CompValue, state: _LowerState) -> CompValue:
    """`DeleteWhere`'s `.triples`/`.quads` serve as *both* the match
    pattern and the delete template simultaneously (`DELETE WHERE {T}` is
    shorthand for `DELETE {T} WHERE {T}`) - fine for the ordinary,
    all-ground-or-plain-variable case (`_lower_flat_triples_op`, unchanged
    below), but a non-ground triple term needs the same
    `Filter`/`Extend`-wrapping `_lower_bgp` gives an ordinary WHERE clause,
    which `evalDeleteWhere` has no way to apply to a bare flat triples list
    (confirmed via reading its source: it calls `evalBGP` directly, no
    wrapping possible) - see `_lower_flat_triples`'s own docstring and
    CLAUDE.md finding #28's closing paragraph for the fuller trace.

    Fixed by rewriting the whole operation into an equivalent
    `Modify(delete=<template>, insert=None, where=<pattern>)` *only* when a
    non-ground triple term is actually present (the ordinary case keeps
    using the simpler, unchanged `_lower_flat_triples_op` path - no
    structural change for the common case). The key insight making this
    reuse-not-just-shape-mimicry: `_lower_triples_for_pattern`'s own
    `new_triples` (the *same* lowered list, with each non-ground triple
    term replaced by the ordinary fresh variable the WHERE pattern's own
    BGP match binds it to) is *already* exactly correct as the DELETE
    template too - by the time the template is instantiated, that variable
    is bound to precisely the triple-term value the WHERE clause matched,
    so reusing it directly (rather than reconstructing the triple term from
    its own components, e.g. via `TT_HASH_FN`) needs no extra machinery at
    all - unlike an ordinary Modify's `.delete`/`.insert` clause (which has
    no such existing pattern-side variable to reuse, hence
    `_lower_template_term`'s unconditional-mint-a-fresh-`BIND`-variable
    approach there instead).

    Each graph's own triples (default graph plus each `.quads` entry) gets
    its *own*, separately-scoped `already_bound` set, deliberately not
    shared across them the way `_collect_mandatory_plain_vars` shares one
    globally for an ordinary WHERE clause: the `Join`/`Graph` nodes built
    here are never marked `lazy=True` (`evalJoin` treats a missing/falsy
    `.lazy` as ordinary independent-branch-then-join evaluation, `_join`),
    and per CLAUDE.md finding #28's own conclusion, a variable shared only
    with an *independently* evaluated sibling branch is not actually bound
    within this branch's own isolated evaluation - the natural join
    equality check catches a real mismatch afterward regardless, without
    needing (and, confirmed via the same finding, actively harmed by) this
    function pretending it's already bound here.
    """
    has_nonground = _contains_nonground_triple_term(node["triples"]) or any(
        _contains_nonground_triple_term(triples) for triples in node["quads"].values()
    )
    if not has_nonground:
        return _lower_flat_triples_op(node, state)

    default_bound = _bgp_plain_vars(node["triples"])
    default_triples, default_constraints = _lower_triples_for_pattern(node["triples"], default_bound, state)
    where_pattern = _wrap_with_constraints(CompValue("BGP", triples=default_triples), default_constraints)

    new_quads: dict = {}
    for graph, triples in node["quads"].items():
        graph_bound = _bgp_plain_vars(triples)
        g_triples, g_constraints = _lower_triples_for_pattern(triples, graph_bound, state)
        new_quads[graph] = g_triples
        graph_pattern = _wrap_with_constraints(CompValue("BGP", triples=g_triples), g_constraints)
        where_pattern = CompValue("Join", p1=where_pattern, p2=CompValue("Graph", term=graph, p=graph_pattern))

    delete_clause = CompValue("DeleteClause", triples=default_triples, quads=new_quads)
    return CompValue("Modify", delete=delete_clause, insert=None, where=where_pattern)


def _lower_modify_clause_triples(triples: list, pending_extends: list, state: _LowerState) -> list:
    """Lower a Modify DELETE/INSERT clause's own flat triples - TEMPLATE
    position (mirrors `_lower_template_term`/`_lower_construct_query`), not
    ordinary pattern position: see this section's own module-level comment
    for why groundedness doesn't matter here the way it does for
    InsertData/DeleteData."""
    extra_triples: list = []
    new_triples = []
    for s, p, o in triples:
        s2 = _lower_template_term(s, pending_extends, extra_triples, state)
        o2 = _lower_template_term(o, pending_extends, extra_triples, state)
        new_triples.append((s2, p, o2))
    new_triples.extend(extra_triples)
    return new_triples


def _lower_modify_clause(clause, pending_extends: list, state: _LowerState):
    """Lower a Modify `.delete`/`.insert` clause - `None` for an INSERT-only
    or DELETE-only Modify (confirmed via `algebra.translateUpdate1`, same
    fact finding #26 already relies on)."""
    if clause is None:
        return None
    new_clause = CompValue(clause.name)
    new_clause["triples"] = _lower_modify_clause_triples(clause["triples"], pending_extends, state)
    new_clause["quads"] = {
        graph: _lower_modify_clause_triples(triples, pending_extends, state)
        for graph, triples in clause["quads"].items()
    }
    return new_clause


def _lower_modify(node: CompValue, state: _LowerState) -> CompValue:
    state.global_plain_vars = _collect_mandatory_plain_vars(node["where"])
    where = _lower_expr(node["where"], state)
    pending_extends: list = []
    # Attribute access, not .get("delete")/.get("insert"): CompValue.get's
    # signature is get(self, a, variables=False, errors=False) - no default
    # parameter - and it falls back to returning the key string itself (not
    # None) when the key is absent (OrderedDict.get(self, a, a)). An
    # INSERT-only or DELETE-only Modify legitimately has no "delete"/"insert"
    # key at all, so .get(...) would silently hand back the literal string
    # "delete"/"insert" instead of None, crashing _lower_modify_clause's own
    # `clause.name` access below. Attribute access uses CompValue.__getattr__
    # instead, which does return None for a missing key.
    new_delete = _lower_modify_clause(node.delete, pending_extends, state)
    new_insert = _lower_modify_clause(node.insert, pending_extends, state)
    inner = where
    for var, expr in pending_extends:
        inner = CompValue("Extend", p=inner, expr=expr, var=var)
    result = CompValue("Modify")
    for key, value in node.items():
        if key in ("_vars", "lazy", "where", "delete", "insert"):
            continue
        result[key] = value
    result["where"] = inner
    result["delete"] = new_delete
    result["insert"] = new_insert
    return result


_FLAT_TRIPLES_OPS = {"InsertData", "DeleteData"}
# Pure graph-management operations - no triple-pattern/template position at
# all (a graph reference is always a plain IRI), so nothing to lower.
_PASSTHROUGH_OPS = {"Load", "Clear", "Drop", "Create", "Add", "Move", "Copy"}


def _lower_update_operation(op: CompValue, state: _LowerState) -> CompValue:
    if op.name in _FLAT_TRIPLES_OPS:
        return _lower_flat_triples_op(op, state)
    if op.name == "DeleteWhere":
        return _lower_delete_where(op, state)
    if op.name == "Modify":
        return _lower_modify(op, state)
    if op.name in _PASSTHROUGH_OPS:
        return op
    raise NotImplementedError(
        f"starsparql.lower_rdf11: no lowering rule for Update operation {op.name!r}"
    )


def _restarlayergraph_dirlang_literals(node):
    """Recursively rewrite every Literal in `node` from this project's own
    dirlang: encoding (vocab.encode_dirlang_datatype - see grammar12.py's
    LangDirLiteral for why this project uses its own, not starlayergraph's) into
    starlayergraph's own dirlang: encoding (starlayergraph.model.encoding) instead -
    the one literal-*value* conversion this module's lowering needs to do,
    parallel to the triple-term-*structure* lowering the rest of this
    module already does.

    Needed because this project's grammar deliberately does *not* use
    starlayergraph's encoding when parsing a dirLangString literal (so the
    algebra's RDF representation, via to_rdf.py, stays safely storable in a
    real StarLayerGraph without that graph's own restoration logic
    mistaking it for one of its own values and silently swapping in a
    DirLangString object where a plain Literal belongs - see vocab.py's
    DIRLANG_NS for the full reasoning) - but *execution* against a real
    StarLayerGraph is the opposite requirement: its own restoration logic
    only recognizes *its own* encoding, so a lowered query actually run
    there needs the literal converted at the one point - lowering - where
    this project hands off to starlayergraph's execution machinery specifically.
    Confirmed via a real failure without this: `expression/triple-on-str-
    literals`, executed via `_run_lowered`, came back with the raw
    unrecognized Literal instead of a restored DirLangString in results.

    Mutates and returns `node` in place - safe here specifically because
    lowering (`_lower_expr`/`_lower_update_operation`, both already
    documented as not mutating their own *input*) has, by the time this
    runs, already built a brand-new tree nothing else references yet, so
    there is no aliasing risk in doing the final pass in place rather than
    building yet another fresh copy.
    """
    from starlayergraph.model.encoding import (
        encode_dirlang_datatype as _starlayergraph_encode_dirlang,
    )

    if isinstance(node, Literal):
        if node.datatype is not None:
            decoded = decode_dirlang_datatype(node.datatype)
            if decoded is not None:
                lang, direction = decoded
                return Literal(str(node), datatype=_starlayergraph_encode_dirlang(lang, direction))
        return node
    if isinstance(node, (CompValue, dict)):
        for key, value in list(node.items()):
            node[key] = _restarlayergraph_dirlang_literals(value)
        return node
    if isinstance(node, list):
        for i, item in enumerate(node):
            node[i] = _restarlayergraph_dirlang_literals(item)
        return node
    if isinstance(node, tuple):
        return tuple(_restarlayergraph_dirlang_literals(item) for item in node)
    return node


def lower_update_to_rdf11(operations: list) -> list:
    """Lower `update.algebra` (a list of Update operations, one per
    semicolon-separated request) to plain SPARQL 1.1 - the `Update`
    counterpart of `lower_algebra_to_rdf11`. Each operation gets its own
    fresh `_LowerState` (its own triple-term-variable counter) - operations
    execute independently in sequence, so there's no reason to share
    numbering across them, mirroring how each is a wholly separate
    algebra tree to begin with."""
    return [
        _restarlayergraph_dirlang_literals(_lower_update_operation(op, _LowerState()))
        for op in operations
    ]


def update_to_rdf11(update: Update) -> tuple[Graph, URIRef]:
    """Lower `update.algebra` to SPARQL 1.1, then encode via the existing,
    unmodified `to_rdf.update_to_rdf`. Returns `(graph, root)` - the RDF
    graph for the lowered 1.1 update, and the node for its root.

    Deliberately passes a plain `rdflib.Graph()` here, not
    `to_rdf`'s own `StarLayerGraph` default: a *lowered* algebra's
    ground-triple-term term-slot values are already real `tt:`-prefixed
    URIRefs (or, before lowering runs its course inside a live query,
    literal `TripleTerm` objects computed via `starlayergraph.model.encoding`),
    and those need to stay inert markers in this salg: encoding, not get
    silently restored back into `TripleTerm` objects by a `StarLayerGraph`'s
    own tt:HASH lookup (which consults a process-global cache, not one
    scoped to this graph - confirmed via a real crash: `remember_tt_hash`
    called during lowering populates that global cache, so any
    `StarLayerGraph.value()`/`.triples()` call anywhere in the same process
    would "helpfully" resolve the very URIRef this encoding needs to stay
    opaque, and `from_rdf.py`'s decoder has no branch for an already-resolved
    `TripleTerm` node). A plain `Graph` has no such lookup, so it can't
    misfire here."""
    lowered_ops = lower_update_to_rdf11(update.algebra)
    lowered_update = Update(update.prologue, lowered_ops)
    return update_to_rdf(lowered_update, graph=Graph())


def rdf11_to_update(graph: Graph, root) -> Update:
    """Decode a lowered-1.1 RDF graph (as produced by `update_to_rdf11`)
    back into a directly executable `rdflib` `Update` object - thin wrapper
    over the existing, unmodified `from_rdf.rdf_to_update`. Hand it
    straight to `rdflib.plugins.sparql.update.evalUpdate`/
    `StarLayerGraph`'s own update-execution path - no SPARQL 1.1 text
    needed anywhere in this path, mirroring `rdf11_to_query`.

    Update serialization back to SPARQL text is out of scope here, same as
    for the rest of this project (see CLAUDE.md's "Not started" section) -
    only the execution path is built.
    """
    return rdf_to_update(graph, root)


class _AlgebraTranslator11(_AlgebraTranslator):
    """``rdflib.plugins.sparql.algebra._AlgebraTranslator``, with one added
    branch: rendering a ``Function`` node (``CompValue('Function', iri=,
    distinct=[], expr=[...])`` — the generic shape for calling any
    registered custom SPARQL function, produced by this module's own
    ``_hash_call``/accessor lowering).

    Confirmed empirically that plain rdflib has **no** branch for this at
    all, for any ``Function`` node — not a gap specific to this project:
    reproduced independently of any lowering, straight from a real
    ``prepareQuery("SELECT * WHERE { BIND(<http://ex/fn>(?x,?y) AS ?z) }")``,
    whose algebra already contains an ordinary ``Function`` node — plain
    ``translateAlgebra`` regenerates ``SELECT ({Function} as ?z){}``, an
    unresolved placeholder. Neither ``starlayergraph``'s ``sparql12_to_11.py``
    (which builds function-call *text* directly, never going through
    algebra/``translateAlgebra`` at all) nor this project's own
    ``serialize12.py`` (whose SPARQL 1.2 extensions — ``Builtin_isTRIPLE``/
    ``SUBJECT``/etc. — are bespoke grammar productions, not generic
    ``Function`` calls) needed this before; lowering to ``TT_HASH_FN``/the
    ``tt:`` accessor functions is the first thing in either project that
    does.

    Mirrors the exact pattern already established by ``serialize12.py``'s
    own ``Builtin_isTRIPLE``/etc. branches for a multi-child node whose
    arguments may themselves be unresolved ``CompValue`` placeholders
    (e.g. a nested ``Function`` call, from a nested ground triple term):
    fall through with an implicit ``None`` return rather than ``return
    node``, so rdflib's own ``_traverse`` continues recursing into
    ``node.expr``'s children afterward and resolves each one's own
    ``"{Function}"`` placeholder in turn.
    """

    def translateAlgebra(self) -> str:
        text = super().translateAlgebra()
        # Same fixup as serialize12.py's own translateAlgebra() override —
        # see its docstring for why this is a real, pre-existing rdflib gap
        # (confirmed independent of triple terms: an ordinary SPARQL 1.1
        # query with no BGP at all, e.g. one using only VALUES/FILTER,
        # already regenerates these same unresolved placeholders from
        # plain, unmodified rdflib) rather than something specific to this
        # module's lowering. A lowered query can just as easily have no
        # ordinary BGP (a VALUES-only query with an eagerly-hashed triple
        # term row, or an isTRIPLE()-only FILTER) as a SPARQL 1.2 one can.
        text = text.replace("-*-SELECT-*-", "SELECT")
        text = text.replace("{GroupBy}", "")
        text = text.replace("{Having}", "")
        return text

    def sparql_query_text(self, node):
        if isinstance(node, CompValue) and node.name == "Function":
            args = ", ".join(self.convert_node_arg(a) for a in node.expr)
            self._replace("{Function}", node.iri.n3() + "(" + args + ")")
            return None

        if isinstance(node, CompValue) and node.name == "ConstructQuery":
            # Mirrors serialize12.py's own ConstructQuery branch (see its
            # docstring for the two non-obvious fixes this replicates:
            # referencing node.p.p directly rather than going through
            # Project's own branch, and always including the literal
            # WHERE keyword for compatibility with StarLayerGraph's own
            # internal rewriting) minus the TripleTermNode/dirLangString
            # handling _term_text adds — nothing lowered still needs
            # either, so plain .n3() suffices for every template term.
            template_text = "".join(
                s.n3() + " " + p.n3() + " " + o.n3() + ". " for s, p, o in node.template
            ) if node.template else ""
            self._alg_translation = (
                "CONSTRUCT {" + template_text + "} WHERE {{" + node.p.p.name + "}}"
            )
            return None

        return super().sparql_query_text(node)


def lower_algebra_to_rdf11(algebra: CompValue) -> CompValue:
    """Lower a SPARQL 1.2 algebra tree (``TripleTermNode``/``Builtin_isTRIPLE``/
    ``Builtin_SUBJECT``/``Builtin_PREDICATE``/``Builtin_OBJECT`` — see module
    docstring) into a plain SPARQL 1.1 algebra tree. Does not mutate `algebra`.
    """
    state = _LowerState()
    state.global_plain_vars = _collect_mandatory_plain_vars(algebra)
    return _restarlayergraph_dirlang_literals(_lower_expr(algebra, state))


def query_to_rdf11(query: Query) -> tuple[Graph, URIRef]:
    """Lower `query.algebra` to SPARQL 1.1, then encode via the existing,
    unmodified ``to_rdf.query_to_rdf``. Returns ``(graph, root)`` — the RDF
    graph for the lowered 1.1 algebra, and the node for its root.

    Deliberately passes a plain `rdflib.Graph()` here, not `to_rdf`'s own
    `StarLayerGraph` default — see `update_to_rdf11`'s docstring for why:
    a lowered algebra's ground-triple-term term-slot values need to stay
    inert `tt:`-prefixed URIRefs in this salg: encoding, and a
    `StarLayerGraph` would silently resolve them back into `TripleTerm`
    objects via its process-global tt:HASH cache, which `from_rdf.py`'s
    decoder can't handle."""
    lowered = lower_algebra_to_rdf11(query.algebra)
    lowered_query = Query(query.prologue, lowered)
    return query_to_rdf(lowered_query, graph=Graph())


def rdf11_to_query(graph: Graph, root) -> Query:
    """Decode a lowered-1.1 RDF graph (as produced by ``query_to_rdf11``)
    back into a directly executable ``rdflib`` ``Query`` object — thin
    wrapper over the existing, unmodified ``from_rdf.rdf_to_query``, which
    already re-runs ``_addVars``/``analyse`` and promotes ``Function``
    nodes to real evaluable ``Expr``s. Nothing further is needed to make
    this object runnable: hand it straight to
    ``StarLayerGraph.query()``/``StarLayerDataset.query()`` — both already
    special-case a non-``str`` ``query_object`` to skip their own text
    rewriting/parsing entirely and execute it as-is.

    Prefer this over ``rdf11_to_sparql11_text`` for actual execution — see
    the module docstring for why the text path is unnecessary (and a real
    source of fragility) for this specific purpose.
    """
    return rdf_to_query(graph, root)


def rdf11_to_sparql11_text(graph: Graph, root) -> str:
    """Decode a lowered-1.1 RDF graph (as produced by ``query_to_rdf11``)
    back into SPARQL 1.1 query text, via the existing, unmodified
    ``from_rdf.rdf_to_query`` (re-runs rdflib's own ``_addVars``/``analyse``,
    promoting ``Function`` nodes to real evaluable ``Expr``s) and
    ``_AlgebraTranslator11`` (plain rdflib ``_AlgebraTranslator`` plus a
    ``Function``-node rendering branch — see its docstring; not
    ``serialize12``'s ``TripleTermNode``-aware translator, since nothing
    lowered still needs that).

    For execution against ``StarLayerGraph``/``StarLayerDataset``, prefer
    ``rdf11_to_query`` instead — this function exists for cases that need
    real SPARQL 1.1 text (debugging, external tools, a string-only
    backend), not because execution needs it.
    """
    query = rdf_to_query(graph, root)
    return _AlgebraTranslator11(query).translateAlgebra()


def _n3_quaddata(triples: list, quads: dict) -> str:
    """Render an InsertData/DeleteData/DeleteWhere-shaped ``{triples,
    quads}`` pair (or a Modify DELETE/INSERT clause — same shape) as a
    ``QuadData``/``QuadPattern`` block: ``{ <default-graph triples>
    GRAPH <g> { <g's triples> } ... }``. Every term here is already ground
    (or, inside a Modify template, a plain ``Variable`` — ``.n3()`` handles
    both identically)."""

    def render(ts) -> str:
        return "".join(s.n3() + " " + p.n3() + " " + o.n3() + " .\n" for s, p, o in ts)

    parts = [render(triples)]
    for g, gtriples in quads.items():
        if gtriples:
            parts.append(f"GRAPH {g.n3()} {{\n{render(gtriples)}}}\n")
    return "{\n" + "".join(parts) + "}"


def _sparql11_text_for_where(where_pattern: CompValue) -> str:
    """Render a Modify's ``.where`` pattern — an ordinary WHERE-clause
    algebra tree, the same node shapes (``BGP``/``Join``/``Graph``/etc.)
    any query's own WHERE clause uses — as ``WHERE { ... }`` text, by
    reusing ``_AlgebraTranslator11``'s existing pattern-rendering
    machinery: wrap it in a throwaway ``SELECT * { ... }``-shaped ``Query``
    and strip the ``SELECT * `` prefix back off. Building a second,
    parallel pattern-to-text renderer just for Update would duplicate that
    machinery for no benefit — the node types a WHERE clause can contain
    are identical whether they were reached via a SelectQuery or a
    Modify."""
    fake_project = CompValue("Project", p=where_pattern, PV=[])
    fake_select = CompValue("SelectQuery", p=fake_project, PV=[], datasetClause=None)
    fake_query = Query(Prologue(), fake_select)
    text = _AlgebraTranslator11(fake_query).translateAlgebra()
    prefix = "SELECT * "
    if not text.startswith(prefix):
        raise ExpressionNotCoveredException(
            f"starsparql: expected _AlgebraTranslator11 to render a throwaway "
            f"'SELECT * ...' for a Modify WHERE clause, got: {text!r}"
        )
    return "WHERE " + text[len(prefix):]


def _sparql11_text_for_operation(op: CompValue) -> str:
    """Render one already-lowered (plain SPARQL 1.1) Update operation
    CompValue back to SPARQL 1.1 text - the Update counterpart of
    ``_AlgebraTranslator11``'s query-side rendering. Handles every
    operation shape ``rdflib.plugins.sparql.algebra.translateUpdate1`` can
    produce (see its own source - this function mirrors that dispatch
    exactly): ``InsertData``/``DeleteData``/``DeleteWhere`` (flat
    ``{triples, quads}``), ``Modify`` (``WITH``/``USING``/``DELETE``/
    ``INSERT``/``WHERE``), and the 7 graph-management operations
    (``Load``/``Clear``/``Drop``/``Create``/``Add``/``Move``/``Copy`` -
    no pattern/template position at all, just IRIs and an optional
    ``SILENT`` flag)."""

    def graph_term(t) -> str:
        # 'DEFAULT'/'NAMED'/'ALL' are literal keywords in this position
        # (confirmed via real parseUpdate output), not real graph IRIs -
        # `type(t) is str`, not `isinstance`: URIRef is itself a str
        # subclass, so isinstance(uriref, str) is also True and would
        # wrongly skip .n3()'s "<...>" bracketing for a real graph IRI.
        # A real IRI needs the literal 'GRAPH' keyword before it here:
        # required by the GraphRefAll grammar (Clear/Drop) and GraphRef
        # (Create) - confirmed via real parseUpdate, `CLEAR <iri>` alone
        # raises ParseException, `CLEAR GRAPH <iri>` doesn't - and merely
        # optional-but-always-valid for GraphOrDefault (Add/Move/Copy), so
        # including it unconditionally is correct everywhere this helper
        # is used.
        return t if type(t) is str else f"GRAPH {t.n3()}"

    # Attribute access throughout this function, never .get(key): CompValue
    # .get's signature (get(self, a, variables=False, errors=False)) has no
    # default parameter and falls back to returning the key string itself
    # (not None/falsy) for a missing key (OrderedDict.get(self, a, a)) - the
    # same landmine _lower_modify already hit once (see its own comment).
    # `op.silent`/`op.withClause`/etc. via __getattr__ correctly return None
    # for a key that isn't present.
    silent = "SILENT " if op.silent else ""

    if op.name in ("InsertData", "DeleteData", "DeleteWhere"):
        keyword = {"InsertData": "INSERT DATA", "DeleteData": "DELETE DATA", "DeleteWhere": "DELETE WHERE"}[op.name]
        return f"{keyword} {_n3_quaddata(op.triples, op.quads)}"

    if op.name == "Modify":
        parts = []
        if op.withClause is not None:
            parts.append(f"WITH {op.withClause.n3()}\n")
        if op.delete is not None:
            parts.append(f"DELETE {_n3_quaddata(op.delete.triples, op.delete.quads)}\n")
        if op.insert is not None:
            parts.append(f"INSERT {_n3_quaddata(op.insert.triples, op.insert.quads)}\n")
        for using in op.using or []:
            if using.named is not None:
                parts.append(f"USING NAMED {using.named.n3()}\n")
            else:
                parts.append(f"USING {using.default.n3()}\n")
        parts.append(_sparql11_text_for_where(op.where))
        return "".join(parts)

    if op.name == "Load":
        into = f" INTO GRAPH {op.graphiri.n3()}" if op.graphiri is not None else ""
        return f"LOAD {silent}{op.iri.n3()}{into}"

    if op.name in ("Clear", "Drop"):
        keyword = "CLEAR" if op.name == "Clear" else "DROP"
        return f"{keyword} {silent}{graph_term(op.graphiri)}"

    if op.name == "Create":
        return f"CREATE {silent}{graph_term(op.graphiri)}"

    if op.name in ("Add", "Move", "Copy"):
        src, dst = op.graph
        return f"{op.name.upper()} {silent}{graph_term(src)} TO {graph_term(dst)}"

    raise ExpressionNotCoveredException(
        f"starsparql: no SPARQL 1.1 text renderer for update operation {op.name!r}"
    )


def rdf11_update_to_sparql11_text(graph: Graph, root) -> str:
    """``rdf11_to_sparql11_text``'s Update counterpart: decode a
    lowered-1.1 RDF graph (as produced by ``update_to_rdf11``) back into
    real SPARQL 1.1 Update text, via the existing, unmodified
    ``from_rdf.rdf_to_update`` plus ``_sparql11_text_for_operation`` for
    each operation (``;``-joined, matching SPARQL Update's own request
    syntax for multiple operations in one string).

    For execution against ``StarLayerGraph``/``StarLayerDataset``, prefer
    ``rdf11_to_update`` instead — this exists for cases that need real
    text: specifically, a remote HTTP store whose own ``update()``
    hard-requires a string (confirmed via real testing:
    ``rdflib.plugins.stores.sparqlstore.SPARQLUpdateStore.update`` asserts
    ``isinstance(query, str)``, so a lowered ``Update`` *object* can't be
    handed to it directly the way a local store accepts one)."""
    update = rdf_to_update(graph, root)
    return " ;\n".join(_sparql11_text_for_operation(op) for op in update.algebra)
