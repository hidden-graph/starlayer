"""``extract_subgraph``: the shape fragment of a data graph (native engine, no pyshacl).

The result is the *shape fragment* of Delva, Dimou, Jakubowski and Van den Bussche (arXiv 2112.11796): the real, stored
triples the shapes read at their conforming targets, so that if the data conforms to the shapes the fragment conforms
too (the Conformance Theorem). The W3C draft ``shacl12-shape-fragments`` is not published yet; the neighborhood rules
follow the paper (Table 2) as the old ``starlayer.shacl.extract_subgraph`` did. Project extensions over the paper, all
inherited from the old function: the entry points are discovered from the shapes graph's own targets when ``shape=`` /
``focus_node=`` are omitted; ``sh:or`` keeps every disjunct that holds; ``sh:qualifiedValueShape`` with only a minimum
count keeps every qualifying value; ``sh:not`` and the failing branches of ``sh:xone`` keep a *full trace* (a superset
of the paper's neighborhood, which the Sufficiency Lemma allows).

Behaviour changes from the old function: ``sh:target`` (SPARQL targets, removed from SHACL 1.2) is ignored with a
``UserWarning`` naming the shape; ``focus_node=`` alone considers only shapes that really target that node (the old
docstring said so, its code tried every shape); deactivated nested shapes contribute nothing; ``sh:shape`` data links
(``<node> sh:shape <shape>``) are targets, as in the engine.

Entailment (the shapes graph's ``sh:entailment``, ``inference=``, ``ont_graph=``) is applied to a view of the data, as
``validate`` does; the returned triples are intersected with the real data graph, so an entailed-only triple never
appears.
"""

from __future__ import annotations

import warnings
from typing import Any

from rdflib.term import Node

from starlayer.shacl_engine import components  # noqa: F401  (registers the constraint components)
from starlayer.shacl_engine.entailment import resolve_data_view
from starlayer.shacl_engine.executor import Context
from starlayer.shacl_engine.paths import parse_path
from starlayer.shacl_engine.plan import SH, Path, Plan, Shape, ShapeError, Term
from starlayer.shacl_engine.terms import (
    RDF,
    RDFS,
    check_graphs,
    engine_view,
    from_engine_triple,
    text,
    to_engine,
    with_term_policy,
)

_Triple = tuple[Any, Any, Any]

_SECOND_PATH_PREDICATES = (SH.equals, SH.disjoint, SH.lessThan, SH.lessThanOrEquals)
_QUALIFIED_FAMILY = frozenset(
    {SH.qualifiedValueShape, SH.qualifiedMinCount, SH.qualifiedMaxCount, SH.qualifiedValueShapesDisjoint}
)
_NON_CONSTRAINT_METADATA = frozenset(
    {SH.path, SH.name, SH.description, SH.order, SH.group, SH.message, SH.severity, SH.deactivated, RDF.type}
)
_SH_TARGET = SH.target


def _items(graph: Any, head: Term) -> list[Term]:
    """Members of an rdf:List (cycle-safe, tolerant of a malformed tail)."""
    out: list[Term] = []
    seen: set = set()
    while head is not None and head != RDF.nil and head not in seen:
        seen.add(head)
        first = next(iter(graph.objects(head, RDF.first)), None)
        if first is None:
            break
        out.append(first)
        head = next(iter(graph.objects(head, RDF.rest)), None)
    return out


def _values(shape: Shape, pred: Term) -> list[Term]:
    """The values of a parameter, without those a reifier deactivates."""
    out = []
    for v in shape.params.get(pred, ()):
        a = shape.annotations.get((pred, v))
        if not (a and a["deactivated"]):
            out.append(v)
    return out


def _reverse(path: Path) -> Path:
    k = path.kind
    if k == "pred":
        return Path(kind="inverse", args=(path,), node=path.node)
    if k == "inverse":
        return path.args[0]
    if k == "seq":
        return Path(kind="seq", args=tuple(_reverse(a) for a in reversed(path.args)), node=path.node)
    return Path(kind=k, args=tuple(_reverse(a) for a in path.args), node=path.node)


def _walk(data: Any, path: Path, focus: Term) -> tuple[frozenset, set[_Triple]]:
    """Value nodes reached by ``path`` from ``focus`` and every data triple traversed to reach them."""
    k = path.kind
    if k == "pred":
        values = set(data.objects(focus, path.iri))
        return frozenset(values), {(focus, path.iri, v) for v in values}
    if k == "inverse":
        sub = path.args[0]
        if sub.kind == "pred":
            values = set(data.subjects(sub.iri, focus))
            return frozenset(values), {(v, sub.iri, focus) for v in values}
        return _walk(data, _reverse(sub), focus)
    if k == "alt":
        values, triples = set(), set()
        for sub in path.args:
            v, t = _walk(data, sub, focus)
            values |= v
            triples |= t
        return frozenset(values), triples
    if k == "seq":
        current, triples = {focus}, set()
        for sub in path.args:
            nxt: set = set()
            for node in current:
                v, t = _walk(data, sub, node)
                nxt |= v
                triples |= t
            current = nxt
        return frozenset(current), triples
    if k == "zero_or_one":
        v, t = _walk(data, path.args[0], focus)
        return frozenset(v | {focus}), t
    if k in ("zero_or_more", "one_or_more"):
        reachable: set = {focus} if k == "zero_or_more" else set()
        triples: set = set()
        frontier, seen = {focus}, {focus}
        while frontier:
            nxt = set()
            for node in frontier:
                v, t = _walk(data, path.args[0], node)
                triples |= t
                for x in v:
                    reachable.add(x)
                    if x not in seen:
                        seen.add(x)
                        nxt.add(x)
            frontier = nxt
        # every edge of every step, including those leaving the focus of a oneOrMore path (it is not itself reached)
        return frozenset(reachable), triples
    raise ShapeError(f"unknown path kind {k}")


def _type_paths(graph: Any, node: Term, cls: Term | None = None) -> set[_Triple]:
    """Triples on the ``rdf:type / rdfs:subClassOf*`` paths from ``node``; with ``cls`` only those ending at ``cls``
    (the evidence that ``node`` is an instance; empty if it is not), without it the whole type closure (what a negated
    class test needs)."""
    typed: set[_Triple] = set()
    edges: set[_Triple] = set()
    stack = []
    for type_ in graph.objects(node, RDF.type):
        typed.add((node, RDF.type, type_))
        stack.append(type_)
    seen: set = set()
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        for parent in graph.objects(current, RDFS.subClassOf):
            edges.add((current, RDFS.subClassOf, parent))
            stack.append(parent)
    if cls is None:
        return typed | edges
    reaches = {cls}
    changed = True
    while changed:
        changed = False
        for child, _, parent in edges:
            if parent in reaches and child not in reaches:
                reaches.add(child)
                changed = True
    return {t for t in typed if t[2] in reaches} | {t for t in edges if t[0] in reaches and t[2] in reaches}


class _Extractor:
    def __init__(self, data: Any, plan: Plan) -> None:
        self.data = data
        self.plan = plan
        self.shapes = plan.shapes_graph
        self.ctx = Context(data=data, plan=plan)

    def conforms(self, shape_node: Term, node: Term) -> bool:
        return self.ctx.conforms(shape_node, node)

    def _class_values(self, shape: Shape) -> list[Term]:
        classes: list[Term] = []
        for value in _values(shape, SH["class"]):
            if value == RDF.nil or (value, RDF.first, None) in self.shapes:
                classes.extend(_items(self.shapes, value))
            else:
                classes.append(value)
        return classes

    def _sole_qualified(self, shape: Shape) -> bool:
        preds = {p for p, _ in self.shapes.predicate_objects(shape.node)}
        return SH.qualifiedValueShape in preds and not (preds - _QUALIFIED_FAMILY - _NON_CONSTRAINT_METADATA)

    def _second_path_triples(self, shape: Shape, focus: Term) -> set[_Triple]:
        triples: set[_Triple] = set()
        for pred in _SECOND_PATH_PREDICATES:
            for other in _values(shape, pred):
                try:
                    path = parse_path(self.shapes, other)
                except ShapeError:
                    continue
                triples |= _walk(self.data, path, focus)[1]
        return triples

    def extract(self, shape: Shape, focus: Term, visiting: frozenset = frozenset(), full_trace: bool = False) -> set[_Triple]:
        """The triples ``shape`` reads at ``focus``: the minimal neighborhood (paper Table 2) or, with ``full_trace``,
        every triple the evaluation reads whether or not its branch holds (what a negated shape needs)."""
        if shape.deactivated:
            return set()
        key = (shape.node, focus, full_trace)
        if key in visiting:
            return set()  # recursion guard for mutually recursive shapes
        visiting = visiting | {key}
        data, plan = self.data, self.plan
        triples: set[_Triple] = set()

        if shape.is_property and shape.path is not None:
            path = shape.path
            value_nodes, path_triples = _walk(data, path, focus)
            qshapes = _values(shape, SH.qualifiedValueShape)
            narrow = (
                bool(qshapes)
                and bool(shape.params.get(SH.qualifiedMinCount))
                and not shape.params.get(SH.qualifiedMaxCount)
                and not full_trace
                and self._sole_qualified(shape)
            )
            if narrow and path.kind in ("pred", "inverse") and (path.kind == "pred" or path.args[0].kind == "pred"):
                qualifying = {v for v in value_nodes if any(self.conforms(q, v) for q in qshapes)}
                index = 2 if path.kind == "pred" else 0
                triples |= {t for t in path_triples if t[index] in qualifying}
                value_nodes = frozenset(qualifying)
            else:
                # a complex path with a qualified shape keeps every hop (safe over-inclusion; the old known boundary)
                triples |= path_triples
            triples |= self._second_path_triples(shape, focus)
            has_max = bool(shape.params.get(SH.qualifiedMaxCount))
            for q in qshapes:
                qshape = plan.shape(q)
                for v in value_nodes:
                    ok = self.conforms(q, v)
                    if ok or full_trace:
                        triples |= self.extract(qshape, v, visiting, full_trace)
                    if has_max and not ok and not full_trace:
                        # "at most n values satisfy the shape": a non-qualifying value must keep failing, so its evidence stays
                        triples |= self.extract(qshape, v, visiting, True)
        else:
            value_nodes = frozenset({focus})

        for cls in self._class_values(shape):
            for v in value_nodes:
                triples |= _type_paths(data, v, None if full_trace else cls)

        for pred in (SH.node,):
            for nested in _values(shape, pred):
                ns = plan.shape(nested)
                for v in value_nodes:
                    triples |= self.extract(ns, v, visiting, full_trace)
        for ps in shape.property_shapes:
            a = shape.annotations.get((SH.property, ps))
            if a and a["deactivated"]:
                continue
            pshape = plan.shape(ps)
            for v in value_nodes:
                triples |= self.extract(pshape, v, visiting, full_trace)

        for head in _values(shape, SH["and"]):
            for member in _items(self.shapes, head):
                ms = plan.shape(member)
                for v in value_nodes:
                    triples |= self.extract(ms, v, visiting, full_trace)

        for head in _values(shape, SH["or"]):
            for v in value_nodes:
                # every disjunct that holds (list order is an authoring artifact); a failing one cannot make the shape fail
                for member in _items(self.shapes, head):
                    if full_trace or self.conforms(member, v):
                        triples |= self.extract(plan.shape(member), v, visiting, full_trace)

        for head in _values(shape, SH.xone):
            for v in value_nodes:
                # the disjunct that holds gives its neighborhood, every other one its full trace so that it keeps failing
                holding_seen = False
                for member in _items(self.shapes, head):
                    ms = plan.shape(member)
                    if full_trace:
                        triples |= self.extract(ms, v, visiting, True)
                    elif not holding_seen and self.conforms(member, v):
                        holding_seen = True
                        triples |= self.extract(ms, v, visiting, False)
                    else:
                        triples |= self.extract(ms, v, visiting, True)

        for neg in _values(shape, SH["not"]):
            ns = plan.shape(neg)
            for v in value_nodes:
                triples |= self.extract(ns, v, visiting, True)
        return triples

    def target_triples(self, shape: Shape, node: Term) -> set[_Triple]:
        """The triples that make ``node`` a target of ``shape`` (the paper conjoins the shape with its target). Nothing
        for ``sh:targetNode``; a SPARQL ``sh:target`` is not supported."""
        triples: set[_Triple] = set()
        data = self.data
        for pred, value in shape.targets:
            if pred == SH.targetClass:
                triples |= _type_paths(data, node, value)
            elif pred == SH.targetSubjectsOf:
                triples |= {(node, value, o) for o in data.objects(node, value)}
            elif pred == SH.targetObjectsOf:
                triples |= {(s, value, node) for s in data.subjects(value, node)}
            elif pred == SH.shape:
                if (node, SH.shape, value) in data:
                    triples.add((node, SH.shape, value))
            elif pred == SH.targetWhere and self.conforms(value, node):
                triples |= self.extract(self.plan.shape(value), node)
        return triples


def _is_target_of(extractor: _Extractor, shape: Shape, node: Term) -> bool:
    return node in extractor.ctx.shape_focus(shape)


@with_term_policy
def extract_subgraph(
    data_graph: Any,
    shacl_graph: Any | None = None,
    ont_graph: Any | None = None,
    *,
    shape: Any | None = None,
    focus_node: Any | None = None,
    inference: Any | None = None,
    include_targets: bool = True,
) -> Any:
    """The subgraph covered by one ``(shape, focus_node)`` pair, or by every entry point the shapes graph declares.

    Same signature and return contract as ``starlayer.shacl.extract_subgraph``: a new ``StarLayerGraph`` that is the
    union of every conforming pair's extraction, empty (never ``None``) when nothing conforms. ``shacl_graph`` defaults to
    ``data_graph``. ``shape`` alone: that shape's own targets; ``focus_node`` alone: every shape that targets the node;
    both: that pair, whether or not the shape targets the node. ``include_targets`` adds the triples that make each
    focus node a target (class membership, subjects-of / objects-of triples). Raises ``TypeError`` for a ``str``
    ``shape`` / ``focus_node`` and ``ValueError`` for a shape that is not in the shapes graph. ``sh:target`` is ignored
    with a ``UserWarning`` (SPARQL targets are not part of SHACL 1.2).
    """
    for argument, value in (("shape", shape), ("focus_node", focus_node)):
        if value is not None and not isinstance(value, Node):
            raise TypeError(f"{argument} must be an rdflib term such as URIRef, not {type(value).__name__}: {value!r}")
    check_graphs((data_graph, "data graph"), (shacl_graph, "shapes graph"), (ont_graph, "ontology graph"))
    shapes = engine_view(shacl_graph if shacl_graph is not None else data_graph, "shapes graph")
    shape, focus_node = to_engine(shape), to_engine(focus_node)
    plan = Plan(shapes_graph=shapes)
    view = resolve_data_view(data_graph, shapes, inference=inference, ont_graph=ont_graph)
    ex = _Extractor(view, plan)

    if shape is not None:
        if next(iter(shapes.predicate_objects(shape)), None) is None:
            raise ValueError(f"shape {text(shape)!r} is not a shape in the shapes graph")
        candidates = [shape]
    else:
        candidates = plan.all_shape_nodes()

    found: set[_Triple] = set()
    for node in candidates:
        sobj = plan.shape(node)
        if sobj.deactivated:
            continue
        if (node, _SH_TARGET, None) in shapes:
            warnings.warn(
                f"sh:target on shape {text(node)} is ignored: SPARQL-based targets are not part of SHACL 1.2",
                UserWarning,
                stacklevel=2,
            )
        if focus_node is not None:
            if shape is None and not _is_target_of(ex, sobj, focus_node):
                continue
            foci = [focus_node]
        else:
            foci = ex.ctx.shape_focus(sobj)
        for focus in foci:
            if not ex.conforms(node, focus):
                continue
            found |= ex.extract(sobj, focus)
            if include_targets:
                found |= ex.target_triples(sobj, focus)

    from starlayer.graph.graph.starlayer_graph import StarLayerGraph

    out = StarLayerGraph()
    for t in found:
        rt = from_engine_triple(t)  # engine terms -> the caller's term model
        if rt in data_graph:
            out.add(rt)
    return out


__all__ = ["extract_subgraph"]
