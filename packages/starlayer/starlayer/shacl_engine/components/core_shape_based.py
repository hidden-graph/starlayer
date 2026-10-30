"""SHACL 1.2 Core: logical (not, and, or, xone), shape-based (node, qualified*), closed, reifier shape, root class."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from rdflib import RDF, RDFS, BNode, Literal, URIRef
from rdflib.namespace import XSD

from starlayer.graph.model import TripleTerm
from starlayer.shacl_engine.components.registry import Violation, component
from starlayer.shacl_engine.plan import SH, Path, ShapeError

_RDF_REIFIES = RDF.reifies if hasattr(RDF, "reifies") else URIRef(str(RDF) + "reifies")


def shacl_list(graph: Any, head: Any) -> list[Any]:
    """Members of a well-formed SHACL list (IRI or blank node cells, exactly one first/rest, no cycle); else ShapeError."""
    members: list[Any] = []
    seen: set = set()
    cell = head
    while cell != RDF.nil:
        if cell in seen or not isinstance(cell, URIRef | BNode):
            raise ShapeError(f"malformed list at {head}")
        seen.add(cell)
        firsts, rests = list(graph.objects(cell, RDF.first)), list(graph.objects(cell, RDF.rest))
        if len(firsts) != 1 or len(rests) != 1:
            raise ShapeError(f"malformed list at {head}")
        members.append(firsts[0])
        cell = rests[0]
    if any(True for _ in graph.objects(RDF.nil, RDF.first)) or any(True for _ in graph.objects(RDF.nil, RDF.rest)):
        raise ShapeError(f"malformed list at {head}")
    return members


def _boolean(term: Any, what: str) -> bool:
    if isinstance(term, Literal) and term.datatype == XSD.boolean and str(term) in ("true", "false", "1", "0"):
        return str(term) in ("true", "1")
    raise ShapeError(f"{what} must be an xsd:boolean literal, got {term!r}")


def _only_true(term: Any, what: str) -> bool:
    """Like ``_boolean`` but only the lexical form ``"true"`` activates (``"1"`` is a valid but inactive boolean)."""
    return _boolean(term, what) and str(term) == "true"


def _count(term: Any, what: str) -> int:
    if isinstance(term, Literal) and term.datatype == XSD.integer and str(term).lstrip("+-").isdigit():
        return int(str(term))
    raise ShapeError(f"{what} must be an xsd:integer literal, got {term!r}")


def _shape_refs(terms: tuple, what: str) -> tuple:
    for t in terms:
        if isinstance(t, Literal):
            raise ShapeError(f"{what} must be an IRI or blank node, got {t!r}")
    return terms


def _lists(ctx: Any, terms: tuple, what: str) -> Iterator[list[Any]]:
    for t in terms:
        members = shacl_list(ctx.shapes, t)
        _shape_refs(tuple(members), what)
        yield members


@component(SH.NotConstraintComponent, SH["not"])
def not_(ctx, shape, params, focus, values):
    for s in _shape_refs(params[SH["not"]], "sh:not"):
        for v in values:
            if ctx.conforms(s, v):
                yield Violation(value=v)


@component(SH.AndConstraintComponent, SH["and"])
def and_(ctx, shape, params, focus, values):
    for members in _lists(ctx, params[SH["and"]], "sh:and"):
        for v in values:
            if not all(ctx.conforms(m, v) for m in members):
                yield Violation(value=v)


@component(SH.OrConstraintComponent, SH["or"])
def or_(ctx, shape, params, focus, values):
    for members in _lists(ctx, params[SH["or"]], "sh:or"):
        for v in values:
            if not any(ctx.conforms(m, v) for m in members):
                yield Violation(value=v)


@component(SH.XoneConstraintComponent, SH.xone)
def xone(ctx, shape, params, focus, values):
    for members in _lists(ctx, params[SH.xone], "sh:xone"):
        for v in values:
            if sum(1 for m in members if ctx.conforms(m, v)) != 1:
                yield Violation(value=v)


@component(SH.NodeConstraintComponent, SH.node)
def node(ctx, shape, params, focus, values):
    for s in _shape_refs(params[SH.node], "sh:node"):
        for v in values:
            if not ctx.conforms(s, v):
                yield Violation(value=v)


def _siblings(ctx: Any, shape: Any, qvs: Any) -> list[Any]:
    """Other sh:qualifiedValueShape values of the property shapes that share a parent shape with this one."""
    out: list[Any] = []
    for parent in ctx.shapes.subjects(SH.property, shape.node):
        for sibling_ps in ctx.shapes.objects(parent, SH.property):
            if sibling_ps == shape.node:
                continue
            for q in ctx.shapes.objects(sibling_ps, SH.qualifiedValueShape):
                if q != qvs and q not in out:
                    out.append(q)
    return out


def _qualified(ctx, shape, params, values) -> Iterator[tuple[int, Any]]:
    """For each sh:qualifiedValueShape, the number of value nodes conforming to it (and to no sibling if disjoint)."""
    shapes = _shape_refs(params.get(SH.qualifiedValueShape, ()), "sh:qualifiedValueShape")
    disjoint = False
    for d in params.get(SH.qualifiedValueShapesDisjoint, ()):
        disjoint = disjoint or _boolean(d, "sh:qualifiedValueShapesDisjoint")
    for q in shapes:
        siblings = _siblings(ctx, shape, q) if disjoint else []
        n = sum(1 for v in values if ctx.conforms(q, v) and not any(ctx.conforms(s, v) for s in siblings))
        yield n, q


@component(SH.QualifiedMinCountConstraintComponent, SH.qualifiedValueShape, SH.qualifiedMinCount, SH.qualifiedValueShapesDisjoint)
def qualified_min(ctx, shape, params, focus, values):
    for m in params.get(SH.qualifiedMinCount, ()):
        minimum = _count(m, "sh:qualifiedMinCount")
        for n, _ in _qualified(ctx, shape, params, values):
            if n < minimum:
                yield Violation()


@component(SH.QualifiedMaxCountConstraintComponent, SH.qualifiedValueShape, SH.qualifiedMaxCount, SH.qualifiedValueShapesDisjoint)
def qualified_max(ctx, shape, params, focus, values):
    for m in params.get(SH.qualifiedMaxCount, ()):
        maximum = _count(m, "sh:qualifiedMaxCount")
        for n, _ in _qualified(ctx, shape, params, values):
            if n > maximum:
                yield Violation()


def _collect_properties(shapes: Any, node_: Any, visited: set) -> set:
    """collectProperties from the sh:ByTypes definition: own sh:property paths, plus, for a class, its superclasses'
    and the targeting shapes' properties, plus, for a node shape, those of its sh:node shapes."""
    if node_ in visited:
        return set()
    visited.add(node_)
    props = {p for ps in shapes.objects(node_, SH.property) for p in shapes.objects(ps, SH.path) if isinstance(p, URIRef)}
    types = set(shapes.objects(node_, RDF.type))
    if isinstance(node_, URIRef) and (RDFS.Class in types or SH.ShapeClass in types):
        for sup in shapes.objects(node_, RDFS.subClassOf):
            props |= _collect_properties(shapes, sup, visited)
        for other in shapes.subjects(SH.targetClass, node_):
            props |= _collect_properties(shapes, other, visited)
    if SH.NodeShape in types:
        for linked in shapes.objects(node_, SH.node):
            props |= _collect_properties(shapes, linked, visited)
    return props


@component(SH.ClosedConstraintComponent, SH.closed, SH.ignoredProperties)
def closed(ctx, shape, params, focus, values):
    closed_vals = params.get(SH.closed, ())
    if len(closed_vals) != 1:
        raise ShapeError(f"{shape.node}: sh:ignoredProperties without exactly one sh:closed")
    mode = closed_vals[0]
    by_types = mode == SH.ByTypes
    if not by_types and not _boolean(mode, "sh:closed"):
        return
    ignored: set = set()
    for members in _lists(ctx, params.get(SH.ignoredProperties, ()), "sh:ignoredProperties"):
        if not all(isinstance(m, URIRef) for m in members):
            raise ShapeError("sh:ignoredProperties members must be IRIs")
        ignored.update(members)
    declared: set = set()
    for ps in shape.property_shapes:
        for p in ctx.shapes.objects(ps, SH.path):
            if isinstance(p, URIRef):
                declared.add(p)
    for v in values:
        if isinstance(v, Literal | TripleTerm):
            continue
        if by_types:
            allowed = {RDF.type} | ignored
            for t in set(ctx.data.objects(v, RDF.type)):
                allowed |= _collect_properties(ctx.shapes, t, set())
        else:
            allowed = declared | ignored
        for _, p, o in ctx.data.triples((v, None, None)):
            if p not in allowed:
                yield Violation(path=Path(kind="pred", iri=p, node=p), value=o)


@component(SH.ReifierShapeConstraintComponent, SH.reifierShape, SH.reificationRequired)
def reifier_shape(ctx, shape, params, focus, values):
    if shape.path is None or shape.path.kind != "pred":
        raise ShapeError(f"{shape.node}: sh:reifierShape/sh:reificationRequired need a property shape with an IRI path")
    required = any(_only_true(r, "sh:reificationRequired") for r in params.get(SH.reificationRequired, ()))
    rshapes = _shape_refs(params.get(SH.reifierShape, ()), "sh:reifierShape")
    for v in values:
        reifiers = list(ctx.data.subjects(_RDF_REIFIES, TripleTerm(focus, shape.path.iri, v)))
        if required and not reifiers:
            yield Violation(value=v)
        for s in rshapes:
            for r in reifiers:
                if not ctx.conforms(s, r):
                    yield Violation(value=v)


@component(SH.RootClassConstraintComponent, SH.rootClass)
def root_class(ctx, shape, params, focus, values):
    roots = params[SH.rootClass]
    for r in roots:
        if not isinstance(r, URIRef | BNode):
            raise ShapeError(f"sh:rootClass must be an IRI or blank node, got {r!r}")
    for v in values:
        seen, stack = set(), [v]
        found = False
        while stack and not found:
            c = stack.pop()
            if c in roots:
                found = True
            elif c not in seen:
                seen.add(c)
                stack.extend(ctx.data.objects(c, RDFS.subClassOf))
        if not found:
            yield Violation(value=v)
