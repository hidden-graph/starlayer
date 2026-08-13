"""Decompose a SPARQL-1.1-*shaped* query (as produced by starsparql's
lowering, see starlayergraph.query.query_cache) for execution against a genuinely
remote store (rdflib's SPARQLStore/SPARQLUpdateStore - real Fuseki-as-1.1 or
any other HTTP SPARQL 1.1 endpoint).

For TRIPLE()/isTRIPLE(TRIPLE(...))/STRLANGDIR() (and SUBJECT()/PREDICATE()/
OBJECT() on a value that isn't already sitting in the store) that lowering
calls starlayergraph's own custom SPARQL extension functions (register_custom_function
- see starlayergraph.query.custom_functions). Those registrations are local-process
only: a remote SPARQL engine has never heard of the function IRI. Per SPARQL
1.1's own extension-function error semantics,
an unbound/unknown function call inside a BIND doesn't fail the query - it
just leaves that BIND's target variable unbound for every row. So the query
runs, returns rows, and the relevant column is silently empty - no exception,
just wrong data.

The fix used here is the same one the original in-memory/native evaluation
path already relies on implicitly: run the plain-SPARQL-1.1-expressible part
of the query remotely in one round trip, then evaluate the custom-function
parts locally in Python - using the exact same, already-registered function
implementations - once the now-known bound values are back, merging the
computed values into each result row before returning to the caller.

Concretely: parse the rewritten text into a real algebra tree (prepareQuery
succeeds locally since the custom functions are registered in-process), walk
it to find every ``Extend`` whose bound expression is - or transitively
depends on - a call to one of starlayergraph's custom functions, strip those
Extend nodes (keeping their inner pattern), and record an ordered "recipe"
list of (variable, expression) to replay locally, per result row, after the
simplified query comes back from the remote store.
"""
from __future__ import annotations

from typing import Any

from rdflib import Variable, URIRef
from rdflib.plugins.sparql.parserutils import CompValue

from starlayergraph.query.custom_functions import (
    DIRLANG_CONSTRUCT_FN,
    TT_HASH_FN,
    _TT_ACCESSOR_FN,
)

_CUSTOM_FUNCTION_IRIS = frozenset(
    URIRef(iri[1:-1])
    for iri in (TT_HASH_FN, DIRLANG_CONSTRUCT_FN, *_TT_ACCESSOR_FN.values())
)


def _cv_get(node: CompValue, key: str, default: Any = None) -> Any:
    # CompValue.get() has a non-standard signature (get(a, variables=False,
    # errors=False) - the second positional arg is NOT a default value), so
    # a plain dict-style get(key, default) would silently misbehave here.
    return node[key] if key in node else default


def _expr_vars(expr: Any) -> set:
    """Variables `expr` depends on. rdflib's own algebra construction
    already computes and stashes this as `_vars` on every CompValue
    expression node - only bare Variable/constant leaves need special-
    casing (a bare Variable reference has no `_vars` of its own; it *is*
    its own dependency)."""
    if isinstance(expr, Variable):
        return {expr}
    if isinstance(expr, CompValue):
        return _cv_get(expr, '_vars', set())
    return set()


def _is_custom_function_call(expr: Any) -> bool:
    return (
        isinstance(expr, CompValue)
        and expr.name == 'Function'
        and _cv_get(expr, 'iri') in _CUSTOM_FUNCTION_IRIS
    )


def contains_custom_function_call(node: Any) -> bool:
    """True iff a call to one of starlayergraph's custom SPARQL functions
    (``_CUSTOM_FUNCTION_IRIS``) appears anywhere in ``node``, recursively -
    a generic tree walk, not scoped to any particular algebra shape (unlike
    ``decompose_for_remote``, which only strips ``Extend`` nodes under a
    ``SelectQuery``). Used to *detect* the problem in shapes
    ``decompose_for_remote`` doesn't (yet) know how to *fix* - e.g. a
    ``ConstructQuery`` template minting a fresh triple term - so a caller
    can fail loudly instead of silently sending an unusable query to a
    remote store.
    """
    if _is_custom_function_call(node):
        return True
    if isinstance(node, CompValue):
        return any(contains_custom_function_call(v) for v in node.values())
    if isinstance(node, (list, tuple)):
        return any(contains_custom_function_call(item) for item in node)
    return False


def _strip_custom_extends(node: Any, local_vars: set, recipes: list, filters: list) -> Any:
    """Recursively strip Extend/Filter nodes that (transitively) depend on
    a starlayergraph custom function.

    Extend nodes get a ``(var, expr)`` recipe appended, same as before.
    Filter nodes - a shape only the starsparql-based pipeline
    produces, not the old text rewriter this module was originally built
    against: a non-ground triple-term pattern's own predicate constraint
    lowers to ``FILTER(PREDICATE(?tt) = :knows)`` rather than an
    Extend+equality-check - get their whole boolean expression appended to
    `filters` instead, to be re-evaluated locally per row (SPARQL's own
    FILTER semantics: exclude the row if the expression is false or
    raises), since a remote engine sent this expression as-is would raise
    on the unknown function and silently exclude every row rather than
    just failing to compute one value the way an unbound BIND target does.

    Post-order: children are visited (and their own recipes/filters
    recorded) before their parent, so `recipes` ends up in dependency
    order - an earlier recipe never references a variable defined by a
    later one, matching how BIND itself would have evaluated them.

    Uses `contains_custom_function_call` (recursive), not
    `_is_custom_function_call` (direct-node-only): a Filter's own
    expression is essentially never *itself* the Function call - it's a
    RelationalExpression/ConditionalExpression *containing* one - so a
    direct-only check would never match it. Strictly more general for
    Extend too (still matches the direct-call case, since
    contains_custom_function_call checks that first), so both use the same
    condition.
    """
    if not isinstance(node, CompValue):
        return node

    for child_key in ('p', 'p1', 'p2'):
        if child_key in node:
            node[child_key] = _strip_custom_extends(node[child_key], local_vars, recipes, filters)

    if node.name == 'Extend':
        expr = node.expr
        if contains_custom_function_call(expr) or (_expr_vars(expr) & local_vars):
            local_vars.add(node.var)
            recipes.append((node.var, expr))
            return node.p  # drop the Extend wrapper, keep its inner pattern

    if node.name == 'Filter':
        expr = node.expr
        if contains_custom_function_call(expr) or (_expr_vars(expr) & local_vars):
            filters.append(expr)
            return node.p  # drop the Filter wrapper, keep its inner pattern

    return node


def decompose_for_remote(prepared_query: Any) -> tuple[list[tuple[Variable, Any]], list[Any]]:
    """Mutate `prepared_query.algebra` in place, stripping every Extend/
    Filter that (transitively) depends on a starlayergraph custom function, and
    return ``(recipes, filters)``: the ordered list of (variable,
    expression) recipes to evaluate locally per result row (same as
    before), plus a list of boolean filter expressions to re-check locally
    per row (new - see `_strip_custom_extends`'s own docstring for why a
    Filter needs different handling than an Extend).

    Only SELECT-shaped queries (``algebra.name == 'SelectQuery'``) are
    decomposed; anything else is left untouched (empty recipes/filters)
    and falls back to the caller's existing plain-text-rewrite behavior -
    not a regression, since those shapes weren't handled before this
    either, and no current test exercises a custom function inside
    CONSTRUCT/ASK/DESCRIBE.

    Any variable a recipe depends on that isn't itself another recipe's
    target (e.g. a triple-term variable bound by an ordinary graph pattern,
    needed as SUBJECT()/PREDICATE()/OBJECT()'s argument) is added to the
    query's own projected-variables list so the remote engine actually
    returns its value - the caller is responsible for trimming the extra
    columns back out of the final result. Same treatment for a variable a
    stripped filter depends on.
    """
    algebra = prepared_query.algebra
    if algebra.name != 'SelectQuery':
        return [], []

    local_vars: set = set()
    recipes: list = []
    filters: list = []
    project = algebra.p
    project['p'] = _strip_custom_extends(project.p, local_vars, recipes, filters)

    required: set = set()
    for _, expr in recipes:
        required |= _expr_vars(expr)
    for expr in filters:
        required |= _expr_vars(expr)
    required -= local_vars

    pv = list(project.PV)
    for var in required:
        if var not in pv:
            pv.append(var)
    project['PV'] = pv

    return recipes, filters


def evaluate_recipes_locally(recipes: list[tuple[Variable, Any]], row: dict, graph: Any) -> dict:
    """Evaluate each stripped (var, expr) recipe against `row` (a dict of
    Variable -> already-bound, not-yet-restored Node, straight from a raw
    remote result row), in order, merging each computed value back in so a
    later recipe can reference an earlier one's result - mirrors evalExtend's
    own per-row behavior, just replayed after the remote round trip instead
    of during it.

    Reuses rdflib's own private expression evaluator (`_eval`) rather than
    reimplementing custom-function dispatch: the recipe's `expr` is the
    exact CompValue node pulled from the algebra tree, already wired to the
    real, already-registered custom function implementations via rdflib's
    own Function() evalfn - evaluating it here runs the identical code path
    evalExtend would have used locally, just against a QueryContext built
    from the returned row instead of a live join.
    """
    from rdflib.plugins.sparql.evaluate import _eval
    from rdflib.plugins.sparql.sparql import FrozenBindings, QueryContext, SPARQLError

    bindings = dict(row)
    qctx = QueryContext(graph=graph)
    for var, expr in recipes:
        fb = FrozenBindings(qctx, bindings)
        try:
            value = _eval(expr, fb)
            # _eval() itself raises for a genuinely unbound dependency
            # (NotBoundError, a SPARQLError subclass); a caught SPARQLError
            # returned rather than raised (e.g. from evaluating a nested
            # Expr) is the same "leave it unbound" signal evalExtend acts on.
            if isinstance(value, SPARQLError):
                continue
        except SPARQLError:
            continue
        bindings[var] = value
    return bindings


def row_passes_filters(filters: list[Any], bindings: dict, graph: Any) -> bool:
    """Re-check each stripped filter expression (see `decompose_for_remote`)
    against `bindings` (the row *after* `evaluate_recipes_locally` has
    merged in every recipe's computed value, so a filter depending on one
    of those - not just on an ordinary matched variable - sees it too),
    mirroring SPARQL FILTER's own semantics: the row is excluded if any
    expression is false or raises, not just if it's literally ``False``
    (a filter's own "effective boolean value" coercion - `EBV` - already
    handles truthy non-boolean results the same way a real FILTER would).
    """
    from rdflib.plugins.sparql.evaluate import _eval
    from rdflib.plugins.sparql.operators import EBV
    from rdflib.plugins.sparql.sparql import FrozenBindings, QueryContext, SPARQLError

    if not filters:
        return True
    qctx = QueryContext(graph=graph)
    fb = FrozenBindings(qctx, bindings)
    for expr in filters:
        try:
            value = _eval(expr, fb)
            if isinstance(value, SPARQLError) or not EBV(value):
                return False
        except SPARQLError:
            return False
    return True
