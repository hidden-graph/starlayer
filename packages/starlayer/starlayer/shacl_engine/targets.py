"""Shape discovery and targets (SHACL 1.2 Core).

``shape_targets`` reads the target declarations of one shape (including the implicit class target of a node that is both
a shape and a class, and the data-graph ``sh:shape`` link as the pseudo target ``(sh:shape, shape)``). ``focus_nodes`` resolves them against the data graph: ``rdfs:subClassOf*`` expansion for class
targets uses the data graph only. ``sh:targetWhere`` takes a shape; its focus nodes are the data graph nodes that
conform to it, decided by the ``conforms(shape_node, node)`` callable the executor passes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rdflib import OWL, RDF, RDFS, URIRef

from starlayer.shacl_engine.plan import SH, Term

_TARGET_PREDICATES = (SH.targetNode, SH.targetClass, SH.targetSubjectsOf, SH.targetObjectsOf, SH.targetWhere)
_SHAPE_TYPES = (SH.NodeShape, SH.PropertyShape, SH.Shape, SH.ShapeClass)
_CLASS_TYPES = (RDFS.Class, OWL.Class, SH.ShapeClass)


def _types(graph: Any, node: Term) -> set:
    return set(graph.objects(node, RDF.type))


def _is_implicit_class_target(graph: Any, node: Term) -> bool:
    types = _types(graph, node)
    return any(t in types for t in _SHAPE_TYPES) and any(t in types for t in _CLASS_TYPES)


def shape_targets(graph: Any, node: Term) -> list[tuple[URIRef, Term]]:
    out: list[tuple[URIRef, Term]] = []
    for pred in _TARGET_PREDICATES:
        for v in graph.objects(node, pred):
            out.append((pred, v))
    if _is_implicit_class_target(graph, node) and (SH.targetClass, node) not in out:
        out.append((SH.targetClass, node))
    # SHACL 1.2: a data graph node can name its shapes with ``sh:shape``; resolved against the data graph.
    out.append((SH.shape, node))
    return out


def declared_shape_nodes(graph: Any) -> list[Term]:
    nodes: dict = {}
    for typ in _SHAPE_TYPES:
        for s in graph.subjects(RDF.type, typ):
            nodes.setdefault(s, None)
    for pred in _TARGET_PREDICATES:
        for s in graph.subjects(pred, None):
            nodes.setdefault(s, None)
    return list(nodes)


def _class_closure(data: Any, cls: Term) -> list[Term]:
    """``cls`` and all its rdfs:subClassOf descendants in the data graph (cycle-safe)."""
    seen: dict = {cls: None}
    queue = [cls]
    while queue:
        c = queue.pop()
        for sub in data.subjects(RDFS.subClassOf, c):
            if sub not in seen:
                seen[sub] = None
                queue.append(sub)
    return list(seen)


def _all_nodes(data: Any) -> list[Term]:
    nodes: dict = {}
    for s, _p, o in data.triples((None, None, None)):
        nodes.setdefault(s, None)
        nodes.setdefault(o, None)
    return list(nodes)


def focus_nodes(
    data: Any,
    shapes: Any,
    targets: tuple[tuple[URIRef, Term], ...],
    conforms: Callable[[Term, Term], bool] | None = None,
) -> list[Term]:
    """Focus nodes of the given targets, each once, in target order. ``conforms`` is only needed for
    ``sh:targetWhere`` (without it, targetWhere contributes nothing)."""
    out: dict = {}
    for pred, value in targets:
        if pred == SH.targetNode:
            out.setdefault(value, None)
        elif pred == SH.targetClass:
            for cls in _class_closure(data, value):
                for inst in data.subjects(RDF.type, cls):
                    out.setdefault(inst, None)
        elif pred == SH.shape:
            for s in data.subjects(SH.shape, value):
                out.setdefault(s, None)
        elif pred == SH.targetSubjectsOf:
            for s in data.subjects(value, None):
                out.setdefault(s, None)
        elif pred == SH.targetObjectsOf:
            for o in data.objects(None, value):
                out.setdefault(o, None)
        elif pred == SH.targetWhere and conforms is not None:
            for n in _all_nodes(data):
                if n not in out and conforms(value, n):
                    out[n] = None
    return list(out)
