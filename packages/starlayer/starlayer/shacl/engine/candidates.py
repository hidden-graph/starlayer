"""``candidate_values``: what a field of a property shape can be offered, read from the shape and the data.

The constraints that name the values are the listing ones; every other constraint can only reject a value, so it is tried
(``only_valid``) and never read to build the list.

- ``sh:in`` and ``sh:hasValue`` name the values (Core, Value Range Constraints); a closed list.
- ``sh:class`` is "SHACL instance" (Core 3.1.3.3): ``rdf:type`` from the data graph, then ``rdfs:subClassOf``, which
  ``Context.superclasses_of`` / ``subclasses_of`` read from the data graph and, with ``subclass_of_in_shapes_graph``, the shapes
  graph too. A class given as an RDF list is a union (the engine's ``alternatives``).
- ``sh:rootClass`` (Core 6.10.9.4) is not about instances: a value must itself be a root class or an ``rdfs:subClassOf``
  descendant of one, so its candidates are the root classes and their subclasses, and the engine merges several
  ``sh:rootClass`` values into one set of roots.
- Several listing constraints must all hold, so they intersect; ``sh:or`` is the union of its alternatives and is open when
  one alternative is; ``sh:and`` intersects its members. ``sh:xone`` and ``sh:not`` cannot name values.
- Several ``sh:hasValue`` values all have to be among the field's values, so together they are one list, not a conflict.

The data graph supplies suggestions only: the instances of a class it holds are offered, and ``closed`` comes from the shape alone
(``sh:in``, ``sh:hasValue``), never from what the data happens to contain. Whether a value is valid is the verdict of the shapes
(``only_valid``, ``check_value``), so a value the data does not back is still reported, as validation reports it: building shapes
means checking that invalid data fails them.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from starlayer.errors import ShapeError
from starlayer.graph import StarLayerDataset
from starlayer.shacl.engine.components.core_shape_based import _lists, _roots
from starlayer.shacl.engine.components.core_value import alternatives, rdf_list
from starlayer.shacl.engine.executor import Context, validate_shape_at
from starlayer.shacl.engine.plan import SH, Plan, Shape
from starlayer.shacl.engine.report import conforms
from starlayer.shacl.engine.terms import (
    RDF,
    BlankNode,
    Literal,
    NamedNode,
    engine_view,
    text,
    to_engine,
)


class _Found(NamedTuple):
    """What one shape (or one constraint of it) lists: ``values`` is ``None`` when it names nothing."""

    values: frozenset | None
    closed: bool


_OPEN = _Found(None, False)


def _and(found: list[_Found]) -> _Found:
    values: frozenset | None = None
    closed = False
    for item in found:
        if item.values is None:
            continue
        values = item.values if values is None else values & item.values
        closed = closed or item.closed
    return _Found(values, closed)


def _or(found: list[_Found]) -> _Found:
    if not found or any(item.values is None for item in found):
        return _OPEN
    return _Found(frozenset().union(*(item.values for item in found)), all(item.closed for item in found))


def _term_order(term: Any) -> tuple:
    """IRIs by text, then blank nodes, then literals by lexical form and datatype, then triple terms."""
    if isinstance(term, NamedNode):
        return (0, term.value, "", "")
    if isinstance(term, BlankNode):
        return (1, term.value, "", "")
    if isinstance(term, Literal):
        return (2, term.value, term.datatype.value, term.language or "")
    return (3, text(term), "", "")


def ordered(terms: Any) -> tuple:
    return tuple(sorted(terms, key=_term_order))


class _Reader:
    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self.shapes = ctx.shapes
        self.data = ctx.data

    def descendants(self, classes: Any) -> set:
        seen: set = set()
        todo = list(classes)
        while todo:
            cls = todo.pop()
            if cls not in seen:
                seen.add(cls)
                todo.extend(self.ctx.subclasses_of(cls))
        return seen

    def instances(self, classes: Any) -> frozenset:
        return frozenset(s for cls in self.descendants(classes) for s in self.data.subjects(RDF.type, cls))

    def shape_found(self, node: Any, stack: tuple = ()) -> tuple[_Found, frozenset]:
        """The listing of the shape at ``node`` and what can be typed for it (datatype IRIs, else those of its ``sh:or`` /
        ``sh:and`` members, else node kinds). A shape reached again through itself names nothing."""
        shape = self.ctx.shape(node)
        if node in stack or shape.deactivated:
            return _OPEN, frozenset()
        stack = (*stack, node)
        params = shape.params
        found: list[_Found] = []
        nested_entry: set = set()
        for head in params.get(SH["in"], ()):
            members = rdf_list(self.shapes, head) if not isinstance(head, Literal) else None
            if members is None:
                raise ShapeError(f"sh:in needs an rdf:list, got {text(head)}", kind="compile")
            found.append(_Found(frozenset(members), True))
        if params.get(SH.hasValue):
            found.append(_Found(frozenset(params[SH.hasValue]), True))
        for param in params.get(SH["class"], ()):
            found.append(_Found(self.instances(alternatives(self.shapes, param, "sh:class")), False))
        if params.get(SH.rootClass):
            found.append(_Found(frozenset(self.descendants(_roots(self.shapes, params))), False))
        for members in _lists(self.shapes, params.get(SH["and"], ()), "sh:and"):
            parts = [self.shape_found(m, stack) for m in members]
            found.extend(f for f, _e in parts)
            nested_entry.update(*(e for _f, e in parts))
        for members in _lists(self.shapes, params.get(SH["or"], ()), "sh:or"):
            parts = [self.shape_found(m, stack) for m in members]
            found.append(_or([f for f, _e in parts]))
            nested_entry.update(*(e for _f, e in parts))
        return _and(found), self._entry(shape, nested_entry)

    def _entry(self, shape: Shape, nested: set) -> frozenset:
        datatypes = {a for p in shape.params.get(SH.datatype, ()) for a in alternatives(self.shapes, p, "sh:datatype")}
        if datatypes:
            return frozenset(a for a in datatypes if isinstance(a, NamedNode))
        if nested:
            return frozenset(nested)
        kinds = {a for p in shape.params.get(SH.nodeKind, ()) for a in alternatives(self.shapes, p, "sh:nodeKind")}
        return frozenset(a for a in kinds if isinstance(a, NamedNode))


def _property_shape(plan: Plan, node: Any) -> Shape:
    shapes = plan.shapes_graph
    if node is None or not any(True for _ in shapes.triples((node, None, None))):
        raise ValueError(f"property_shape {text(node) if node is not None else None!r} is not a node of the shapes graph")
    shape = plan.shape(node)
    if shape.path is None or not shape.is_property:
        raise ValueError(f"property_shape {text(node)!r} is not a property shape (it has no sh:path)")
    return shape


def _link(shape: Shape, focus: Any, value: Any) -> tuple:
    """The triple that makes ``value`` a value of the property of ``focus``: only a predicate path or the inverse of one can be written."""
    path = shape.path
    if path.kind == "pred":
        return (focus, path.iri, value)
    if path.kind == "inverse" and path.args[0].kind == "pred":
        return (value, path.args[0].iri, focus)
    raise ValueError(f"only_valid needs sh:path to be a predicate or an inverse predicate, got {text(path.node)!r}")


def candidates(
    data_graph: Any,
    shapes_graph: Any,
    property_shape: Any,
    *,
    focus: Any = None,
    only_valid: bool = False,
    subclass_of_in_shapes_graph: bool = False,
    conformance_disallows: Any = None,
) -> tuple[str, tuple, bool, tuple]:
    """``(kind, values, closed, entry)`` for the field of ``property_shape`` (see ``starlayer.shacl.candidates.Candidates``)."""
    if only_valid and focus is None:
        raise ValueError("only_valid=True needs a focus node to try the candidates on")
    data = engine_view(data_graph, "data graph")
    plan = Plan(shapes_graph=engine_view(shapes_graph, "shapes graph"))
    node, focus = to_engine(property_shape), to_engine(focus)
    shape = _property_shape(plan, node)
    reader = _Reader(Context(data=data, plan=plan, subclass_of_in_shapes_graph=subclass_of_in_shapes_graph))
    found, entry = reader.shape_found(node)
    if found.values is None:
        return "open", (), False, ordered(entry)
    values = ordered(found.values)
    if only_valid:
        values = _valid(data, plan, shape, focus, values, subclass_of_in_shapes_graph, conformance_disallows)
    kind = "list" if found.closed else "instances"
    return kind, values, found.closed, () if found.closed else ordered(entry)


def _valid(data: Any, plan: Plan, shape: Shape, focus: Any, values: tuple, subclass_of: bool, floor: Any) -> tuple:
    """The values that, as the only value of the property of ``focus`` in a scratch copy of the data, leave ``shape`` conforming."""
    if isinstance(data, StarLayerDataset):
        data = data.to_graph()
    scratch = data.copy()
    _link(shape, focus, focus)  # a path that cannot be written is refused before any work
    for pattern in _existing(shape, focus):
        scratch.remove(pattern)
    kept = []
    for value in values:
        if isinstance(value, Literal) and shape.path.kind == "inverse":
            continue  # a literal cannot be the subject of the triple
        triple = _link(shape, focus, value)
        scratch.add(triple)
        try:
            ctx = Context(data=scratch, plan=plan, subclass_of_in_shapes_graph=subclass_of)
            if conforms(validate_shape_at(ctx, shape, focus), floor):
                kept.append(value)
        finally:
            scratch.remove(triple)
    return tuple(kept)


def _existing(shape: Shape, focus: Any) -> list:
    path = shape.path
    return [(focus, path.iri, None)] if path.kind == "pred" else [(None, path.args[0].iri, focus)]
