"""SHACL property paths: parsing a path term from the shapes graph and evaluating it on the data graph.

Paths are sets: ``eval_path`` returns each reached node once, in a stable order (breadth-first discovery order, with
graph order inside a step). Transitive closures track visited nodes, so cycles terminate. ``zero_or_more`` and
``zero_or_one`` include the start node itself. Malformed paths raise ``ShapeError``.
"""

from __future__ import annotations

from typing import Any

from starlayer.shacl_engine.plan import SH, Path, ShapeError, Term
from starlayer.shacl_engine.terms import RDF, BlankNode, Literal, NamedNode

_UNARY = {
    SH.inversePath: "inverse",
    SH.zeroOrMorePath: "zero_or_more",
    SH.oneOrMorePath: "one_or_more",
    SH.zeroOrOnePath: "zero_or_one",
}
_KEYWORDS = (*_UNARY, SH.alternativePath)


def _read_list(graph: Any, head: Term, what: str) -> list[Term]:
    items: list[Term] = []
    seen: set = set()
    node = head
    while node != RDF.nil:
        if node in seen:
            raise ShapeError(f"{what}: cyclic rdf:List")
        seen.add(node)
        firsts = list(graph.objects(node, RDF.first))
        rests = list(graph.objects(node, RDF.rest))
        if len(firsts) != 1 or len(rests) != 1:
            raise ShapeError(f"{what}: malformed rdf:List at {node!r}")
        items.append(firsts[0])
        node = rests[0]
    return items


def parse_path(graph: Any, node: Term, _stack: tuple = ()) -> Path:
    if isinstance(node, NamedNode):
        return Path(kind="pred", iri=node, node=node)
    if isinstance(node, Literal) or not isinstance(node, BlankNode):
        raise ShapeError(f"a property path must be an IRI or blank node, got {node!r}")
    if node in _stack:
        raise ShapeError(f"cyclic property path at {node!r}")
    stack = _stack + (node,)
    present = [kw for kw in _KEYWORDS if (node, kw, None) in graph]
    is_list = (node, RDF.first, None) in graph
    if len(present) + (1 if is_list else 0) != 1:
        raise ShapeError(f"{node!r} is not a well-formed property path ({len(present)} path keywords)")
    if is_list:
        members = _read_list(graph, node, "sequence path")
        if len(members) < 2:
            raise ShapeError("a sequence path needs at least two members")
        return Path(kind="seq", args=tuple(parse_path(graph, m, stack) for m in members), node=node)
    kw = present[0]
    values = list(graph.objects(node, kw))
    if len(values) != 1:
        raise ShapeError(f"{node!r}: {kw} must have exactly one value")
    if kw == SH.alternativePath:
        head = values[0]
        if head == RDF.nil or isinstance(head, Literal):
            raise ShapeError("an alternative path needs an rdf:List of at least two members")
        members = _read_list(graph, head, "alternative path")
        if len(members) < 2:
            raise ShapeError("an alternative path needs at least two members")
        return Path(kind="alt", args=tuple(parse_path(graph, m, stack) for m in members), node=node)
    return Path(kind=_UNARY[kw], args=(parse_path(graph, values[0], stack),), node=node)


def _dedupe(items: Any) -> list[Term]:
    items = items if isinstance(items, list) else list(items)
    if len(items) < 2:  # nothing to de-duplicate (the common case: functional properties, missing values)
        return items
    return list(dict.fromkeys(items))


def _step(data: Any, path: Path, focus: Term) -> list[Term]:
    k = path.kind
    if k == "pred":
        return _dedupe(data.objects(focus, path.iri))
    if k == "inverse":
        sub = path.args[0]
        if sub.kind == "pred":
            return _dedupe(data.subjects(sub.iri, focus))
        return _dedupe(_inverse_eval(data, sub, focus))
    if k == "seq":
        current = [focus]
        for sub in path.args:
            nxt: dict = {}
            for n in current:
                for m in _step(data, sub, n):
                    nxt[m] = None
            current = list(nxt)
        return current
    if k == "alt":
        out: dict = {}
        for sub in path.args:
            for m in _step(data, sub, focus):
                out[m] = None
        return list(out)
    if k == "zero_or_one":
        return _dedupe([focus, *_step(data, path.args[0], focus)])
    if k in ("zero_or_more", "one_or_more"):
        sub = path.args[0]
        reached: dict = {}
        queue = [focus]
        visited = {focus}
        while queue:
            n = queue.pop(0)
            for m in _step(data, sub, n):
                reached.setdefault(m, None)
                if m not in visited:
                    visited.add(m)
                    queue.append(m)
        if k == "zero_or_more":
            return _dedupe([focus, *reached])
        return list(reached)
    raise ValueError(f"unknown path kind {k}")


def _reverse(path: Path) -> Path:
    """The path that traverses ``path`` backwards, so ``sh:inversePath`` of a complex path is evaluated forwards."""
    k = path.kind
    if k == "pred":
        return Path(kind="inverse", args=(path,), node=path.node)
    if k == "inverse":
        return path.args[0]
    if k == "seq":
        return Path(kind="seq", args=tuple(_reverse(a) for a in reversed(path.args)), node=path.node)
    return Path(kind=k, args=tuple(_reverse(a) for a in path.args), node=path.node)


def _inverse_eval(data: Any, sub: Path, focus: Term) -> list[Term]:
    return _step(data, _reverse(sub), focus)


def eval_path(data: Any, path: Path, focus: Term) -> list[Term]:
    """Value nodes reached from ``focus`` along ``path``: a set, each node once, in a stable order."""
    return _step(data, path, focus)
