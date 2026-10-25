"""Monkeypatches for rdflib's SPARQL Update evaluation of graph management
operations on a ``Dataset`` (``rdflib.plugins.sparql.update``).

rdflib's update code mixes up "the default graph" with ``ctx.graph``, which is
the union of every graph when the dataset has ``default_union`` set (the
setting ``StarLayerDataset`` passes on so a ``GRAPH``-less ``WHERE`` sees all
the data). The graph management operations must act on the true default
graph (SPARQL 1.1 Update 3.2), so ``CLEAR DEFAULT`` wiped the whole dataset,
``ADD``/``COPY``/``MOVE`` involving ``DEFAULT`` crashed or lost data,
``CREATE`` always raised, ``DELETE WHERE { GRAPH ?g {...} }`` deleted nothing
and ``USING``/``USING NAMED`` tried to fetch the graph over the network
(GitHub issue #78). The bugs are in ``docs/upstream-issues/rdflib-upstream-issues.md``.

Each patch is idempotent, with a sentinel attribute, like the others in this
package.
"""

from __future__ import annotations

from rdflib.plugins.sparql.evaluate import evalBGP
from rdflib.plugins.sparql.evalutils import _fillTemplate, _join
from rdflib.term import URIRef, Variable

_SENTINEL = "_starlayer_graph_update_patch"
_status: bool | None = None


def _dataset(ctx):
    """The dataset being updated, or None when the target is a plain graph (which has only a default graph)."""
    try:
        return ctx.dataset
    except Exception:
        return None


def _default_graph(ctx):
    dataset = _dataset(ctx)
    if dataset is None:
        return ctx.graph
    return getattr(dataset, "default_graph", None) or dataset.default_context


def _named_graphs(ctx) -> list:
    dataset = _dataset(ctx)
    if dataset is None:
        return []
    default_id = _default_graph(ctx).identifier
    return [c for c in dataset.contexts() if c.identifier != default_id]


def _graph_or_default(ctx, name):
    if name == "DEFAULT":
        return _default_graph(ctx)
    return ctx.dataset.get_context(name)


def _graphs(ctx, which):
    if which == "DEFAULT":
        return [_default_graph(ctx)]
    if which == "NAMED":
        return _named_graphs(ctx)
    if which == "ALL":
        return [_default_graph(ctx), *_named_graphs(ctx)]
    return [ctx.dataset.get_context(which)]


def _graph_exists(ctx, name) -> bool:
    return any(c.identifier == name for c in ctx.dataset.contexts())


def _empty(ctx, graph) -> None:
    graph.remove((None, None, None))


def _remove_graph(ctx, graph) -> None:
    if graph.identifier == _default_graph(ctx).identifier:
        _empty(ctx, graph)  # the default graph always exists
    elif ctx.dataset.store.graph_aware:
        ctx.dataset.store.remove_graph(graph)
    else:
        _empty(ctx, graph)


def _eval_clear(ctx, u):
    for g in _graphs(ctx, u.graphiri):
        _empty(ctx, g)


def _eval_drop(ctx, u):
    for g in _graphs(ctx, u.graphiri):
        _remove_graph(ctx, g)


def _eval_create(ctx, u):
    name = u.graphiri
    if _graph_exists(ctx, name):
        if not u.silent:
            raise Exception(f"Graph {name} already exists.")
        return
    ctx.dataset.add_graph(name)


def _copy_into(src, dst) -> None:
    triples = list(src.triples((None, None, None)))
    for triple in triples:
        dst.add(triple)


def _eval_add(ctx, u):
    src, dst = u.graph
    srcg, dstg = _graph_or_default(ctx, src), _graph_or_default(ctx, dst)
    if srcg.identifier == dstg.identifier:
        return
    _copy_into(srcg, dstg)


def _eval_copy(ctx, u):
    src, dst = u.graph
    srcg, dstg = _graph_or_default(ctx, src), _graph_or_default(ctx, dst)
    if srcg.identifier == dstg.identifier:
        return
    # copy first: dst and src can share a store, and dst may not be empty
    triples = list(srcg.triples((None, None, None)))
    _empty(ctx, dstg)
    for triple in triples:
        dstg.add(triple)


def _eval_move(ctx, u):
    src, dst = u.graph
    srcg, dstg = _graph_or_default(ctx, src), _graph_or_default(ctx, dst)
    if srcg.identifier == dstg.identifier:
        return
    triples = list(srcg.triples((None, None, None)))
    _empty(ctx, dstg)
    for triple in triples:
        dstg.add(triple)
    _remove_graph(ctx, srcg)


def _graph_solutions(ctx, pattern, graph_term):
    """Solutions of one ``GRAPH graph_term { pattern }`` block, binding the
    graph variable when the name is a variable."""
    if not isinstance(graph_term, Variable):
        cg = ctx.dataset.get_context(graph_term)
        return list(evalBGP(ctx.pushGraph(cg), pattern))
    out = []
    for cg in _named_graphs(ctx):
        sub = ctx.pushGraph(cg)
        for solution in evalBGP(sub, pattern):
            out.append(solution.merge({graph_term: cg.identifier}))
    return out


def _eval_delete_where(ctx, u):
    solutions = list(evalBGP(ctx, u.triples))
    for graph_term, pattern in u.quads.items():
        solutions = list(_join(iter(solutions), _graph_solutions(ctx, pattern, graph_term)))

    for solution in solutions:
        ctx.graph.__isub__(_fillTemplate(u.triples, solution))
        for graph_term, pattern in u.quads.items():
            name = solution.get(graph_term) if isinstance(graph_term, Variable) else graph_term
            if name is None:
                continue
            cg = ctx.dataset.get_context(name)
            cg -= _fillTemplate(pattern, solution)


def patch_update_graph_management() -> bool:
    """Replace rdflib's CLEAR, DROP, CREATE, ADD, COPY, MOVE and DELETE WHERE
    with versions that act on the true default graph and on the dataset's
    named graphs, and make ``USING``/``USING NAMED`` read graphs already in
    the dataset instead of fetching them.

    Returns:
        True if applied (or already applied), False if rdflib's internals
        did not match what this shim expects.
    """
    global _status
    if _status is not None:
        return _status
    try:
        from rdflib.plugins.sparql import sparql as sparql_module
        from rdflib.plugins.sparql import update as update_module

        if getattr(update_module.evalClear, _SENTINEL, False):
            _status = True
            return True

        for name, fn in (
            ("evalClear", _eval_clear),
            ("evalDrop", _eval_drop),
            ("evalCreate", _eval_create),
            ("evalAdd", _eval_add),
            ("evalCopy", _eval_copy),
            ("evalMove", _eval_move),
            ("evalDeleteWhere", _eval_delete_where),
        ):
            setattr(fn, _SENTINEL, True)
            setattr(update_module, name, fn)

        original_load = sparql_module.QueryContext.load

        def _load(self, source, default=False, into=None, **kwargs):
            # USING / USING NAMED name graphs of the dataset: read those, never fetch
            if into is None and isinstance(source, URIRef) and _graph_exists(self, source):
                if default:
                    for triple in list(self.dataset.get_context(source).triples((None, None, None))):
                        self.graph.add(triple)
                return None
            return original_load(self, source, default=default, into=into, **kwargs)

        setattr(_load, _SENTINEL, True)
        sparql_module.QueryContext.load = _load
        _status = True
    except Exception:
        _status = False
    return _status


__all__ = ["patch_update_graph_management"]
