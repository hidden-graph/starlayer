"""Targeted compatibility shims for the in-memory backend's SPARQL
*evaluator* (``rdflib.plugins.sparql.evaluate``/``operators``) - not the
algebra translator (see ``algebra_translator_patches.py`` for those) and not
the arithmetic/numeric-function evaluation bugs (see
``operator_patches.py``).

Two different categories of shim live here:

1. ``patch_evalextend_forgotten_bind_vars``/``patch_construct_skips_encoding_solutions``
   fix confirmed bugs in *plain rdflib itself* (see
   ``docs/rdflib-upstream-issues.md`` issue 5 for the first). This is the
   most important category to have applied correctly: unlike the
   algebra-translator bugs (which fail loudly, with a ``ParseException`` or
   similar on the malformed regenerated text) and the arithmetic bugs
   (wrong but well-formed output), these silently produce wrong query
   *results* with no error or warning at all.

2. ``patch_relational_expression_tt_hash_equality`` is a different kind of
   thing - not a plain-rdflib bug (rdflib's own ``=``/``!=`` behavior is
   entirely correct for the plain ``URIRef``s it's actually given), but a
   necessary complement to this library's own in-memory tt:HASH encoding:
   a triple term is stored as an opaque, content-addressed URIRef, which
   hides the RDF 1.2 value-equality semantics (recursing into components,
   applying numeric/etc value equality per SPARQL's own literal-equality
   rules) that a real triple-term-aware engine (Oxigraph, Fuseki) already
   gives for free. See its own docstring below for the full detail.

Same idempotent apply-once pattern as ``operator_patches.py``/
``algebra_translator_patches.py``.
"""

from __future__ import annotations

from rdflib import Literal, URIRef, Variable
from rdflib.namespace import RDF
from rdflib.plugins.sparql import evaluate
from rdflib.plugins.sparql.parserutils import CompValue
from rdflib.plugins.sparql.sparql import SPARQLError

_evaluate_patch_status: bool | None = None


def _expr_free_vars(expr) -> set:
    """The set of variables ``expr`` itself references - a genuine
    recursive structural walk, *not* a lookup into the ``_vars``
    bookkeeping rdflib's own ``_addVars`` pass computes.

    An earlier version of this function *did* just read ``expr``'s own
    ``_vars`` (rdflib's ``algebra.py``, run once during ``translateQuery``)
    as a shortcut, on the assumption that it already reflects exactly this
    set. That assumption is confirmed wrong for a ``RelationalExpression``
    specifically (``FILTER(?x = ?o)``'s own algebra shape): reproduced
    directly against plain, unpatched rdflib -
    ``prepareQuery("SELECT * WHERE { ?s ?p ?x FILTER(?x = ?o) }")`` (``?o``
    appearing *only* in the filter, never in the wrapped pattern) - the
    resulting ``RelationalExpression`` node's own ``_vars`` is an empty
    ``set()`` regardless of which side (``expr`` or ``other``) ``?o`` sits
    on, even though ``?o`` is plainly a free variable of the expression by
    any reasonable definition. ``_addVars``'s handling of comparison
    expressions apparently never populates ``_vars`` for them at all (not
    a one-sided ``other``-only gap, as first suspected - ``expr``-side
    ``?x`` is *also* absent from ``_vars`` here, it just doesn't matter for
    callers of this function since ``?x`` is already visible through the
    wrapped pattern's own ``_vars`` in every real case tested). Confirmed
    via ``starsparql``'s own W3C-suite-driven testing (fixture
    ``graphs-1``): a ``Filter`` built with a ``RelationalExpression``
    comparing an extracted value against a variable bound only by a
    lazy-joined *sibling* pattern (not this ``Filter``'s own wrapped ``p``)
    got that variable silently forgotten by ``evalFilter``'s
    ``c.forget(ctx, _except=part._vars)`` before the comparison ever ran -
    same failure shape as the ``evalExtend`` bug this function was
    originally written for (see ``patch_evalextend_forgotten_bind_vars``),
    just reached through ``FILTER`` instead of ``BIND``, and not covered by
    that patch alone since it only touches ``evalExtend``.

    A structural walk sidesteps needing to know which rdflib expression
    types ``_addVars`` does or doesn't populate correctly - it finds every
    bare ``Variable`` in the tree regardless of which key it's stored
    under, recursing through every ``CompValue``/``list``/``tuple``
    (mirroring ``_traverseAgg``'s own generic traversal shape). Strictly
    more complete than the old ``_vars``-based version for every existing
    caller (``patch_evalextend_forgotten_bind_vars``,
    ``_bind_expr_dependencies``) - no behavior it relied on is lost, only
    gaps like this one are closed.
    """
    found: set = set()

    def walk(node) -> None:
        if isinstance(node, Variable):
            found.add(node)
        elif isinstance(node, CompValue):
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(expr)
    return found


def patch_evalextend_forgotten_bind_vars() -> bool:
    """Fix a confirmed rdflib bug: ``evalExtend`` (``BIND``/``SELECT (expr
    AS ?v)`` evaluation) forgets a variable its own ``expr`` depends on
    before evaluating that ``expr``, whenever that variable isn't *also* a
    pattern variable of the ``Extend`` node's own local ``p`` (e.g. `{
    BIND(?t0 AS ?o) }` with an empty local pattern, where ``?t0`` was bound
    by an *earlier, outer* ``BIND``). The forgotten variable makes ``expr``
    evaluate against an unbound variable, which raises internally and is
    silently swallowed by ``evalExtend``'s own ``except SPARQLError: yield
    c`` - yielding the row with the *target* variable (``?o`` here) left
    completely unbound instead, rather than raising or skipping the row.
    An unbound variable later joined against (e.g. ``?s :p ?o .``) then
    matches *anything*, producing extra, wrong results with no error at
    all. See ``docs/rdflib-upstream-issues.md`` issue 5 for the full
    root-cause trace (down to ``algebra.py``'s ``_addVars`` "Extend" case,
    which the root cause - not just the trigger shape - is confirmed
    against).

    Fix: union in ``expr``'s own free variables (see ``_expr_free_vars``)
    before forgetting, so a variable ``expr`` genuinely depends on is never
    forgotten regardless of whether static analysis attributed it to this
    ``Extend`` node's own ``_vars``. This is the same evaluation
    ``evalExtend`` already performs, unchanged in every other respect -
    only the ``_except`` set passed to ``c.forget(...)`` differs.

    Idempotent and defensive, matching the established
    ``operator_patches.py``/``algebra_translator_patches.py`` idiom -
    returns ``False`` without raising if rdflib's internals don't match
    what this shim expects.
    """
    global _evaluate_patch_status
    if _evaluate_patch_status is not None:
        return _evaluate_patch_status

    try:
        original_eval_extend = evaluate.evalExtend
        if getattr(original_eval_extend, "_starlayergraph_evalextend_patch", False):
            _evaluate_patch_status = True
            return True

        _eval = evaluate._eval
        evalPart = evaluate.evalPart

        def _patched_eval_extend(ctx, extend):
            for c in evalPart(ctx, extend.p):
                try:
                    # extend._vars can genuinely be None, not just "unset
                    # defaulting to an empty set": rdflib's own
                    # translateUpdate never runs the _addVars/analyse pass
                    # at all (confirmed - unlike translateQuery, which
                    # always does), so any Extend node arising from a
                    # SPARQL Update's WHERE-clause processing has no
                    # "_vars" attribute computed whatsoever. `None | a_set`
                    # raises TypeError, so this can't just reuse the
                    # ordinary "attribute defaults to None" CompValue
                    # convention here - confirmed a real, reproducible
                    # crash on Update evaluation when first tried.
                    except_vars = (extend._vars or set()) | _expr_free_vars(extend.expr)
                    e = _eval(extend.expr, c.forget(ctx, _except=except_vars))
                    if isinstance(e, SPARQLError):
                        raise e

                    yield c.merge({extend.var: e})

                except SPARQLError:
                    yield c

        _patched_eval_extend._starlayergraph_evalextend_patch = True  # type: ignore[attr-defined]
        evaluate.evalExtend = _patched_eval_extend
        _evaluate_patch_status = True
    except Exception:
        _evaluate_patch_status = False

    return _evaluate_patch_status


_evalfilter_patch_status: bool | None = None


def patch_evalfilter_forgotten_vars() -> bool:
    """Fix a confirmed rdflib bug: ``evalFilter`` forgets a variable its own
    ``expr`` depends on before evaluating that ``expr``, whenever that
    variable isn't *also* a pattern variable of the ``Filter`` node's own
    local ``p`` - the same root cause and shape as
    ``patch_evalextend_forgotten_bind_vars`` above (``_addVars`` failing to
    populate ``_vars`` for the relevant expression node), reached through
    ``FILTER`` instead of ``BIND``, and *not* covered by that patch since it
    only touches ``evalExtend``.

    Confirmed via a minimal, standalone plain-rdflib reproduction (no
    starlayergraph/starsparql code involved) - see ``_expr_free_vars``'s
    own docstring for the exact repro: a ``RelationalExpression`` comparing
    a variable that's free in the filter but not in the wrapped pattern
    (``FILTER(?x = ?o)`` where ``?o`` never appears in ``p``) gets its own
    ``_vars`` computed as an empty ``set()`` by ``_addVars`` regardless of
    which side of the comparison ``?o`` is on. ``evalFilter``'s
    ``c.forget(ctx, _except=part._vars)`` then drops ``?o`` before ``_ebv``
    ever evaluates the expression, making the comparison see an unbound
    variable - which ``_ebv``/the underlying relational-expression operator
    treats as an error, so the filter evaluates false for *every* row
    regardless of ``?o``'s real (outer) value, silently emptying the
    result with no error at all. Found via ``starsparql``'s own W3C
    test suite (fixture ``graphs-1``): a value extracted from a
    lazily-joined ``GRAPH`` pattern, compared against a variable bound only
    by the *other* (sibling) branch of that join, needs exactly this shape
    to work correctly - see that project's ``lower_rdf11.py``
    ``_add_single_constraint`` for the query-construction side of the same
    finding.

    Fix: identical strategy to the ``Extend`` patch - union in ``expr``'s
    own free variables (the corrected, structural ``_expr_free_vars``, not
    a re-trust of ``_vars``) before forgetting. Unchanged in every other
    respect from rdflib's own ``evalFilter``.

    Same idempotent apply-once pattern as the other patches in this module.
    """
    global _evalfilter_patch_status
    if _evalfilter_patch_status is not None:
        return _evalfilter_patch_status

    try:
        original_eval_filter = evaluate.evalFilter
        if getattr(original_eval_filter, "_starlayergraph_evalfilter_patch", False):
            _evalfilter_patch_status = True
            return True

        _ebv = evaluate._ebv
        evalPart = evaluate.evalPart

        def _patched_eval_filter(ctx, part):
            except_vars = (part._vars or set()) | _expr_free_vars(part.expr)
            for c in evalPart(ctx, part.p):
                if _ebv(
                    part.expr,
                    c.forget(ctx, _except=except_vars) if not part.no_isolated_scope else c,
                ):
                    yield c

        _patched_eval_filter._starlayergraph_evalfilter_patch = True  # type: ignore[attr-defined]
        evaluate.evalFilter = _patched_eval_filter
        _evalfilter_patch_status = True
    except Exception:
        _evalfilter_patch_status = False

    return _evalfilter_patch_status


_evalmodify_patch_status: bool | None = None


def patch_evalmodify_default_graph_selection() -> bool:
    """Fix a confirmed bug in plain rdflib's own ``evalModify``
    (``rdflib.plugins.sparql.update``, a different module from
    ``evaluate`` - not covered by anything above): it writes DELETE/INSERT
    changes to ``ctx.dataset.default_context`` whenever ``ctx.graph``
    isn't *exactly* a bare ``rdflib.graph.Graph`` instance (its own source
    comment even flags this as fragile: "weird type checking logic ... once
    ConjunctiveGraph is removed and Dataset no longer inherits from
    Graph") - rather than ``ctx.graph`` itself, which is what its sibling
    function ``evalDeleteWhere`` uses unconditionally, and what turns out
    to be the only one of the two that works correctly against this
    library's own in-memory backend.

    Confirmed via direct, minimal reproduction (no ``starsparql``
    code involved): ``ctx.dataset.default_context`` and ``ctx.graph`` are
    two *different* Python objects for a ``StarLayerDataset`` (the former
    a plain ``rdflib.graph.Graph`` wrapper, the latter the real
    ``StarLayerDataset``/``StarLayerGraph`` instance with its own
    triple-term-aware ``add``/``remove``/``triples`` overrides) - for an
    *ordinary* triple this doesn't matter (both wrappers share the same
    underlying ``Store``, so removal reaches it either way), but for a
    triple whose subject/object is a native ``TripleTerm`` value, only the
    real ``StarLayerDataset``/``StarLayerGraph`` object correctly
    translates it to/from this library's internal encoding - going through
    the generic ``default_context`` wrapper silently fails to remove or
    insert the triple at all, with no error. Found via
    ``starsparql``'s own `DeleteWhere`->`Modify` rewrite for a
    non-ground triple-term pattern (`DELETE WHERE { ?r rdf:reifies
    <<( ?s :b :c )>> }`): the WHERE clause matched the correct rows, but
    nothing was actually deleted - traced down to this exact line, not a
    bug in that project's own lowering.

    Fix: use ``ctx.graph`` unconditionally, dropping the
    ``type(ctx.graph) is Graph`` check and the ``default_context``
    fallback entirely - safe for the `WITH`/`USING` cases too, since
    ``evalModify`` already reassigns ``ctx`` (via ``ctx.pushGraph(...)``)
    to reflect either clause *before* this line runs, so ``ctx.graph`` is
    already correct in every case, exactly mirroring what
    ``evalDeleteWhere``'s own simpler `g = ctx.graph` already does
    unconditionally.

    Same idempotent apply-once pattern as the other patches in this
    module.
    """
    global _evalmodify_patch_status
    if _evalmodify_patch_status is not None:
        return _evalmodify_patch_status

    try:
        from rdflib.plugins.sparql import update as update_module

        original_eval_modify = update_module.evalModify
        if getattr(original_eval_modify, "_starlayergraph_evalmodify_patch", False):
            _evalmodify_patch_status = True
            return True

        evalPart = evaluate.evalPart
        _fillTemplate = update_module._fillTemplate

        def _patched_eval_modify(ctx, u):
            originalctx = ctx

            if u.using:
                otherDefault = False
                for d in u.using:
                    if d.default:
                        if not otherDefault:
                            from rdflib import Graph

                            ctx = ctx.pushGraph(Graph())
                            otherDefault = True
                        ctx.load(d.default, default=True)
                    elif d.named:
                        ctx.load(d.named, default=False)

            if not u.using and u.withClause:
                g = ctx.dataset.get_context(u.withClause)
                ctx = ctx.pushGraph(g)

            res = evalPart(ctx, u.where)

            if u.using:
                if otherDefault:
                    ctx = originalctx
                if u.withClause:
                    g = ctx.dataset.get_context(u.withClause)
                    ctx = ctx.pushGraph(g)

            for c in list(res):
                dg = ctx.graph
                if u.delete:
                    # Explicit per-triple .remove() calls, not `dg -=
                    # _fillTemplate(...)`: ConjunctiveGraph.__isub__ (which
                    # `dg` resolves to whenever it's a genuine
                    # Dataset/StarLayerDataset, not a plain Graph -
                    # confirmed by reading its source) expects `other` to
                    # already be *quads* (4-tuples), unlike
                    # Graph.__isub__'s own triple-based (3-tuple) contract
                    # - `_fillTemplate` always yields plain triples, so `-=`
                    # here would try to unpack each as 4 values.
                    # `.remove()` has no such divergence between the two
                    # graph types, and is what Graph.__isub__ itself calls
                    # in a loop internally anyway - functionally identical
                    # for a plain Graph, and correct (rather than crashing)
                    # for a Dataset too.
                    for triple in _fillTemplate(u.delete.triples, c):
                        dg.remove(triple)
                    for g, q in u.delete.quads.items():
                        cg = ctx.dataset.get_context(c.get(g))
                        cg -= _fillTemplate(q, c)

                if u.insert:
                    # Same reasoning as the delete branch above, mirrored
                    # for Graph.__iadd__/.add().
                    for triple in _fillTemplate(u.insert.triples, c):
                        dg.add(triple)
                    for g, q in u.insert.quads.items():
                        cg = ctx.dataset.get_context(c.get(g))
                        cg += _fillTemplate(q, c)

        _patched_eval_modify._starlayergraph_evalmodify_patch = True  # type: ignore[attr-defined]
        update_module.evalModify = _patched_eval_modify
        _evalmodify_patch_status = True
    except Exception:
        _evalmodify_patch_status = False

    return _evalmodify_patch_status


_evalinsertdata_patch_status: bool | None = None


def patch_evalinsertdata_quad_unpacking() -> bool:
    """Fix a confirmed bug in plain rdflib's own ``evalInsertData``
    (``rdflib.plugins.sparql.update``): ``g = ctx.graph; g += u.triples``
    assumes ``+=`` accepts a plain iterable of triples, which is true for a
    bare ``rdflib.graph.Graph`` (``Graph.__iadd__`` wraps each ``(s, p, o)``
    with ``self`` itself before calling ``addN``) but not for a genuine
    ``Dataset``/``ConjunctiveGraph`` (``ctx.graph`` for a
    ``StarLayerDataset``'s default-graph ``INSERT DATA``, with no `WITH`/
    `GRAPH` clause) - its own ``__iadd__`` override expects ``other`` to
    already *be* quads (4-tuples), so unpacking each plain 3-tuple triple
    from ``u.triples`` as ``s, p, o, g`` raises ``ValueError: not enough
    values to unpack (expected 4, got 3)``.

    Confirmed via direct, minimal reproduction (no ``starsparql`` code
    involved): ``StarLayerDataset().update("INSERT DATA { ... }")`` with
    zero triple terms anywhere raises this exact error - not specific to
    RDF 1.2 at all, a plain SPARQL 1.1 `INSERT DATA` against any
    ``Dataset``-shaped default graph.

    Asymmetric with `DELETE DATA`, confirmed by reading both:
    ``evalDeleteData``'s ``g -= u.triples`` hits ``Graph.__isub__``, which
    loops and calls ``self.remove(triple)`` per plain triple regardless of
    graph type (no quad-only override exists for ``-=`` the way there is
    for ``+=``) - so only ``evalInsertData`` needs this fix, confirmed by
    reproduction that ``DELETE DATA`` already works correctly against a
    ``StarLayerDataset`` without it.

    Fix: explicit per-triple ``.add()`` calls instead of ``+=`` - the exact
    same fix ``patch_evalmodify_default_graph_selection`` above already
    established for `evalModify`'s own identical `.insert`/`.delete`
    quad-vs-triple mismatch, applied here to `INSERT DATA`'s simpler,
    unconditional-default-graph case. Functionally identical to what
    ``Graph.__iadd__`` already does internally for a plain ``Graph``, and
    correct (rather than crashing) for a ``Dataset``/``StarLayerDataset``.

    Same idempotent apply-once pattern as the other patches in this module.
    """
    global _evalinsertdata_patch_status
    if _evalinsertdata_patch_status is not None:
        return _evalinsertdata_patch_status

    try:
        from rdflib.plugins.sparql import update as update_module

        original_eval_insert_data = update_module.evalInsertData
        if getattr(original_eval_insert_data, "_starlayergraph_evalinsertdata_patch", False):
            _evalinsertdata_patch_status = True
            return True

        def _patched_eval_insert_data(ctx, u):
            g = ctx.graph
            for triple in u.triples:
                g.add(triple)
            for graph_id in u.quads:
                cg = ctx.dataset.get_context(graph_id)
                cg += u.quads[graph_id]

        _patched_eval_insert_data._starlayergraph_evalinsertdata_patch = True  # type: ignore[attr-defined]
        update_module.evalInsertData = _patched_eval_insert_data
        _evalinsertdata_patch_status = True
    except Exception:
        _evalinsertdata_patch_status = False

    return _evalinsertdata_patch_status


# ---------------------------------------------------------------------------
# Lazy-join evaluation order - a second, distinct manifestation of the same
# root cause as issue 5 (`_addVars`'s "Extend" case deliberately excluding
# expr-only variables from `_vars`), this time affecting `evalJoin`/
# `evalLazyJoin` rather than `evalExtend` itself.
# ---------------------------------------------------------------------------

_lazy_join_patch_status: bool | None = None


def _bind_expr_dependencies(node) -> set:
    """The set of variables some ``Extend`` (``BIND``) node *anywhere* in
    `node`'s subtree references in its own expression - a conservative,
    over-inclusive approximation of what this subtree actually needs bound
    before it can evaluate correctly, as opposed to what it's statically
    attributed as *producing* (`node`'s own ``_vars``, which - per
    ``_addVars``'s "Extend" case - deliberately excludes exactly these
    variables). Recurses into every ``CompValue``/``list``/``tuple`` found,
    mirroring ``_traverseAgg``'s own generic traversal shape.
    """
    found: set = set()

    def walk(n):
        if isinstance(n, CompValue):
            if n.name == "Extend":
                found.update(_expr_free_vars(dict.get(n, "expr")))
            for v in n.values():
                walk(v)
        elif isinstance(n, (list, tuple)):
            for item in n:
                walk(item)

    walk(node)
    return found


def patch_lazy_join_expr_dependency_order() -> bool:
    """Fix a confirmed bug in plain rdflib's own ``evalLazyJoin``: it always
    evaluates a ``Join``'s left branch (``join.p1``) first, then pushes its
    bindings into evaluating the right branch (``join.p2``) - an
    optimization that assumes ``p1`` never depends on a variable only
    ``p2`` provides. That assumption can be wrong, and rdflib has no check
    for it: a ``BIND`` inside ``p1`` whose own expression references a
    variable that's only ever bound inside ``p2`` evaluates with that
    variable unbound (``p1`` runs first, before ``p2`` has bound anything),
    silently yields with ``p1``'s own ``Extend`` variable left unbound too
    (``evalExtend`` swallows the resulting ``SPARQLError``), and the
    mistake propagates through the join and any ``FILTER`` referencing that
    variable, silently emptying the result with no error at all.

    Confirmed via a minimal, standalone plain-rdflib reproduction (no
    starlayergraph/starsparql code involved)::

        SELECT ?t{FILTER(?a0 = 1) { BIND(?t + 0 AS ?a0) { BIND(1 AS ?t) } }}

    should return ``?t = 1`` (the ``FILTER`` sees ``?a0 = 1`` since
    ``?t = 1``) but returns empty against plain, unpatched rdflib - even
    with ``patch_evalextend_forgotten_bind_vars`` above already applied,
    which fixes a related but distinct bug (``evalExtend`` forgetting a
    variable *within its own* evaluation) - this one is about *join
    ordering*, a different rdflib function, not covered by that fix.
    Same root cause underneath both, though: ``_addVars``'s "Extend" case
    excludes a ``BIND``'s own expression-only variables from ``_vars`` (by
    design, for computing what a node's result rows actually contain) -
    which also means the join-ordering logic that reads ``_vars`` to decide
    "can I skip pushing bindings, is order-independent lazy evaluation
    safe" has no way to see this specific kind of cross-branch dependency.

    Fix: before evaluating a lazy join's branches in rdflib's own default
    order, check whether ``p1`` actually depends (via
    ``_bind_expr_dependencies``, which - unlike ``_vars`` - does see
    expression-only variables) on anything only ``p2`` provides
    (``p2``'s own, correctly-computed ``_vars``) and isn't already bound in
    the incoming context. If so, swap: evaluate ``p2`` first and push its
    bindings into ``p1``, exactly mirroring rdflib's own existing
    ``evalLazyJoin`` logic, just with the two sides reversed. The ordinary,
    overwhelmingly common case (neither side has this dependency) is
    unaffected - falls through to rdflib's own unmodified, unswapped
    behavior.

    Idempotent and defensive, matching the established
    ``operator_patches.py``/``algebra_translator_patches.py`` idiom -
    returns ``False`` without raising if rdflib's internals don't match
    what this shim expects.
    """
    global _lazy_join_patch_status
    if _lazy_join_patch_status is not None:
        return _lazy_join_patch_status

    try:
        original_eval_join = evaluate.evalJoin
        if getattr(original_eval_join, "_starlayergraph_lazy_join_patch", False):
            _lazy_join_patch_status = True
            return True

        evalPart = evaluate.evalPart

        def _lazy_join(ctx, p_first, p_second):
            for a in evalPart(ctx, p_first):
                c = ctx.thaw(a)
                for b in evalPart(c, p_second):
                    yield b.merge(a)

        def _patched_eval_join(ctx, join):
            if not join.lazy:
                a = evalPart(ctx, join.p1)
                b = set(evalPart(ctx, join.p2))
                from rdflib.plugins.sparql.evaluate import _join

                return _join(a, b)

            p1_needs = _bind_expr_dependencies(join.p1)
            p2_provides = dict.get(join.p2, "_vars") or set()
            already_bound = set(ctx.bindings.keys()) if ctx.bindings else set()
            if p1_needs & p2_provides - already_bound:
                # p1 depends on a variable only p2 provides - rdflib's own
                # default order (p1 first) would evaluate it unbound. Swap.
                return _lazy_join(ctx, join.p2, join.p1)

            return _lazy_join(ctx, join.p1, join.p2)

        _patched_eval_join._starlayergraph_lazy_join_patch = True  # type: ignore[attr-defined]
        evaluate.evalJoin = _patched_eval_join
        _lazy_join_patch_status = True
    except Exception:
        _lazy_join_patch_status = False

    return _lazy_join_patch_status


_construct_patch_status: bool | None = None


def patch_construct_skips_encoding_solutions() -> bool:
    """Fix a real, general gap (not an rdflib bug - a starlayergraph-side one):
    ``StarLayerGraph.query()``/``StarLayerDataset.query()`` execute the
    rewritten SPARQL 1.1 text against a *raw*, unfiltered view of the
    underlying store (``raw = Graph(store=self.store, ...)`` in
    ``starlayer_graph.py``) - deliberately, since triple-term pattern
    rewriting (``sparql12_to_11.py``) needs to match the internal
    ``rdf:subject``/``rdf:predicate``/``rdf:object`` encoding triples
    directly. An *unconstrained* pattern like a bare ``?s ?p ?o .`` matches
    those internal triples too, alongside ordinary user-visible ones.

    For SELECT, ``starlayergraph.model.encoding.restore_select_bindings`` already
    drops any result row that incidentally matched these internal triples
    (a TT_NS-prefixed URIRef paired with an encoding predicate as a bound
    *value* - never something a real query result should surface). CONSTRUCT
    has no equivalent: rdflib's own ``evalConstructQuery`` iterates WHERE
    solutions and instantiates the template for every one, with no per-
    solution filtering hook. Confirmed via two real W3C SPARQL 1.2 test
    fixtures (construct-3, expr-1), both using an unconstrained ``?s ?p ?o``
    inside a CONSTRUCT/GRAPH block over data that already contains
    reification/triple-term encoding triples: the template silently wrapped
    an internal row (e.g. ``tt:HASH rdf:subject :a``) into a bogus *nested*
    triple term, which then crashed downstream in
    ``StarLayerGraph.from_rdflib``/``_restore`` with "the subject of a
    triple term must be an IRI or blank node, not a triple term" - not a
    query-authoring mistake, a leak of storage internals into CONSTRUCT
    output that should never have been visible in the first place.

    Fix: the same skip-check ``restore_select_bindings`` already applies to
    SELECT rows, applied here per-solution before templating instead of
    per-output-row after.
    """
    global _construct_patch_status
    if _construct_patch_status is not None:
        return _construct_patch_status

    try:
        original_eval_construct = evaluate.evalConstructQuery
        if getattr(original_eval_construct, "_starlayergraph_construct_patch", False):
            _construct_patch_status = True
            return True

        from rdflib import Graph, URIRef

        from starlayergraph.model.encoding import ENCODING_PREDS, TT_NS

        evalPart = evaluate.evalPart
        _fillTemplate = evaluate._fillTemplate

        def _is_encoding_solution(c) -> bool:
            values = list(c.values())
            return (
                any(isinstance(v, URIRef) and str(v).startswith(TT_NS) for v in values)
                and bool(ENCODING_PREDS.intersection(values))
            )

        def _patched_eval_construct_query(ctx, query):
            template = query.template
            if not template:
                # a construct-where query
                template = query.p.p.triples  # query->project->bgp ...

            graph = Graph()
            for c in evalPart(ctx, query.p):
                if _is_encoding_solution(c):
                    continue
                graph += _fillTemplate(template, c)

            return {"type_": "CONSTRUCT", "graph": graph}

        _patched_eval_construct_query._starlayergraph_construct_patch = True  # type: ignore[attr-defined]
        evaluate.evalConstructQuery = _patched_eval_construct_query
        _construct_patch_status = True
    except Exception:
        _construct_patch_status = False

    return _construct_patch_status


# ---------------------------------------------------------------------------
# tt:HASH-aware `=`/`!=` - restores RDF 1.2 triple-term value-equality for
# the in-memory backend specifically.
# ---------------------------------------------------------------------------

_relational_expression_patch_status: bool | None = None


def _decode_tt_hash(graph, node):
    """Decode `node` (a tt:HASH URIRef) into its raw (subject, predicate,
    object) encoding triples, read directly from `graph`. Returns None for
    anything that isn't a tt:HASH URIRef with encoding triples present in
    `graph`.

    Deliberately *not* recursive - `subject`/`object` are returned exactly
    as read (which may themselves be a nested tt:HASH URIRef, or may not),
    never pre-decoded into a tuple here. `_tt_aware_eq` is what recurses,
    by calling this function again on each component it compares - keeping
    every value this function ever returns a single, consistent shape (an
    rdflib term, never a tuple) is what makes that recursion correct;
    pre-decoding a nested component here produced a tuple one level too
    early, which `_tt_aware_eq`'s own recursive call then couldn't
    re-decode (`isinstance(node, URIRef)` is false for a tuple), silently
    falling through to `a.eq(b)` on two raw tuples and crashing - confirmed
    a real bug this way, not a hypothetical, via the W3C `op-2` fixture's
    own nested-triple-term case.

    Deliberately reads the *graph's own* rdf:subject/predicate/object
    triples rather than a `StarLayerGraph._tt_nodes` Python-side registry:
    the graph object seen during query evaluation (`ctx.graph`) is a bare
    `rdflib.Graph` view over the same store (see
    `StarLayerGraph.query()` - `raw = Graph(store=self.store, ...)`), not
    the `StarLayerGraph` instance itself, so `_tt_nodes` isn't reachable
    from here. Reading the on-store encoding triples directly works
    identically to (and is the same technique as) `StarLayerGraph.
    _build_registry_from_store()`'s own reconstruction.
    """
    from starlayergraph.model.encoding import TT_NS

    if not (isinstance(node, URIRef) and str(node).startswith(TT_NS)):
        return None
    s = graph.value(node, RDF.subject)
    p = graph.value(node, RDF.predicate)
    o = graph.value(node, RDF.object)
    if s is None or p is None or o is None:
        return None
    return (s, p, o)


def _tt_aware_eq(graph, a, b) -> bool:
    """RDF 1.2 term-equality between `a`/`b`: decode either side that's a
    tt:HASH URIRef into its (subject, predicate, object) components first,
    recursing - restores the value-equality semantics the opaque encoding
    otherwise hides (e.g. ``TRIPLE(:a,:b,123) = TRIPLE(:a,:b,123.0)`` must
    be true - numeric value equality on the differing object - despite the
    two encoded tt:HASH URIs being different, unrelated strings, since the
    hash is computed from *lexical* form - see
    ``starlayergraph/model/encoding.py::tt_hash``).

    Falls through to plain ``Identifier.eq()`` - which already correctly
    implements SPARQL's own literal value-equality (numeric/date/etc,
    per-datatype) - for any component that isn't itself a tt:HASH URIRef on
    either side, so this only adds recursion where the opaque encoding
    would otherwise have masked it; ordinary IRI/BNode/Literal comparisons
    are unaffected.
    """
    da = _decode_tt_hash(graph, a)
    db = _decode_tt_hash(graph, b)
    if da is None and db is None:
        return a.eq(b)
    if da is None or db is None:
        return False  # one side is a triple term, the other isn't - never equal
    return (
        _tt_aware_eq(graph, da[0], db[0])
        and da[1].eq(db[1])  # predicate is never itself a triple term (RDF 1.2)
        and _tt_aware_eq(graph, da[2], db[2])
    )


def _looks_like_tt_hash(node) -> bool:
    from starlayergraph.model.encoding import TT_NS

    return isinstance(node, URIRef) and str(node).startswith(TT_NS)


def patch_relational_expression_tt_hash_equality() -> bool:
    """Patch ``RelationalExpression`` (the ``=``/``!=``/``<``/etc. FILTER
    comparison grammar production) so that ``=``/``!=`` between two tt:HASH
    URIRefs (the in-memory backend's opaque, content-addressed encoding of
    a triple term) applies real RDF 1.2 value-equality (see
    ``_tt_aware_eq`` above) instead of stock rdflib's plain URIRef string
    equality, which can only ever agree with ``sameTerm`` - never true for
    two triple terms differing only in a component's lexical form (e.g.
    ``123`` vs ``123.0``), which SPARQL's own value-equality rules require.

    Confirmed via the W3C SPARQL 1.2 test suite's own ``eval-triple-terms/
    op-2`` fixture (``FILTER(!sameTerm(?left,?right)) FILTER(?left =
    ?right)`` over two triple terms differing only in a literal's lexical
    form) - previously an unconditional empty result against the in-memory
    backend; see ``tests/w3c_sparql12/test_w3c_sparql12_eval.py``'s
    (now-removed) ``op-2`` entry in ``_IN_MEMORY_KNOWN_DIVERGENCES``.

    Only intervenes when at least one operand is a tt:HASH URIRef - zero
    behavior change, and negligible overhead (one cheap ``isinstance``/
    prefix check), for the overwhelmingly common case of comparing ordinary
    terms. Falls through to the original evalfn for ``<``/``>``/``<=``/
    ``>=``/``IN``/``NOT IN`` unconditionally - RDF 1.2 doesn't define an
    ordering over triple terms the way it does over term *kinds* for
    ``ORDER BY`` (a separate, harder gap - see
    ``_IN_MEMORY_KNOWN_DIVERGENCES``'s ``order-1``/``order-2`` entries,
    not attempted here), so widening this patch to those operators isn't
    attempted.

    Idempotent and defensive, matching the established
    ``operator_patches.py``/``algebra_translator_patches.py`` idiom -
    returns ``False`` without raising if rdflib's internals don't match
    what this shim expects.
    """
    global _relational_expression_patch_status
    if _relational_expression_patch_status is not None:
        return _relational_expression_patch_status

    try:
        from rdflib.plugins.sparql import parser as rdflib_sparql_parser

        comp = rdflib_sparql_parser.RelationalExpression
        original_evalfn = comp.evalfn
        if getattr(original_evalfn, "_starlayergraph_tt_hash_equality_patch", False):
            _relational_expression_patch_status = True
            return True

        def _patched_relational_expression(e, ctx):
            if e.op in ("=", "!="):
                expr_val = e.expr
                other_val = e.other
                if (
                    other_val is not None
                    and not isinstance(other_val, list)
                    and (_looks_like_tt_hash(expr_val) or _looks_like_tt_hash(other_val))
                ):
                    graph = getattr(ctx, "graph", None) or getattr(getattr(ctx, "ctx", None), "graph", None)
                    if graph is not None:
                        result = _tt_aware_eq(graph, expr_val, other_val)
                        return Literal(result if e.op == "=" else not result)
            return original_evalfn(e, ctx)

        _patched_relational_expression._starlayergraph_tt_hash_equality_patch = True  # type: ignore[attr-defined]
        comp.setEvalFn(_patched_relational_expression)
        _relational_expression_patch_status = True
    except Exception:
        _relational_expression_patch_status = False

    return _relational_expression_patch_status


# ---------------------------------------------------------------------------
# tt:HASH-aware ORDER BY - restores RDF 1.2 term-kind ordering for the
# in-memory backend specifically.
# ---------------------------------------------------------------------------

_order_by_patch_status: bool | None = None


def _tt_aware_sort_key(graph, v):
    """RDF 1.2 term-kind-aware ORDER BY sort key for `v` - unbound < blank
    node < IRI < literal < triple term, matching stock rdflib's own
    ``evaluate._val`` bucketing exactly for every kind *except* triple
    terms, which stock rdflib has no bucket for at all (a tt:HASH URIRef
    sorts as bucket 2, indistinguishable from an ordinary IRI, since rdflib
    predates RDF 1.2 triple terms entirely).

    A tt:HASH URIRef gets its own bucket (4, after literal) and, within
    that bucket, is ordered by its own (subject, predicate, object) -
    recursively applying this same function to each component (predicate
    is always a plain IRI - RDF 1.2 forbids it being a triple term - but
    object may itself be a nested tt:HASH URIRef, needing the same
    recursive bucketing again). Confirmed against the W3C SPARQL 1.2
    eval-triple-terms/order-2 fixture's own expected order, which requires
    exactly this: subject-then-predicate-then-object, each individually
    term-kind-bucketed - not e.g. a flat hash/string comparison.

    Every non-triple-term bucket's second tuple element is deliberately
    kept exactly what stock ``_val`` would use (raw ``Literal`` for the
    literal bucket, so ``Literal.__lt__``'s own value-aware numeric/date/etc
    comparison still applies unchanged; ``str(v)`` for BNode/IRI, matching
    plain string comparison, since neither overrides ``__lt__`` specially)
    - this patch only ever *adds* the missing triple-term bucket, never
    changes how any other kind compares against its own kind.
    """
    from rdflib import BNode, Literal, URIRef, Variable

    if isinstance(v, Variable):
        return (0, "")
    if isinstance(v, BNode):
        return (1, str(v))
    if isinstance(v, URIRef):
        decoded = _decode_tt_hash(graph, v)
        if decoded is not None:
            s, p, o = decoded
            return (
                4,
                (
                    _tt_aware_sort_key(graph, s),
                    _tt_aware_sort_key(graph, p),
                    _tt_aware_sort_key(graph, o),
                ),
            )
        return (2, str(v))
    if isinstance(v, Literal):
        return (3, v)
    return (5, str(v))


def patch_order_by_tt_hash_term_kind() -> bool:
    """Patch ``evalOrderBy`` so a tt:HASH URIRef (the in-memory backend's
    opaque, content-addressed encoding of a triple term) sorts in its own,
    RDF-1.2-mandated term-kind bucket - after literals - instead of stock
    rdflib's ``_val``, which has no bucket for triple terms at all (rdflib
    predates RDF 1.2) and so sorts it as an ordinary IRI, intermixed with
    real IRIs. See ``_tt_aware_sort_key`` above for the full detail.

    Confirmed via the W3C SPARQL 1.2 test suite's own ``eval-triple-terms/
    order-1``/``order-2`` fixtures (``ORDER BY`` across mixed blank-node/
    IRI/literal/triple-term values, several distinct triple terms in
    ``order-2`` specifically) - previously wrong ordering against the
    in-memory backend; see ``tests/w3c_sparql12/test_w3c_sparql12_eval.py``'s
    (now-removed) ``order-1``/``order-2`` entries in
    ``_IN_MEMORY_KNOWN_DIVERGENCES``.

    ``_val`` itself is used exactly once in stock rdflib
    (``rdflib.plugins.sparql.evaluate``, inside ``evalOrderBy`` only) -
    confirmed by inspection, not assumed - so replacing ``evalOrderBy``
    wholesale (rather than trying to patch ``_val`` in place, which has no
    way to reach the graph a raw value needs decoding against) is safe and
    complete; no other code path depends on ``_val``'s own bucketing.

    Idempotent and defensive, matching the established
    ``operator_patches.py``/``algebra_translator_patches.py`` idiom -
    returns ``False`` without raising if rdflib's internals don't match
    what this shim expects.
    """
    global _order_by_patch_status
    if _order_by_patch_status is not None:
        return _order_by_patch_status

    try:
        original_eval_order_by = evaluate.evalOrderBy
        if getattr(original_eval_order_by, "_starlayergraph_order_by_patch", False):
            _order_by_patch_status = True
            return True

        evalPart = evaluate.evalPart

        def _patched_eval_order_by(ctx, part):
            res = evalPart(ctx, part.p)
            graph = getattr(ctx, "graph", None) or getattr(getattr(ctx, "ctx", None), "graph", None)

            from rdflib.plugins.sparql.evaluate import value

            for e in reversed(part.expr):
                reverse = bool(e.order and e.order == "DESC")
                res = sorted(
                    res,
                    key=lambda x: _tt_aware_sort_key(graph, value(x, e.expr, variables=True)),
                    reverse=reverse,
                )
            return res

        _patched_eval_order_by._starlayergraph_order_by_patch = True  # type: ignore[attr-defined]
        evaluate.evalOrderBy = _patched_eval_order_by
        _order_by_patch_status = True
    except Exception:
        _order_by_patch_status = False

    return _order_by_patch_status


# ---------------------------------------------------------------------------
# BGP-level encoding-triple filtering - a general fix for the in-memory
# backend leaking internal tt:HASH-encoding infrastructure triples through
# an *unconstrained* BGP match specifically, not just CONSTRUCT (see
# patch_construct_skips_encoding_solutions above, which only covers that one
# case).
# ---------------------------------------------------------------------------

_bgp_patch_status: bool | None = None


def patch_bgp_skips_encoding_triples() -> bool:
    """Patch ``evalBGP`` (the core basic-graph-pattern matcher every SPARQL
    query goes through) so it never yields a solution derived from an
    *unconstrained* match against the in-memory backend's own internal
    rdf:subject/predicate/object encoding triples for a tt:HASH URI - the
    same class of leak ``patch_construct_skips_encoding_solutions`` already
    fixes, but that patch only filters at the very end, in
    ``evalConstructQuery`` - any *other* query shape that matches an
    unconstrained ``?s ?p ?o`` (most naturally a nested ``SELECT``
    subquery, but not exclusively) sees these fragments too, with no
    equivalent filter.

    A first version of this patch (filtering *every* BGP match against an
    encoding triple, regardless of whether the pattern's own predicate
    position was already constrained) was tried and reverted: it isn't
    safely generalizable that way - the SPARQL 1.2 -> 1.1 rewriter's own
    generated queries *legitimately* need to match these same triples to
    decode a triple-term pattern containing a variable (e.g.
    ``sparql12_to_11.py``'s own expansion of ``<<:a :b ?o>> ?q :z .`` into
    ``?tt rdf:subject :a . ?tt rdf:predicate :b . ?tt rdf:object ?o . ...``),
    and a filter keyed only on the *matched values* can't tell that apart
    from an accidental wildcard leak - confirmed via a real regression
    (``basic-5``) when first tried.

    The fix: only filter a match where the *pattern's own* predicate
    position was unconstrained (a variable, not yet bound - ``ctx[p] is
    None`` before this triple is matched) - never one where the pattern
    itself already specifies the predicate as a literal
    rdf:subject/predicate/object IRI, which is exactly the shape every
    rewriter-generated decode pattern always uses (a ground predicate,
    never a variable there). This is the precise distinguishing signal the
    first attempt was missing: "did the *query text* ask for this
    predicate specifically" vs "did an unconstrained wildcard happen to
    match it" - not visible from the matched triple's values alone, but
    directly available from the pattern's own (pre-match) term for the
    predicate position.

    Confirmed via the W3C SPARQL 1.2 ``eval-triple-terms/order-1``/
    ``order-2`` fixtures' own query shape (``{ SELECT ?v { ?s ?p ?v }
    ORDER BY ?v OFFSET N LIMIT 1 }``, repeated across 20 ``UNION``
    branches - predicate ``?p`` genuinely unconstrained there) - and,
    separately, that this version does *not* regress ``basic-5`` (predicate
    ``rdf:subject``/etc. always ground in the rewriter's own generated
    pattern there) or any other currently-passing test.

    Idempotent and defensive, matching the established
    ``operator_patches.py``/``algebra_translator_patches.py`` idiom -
    returns ``False`` without raising if rdflib's internals don't match
    what this shim expects.
    """
    global _bgp_patch_status
    if _bgp_patch_status is not None:
        return _bgp_patch_status

    try:
        from rdflib import URIRef
        from rdflib.plugins.sparql.sparql import AlreadyBound

        from starlayergraph.model.encoding import ENCODING_PREDS, TT_NS

        original_eval_bgp = evaluate.evalBGP
        if getattr(original_eval_bgp, "_starlayergraph_bgp_patch", False):
            _bgp_patch_status = True
            return True

        def _is_unconstrained_encoding_leak(pattern_p_was_bound: bool, sp, ss) -> bool:
            if pattern_p_was_bound:
                # The pattern itself already specified this predicate (a
                # ground rdf:subject/predicate/object, or any other already-
                # bound term) - a deliberate, constrained match, never a
                # wildcard leak, regardless of what it matches.
                return False
            return sp in ENCODING_PREDS and isinstance(ss, URIRef) and str(ss).startswith(TT_NS)

        def _patched_eval_bgp(ctx, bgp):
            if not bgp:
                yield ctx.solution()
                return

            s, p, o = bgp[0]
            _s = ctx[s]
            _p = ctx[p]
            _o = ctx[o]
            p_was_bound = _p is not None

            for ss, sp, so in ctx.graph.triples((_s, _p, _o)):
                if _is_unconstrained_encoding_leak(p_was_bound, sp, ss):
                    continue

                if None in (_s, _p, _o):
                    c = ctx.push()
                else:
                    c = ctx

                if _s is None:
                    c[s] = ss

                try:
                    if _p is None:
                        c[p] = sp
                except AlreadyBound:
                    continue

                try:
                    if _o is None:
                        c[o] = so
                except AlreadyBound:
                    continue

                yield from _patched_eval_bgp(c, bgp[1:])

        _patched_eval_bgp._starlayergraph_bgp_patch = True  # type: ignore[attr-defined]
        evaluate.evalBGP = _patched_eval_bgp
        _bgp_patch_status = True
    except Exception:
        _bgp_patch_status = False

    return _bgp_patch_status


# ---------------------------------------------------------------------------
# GROUP BY with an un-aliased, expression-valued grouping key - a genuine
# bug in plain rdflib's own *parse-tree-to-algebra translation*
# (`rdflib.plugins.sparql.algebra.translate`), not its evaluator - patched
# here anyway (not in `algebra_translator_patches.py`, which is about the
# opposite direction, algebra-to-*text*) since this module already hosts
# the other GROUP BY/aggregate-adjacent fixes (issues 5/8) and the
# observable symptom is a query that fails to evaluate. See
# docs/rdflib-upstream-issues.md Issue 9 for the full writeup.
# ---------------------------------------------------------------------------

_group_by_unaliased_key_patch_status: bool | None = None
_group_by_synthetic_var_counter = 0


def patch_group_by_unaliased_expression_key() -> bool:
    """Fix a confirmed bug in plain rdflib's own ``algebra.translate``: a
    parenthesized, *un-aliased* computed ``GROUP BY`` key (``GROUP BY
    (?o+1)``, no ``AS ?var``) - legal per SPARQL 1.1's own grammar
    (``GroupCondition ::= ... | '(' Expression ( 'AS' Var )? ')' | ...``,
    the ``AS Var`` part explicitly optional) - produces an algebra shape
    that later crashes ``evaluate.evalAggregateJoin`` outright
    (``Exception: Cannot eval thing: None``), with **no** RDF 1.2/triple-
    term/``starsparql`` involvement at all. See
    ``docs/rdflib-upstream-issues.md`` Issue 9 for the full root-cause
    trace and a minimal, plain-rdflib reproduction.

    Root cause, confirmed by reading ``algebra.py::translate`` directly:
    for *every* parenthesized-expression ``GROUP BY`` condition (aliased
    or not), the parser produces a ``GroupAs`` node with an ``.expr``, and
    (only for the aliased form) a real ``.var``. ``translate``'s own loop
    (``if isinstance(c, CompValue) and c.name == "GroupAs": M =
    Extend(M, c.expr, c.var); c = c.var``) uses ``c.var`` for *both* the
    ``Extend``'s own bind target *and* the value appended to the
    ``Group.expr`` list that identifies this grouping key later - for the
    un-aliased form, ``c.var`` is ``None`` (the key is genuinely absent
    from the ``GroupAs`` node, not just falsy), so both end up
    ``Extend(var=None)`` and ``Group.expr=[None, ...]``, and neither
    ``evalExtend`` nor ``evalAggregateJoin`` has any handling for a bare
    ``None`` in these positions.

    Fix: rather than trying to patch the two evaluator functions to
    special-case ``None`` after the fact (which would need to correctly
    re-pair each ``None`` in ``Group.expr`` with its corresponding
    ``Extend(var=None)`` - genuinely ambiguous once other, unrelated
    grouping conditions are mixed in, since only some conditions produce
    an ``Extend`` at all), this pre-processes the *parse tree* immediately
    before ``translate`` runs: for any ``GroupAs`` condition missing its
    own ``var``, mint a fresh synthetic ``Variable`` and assign it
    directly onto the parse-tree node (``cond["var"] = synthetic``) -
    confirmed via direct reproduction that ``translate``'s own,
    completely unmodified logic then naturally uses this same synthetic
    variable for *both* the ``Extend`` and the ``Group.expr`` entry, with
    no further changes needed anywhere: the pairing was never actually
    ambiguous at the *parse-tree* level, only after the ``None`` erased
    the connection between the two positions. Mirrors rdflib's own
    ``__agg_N__`` naming convention (used elsewhere in the same function
    for `SAMPLE`'s own synthetic result variables) for the same reason:
    a name unlikely to collide with any real, user-written variable, and
    never projected out (this grouping key was never given a name by the
    query's own author, so it correctly stays invisible in the result set
    either way - confirmed via execution, not just algebra inspection).

    Applies to ``algebra.translate`` (rebinding the module attribute, so
    ``translateQuery``'s own internal call - a same-module global lookup,
    resolved at call time - picks up the wrapped version automatically,
    the same mechanism every other patch in this file already relies on).

    Same idempotent apply-once pattern as the other patches in this module.
    """
    global _group_by_unaliased_key_patch_status
    if _group_by_unaliased_key_patch_status is not None:
        return _group_by_unaliased_key_patch_status

    try:
        from rdflib.plugins.sparql import algebra as algebra_module

        original_translate = algebra_module.translate
        if getattr(original_translate, "_starlayergraph_groupby_patch", False):
            _group_by_unaliased_key_patch_status = True
            return True

        def _fill_in_missing_group_condition_vars(q) -> None:
            groupby = dict.get(q, "groupby")
            if not groupby:
                return
            for cond in dict.get(groupby, "condition") or []:
                if not (isinstance(cond, CompValue) and cond.name == "GroupAs"):
                    continue
                if dict.get(cond, "var") is not None:
                    continue
                global _group_by_synthetic_var_counter
                _group_by_synthetic_var_counter += 1
                cond["var"] = Variable(
                    f"__starlayergraph_groupkey_{_group_by_synthetic_var_counter}__"
                )

        def _patched_translate(q):
            _fill_in_missing_group_condition_vars(q)
            return original_translate(q)

        _patched_translate._starlayergraph_groupby_patch = True  # type: ignore[attr-defined]
        algebra_module.translate = _patched_translate
        _group_by_unaliased_key_patch_status = True
    except Exception:
        _group_by_unaliased_key_patch_status = False

    return _group_by_unaliased_key_patch_status
