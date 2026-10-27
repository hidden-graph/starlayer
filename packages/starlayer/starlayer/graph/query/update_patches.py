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

The data operations are patched too (GitHub issue #135): ``DELETE DATA``,
``DELETE WHERE`` and ``DELETE { }`` removed the triple from every graph of the
dataset (``ctx.graph`` is the dataset, and ``Dataset.remove`` removes from all
contexts), ``USING <g>`` made the delete template reach ``g``, ``USING NAMED``
restricted nothing, template triples that are not valid RDF were inserted, and
a missing graph was no error for ``CLEAR``/``DROP``/``ADD``/``COPY``/``MOVE``.

Each patch is idempotent, with a sentinel attribute, like the others in this
package.
"""

from __future__ import annotations

from rdflib import Dataset, Graph
from rdflib.plugins.sparql.evaluate import evalBGP, evalPart
from rdflib.plugins.sparql.evalutils import _fillTemplate, _join
from rdflib.term import Literal, URIRef, Variable

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
    graph = getattr(dataset, "default_graph", None)  # not ``or``: an empty graph is falsy
    return graph if graph is not None else dataset.default_context


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
    _require_graph(ctx, which)
    return [ctx.dataset.get_context(which)]


def _graph_exists(ctx, name) -> bool:
    return any(c.identifier == name for c in ctx.dataset.contexts())


def _require_graph(ctx, name) -> None:
    """SPARQL 1.1 Update 3.2: without SILENT it is an error to operate on a graph that does not exist (``evalUpdate``
    swallows the error for SILENT)."""
    if name != "DEFAULT" and not _graph_exists(ctx, name):
        raise Exception(f"Graph {name} does not exist.")


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
    _require_graph(ctx, src)
    srcg, dstg = _graph_or_default(ctx, src), _graph_or_default(ctx, dst)
    if srcg.identifier == dstg.identifier:
        return
    _copy_into(srcg, dstg)


def _eval_copy(ctx, u):
    src, dst = u.graph
    _require_graph(ctx, src)
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
    _require_graph(ctx, src)
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

    # the default-graph triples go through the true default graph: ``ctx.graph.__isub__`` removed them from every graph
    target = _target_graph(ctx)
    for solution in solutions:
        for triple in _valid_triples(u.triples, solution):
            target.remove(triple)
        for graph_term, pattern in u.quads.items():
            name = _graph_name(graph_term, solution)
            cg = _existing_graph(ctx, name) if name is not None else None
            if cg is not None:
                for triple in _valid_triples(pattern, solution):
                    cg.remove(triple)


def _is_valid_triple(triple) -> bool:
    """A template triple that is not a valid RDF triple is skipped (SPARQL 1.1 Update 3.1.3): no literal subject, no
    non-IRI predicate, no unbound term."""
    s, p, o = triple
    return (
        s is not None
        and not isinstance(s, (Literal, Variable))
        and isinstance(p, URIRef)
        and o is not None
        and not isinstance(o, Variable)
    )


def _valid_triples(template, solution) -> list:
    return [t for t in _fillTemplate(template, solution) if _is_valid_triple(t)]


def _graph_name(term, solution):
    """The IRI a ``GRAPH`` template names, or None when it is unbound or not an IRI (that quad is skipped)."""
    name = solution.get(term) if isinstance(term, Variable) else term
    return name if isinstance(name, URIRef) else None


def _existing_graph(ctx, name):
    """A graph to delete from; deleting from a graph that does not exist must not create it."""
    return ctx.dataset.get_context(name) if _graph_exists(ctx, name) else None


def _target_graph(ctx):
    """The graph a template without ``GRAPH`` writes to: the true default graph, never the union view ``ctx.graph``."""
    return _default_graph(ctx)


def _eval_insert_data(ctx, u):
    target = _target_graph(ctx)
    for triple in u.triples:
        target.add(triple)
    for name, triples in u.quads.items():
        cg = ctx.dataset.get_context(name)
        for triple in triples:
            cg.add(triple)


def _eval_delete_data(ctx, u):
    target = _target_graph(ctx)
    for triple in u.triples:
        target.remove(triple)
    for name, triples in u.quads.items():
        cg = _existing_graph(ctx, name)
        if cg is not None:
            for triple in triples:
                cg.remove(triple)


def _using_where_context(ctx, using):
    """The context a ``USING``/``USING NAMED`` ``WHERE`` runs in (SPARQL 1.1 Update 3.1.3): the default graph is the
    merge of the ``USING`` graphs (empty with only ``USING NAMED``), the named graphs are exactly the ``USING NAMED``
    ones. Graphs are copied, so the template never writes through to a ``USING`` graph; one that is not in the dataset is
    empty (never fetched)."""
    dataset = ctx.dataset
    merged = Graph()
    where_dataset = Dataset()
    for clause in using:
        if clause.default:
            if _graph_exists(ctx, clause.default):
                for triple in dataset.get_context(clause.default).triples((None, None, None)):
                    merged.add(triple)
        elif clause.named and _graph_exists(ctx, clause.named):
            named = where_dataset.get_context(clause.named)
            for triple in dataset.get_context(clause.named).triples((None, None, None)):
                named.add(triple)
    where_ctx = ctx.clone()
    where_ctx._dataset = where_dataset
    where_ctx.graph = merged
    return where_ctx


def _eval_modify(ctx, u):
    if u.using:
        where_ctx = _using_where_context(ctx, u.using)
    elif u.withClause:
        where_ctx = ctx.pushGraph(ctx.dataset.get_context(u.withClause))
    else:
        where_ctx = ctx
    solutions = list(evalPart(where_ctx, u.where))

    # the template writes to WITH, else the true default graph: not to the USING graphs and not to the union view
    target = ctx.dataset.get_context(u.withClause) if u.withClause else _target_graph(ctx)

    # all deletes first, then all inserts (SPARQL 1.1 Update 3.1.3)
    if u.delete:
        for c in solutions:
            for triple in _valid_triples(u.delete.triples, c):
                target.remove(triple)
            for term, template in u.delete.quads.items():
                name = _graph_name(term, c)
                cg = _existing_graph(ctx, name) if name is not None else None
                if cg is not None:
                    for triple in _valid_triples(template, c):
                        cg.remove(triple)
    if u.insert:
        for c in solutions:
            for triple in _valid_triples(u.insert.triples, c):
                target.add(triple)
            for term, template in u.insert.quads.items():
                name = _graph_name(term, c)
                if name is not None:
                    cg = ctx.dataset.get_context(name)
                    for triple in _valid_triples(template, c):
                        cg.add(triple)


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
            ("evalInsertData", _eval_insert_data),
            ("evalDeleteData", _eval_delete_data),
            ("evalModify", _eval_modify),
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
