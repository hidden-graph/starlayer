"""Monkeypatches for the in-memory backend's SPARQL *evaluator*
(``rdflib.plugins.sparql.evaluate``/``operators``) - not the algebra
translator (see ``algebra_translator_patches.py``) and not the
arithmetic/numeric-function evaluation bugs (see ``operator_patches.py``).

Two categories of shim live here:

1. ``patch_evalextend_forgotten_bind_vars``/``patch_construct_skips_encoding_solutions``
   and most of the others below fix confirmed bugs in *plain rdflib
   itself* (see ``docs/upstream-issues/rdflib-upstream-issues.md`` issue 5 for the first).
   This is the most important category to have applied correctly: unlike
   the algebra-translator bugs (which fail loudly, with a
   ``ParseException`` or similar on the malformed regenerated text) and
   the arithmetic bugs (wrong but well-formed output), these silently
   produce wrong query *results* with no error or warning at all.

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

from rdflib import BNode, Literal, URIRef, Variable
from rdflib.namespace import RDF
from rdflib.plugins.sparql import evaluate
from rdflib.plugins.sparql.parserutils import CompValue


def _expr_free_vars(expr) -> set:
    """The set of variables ``expr`` itself references - a genuine
    recursive structural walk, *not* a lookup into the ``_vars``
    bookkeeping rdflib's own ``_addVars`` pass computes.

    ``_addVars`` never populates ``_vars`` for a ``RelationalExpression``
    node (``FILTER(?x = ?o)``'s own algebra shape) - not a one-sided
    ``other``-only gap either: ``expr``-side ``?x`` is equally absent from
    ``_vars``, it just doesn't matter for callers of this function since
    ``?x`` is already visible through the wrapped pattern's own ``_vars``
    in every real case. Code that trusts ``_vars`` to know what a
    sub-expression depends on therefore misses a real dependency for any
    expression containing a comparison - the same failure shape as the
    ``evalExtend`` bug ``patch_evalextend_forgotten_bind_vars`` fixes,
    reachable through ``FILTER`` as well as ``BIND`` (see
    ``patch_evalfilter_forgotten_vars``).

    A structural walk sidesteps needing to know which rdflib expression
    types ``_addVars`` does or doesn't populate correctly - it finds every
    bare ``Variable`` in the tree regardless of which key it's stored
    under, recursing through every ``CompValue``/``list``/``tuple``
    (mirroring ``_traverseAgg``'s own generic traversal shape). Strictly
    more complete than a ``_vars``-based lookup for every existing caller
    (``patch_evalextend_forgotten_bind_vars``, ``_bind_expr_dependencies``).

    Args:
        expr: The rdflib SPARQL algebra expression node to scan.

    Returns:
        The set of ``Variable`` instances found anywhere in expr's tree.
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


def _inside_exists_evaluation() -> bool:
    """True when the caller is (indirectly) evaluating an ``EXISTS``/``NOT EXISTS`` pattern. SPARQL
    evaluates those by substituting the outer solution into the pattern, so a filter inside one DOES see
    the outer variables; rdflib's evaluation of a lazily joined group looks the same to a filter, so the
    two are told apart by the call stack."""
    import sys

    frame = sys._getframe(2)
    while frame is not None:
        if frame.f_code.co_name in ("Builtin_EXISTS", "Builtin_NOTEXISTS"):
            return True
        frame = frame.f_back
    return False


def _is_lowered_triple_term_filter(expr) -> bool:
    """True when a filter expression was written by the triple-term lowering, not by the user. A pattern
    like ``<<:s :p ?o>>`` is lowered to a pattern variable plus a filter over its parts, which leaves ``?o``
    in the filter only; such a filter must keep seeing ``?o``. Recognized by the internal ``tt:`` functions
    and ``__tt`` variables the lowering uses."""
    from starlayer.graph.model.encoding import TT_NS

    def walk(item) -> bool:
        if isinstance(item, Variable):
            return str(item).startswith("__tt")
        if isinstance(item, CompValue):
            iri = item.get("iri") if item.name == "Function" else None
            if iri is not None and str(iri).startswith(TT_NS):
                return True
            return any(walk(v) for v in item.values())
        if isinstance(item, (list, tuple)):
            return any(walk(v) for v in item)
        return False

    return walk(expr)


def _expr_blank_nodes(expr) -> set:
    """Blank nodes appearing inside a filter expression. The lowering of triple terms writes a query blank
    node into an expression as an operand; it stands for a variable and must stay visible to the filter."""
    found: set = set()

    def walk(item) -> None:
        if isinstance(item, BNode):
            found.add(item)
        elif isinstance(item, CompValue):
            for value in item.values():
                walk(value)
        elif isinstance(item, (list, tuple)):
            for sub in item:
                walk(sub)

    walk(expr)
    return found


def _pattern_scope_vars(node) -> set:
    """The variables a graph pattern can bind (what a ``FILTER`` over it may refer to): every variable in
    its triple patterns, ``BIND`` targets, ``VALUES`` columns and graph terms, a sub-select's projection
    only, and the left side of a ``MINUS`` only. Filter and ``ORDER BY`` expressions are not part of it.
    """
    found: set = set()

    def walk(item) -> None:
        if isinstance(item, (Variable, BNode)):
            # a blank node in a pattern is a variable too (the lowering of triple terms puts them there)
            found.add(item)
        elif isinstance(item, CompValue):
            name = item.name
            if name == "Project":
                found.update(item.PV or [])
                return
            if name == "Minus":
                walk(item.p1)
                return
            for key, value in item.items():
                if key in ("expr", "_vars", "lazy"):
                    continue
                if key == "var":
                    walk(value)
                else:
                    walk(value)
        elif isinstance(item, dict):
            for key, value in item.items():
                walk(key)
                walk(value)
        elif isinstance(item, (list, tuple)):
            for sub in item:
                walk(sub)

    walk(node)
    return found


_evalfilter_patch_status: bool | None = None


def patch_evalfilter_forgotten_vars() -> bool:
    """Fix a confirmed rdflib bug: ``evalFilter`` forgets a variable its own
    ``expr`` depends on before evaluating that ``expr``, whenever that
    variable isn't *also* a pattern variable of the ``Filter`` node's own
    local ``p`` - the same root cause and shape as
    ``patch_evalextend_forgotten_bind_vars`` above (``_addVars`` failing to
    populate ``_vars`` for the relevant expression node), reached through
    ``FILTER`` instead of ``BIND``, and *not* covered by that patch since it
    only touches ``evalExtend``. See ``_expr_free_vars``'s own docstring
    for the underlying mechanism.

    A ``RelationalExpression`` comparing a variable that's free in the
    filter but not in the wrapped pattern (``FILTER(?x = ?o)`` where ``?o``
    never appears in ``p``) gets its own ``_vars`` computed as an empty
    ``set()`` by ``_addVars`` regardless of which side of the comparison
    ``?o`` is on. ``evalFilter``'s ``c.forget(ctx, _except=part._vars)``
    then drops ``?o`` before ``_ebv`` ever evaluates the expression, making
    the comparison see an unbound variable - which ``_ebv``/the underlying
    relational-expression operator treats as an error, so the filter
    evaluates false for *every* row regardless of ``?o``'s real (outer)
    value, silently emptying the result with no error at all. A value
    extracted from a lazily-joined ``GRAPH`` pattern, compared against a
    variable bound only by the *other* (sibling) branch of that join,
    needs exactly this shape to work correctly.

    Fix: identical strategy to the ``Extend`` patch - union in ``expr``'s
    own free variables (the structural ``_expr_free_vars``, not a re-trust
    of ``_vars``) before forgetting. Unchanged in every other respect from
    rdflib's own ``evalFilter``.

    Same idempotent apply-once pattern as the other patches in this module.

    Returns:
        True if the patch applied (or was already applied), False if
        rdflib's internals didn't match what this shim expects.
    """
    global _evalfilter_patch_status
    if _evalfilter_patch_status is not None:
        return _evalfilter_patch_status

    try:
        original_eval_filter = evaluate.evalFilter
        if getattr(original_eval_filter, "_starlayer_graph_evalfilter_patch", False):
            _evalfilter_patch_status = True
            return True

        from rdflib.plugins.sparql.sparql import FrozenBindings

        _ebv = evaluate._ebv
        evalPart = evaluate.evalPart

        def _patched_eval_filter(ctx, part):
            # The filter may see exactly the variables its own group can bind (spec sec 18.2.2.7: a
            # group is evaluated on its own and joined with its siblings afterwards). rdflib hands a
            # lazily joined group the outer solution, so the solution `c` also carries variables bound
            # outside the group, and `forget(ctx, ...)` never removes those (it only drops variables
            # bound since `ctx`). The group's variables are taken from a structural walk of its pattern
            # (rdflib's `_vars` is sometimes incomplete, which an earlier version of this patch worked
            # around by keeping every variable the expression mentions - that let a filter see
            # variables bound OUTSIDE its group), and the expression is evaluated over those only.
            # The solution that is yielded is unchanged.
            scope = _pattern_scope_vars(part.p) | _expr_blank_nodes(part.expr)
            if _is_lowered_triple_term_filter(part.expr) or _inside_exists_evaluation():
                scope |= _expr_free_vars(part.expr)
            for c in evalPart(ctx, part.p):
                if part.no_isolated_scope:
                    visible = c
                else:
                    visible = FrozenBindings(
                        c.ctx, ((k, v) for k, v in c.items() if k in scope or k in c.ctx.initBindings)
                    )
                if _ebv(part.expr, visible):
                    yield c

        _patched_eval_filter._starlayer_graph_evalfilter_patch = True  # type: ignore[attr-defined]
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
    function ``evalDeleteWhere`` uses unconditionally, and which is the
    only one of the two that works correctly against this library's own
    in-memory backend.

    ``ctx.dataset.default_context`` and ``ctx.graph`` are two *different*
    Python objects for a ``StarLayerDataset`` (the former a plain
    ``rdflib.graph.Graph`` wrapper, the latter the real
    ``StarLayerDataset``/``StarLayerGraph`` instance with its own
    triple-term-aware ``add``/``remove``/``triples`` overrides) - for an
    *ordinary* triple this doesn't matter (both wrappers share the same
    underlying ``Store``, so removal reaches it either way), but for a
    triple whose subject/object is a native ``TripleTerm`` value, only the
    real ``StarLayerDataset``/``StarLayerGraph`` object correctly
    translates it to/from this library's internal encoding - going through
    the generic ``default_context`` wrapper silently fails to remove or
    insert the triple at all, with no error.

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

    Returns:
        True if the patch applied (or was already applied), False if
        rdflib's internals didn't match what this shim expects.
    """
    global _evalmodify_patch_status
    if _evalmodify_patch_status is not None:
        return _evalmodify_patch_status

    try:
        from rdflib.plugins.sparql import update as update_module

        original_eval_modify = update_module.evalModify
        if getattr(original_eval_modify, "_starlayer_graph_evalmodify_patch", False):
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

        _patched_eval_modify._starlayer_graph_evalmodify_patch = True  # type: ignore[attr-defined]
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
    values to unpack (expected 4, got 3)``. Not specific to RDF 1.2 at
    all - a plain SPARQL 1.1 `INSERT DATA` against any ``Dataset``-shaped
    default graph hits this.

    Asymmetric with `DELETE DATA`: ``evalDeleteData``'s ``g -= u.triples``
    hits ``Graph.__isub__``, which loops and calls ``self.remove(triple)``
    per plain triple regardless of graph type (no quad-only override
    exists for ``-=`` the way there is for ``+=``) - so only
    ``evalInsertData`` needs this fix.

    Fix: explicit per-triple ``.add()`` calls instead of ``+=`` - the same
    fix ``patch_evalmodify_default_graph_selection`` above establishes for
    `evalModify`'s own identical `.insert`/`.delete` quad-vs-triple
    mismatch, applied here to `INSERT DATA`'s simpler,
    unconditional-default-graph case. Functionally identical to what
    ``Graph.__iadd__`` already does internally for a plain ``Graph``, and
    correct (rather than crashing) for a ``Dataset``/``StarLayerDataset``.

    Same idempotent apply-once pattern as the other patches in this module.

    Returns:
        True if the patch applied (or was already applied), False if
        rdflib's internals didn't match what this shim expects.
    """
    global _evalinsertdata_patch_status
    if _evalinsertdata_patch_status is not None:
        return _evalinsertdata_patch_status

    try:
        from rdflib.plugins.sparql import update as update_module

        original_eval_insert_data = update_module.evalInsertData
        if getattr(original_eval_insert_data, "_starlayer_graph_evalinsertdata_patch", False):
            _evalinsertdata_patch_status = True
            return True

        def _patched_eval_insert_data(ctx, u):
            g = ctx.graph
            for triple in u.triples:
                g.add(triple)
            for graph_id in u.quads:
                cg = ctx.dataset.get_context(graph_id)
                cg += u.quads[graph_id]

        _patched_eval_insert_data._starlayer_graph_evalinsertdata_patch = True  # type: ignore[attr-defined]
        update_module.evalInsertData = _patched_eval_insert_data
        _evalinsertdata_patch_status = True
    except Exception:
        _evalinsertdata_patch_status = False

    return _evalinsertdata_patch_status


_construct_patch_status: bool | None = None


def patch_construct_skips_encoding_solutions() -> bool:
    """Fix a real, general gap (not an rdflib bug - a starlayer.graph-side
    one): ``StarLayerGraph.query()``/``StarLayerDataset.query()`` execute
    the rewritten SPARQL 1.1 text against a *raw*, unfiltered view of the
    underlying store (``raw = Graph(store=self.store, ...)`` in
    ``starlayer_graph.py``) - deliberately, since triple-term pattern
    rewriting (``sparql12_to_11.py``) needs to match the internal
    ``rdf:subject``/``rdf:predicate``/``rdf:object`` encoding triples
    directly. An *unconstrained* pattern like a bare ``?s ?p ?o .`` matches
    those internal triples too, alongside ordinary user-visible ones.

    For SELECT, ``starlayer.graph.model.encoding.restore_select_bindings``
    already drops any result row that incidentally matched these internal
    triples (a TT_NS-prefixed URIRef paired with an encoding predicate as a
    bound *value* - never something a real query result should surface).
    CONSTRUCT has no equivalent: rdflib's own ``evalConstructQuery``
    iterates WHERE solutions and instantiates the template for every one,
    with no per-solution filtering hook. An unconstrained ``?s ?p ?o``
    inside a CONSTRUCT/GRAPH block over data that already contains
    reification/triple-term encoding triples silently wraps an internal
    row (e.g. ``tt:HASH rdf:subject :a``) into a bogus *nested* triple
    term, which then crashes downstream in
    ``StarLayerGraph.from_rdflib``/``_restore`` with "the subject of a
    triple term must be an IRI or blank node, not a triple term" - a leak
    of storage internals into CONSTRUCT output that should never have been
    visible in the first place. Seen in the W3C SPARQL 1.2
    ``construct-3``/``expr-1`` fixtures.

    Fix: the same skip-check ``restore_select_bindings`` already applies to
    SELECT rows, applied here per-solution before templating instead of
    per-output-row after.

    Returns:
        True if the patch applied (or was already applied), False if
        rdflib's internals didn't match what this shim expects.
    """
    global _construct_patch_status
    if _construct_patch_status is not None:
        return _construct_patch_status

    try:
        original_eval_construct = evaluate.evalConstructQuery
        if getattr(original_eval_construct, "_starlayer_graph_construct_patch", False):
            _construct_patch_status = True
            return True

        from rdflib import Graph, Literal, URIRef

        from starlayer.graph.model.encoding import ENCODING_MARKERS, TT_NS

        evalPart = evaluate.evalPart
        _fillTemplate = evaluate._fillTemplate

        def _is_encoding_solution(c) -> bool:
            values = list(c.values())
            return (
                any(isinstance(v, URIRef) and str(v).startswith(TT_NS) for v in values)
                and bool(ENCODING_MARKERS.intersection(values))
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
                # SPARQL 1.1 sec 16.2.1: a template triple that instantiates to something that is not valid
                # RDF (a literal subject, a predicate that is not an IRI) is left out of the output.
                # rdflib kept them, so `CONSTRUCT { ?n ex:p ?n }` over numbers produced literal-subject
                # triples (found by the Oxigraph differential tests).
                graph += (
                    (s, p, o)
                    for s, p, o in _fillTemplate(template, c)
                    if not isinstance(s, Literal) and isinstance(p, URIRef)
                )

            return {"type_": "CONSTRUCT", "graph": graph}

        _patched_eval_construct_query._starlayer_graph_construct_patch = True  # type: ignore[attr-defined]
        evaluate.evalConstructQuery = _patched_eval_construct_query
        _construct_patch_status = True
    except Exception:
        _construct_patch_status = False

    return _construct_patch_status


# ---------------------------------------------------------------------------
# Explicit GROUP BY over no solutions: no groups, so no rows.
# ---------------------------------------------------------------------------

_aggregate_join_patch_status: bool | None = None


def patch_aggregate_join_no_row_for_empty_explicit_group() -> bool:
    """Fix a confirmed rdflib bug: ``evalAggregateJoin`` ends with ``if len(res) == 0: yield
    FrozenBindings(ctx)``. For an *implicit* group (aggregates, no ``GROUP BY``) ``res`` always holds the
    one group, so that line never runs; it only runs for an explicit ``GROUP BY`` that matched nothing, and
    there it adds a row that should not exist. SPARQL 1.1 sec 11.2: grouping an empty solution sequence by
    a key gives no groups, hence no rows (only the implicit single group exists even when empty, and gives
    one row, e.g. ``COUNT`` = 0). Found by the Oxigraph differential tests.

    Fix: the same function without that last line.

    Returns:
        True if the patch applied (or was already applied), False if rdflib's internals differ.
    """
    global _aggregate_join_patch_status
    if _aggregate_join_patch_status is not None:
        return _aggregate_join_patch_status

    try:
        import collections

        from rdflib.plugins.sparql.aggregates import Aggregator
        from rdflib.plugins.sparql.sparql import FrozenBindings

        original = evaluate.evalAggregateJoin
        if getattr(original, "_starlayer_graph_aggregate_join_patch", False):
            _aggregate_join_patch_status = True
            return True

        evalPart = evaluate.evalPart
        _eval = evaluate._eval

        def _patched_eval_aggregate_join(ctx, agg):
            p = evalPart(ctx, agg.p)
            group_expr = agg.p.expr
            res = collections.defaultdict(lambda: Aggregator(aggregations=agg.A))
            if group_expr is None:
                aggregator = res[True]
                for row in p:
                    aggregator.update(row)
            else:
                for row in p:
                    k = tuple(_eval(e, row, False) for e in group_expr)
                    res[k].update(row)
            for aggregator in res.values():
                yield FrozenBindings(ctx, aggregator.get_bindings())

        _patched_eval_aggregate_join._starlayer_graph_aggregate_join_patch = True  # type: ignore[attr-defined]
        evaluate.evalAggregateJoin = _patched_eval_aggregate_join
        _aggregate_join_patch_status = True
    except Exception:
        _aggregate_join_patch_status = False

    return _aggregate_join_patch_status


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
    pre-decoding a nested component here would produce a tuple one level
    too early, which `_tt_aware_eq`'s own recursive call couldn't re-decode
    (`isinstance(node, URIRef)` is false for a tuple), falling through to
    `a.eq(b)` on two raw tuples and crashing - exercised by the W3C `op-2`
    fixture's own nested-triple-term case.

    Deliberately reads the *graph's own* rdf:subject/predicate/object
    triples rather than a `StarLayerGraph._tt_nodes` Python-side registry:
    the graph object seen during query evaluation (`ctx.graph`) is a bare
    `rdflib.Graph` view over the same store (see
    `StarLayerGraph.query()` - `raw = Graph(store=self.store, ...)`), not
    the `StarLayerGraph` instance itself, so `_tt_nodes` isn't reachable
    from here. Reading the on-store encoding triples directly works
    identically to (and is the same technique as) `StarLayerGraph.
    _build_registry_from_store()`'s own reconstruction.

    Args:
        graph: The graph to read encoding triples from.
        node: The candidate tt:HASH URIRef to decode.

    Returns:
        The (subject, predicate, object) tuple of resolved terms, or None
        if node isn't a tt:HASH URIRef with encoding triples present in
        graph.
    """
    from starlayer.graph.model.encoding import TT_NS

    if not (isinstance(node, URIRef) and str(node).startswith(TT_NS)):
        return None
    from starlayer.graph.model.encoding import TT_OBJECT, TT_PREDICATE, TT_SUBJECT

    s = graph.value(node, TT_SUBJECT)
    p = graph.value(node, TT_PREDICATE)
    o = graph.value(node, TT_OBJECT)
    if s is None or p is None or o is None:
        # A ground TRIPLE()/<<( )>> built inside the query was never written
        # to the graph; the process-wide memo still knows what it means.
        from starlayer.graph.model.encoding import lookup_tt_hash

        return lookup_tt_hash(node)
    return (s, p, o)


def _components_of_triple_term(node):
    from starlayer.graph.model.triple import TripleTerm

    if isinstance(node, TripleTerm):
        return (node.subject, node.predicate, node.object)
    return None


def _tt_aware_eq(graph, a, b) -> bool:
    """RDF 1.2 term-equality between `a`/`b`: decode either side that's a
    tt:HASH URIRef into its (subject, predicate, object) components first,
    recursing - restores the value-equality semantics the opaque encoding
    otherwise hides (e.g. ``TRIPLE(:a,:b,123) = TRIPLE(:a,:b,123.0)`` must
    be true - numeric value equality on the differing object - despite the
    two encoded tt:HASH URIs being different, unrelated strings, since the
    hash is computed from *lexical* form - see
    ``starlayer.graph/model/encoding.py::tt_hash``).

    Falls through to plain ``Identifier.eq()`` - which already correctly
    implements SPARQL's own literal value-equality (numeric/date/etc,
    per-datatype) - for any component that isn't itself a tt:HASH URIRef on
    either side, so this only adds recursion where the opaque encoding
    would otherwise have masked it; ordinary IRI/BNode/Literal comparisons
    are unaffected.

    Args:
        graph: The graph to resolve any tt:HASH URIRef against.
        a: The left-hand term to compare.
        b: The right-hand term to compare.

    Returns:
        True if a and b are RDF-1.2-value-equal.
    """
    da = _decode_tt_hash(graph, a) or _components_of_triple_term(a)
    db = _decode_tt_hash(graph, b) or _components_of_triple_term(b)
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
    from starlayer.graph.model.encoding import TT_NS

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
    Exercised by the W3C SPARQL 1.2 test suite's ``eval-triple-terms/op-2``
    fixture (``FILTER(!sameTerm(?left,?right)) FILTER(?left = ?right)``
    over two triple terms differing only in a literal's lexical form).

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
    ``operator_patches.py``/``algebra_translator_patches.py`` idiom.

    Returns:
        True if the patch applied (or was already applied), False if
        rdflib's internals didn't match what this shim expects.
    """
    global _relational_expression_patch_status
    if _relational_expression_patch_status is not None:
        return _relational_expression_patch_status

    try:
        from rdflib.plugins.sparql import parser as rdflib_sparql_parser

        comp = rdflib_sparql_parser.RelationalExpression
        original_evalfn = comp.evalfn
        if getattr(original_evalfn, "_starlayer_graph_tt_hash_equality_patch", False):
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
            elif e.op in ("IN", "NOT IN") and isinstance(e.other, list):
                if _looks_like_tt_hash(e.expr) or any(_looks_like_tt_hash(x) for x in e.other):
                    graph = getattr(ctx, "graph", None) or getattr(getattr(ctx, "ctx", None), "graph", None)
                    if graph is not None:
                        found = any(_tt_aware_eq(graph, e.expr, x) for x in e.other)
                        return Literal(found if e.op == "IN" else not found)
            return original_evalfn(e, ctx)

        _patched_relational_expression._starlayer_graph_tt_hash_equality_patch = True  # type: ignore[attr-defined]
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
    recursive bucketing again). This subject-then-predicate-then-object,
    each individually term-kind-bucketed, ordering is exactly what the W3C
    SPARQL 1.2 ``eval-triple-terms/order-2`` fixture requires - not e.g. a
    flat hash/string comparison.

    Every non-triple-term bucket's second tuple element is deliberately
    kept exactly what stock ``_val`` would use (raw ``Literal`` for the
    literal bucket, so ``Literal.__lt__``'s own value-aware numeric/date/etc
    comparison still applies unchanged; ``str(v)`` for BNode/IRI, matching
    plain string comparison, since neither overrides ``__lt__`` specially)
    - this patch only ever *adds* the missing triple-term bucket, never
    changes how any other kind compares against its own kind.

    Args:
        graph: The graph to resolve a tt:HASH URIRef against, for
            recursive bucketing of its components.
        v: The term (or unbound value) to compute a sort key for.

    Returns:
        A tuple sort key ordering v per RDF 1.2 term-kind rules.
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
    Exercised by the W3C SPARQL 1.2 test suite's ``eval-triple-terms/
    order-1``/``order-2`` fixtures (``ORDER BY`` across mixed blank-node/
    IRI/literal/triple-term values, several distinct triple terms in
    ``order-2`` specifically).

    ``_val`` is used exactly once in stock rdflib
    (``rdflib.plugins.sparql.evaluate``, inside ``evalOrderBy`` only), so
    replacing ``evalOrderBy`` wholesale (rather than trying to patch
    ``_val`` in place, which has no way to reach the graph a raw value
    needs decoding against) is safe and complete; no other code path
    depends on ``_val``'s own bucketing.

    Idempotent and defensive, matching the established
    ``operator_patches.py``/``algebra_translator_patches.py`` idiom.

    Returns:
        True if the patch applied (or was already applied), False if
        rdflib's internals didn't match what this shim expects.
    """
    global _order_by_patch_status
    if _order_by_patch_status is not None:
        return _order_by_patch_status

    try:
        original_eval_order_by = evaluate.evalOrderBy
        if getattr(original_eval_order_by, "_starlayer_graph_order_by_patch", False):
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

        _patched_eval_order_by._starlayer_graph_order_by_patch = True  # type: ignore[attr-defined]
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


# ---------------------------------------------------------------------------
# Join keeps duplicate solutions of its right side (multiset semantics).
# ---------------------------------------------------------------------------

_join_patch_status: bool | None = None


def patch_join_keeps_duplicate_rows() -> bool:
    """rdflib's non-lazy ``evalJoin`` builds its right operand as ``set(evalPart(ctx, join.p2))``, which drops duplicate
    solutions. SPARQL 1.1 section 18.5 defines ``Join`` over multisets: two identical right-hand solutions each join
    with every compatible left solution. A join is non-lazy when its right side holds a ``LIMIT``/``OFFSET`` slice or a
    ``DISTINCT`` (rdflib's ``analyse``), so ``{ ?x :says ?t { SELECT ?t { ?q :says ?t } LIMIT 5 } }`` lost rows (GitHub
    issue #134). The patched ``evalJoin`` materialises the right side as a list instead.

    Returns:
        True if the patch applied (or was already applied), False if rdflib's internals differ.
    """
    global _join_patch_status
    if _join_patch_status is not None:
        return _join_patch_status
    try:
        from rdflib.plugins.sparql.evalutils import _join

        original = evaluate.evalJoin
        if getattr(original, "_starlayer_graph_join_patch", False):
            _join_patch_status = True
            return True

        evalPart = evaluate.evalPart

        def _patched_eval_join(ctx, join):
            if join.lazy:
                return evaluate.evalLazyJoin(ctx, join)
            a = evalPart(ctx, join.p1)
            b = list(evalPart(ctx, join.p2))
            return _join(a, b)

        _patched_eval_join._starlayer_graph_join_patch = True  # type: ignore[attr-defined]
        evaluate.evalJoin = _patched_eval_join
        _join_patch_status = True
    except Exception:
        _join_patch_status = False
    return _join_patch_status


_negated_path_patch_status: bool | None = None


def patch_negated_path_skips_encoding_triples() -> bool:
    """A negated property set (``?x !(:p) ?y``) matched every triple whose predicate is not listed, including the
    rdf-1.1 backend's internal triple-term encoding triples, so the decomposition of a triple term showed up as data
    (GitHub issue #74). Replaces ``NegatedPath.eval`` with one that skips those triples, as the BGP patch does for an
    unconstrained predicate. Idempotent, like the other patches here."""
    global _negated_path_patch_status
    if _negated_path_patch_status is not None:
        return _negated_path_patch_status
    try:
        from rdflib.paths import InvPath, NegatedPath

        from starlayer.graph.model.encoding import ENCODING_PREDS, TT_CLASS

        if getattr(NegatedPath.eval, "_starlayer_graph_negated_path_patch", False):
            _negated_path_patch_status = True
            return True

        def _eval(self, graph, subj=None, obj=None):
            # SPARQL 1.1 section 18.4: !(a|^b) is !(a) | ^(!(b)): a forward part only if a forward member is listed, an
            # inverse part only if an inverse member is. rdflib instead treated ^b as "skip a forward edge whose reverse
            # exists" (and crashed on the member); the encoding triples of the rdf-1.1 triple-term representation are
            # skipped in both directions (GitHub issues #74, #77).
            forward = [a for a in self.args if isinstance(a, URIRef)]
            inverse = [a.arg for a in self.args if isinstance(a, InvPath)]
            if len(forward) + len(inverse) != len(self.args):
                raise Exception(f"Invalid path in NegatedPath: {self.args}")
            if forward or not inverse:
                for s, p, o in graph.triples((subj, None, obj)):
                    if p in ENCODING_PREDS or (p == RDF.type and o == TT_CLASS):
                        continue
                    if p not in forward:
                        yield s, o
            if inverse:
                for o2, p, s2 in graph.triples((obj, None, subj)):
                    if p in ENCODING_PREDS or (p == RDF.type and s2 == TT_CLASS):
                        continue
                    if p not in inverse:
                        yield s2, o2

        _eval._starlayer_graph_negated_path_patch = True  # type: ignore[attr-defined]
        NegatedPath.eval = _eval
        _negated_path_patch_status = True
    except Exception:
        _negated_path_patch_status = False
    return _negated_path_patch_status


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

    The filter only applies to a match where the *pattern's own* predicate
    position was unconstrained (a variable, not yet bound - ``ctx[p] is
    None`` before this triple is matched) - never one where the pattern
    itself already specifies the predicate as a literal
    rdf:subject/predicate/object IRI, which is exactly the shape every
    rewriter-generated decode pattern always uses (a ground predicate,
    never a variable there). This distinction matters: the SPARQL 1.2 ->
    1.1 rewriter's own generated queries *legitimately* need to match these
    same triples to decode a triple-term pattern containing a variable
    (e.g. ``sparql12_to_11.py``'s own expansion of ``<<:a :b ?o>> ?q :z .``
    into ``?tt rdf:subject :a . ?tt rdf:predicate :b . ?tt rdf:object
    ?o . ...``), and a filter keyed only on the *matched values* can't tell
    that apart from an accidental wildcard leak, since both shapes match
    the identical encoding triples. "Did the *query text* ask for this
    predicate specifically" vs "did an unconstrained wildcard happen to
    match it" is not visible from the matched triple's values alone, but
    is directly available from the pattern's own (pre-match) term for the
    predicate position - which is what this patch keys on instead.

    Exercised by the W3C SPARQL 1.2 ``eval-triple-terms/order-1``/
    ``order-2`` fixtures' own query shape (``{ SELECT ?v { ?s ?p ?v }
    ORDER BY ?v OFFSET N LIMIT 1 }``, repeated across 20 ``UNION``
    branches - predicate ``?p`` genuinely unconstrained there), without
    regressing ``basic-5`` (predicate ``rdf:subject``/etc. always ground
    in the rewriter's own generated pattern there) or any other
    currently-passing test.

    Idempotent and defensive, matching the established
    ``operator_patches.py``/``algebra_translator_patches.py`` idiom.

    Returns:
        True if the patch applied (or was already applied), False if
        rdflib's internals didn't match what this shim expects.
    """
    global _bgp_patch_status
    if _bgp_patch_status is not None:
        return _bgp_patch_status

    try:
        from rdflib.plugins.sparql.sparql import AlreadyBound

        from starlayer.graph.model.encoding import ENCODING_PREDS, TT_CLASS

        original_eval_bgp = evaluate.evalBGP
        if getattr(original_eval_bgp, "_starlayer_graph_bgp_patch", False):
            _bgp_patch_status = True
            return True

        def _is_unconstrained_encoding_leak(pattern_p_was_bound: bool, sp, so) -> bool:
            if pattern_p_was_bound:
                # The pattern itself already specified this predicate (a
                # ground rdf:subject/predicate/object, or any other already-
                # bound term) - a deliberate, constrained match, never a
                # wildcard leak, regardless of what it matches.
                return False
            return sp in ENCODING_PREDS or (sp == RDF.type and so == TT_CLASS)

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
                if _is_unconstrained_encoding_leak(p_was_bound, sp, so):
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

        _patched_eval_bgp._starlayer_graph_bgp_patch = True  # type: ignore[attr-defined]
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
# docs/upstream-issues/rdflib-upstream-issues.md Issue 9 for the full writeup.
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
    term/``starlayer.sparql`` involvement at all. See
    ``docs/upstream-issues/rdflib-upstream-issues.md`` Issue 9 for the full root-cause
    trace and a minimal, plain-rdflib reproduction.

    Root cause: for *every* parenthesized-expression ``GROUP BY``
    condition (aliased or not), the parser produces a ``GroupAs`` node
    with an ``.expr``, and (only for the aliased form) a real ``.var``.
    ``translate``'s own loop (``if isinstance(c, CompValue) and c.name ==
    "GroupAs": M = Extend(M, c.expr, c.var); c = c.var``) uses ``c.var``
    for *both* the ``Extend``'s own bind target *and* the value appended
    to the ``Group.expr`` list that identifies this grouping key later -
    for the un-aliased form, ``c.var`` is ``None`` (the key is genuinely
    absent from the ``GroupAs`` node, not just falsy), so both end up
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
    ``translate``'s own, completely unmodified logic then naturally uses
    this same synthetic variable for *both* the ``Extend`` and the
    ``Group.expr`` entry, with no further changes needed anywhere: the
    pairing was never actually ambiguous at the *parse-tree* level, only
    after the ``None`` erased the connection between the two positions.
    Mirrors rdflib's own ``__agg_N__`` naming convention (used elsewhere in
    the same function for `SAMPLE`'s own synthetic result variables) for
    the same reason: a name unlikely to collide with any real,
    user-written variable, and never projected out - this grouping key
    was never given a name by the query's own author, so it correctly
    stays invisible in the result set either way.

    Applies to ``algebra.translate`` (rebinding the module attribute, so
    ``translateQuery``'s own internal call - a same-module global lookup,
    resolved at call time - picks up the wrapped version automatically,
    the same mechanism every other patch in this file already relies on).

    Same idempotent apply-once pattern as the other patches in this module.

    Returns:
        True if the patch applied (or was already applied), False if
        rdflib's internals didn't match what this shim expects.
    """
    global _group_by_unaliased_key_patch_status
    if _group_by_unaliased_key_patch_status is not None:
        return _group_by_unaliased_key_patch_status

    try:
        from rdflib.plugins.sparql import algebra as algebra_module

        original_translate = algebra_module.translate
        if getattr(original_translate, "_starlayer_graph_groupby_patch", False):
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
                    f"__starlayer_graph_groupkey_{_group_by_synthetic_var_counter}__"
                )

        def _patched_translate(q):
            _fill_in_missing_group_condition_vars(q)
            return original_translate(q)

        _patched_translate._starlayer_graph_groupby_patch = True  # type: ignore[attr-defined]
        algebra_module.translate = _patched_translate
        _group_by_unaliased_key_patch_status = True
    except Exception:
        _group_by_unaliased_key_patch_status = False

    return _group_by_unaliased_key_patch_status
