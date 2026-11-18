"""``graph.ox``: Oxigraph's own store methods, called as Oxigraph defines them.

``g.ox.add(quad)`` runs ``Store.add`` on the store behind ``g``, with Oxigraph's arguments and results, so a name the rdflib-style
methods also use (``add``, ``extend``, ``remove``, ``query``, ``update``) is never ambiguous. A method that changes the store
calls ``union.touch()`` after it ran (the entailment cache and the deduplicated union copy depend on the write counter); a
method that only reads does not.

On a ``StarLayerGraph`` a call that would reach a graph other than its own raises ``ValueError``: a quad of another graph, a
``graph_name`` / ``to_graph`` / ``from_graph`` naming another graph, a quad format (it can carry any graph), ``clear()`` (every
graph), and a call that leaves the graph to Oxigraph's default (``quads_for_pattern`` with no graph reads every graph,
``load`` with no ``to_graph`` writes the default graph, ``dump`` with no ``from_graph``). ``update`` text is parsed and aimed at the graph, or refused
if it names another (``execution/update_scope.py``); the text of ``query`` is not parsed, so a ``GRAPH`` clause in it can still name any graph. On a
``StarLayerDataset`` nothing is checked.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

import pyoxigraph as ox

from starlayer.graph import terms
from starlayer.graph.execution import union

#: the store methods that change the store: the write counter moves after each
WRITERS = frozenset({"add", "add_graph", "bulk_extend", "bulk_load", "clear", "clear_graph", "extend", "load", "remove", "remove_graph", "update"})
#: constructors: ``StarLayerGraph.read_only(path)``, not an instance route
_NOT_ON_AN_INSTANCE = frozenset({"read_only", "secondary"})
STORE_METHODS = frozenset(n for n in dir(ox.Store) if not n.startswith("_")) - _NOT_ON_AN_INSTANCE


def _arg(args: tuple[Any, ...], kw: dict[str, Any], index: int | None, key: str, default: Any = None) -> Any:
    if key in kw:
        return kw[key]
    return args[index] if index is not None and len(args) > index else default


def _refuse(method: str, scope: Any, what: str) -> ValueError:
    return ValueError(f"this StarLayerGraph holds graph {scope}; ox.{method}() cannot {what}")


def _own(method: str, scope: Any, name: Any, *, none_means: str | None = None) -> None:
    """Raise ``ValueError`` unless ``name`` is the graph ``scope``. ``none_means`` says what an omitted name would mean."""
    if name is None:
        if none_means:
            raise _refuse(method, scope, f"{none_means}; name the graph ({scope})")
        name = ox.DefaultGraph()
    else:
        name = terms.graph_name(name)
    if name != scope:
        raise _refuse(method, scope, f"act on graph {name}")


def _own_quad(method: str, scope: Any, quad: Any) -> Any:
    if isinstance(quad, ox.Quad) and quad.graph_name != scope:
        raise _refuse(method, scope, f"write to graph {quad.graph_name}")
    return quad


def _own_quads(method: str, scope: Any, quads: Iterable[Any]) -> Iterator[Any]:
    return (_own_quad(method, scope, q) for q in quads)


def _graph_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple, set, frozenset)) else [value]


def _check_single_quad(method: str, scope: Any, args: tuple[Any, ...], kw: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any]]:
    _own_quad(method, scope, _arg(args, kw, 0, "quad"))
    return args, kw


def _check_quads(method: str, scope: Any, args: tuple[Any, ...], kw: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any]]:
    if "quads" in kw:
        kw = {**kw, "quads": _own_quads(method, scope, kw["quads"])}
    elif args:
        args = (_own_quads(method, scope, args[0]), *args[1:])
    return args, kw


def _check_graph_name(method: str, scope: Any, args: tuple[Any, ...], kw: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any]]:
    _own(method, scope, _arg(args, kw, 0, "graph_name"))
    return args, kw


def _check_clear(method: str, scope: Any, args: tuple[Any, ...], kw: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any]]:
    raise _refuse(method, scope, "clear every graph of the store; use clear_graph() or the graph's own clear()")


def _check_load(method: str, scope: Any, args: tuple[Any, ...], kw: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any]]:
    fmt = _arg(args, kw, 1, "format")
    if fmt is None and (path := kw.get("path")) is not None:
        fmt = ox.RdfFormat.from_extension(Path(os.fspath(path)).suffix.lstrip("."))
    if getattr(fmt, "supports_datasets", False):
        raise _refuse(method, scope, f"load a quad format ({fmt}): it can carry any graph; use a StarLayerDataset")
    to_graph = kw.get("to_graph")
    if to_graph is None:
        to_graph = ox.DefaultGraph()
    _own(method, scope, to_graph)
    return args, kw


def _check_dump(method: str, scope: Any, args: tuple[Any, ...], kw: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any]]:
    _own(method, scope, kw.get("from_graph"), none_means="dump every graph")
    return args, kw


def _check_pattern(method: str, scope: Any, args: tuple[Any, ...], kw: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any]]:
    _own(method, scope, _arg(args, kw, 3, "graph_name"), none_means="read every graph")
    return args, kw


def _check_update(method: str, scope: Any, args: tuple[Any, ...], kw: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """The update text aimed at the graph, or refused if it names another (``execution/update_scope.py``)."""
    from starlayer.graph.execution.update_scope import scope_update

    text = _arg(args, kw, 0, "update")
    scoped = scope_update(text, scope, base=kw.get("base_iri"), prefixes=kw.get("prefixes"))
    if "update" in kw:
        return args, {**kw, "update": scoped}
    return (scoped, *args[1:]), kw


def _check_query(method: str, scope: Any, args: tuple[Any, ...], kw: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any]]:
    if kw.get("use_default_graph_as_union"):
        raise _refuse(method, scope, "read the union of every graph")
    default_graph = _graph_list(kw.get("default_graph"))
    for name in (*default_graph, *_graph_list(kw.get("named_graphs"))):
        _own(method, scope, name)
    if not default_graph and not isinstance(scope, ox.DefaultGraph):
        raise _refuse(method, scope, f"read the default graph; pass default_graph=[{scope}]")
    return args, kw


_CHECKS: dict[str, Callable[[str, Any, tuple[Any, ...], dict[str, Any]], tuple[tuple[Any, ...], dict[str, Any]]]] = {
    "add": _check_single_quad,
    "remove": _check_single_quad,
    "extend": _check_quads,
    "bulk_extend": _check_quads,
    "add_graph": _check_graph_name,
    "clear_graph": _check_graph_name,
    "remove_graph": _check_graph_name,
    "clear": _check_clear,
    "load": _check_load,
    "bulk_load": _check_load,
    "dump": _check_dump,
    "quads_for_pattern": _check_pattern,
    "query": _check_query,
    "update": _check_update,
}


class OxStore:
    """The Oxigraph store methods of a graph or dataset: ``g.ox.<method>(...)``. See the module docstring."""

    def __init__(self, owner: Any) -> None:
        self._owner = owner

    def __getattr__(self, name: str) -> Callable[..., Any]:
        if name in _NOT_ON_AN_INSTANCE:
            raise AttributeError(f"{name} makes a store: call {type(self._owner).__name__}.{name}(path)")
        if name not in STORE_METHODS:
            raise AttributeError(f"pyoxigraph.Store has no method {name!r}")
        owner = self._owner
        method = getattr(owner.store, name)
        scope = owner._scope()
        check = _CHECKS.get(name) if scope is not None else None
        writes = name in WRITERS

        def call(*args: Any, **kw: Any) -> Any:
            if check is not None:
                args, kw = check(name, scope, args, kw)
            try:
                return method(*args, **kw)
            finally:
                if writes:
                    union.touch(owner.store)

        call.__name__ = name
        call.__doc__ = getattr(method, "__doc__", None)
        return call

    def __dir__(self) -> list[str]:
        return sorted(STORE_METHODS)

    def __repr__(self) -> str:
        return f"<ox: Oxigraph's store methods on {self._owner!r}>"
