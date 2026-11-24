"""``value_form``: how the value of a field is held, read from the property shape's own constraints.

A field's value is **one term** or an **RDF list** (a term that heads one). The shapes already say which: a shape requires a list when
what a value node must conform to describes a list, and it says "one term or a list" with an ``sh:or`` that has both kinds of alternative.
Nothing here is a vocabulary of its own. What counts as describing a list:

- the SHACL 1.2 list constraints ``sh:minListLength``, ``sh:maxListLength``, ``sh:memberShape`` and ``sh:uniqueMembers true`` (each
  requires its value node to be a well-formed list, Core 7.5);
- ``sh:class rdf:List``;
- ``shsh:ListShape`` itself, or a shape with the property shape of its pattern: the path ``[ sh:zeroOrMorePath rdf:rest ]`` with
  ``sh:hasValue rdf:nil``, or the member path ``( [ sh:zeroOrMorePath rdf:rest ] rdf:first )`` with ``sh:minCount`` of at least 1
  (without one an IRI conforms too, so it is no requirement);
- reached through ``sh:node``, ``sh:and`` or the shape itself: a conjunction requires a list when any part does.

``sh:or`` and ``sh:xone`` with at least one alternative that requires a list and one that does not (or that is itself either) give
"single-or-list". ``sh:xone`` counts like ``sh:or`` because the question is which kinds of value are allowed; the one case where they differ
is a value that fits two alternatives (``rdf:nil`` is both an IRI and the empty list), which ``sh:xone`` rejects when validating. The shape's own ``sh:path`` is the field, not evidence: ``sh:in`` as a path says nothing, while a ``sh:in`` list in
a shape is a parameter of that shape. A shape reached again through itself, and a deactivated one, add nothing.
"""

from __future__ import annotations

from typing import Any

from starlayer.shacl.engine.candidates import _property_shape
from starlayer.shacl.engine.components.core_value import rdf_list
from starlayer.shacl.engine.plan import SH, Plan, Shape
from starlayer.shacl.engine.terms import RDF, Literal, NamedNode, engine_view, to_engine

SINGLE, LIST, EITHER = "single", "list", "single-or-list"
_NONE = "none"  # a shape that says nothing about lists: "single" at the top, "not a list" as an alternative

_SHSH_LIST_SHAPE = NamedNode("http://www.w3.org/ns/shacl-shacl#ListShape")
_LIST_PARAMETERS = (SH.minListLength, SH.maxListLength, SH.memberShape)


def _is_true(term: Any) -> bool:
    return isinstance(term, Literal) and term.value in ("true", "1")


def _at_least_one(terms: Any) -> bool:
    for term in terms:
        try:
            if isinstance(term, Literal) and int(term.value) >= 1:
                return True
        except ValueError:
            continue
    return False


def _is_rest_star(path: Any) -> bool:
    return path.kind == "zero_or_more" and path.args[0].kind == "pred" and path.args[0].iri == RDF.rest


class _Reader:
    def __init__(self, plan: Plan) -> None:
        self.plan = plan
        self.shapes = plan.shapes_graph

    def _lists(self, heads: Any) -> list[list]:
        found = (rdf_list(self.shapes, head) if not isinstance(head, Literal) else None for head in heads)
        return [members for members in found if members is not None]

    def _list_pattern(self, node: Any) -> bool:
        """The property shape at ``node`` is a part of the pattern of ``shsh:ListShape`` or of a list's member path."""
        shape = self.plan.shape(node)
        path, params = shape.path, shape.params
        if path is None or shape.deactivated:
            return False
        if _is_rest_star(path):
            return RDF.nil in params.get(SH.hasValue, ())
        return (
            path.kind == "seq"
            and len(path.args) == 2
            and _is_rest_star(path.args[0])
            and path.args[1].kind == "pred"
            and path.args[1].iri == RDF.first
            and _at_least_one(params.get(SH.minCount, ()))
        )

    def form(self, node: Any, stack: tuple = ()) -> str:
        if node == _SHSH_LIST_SHAPE:
            return LIST
        if node in stack:
            return _NONE
        shape: Shape = self.plan.shape(node)
        if shape.deactivated:
            return _NONE
        stack = (*stack, node)
        params = shape.params
        direct = (
            any(params.get(name) for name in _LIST_PARAMETERS)
            or any(_is_true(p) for p in params.get(SH.uniqueMembers, ()))
            or RDF.List in params.get(SH["class"], ())
            or any(self._list_pattern(p) for p in shape.property_shapes)
        )
        parts = [LIST] if direct else []
        parts += [self.form(n, stack) for n in params.get(SH.node, ())]
        for members in self._lists(params.get(SH["and"], ())):
            parts += [self.form(m, stack) for m in members]
        for name in (SH["or"], SH.xone):
            for members in self._lists(params.get(name, ())):
                parts.append(_choice([self.form(m, stack) for m in members]))
        if LIST in parts:
            return LIST
        return EITHER if EITHER in parts else _NONE


def _choice(alternatives: list[str]) -> str:
    """One of several alternatives: a list is possible when one is LIST or EITHER, a single term when one is neither a list requirement."""
    can_list = any(a in (LIST, EITHER) for a in alternatives)
    can_single = any(a in (_NONE, EITHER) for a in alternatives)
    if can_list and can_single:
        return EITHER
    return LIST if can_list else _NONE


def value_form(shapes_graph: Any, property_shape: Any) -> str:
    """``"single"``, ``"list"`` or ``"single-or-list"`` for the field of ``property_shape`` (see the module docstring)."""
    plan = Plan(shapes_graph=engine_view(shapes_graph, "shapes graph"))
    node = to_engine(property_shape)
    _property_shape(plan, node)
    form = _Reader(plan).form(node)
    return SINGLE if form == _NONE else form
