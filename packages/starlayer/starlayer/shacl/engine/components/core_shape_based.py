"""SHACL 1.2 Core: logical (not, and, or, xone), shape-based (node, qualified*), closed, reifier shape, root class."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from starlayer.errors import ShapeError
from starlayer.shacl.engine.components.registry import Violation, component, words
from starlayer.shacl.engine.plan import SH, Path
from starlayer.shacl.engine.terms import (
    RDF,
    RDFS,
    XSD,
    BlankNode,
    Literal,
    NamedNode,
    Triple,
    text,
)

_RDF_REIFIES = RDF.reifies


def shacl_list(graph: Any, head: Any) -> list[Any]:
    """Members of a well-formed SHACL list (IRI or blank node cells, exactly one first/rest, no cycle); else ShapeError."""
    members: list[Any] = []
    seen: set = set()
    cell = head
    while cell != RDF.nil:
        if cell in seen or not isinstance(cell, NamedNode | BlankNode):
            raise ShapeError(f"malformed list at {text(head)}", kind="compile")
        seen.add(cell)
        firsts, rests = list(graph.objects(cell, RDF.first)), list(graph.objects(cell, RDF.rest))
        if len(firsts) != 1 or len(rests) != 1:
            raise ShapeError(f"malformed list at {text(head)}", kind="compile")
        members.append(firsts[0])
        cell = rests[0]
    if any(True for _ in graph.objects(RDF.nil, RDF.first)) or any(True for _ in graph.objects(RDF.nil, RDF.rest)):
        raise ShapeError(f"malformed list at {text(head)}", kind="compile")
    return members


def _boolean(term: Any, what: str) -> bool:
    if isinstance(term, Literal) and term.datatype == XSD.boolean and term.value in ("true", "false", "1", "0"):
        return term.value in ("true", "1")
    raise ShapeError(f"{what} must be an xsd:boolean literal, got {term!r}", kind="compile")


def _only_true(term: Any, what: str) -> bool:
    """Like ``_boolean`` but only the lexical form ``"true"`` activates (``"1"`` is a valid but inactive boolean)."""
    return _boolean(term, what) and term.value == "true"


_INTEGER = re.compile(r"[+-]?[0-9]+")  # the xsd:integer lexical form; str.isdigit() also accepts "\u00b2" and "\u0663"


def _count(term: Any, what: str) -> int:
    if isinstance(term, Literal) and term.datatype == XSD.integer and _INTEGER.fullmatch(term.value):
        return int(term.value)
    raise ShapeError(f"{what} must be an xsd:integer literal, got {term!r}", kind="compile")


def _shape_refs(terms: tuple, what: str) -> tuple:
    for t in terms:
        if isinstance(t, Literal):
            raise ShapeError(f"{what} must be an IRI or blank node, got {t!r}", kind="compile")
    return terms


def _lists(shapes: Any, terms: tuple, what: str) -> Iterator[list[Any]]:
    for t in terms:
        members = shacl_list(shapes, t)
        _shape_refs(tuple(members), what)
        yield members


def _refs_check(pred: Any):
    def check(shapes, shape, params):
        return _shape_refs(params[pred], f"sh:{pred.value.rsplit('#', 1)[-1]}")

    return check


def _lists_check(pred: Any, what: str):
    def check(shapes, shape, params):
        return [m for members in _lists(shapes, params[pred], what) for m in members]

    return check


@component(SH.NotConstraintComponent, SH["not"], check=_refs_check(SH["not"]))
def not_(ctx, shape, params, focus, values):
    """sh:not: each value node must not conform to the referenced shape."""
    for s in _shape_refs(params[SH["not"]], "sh:not"):
        for v in values:
            if ctx.conforms(s, v, negated=True):
                yield Violation(value=v)


@component(SH.AndConstraintComponent, SH["and"], check=_lists_check(SH["and"], "sh:and"))
def and_(ctx, shape, params, focus, values):
    """sh:and: each value node must conform to every shape in the list."""
    for members in _lists(ctx.shapes, params[SH["and"]], "sh:and"):
        for v in values:
            if not all(ctx.conforms(m, v) for m in members):
                yield Violation(value=v)


@component(SH.OrConstraintComponent, SH["or"], check=_lists_check(SH["or"], "sh:or"))
def or_(ctx, shape, params, focus, values):
    """sh:or: each value node must conform to at least one shape in the list."""
    for members in _lists(ctx.shapes, params[SH["or"]], "sh:or"):
        for v in values:
            if not any(ctx.conforms(m, v) for m in members):
                yield Violation(value=v)


@component(SH.XoneConstraintComponent, SH.xone, check=_lists_check(SH.xone, "sh:xone"))
def xone(ctx, shape, params, focus, values):
    """sh:xone: each value node must conform to exactly one shape in the list."""
    for members in _lists(ctx.shapes, params[SH.xone], "sh:xone"):
        for v in values:
            if sum(1 for m in members if ctx.conforms(m, v)) != 1:
                yield Violation(value=v)


@component(SH.NodeConstraintComponent, SH.node, check=_refs_check(SH.node))
def node(ctx, shape, params, focus, values):
    """sh:node: each value node must conform to the referenced node shape; that shape's own results are reported as sh:detail."""
    for s in _shape_refs(params[SH.node], "sh:node"):
        for v in values:
            if not ctx.conforms(s, v):
                # Core 6.9.2.6: the node shape's own results for the value node may be reported as sh:detail
                yield Violation(value=v, details=tuple(ctx.detail_results(s, v)))


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


def _qualified_message(ctx, shape, params, lead: str, limit: int, qvs: Any, found: int) -> str:
    """``Needs at least 2 values for ex:p conforming to ex:DuckShape, found 1``."""
    wd = words(ctx)
    disjoint = any(_only_true(d, "sh:qualifiedValueShapesDisjoint") for d in params.get(SH.qualifiedValueShapesDisjoint, ()))
    also = " and to no sibling qualified shape" if disjoint else ""
    path = shape.path.node if shape.path is not None else None
    return f"{lead} {limit} value{'' if limit == 1 else 's'}{wd.on(path)} conforming to {wd.shape(qvs)}{also}, found {found}"  # str-ok: text


def _qualified_check(count_pred: Any, what: str):
    def check(shapes, shape, params):
        for m in params.get(count_pred, ()):
            _count(m, what)
        for d in params.get(SH.qualifiedValueShapesDisjoint, ()):
            _boolean(d, "sh:qualifiedValueShapesDisjoint")
        return _shape_refs(params.get(SH.qualifiedValueShape, ()), "sh:qualifiedValueShape")

    return check


@component(
    SH.QualifiedMinCountConstraintComponent,
    SH.qualifiedValueShape,
    SH.qualifiedMinCount,
    SH.qualifiedValueShapesDisjoint,
    check=_qualified_check(SH.qualifiedMinCount, "sh:qualifiedMinCount"),
)
def qualified_min(ctx, shape, params, focus, values):
    """sh:qualifiedMinCount: at least that many value nodes conform to sh:qualifiedValueShape (and, if sh:qualifiedValueShapesDisjoint, to no sibling's).

    One violation is yielded for each (qualifiedMinCount, qualifiedValueShape) pair that falls short.
    """
    for m in params.get(SH.qualifiedMinCount, ()):
        minimum = _count(m, "sh:qualifiedMinCount")
        for n, q in _qualified(ctx, shape, params, values):
            if n < minimum:
                yield Violation(message=_qualified_message(ctx, shape, params, "Needs at least", minimum, q, n))


@component(
    SH.QualifiedMaxCountConstraintComponent,
    SH.qualifiedValueShape,
    SH.qualifiedMaxCount,
    SH.qualifiedValueShapesDisjoint,
    check=_qualified_check(SH.qualifiedMaxCount, "sh:qualifiedMaxCount"),
)
def qualified_max(ctx, shape, params, focus, values):
    """sh:qualifiedMaxCount: at most that many value nodes conform to sh:qualifiedValueShape (and, if sh:qualifiedValueShapesDisjoint, to no sibling's).

    One violation is yielded for each (qualifiedMaxCount, qualifiedValueShape) pair that is exceeded.
    """
    for m in params.get(SH.qualifiedMaxCount, ()):
        maximum = _count(m, "sh:qualifiedMaxCount")
        for n, q in _qualified(ctx, shape, params, values):
            if n > maximum:
                yield Violation(message=_qualified_message(ctx, shape, params, "Allows at most", maximum, q, n))


def _shacl_types(shapes: Any, node_: Any) -> set:
    """The SHACL types of a node: its rdf:type values and their rdfs:subClassOf ancestors, in the shapes graph."""
    found: set = set()
    stack = list(shapes.objects(node_, RDF.type))
    while stack:
        t = stack.pop()
        if t not in found:
            found.add(t)
            stack.extend(shapes.objects(t, RDFS.subClassOf))
    return found


def _collect_properties(shapes: Any, node_: Any, visited: set) -> set:
    """collectProperties from the sh:ByTypes definition: own sh:property paths, plus, for a class, its superclasses'
    and the targeting shapes' properties, plus, for a node shape, those of its sh:node shapes."""
    if node_ in visited:
        return set()
    visited.add(node_)
    props = {p for ps in shapes.objects(node_, SH.property) for p in shapes.objects(ps, SH.path) if isinstance(p, NamedNode)}
    types = _shacl_types(shapes, node_)
    if isinstance(node_, NamedNode) and (RDFS.Class in types or SH.ShapeClass in types):
        for sup in shapes.objects(node_, RDFS.subClassOf):
            props |= _collect_properties(shapes, sup, visited)
        for other in shapes.subjects(SH.targetClass, node_):
            props |= _collect_properties(shapes, other, visited)
    if SH.NodeShape in types:
        for linked in shapes.objects(node_, SH.node):
            props |= _collect_properties(shapes, linked, visited)
    return props


def _closed_setup(shapes: Any, shape: Any, params: dict) -> tuple[bool, set] | None:
    """``(by_types, ignored properties)`` of a closed shape, ``None`` when the shape is not closed; ShapeError for a bad value."""
    closed_vals = params.get(SH.closed, ())
    if not closed_vals:
        return None  # sh:closed is the only required parameter: sh:ignoredProperties alone is not an instance of the component
    if len(closed_vals) != 1:
        raise ShapeError(f"{text(shape.node)}: more than one sh:closed", kind="compile")
    mode = closed_vals[0]
    by_types = mode == SH.ByTypes
    if not by_types and not _boolean(mode, "sh:closed"):
        return None
    ignored: set = set()
    for members in _lists(shapes, params.get(SH.ignoredProperties, ()), "sh:ignoredProperties"):
        if not all(isinstance(m, NamedNode) for m in members):
            raise ShapeError("sh:ignoredProperties members must be IRIs", kind="compile")
        ignored.update(members)
    return by_types, ignored


@component(SH.ClosedConstraintComponent, SH.closed, SH.ignoredProperties, check=lambda shapes, shape, params: _closed_setup(shapes, shape, params) and None)
def closed(ctx, shape, params, focus, values):
    """sh:closed: when true, a value node may only have the properties its shape declares or sh:ignoredProperties lists.

    With the value sh:ByTypes, the properties declared by the value node's types are allowed instead.
    """
    setup = _closed_setup(ctx.shapes, shape, params)
    if setup is None:
        return
    by_types, ignored = setup
    declared: set = set()
    for ps in shape.property_shapes:
        for p in ctx.shapes.objects(ps, SH.path):
            if isinstance(p, NamedNode):
                declared.add(p)
    wd = words(ctx)
    for v in values:
        if isinstance(v, Literal | Triple):
            continue
        if by_types:
            allowed = {RDF.type} | ignored
            for t in set(ctx.data.objects(v, RDF.type)):
                allowed |= _collect_properties(ctx.shapes, t, set())
        else:
            allowed = declared | ignored
        for _, p, o in ctx.data.triples((v, None, None)):
            if p not in allowed:
                why = "which none of its types declare" if by_types else "which the closed shape does not allow"
                holder = wd.data(v)
                holder = "A blank node" if holder == "a blank node" else holder
                yield Violation(path=Path(kind="pred", iri=p, node=p), value=o, message=f"{holder} has the property {wd.shape(p)}, {why}")  # str-ok: text


def _reifier_params(shape: Any, params: dict) -> tuple[bool, tuple]:
    """``(reification required, reifier shapes)``; ShapeError unless the shape is a property shape with an IRI path."""
    if shape.path is None or shape.path.kind != "pred":
        raise ShapeError(f"{text(shape.node)}: sh:reifierShape/sh:reificationRequired need a property shape with an IRI path", kind="compile")
    required = any(_only_true(r, "sh:reificationRequired") for r in params.get(SH.reificationRequired, ()))
    return required, _shape_refs(params.get(SH.reifierShape, ()), "sh:reifierShape")


@component(SH.ReifierShapeConstraintComponent, SH.reifierShape, SH.reificationRequired, check=lambda shapes, shape, params: _reifier_params(shape, params)[1])
def reifier_shape(ctx, shape, params, focus, values):
    """sh:reifierShape / sh:reificationRequired: the reifiers of each (focus, path, value) triple conform to every reifier shape.

    Needs a property shape with an IRI path; anything else raises ShapeError.
    """
    required, rshapes = _reifier_params(shape, params)
    wd = words(ctx)
    for v in values:
        claim = f"The claim ({wd.data(focus)} {wd.shape(shape.path.iri)} {wd.data(v)})"  # str-ok: text
        reifiers = (
            list(ctx.data.subjects(_RDF_REIFIES, Triple(focus, shape.path.iri, v)))
            if not isinstance(focus, Literal | Triple)
            else []
        )
        if required and not reifiers:
            yield Violation(value=v, message=f"{claim} has no reifier")  # str-ok: text
        for s in rshapes:
            for r in reifiers:
                if not ctx.conforms(s, r):
                    yield Violation(value=v, message=f"{claim} has a reifier that does not conform to {wd.shape(s)}")  # str-ok: text


def _roots(shapes: Any, params: dict) -> set:
    roots: set = set()
    for r in params[SH.rootClass]:
        if isinstance(r, NamedNode):
            roots.add(r)
        elif isinstance(r, BlankNode):  # Core 6.10.9.4: a blank node is a SHACL list of IRIs
            members = shacl_list(shapes, r)
            if not all(isinstance(m, NamedNode) for m in members):
                raise ShapeError(f"sh:rootClass list members must be IRIs, got {text(r)}", kind="compile")
            roots.update(members)
        else:
            raise ShapeError(f"sh:rootClass must be an IRI or a list of IRIs, got {r!r}", kind="compile")
    return roots


@component(SH.RootClassConstraintComponent, SH.rootClass, check=lambda shapes, shape, params: _roots(shapes, params) and None)
def root_class(ctx, shape, params, focus, values):
    """sh:rootClass: each value node must be, or be an rdfs:subClassOf descendant of, one of the root classes."""
    roots = _roots(ctx.shapes, params)
    for v in values:
        seen, stack = set(), [v]
        found = False
        while stack and not found:
            c = stack.pop()
            if c in roots:
                found = True
            elif c not in seen:
                seen.add(c)
                stack.extend(ctx.superclasses_of(c))
        if not found:
            yield Violation(value=v)
