"""SPARQL Update confined to one graph of a store.

``scope_update(text, scope)`` is the text a ``StarLayerGraph`` may run: what the update leaves unqualified is aimed at ``scope``, and
what it names must be ``scope``. The update is parsed (``sparql.parse_sparql.parse_sparql_update``), checked, edited on the tree and
written back as text (``render_sqe_tree``); an update that needs no edit is returned as written.

For a named graph ``G``:

* ``INSERT DATA`` / ``DELETE DATA`` / ``DELETE WHERE``: triples outside a ``GRAPH`` block go in ``GRAPH G { }``.
* ``DELETE`` / ``INSERT`` ... ``WHERE``: ``WITH G`` when there is none, and ``USING G`` and ``USING NAMED G`` when there is no
  ``USING``, so the ``WHERE`` reads ``G`` alone (``GRAPH ?g`` there can bind only ``G``).
* ``CLEAR`` / ``DROP``: ``DEFAULT``, ``NAMED`` and ``ALL`` mean ``G``. ``LOAD`` without ``INTO`` loads into ``G``.
* A graph named by IRI, in a ``GRAPH`` block, ``WITH``, ``USING``, ``CLEAR``, ``LOAD INTO`` and so on, must be ``G`` or the update is
  refused with ``ValueError``; so is a ``GRAPH ?g`` in an ``INSERT`` / ``DELETE`` template or in ``DELETE WHERE`` (a variable
  could be bound to another graph by ``VALUES`` or ``BIND``).

For the default graph nothing is rewritten except ``CLEAR ALL`` (``CLEAR DEFAULT``) and ``CLEAR NAMED`` (dropped, as it has nothing to
act on); any graph named by IRI is refused. No ``USING`` can name the default graph, so a ``GRAPH ?g`` in a ``WHERE`` still reads
the named graphs. A graph named by a blank node cannot be named in SPARQL, so an update cannot be scoped to one.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pyoxigraph as ox


class _Scoper:
    def __init__(self, scope: Any) -> None:
        self.scope = scope
        self.named = isinstance(scope, ox.NamedNode)
        self.changed = False

    def refuse(self, what: str) -> ValueError:
        return ValueError(f"this StarLayerGraph holds graph {self.scope}; update cannot {what}")

    def own_iri(self, iri: Any, what: str = "act on graph") -> None:
        if not (self.named and iri == self.scope):
            raise self.refuse(f"{what} {iri}")

    def ref(self, node: Any, Node: Any, *, groups: bool) -> Any:
        """A graph reference of an operation, aimed at the scope; ``None`` when there is nothing in the scope to act on."""
        kind = node.kind
        if kind == "GraphRef":
            self.own_iri(node.f["iri"])
            return node
        if kind == "DefaultGraph":
            if self.named:
                self.changed = True
                return Node("GraphRef", iri=self.scope)
            return node
        if groups and kind in ("AllGraphs", "NamedGraphs"):
            if self.named:
                self.changed = True
                return Node("GraphRef", iri=self.scope)
            if kind == "AllGraphs":
                self.changed = True
                return Node("DefaultGraph")
            return None
        raise self.refuse(f"use a {kind}")

    def blocks(self, items: Any, Node: Any, *, wrap: bool) -> list[Any]:
        """The quads of a data operation: a ``GRAPH`` block must name the scope; with ``wrap`` the triples outside one go in a block for it."""
        kept: list[Any] = []
        loose: list[Any] = []
        for item in items or []:
            if item.kind == "QuadGraph":
                self.own_iri(item.f["term"], "write to graph")
                kept.append(item)
            else:
                loose.append(item)
        if loose and wrap and self.named:
            self.changed = True
            kept.append(Node("QuadGraph", term=self.scope, triples=loose))
            return kept
        return kept + loose

    def template(self, items: Any) -> None:
        for item in items or []:
            if item.kind == "QuadGraph":
                self.own_iri(item.f["term"], "write to graph")

    def operation(self, op: Any, Node: Any) -> Any:
        f, kind = op.f, op.kind
        if kind in ("Clear", "Drop"):
            target = self.ref(f["target"], Node, groups=True)
            if target is None:
                self.changed = True
                return None
            f["target"] = target
        elif kind == "Create":
            self.own_iri(f["graph"].f["iri"], "create graph")
        elif kind == "Load":
            if f["into"] is None:
                if self.named:
                    self.changed = True
                    f["into"] = Node("GraphRef", iri=self.scope)
            else:
                f["into"] = self.ref(f["into"], Node, groups=False)
        elif kind in ("Add", "Move", "Copy"):
            f["source"] = self.ref(f["source"], Node, groups=False)
            f["dest"] = self.ref(f["dest"], Node, groups=False)
        elif kind in ("InsertData", "DeleteData", "DeleteWhere"):
            f["quads"] = self.blocks(f["quads"], Node, wrap=True)
        elif kind == "Modify":
            self.modify(f, Node)
        else:
            raise self.refuse(f"run a {kind} operation")
        return op

    def modify(self, f: dict[str, Any], Node: Any) -> None:
        if f["with_"] is not None:
            self.own_iri(f["with_"], "use WITH graph")
        elif self.named:
            self.changed = True
            f["with_"] = self.scope
        using = f["using"] or []
        for _, iri in using:
            self.own_iri(iri, "use graph")
        if self.named and not using:
            self.changed = True
            f["using"] = [(False, self.scope), (True, self.scope)]
        self.template(f["delete"])
        self.template(f["insert"])
        for term in _graph_terms(f["where"]):
            if isinstance(term, ox.NamedNode):
                self.own_iri(term, "read graph")


def _graph_terms(x: Any) -> Iterator[Any]:
    """The graph terms of every ``GRAPH`` pattern in a tree."""
    if hasattr(x, "kind") and hasattr(x, "f"):
        if x.kind == "Graph":
            yield x.f["term"]
        for v in x.f.values():
            yield from _graph_terms(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _graph_terms(v)


def scope_update(text: str, scope: Any, *, base: str | None = None, prefixes: Any = None) -> str:
    """``text`` aimed at the graph ``scope`` (a ``NamedNode`` or ``DefaultGraph``); see the module docstring.

    Raises:
        ValueError: The update names another graph, or ``scope`` is a blank node.
        FormatError: (kind "sparql") The update is not valid SPARQL Update, with ``line`` / ``col`` of the text as scoped.
        ExecutionError: (kind "nesting") The update is nested too deeply to parse.
    """
    from starlayer.sparql.parse_sparql import (
        Node,
        ast_to_tree,
        parse_sparql_update,
    )
    from starlayer.sparql.sqe.to_text import render_sqe_tree

    if isinstance(scope, ox.BlankNode):
        raise ValueError(f"an update cannot be scoped to the blank-node graph {scope}: SPARQL cannot name it")
    head = "".join(f"PREFIX {p}: <{iri}>\n" for p, iri in (prefixes or {}).items())
    ast = parse_sparql_update(head + text, base)
    scoper = _Scoper(scope)
    operations = [op for op in (scoper.operation(op, Node) for op in ast.f["operations"]) if op is not None]
    if not scoper.changed:
        return text
    ast.f["operations"] = operations
    tree, root = ast_to_tree(ast)
    return render_sqe_tree(tree, root)
