"""Components that compare a focus node with the other focus nodes of the same shape."""

from __future__ import annotations

from starlayer.shacl.engine.components.registry import Violation, component
from starlayer.shacl.engine.plan import SH, ShapeCompileError
from starlayer.shacl.engine.terms import RDF
from starlayer.shacl.engine.terms import NamedNode as URIRef


def _properties(shapes, value) -> list[URIRef]:
    """A property IRI, or an rdf:List of property IRIs (the composite key)."""
    if isinstance(value, URIRef):
        return [value]
    items, node, seen = [], value, set()
    while node != RDF.nil:
        if node in seen:
            raise ShapeCompileError("cyclic list in sh:uniqueValuesFor")
        seen.add(node)
        first = list(shapes.objects(node, RDF.first))
        rest = list(shapes.objects(node, RDF.rest))
        if len(first) != 1 or len(rest) != 1 or not isinstance(first[0], URIRef):
            raise ShapeCompileError("sh:uniqueValuesFor must be an IRI or a list of IRIs")
        items.append(first[0])
        node = rest[0]
    if not items:
        raise ShapeCompileError("sh:uniqueValuesFor list is empty")
    return items


def _clash_message(ctx, props, focus, others, shared) -> str:
    """``ex:c4 has the same values as ex:c3 for ex:notation "456", ex:inScheme (none)``; several clashing nodes are listed in
    sorted order, the values of a property likewise."""
    from starlayer.shacl.engine.text import plain_term

    data = lambda term: plain_term(ctx.data, term)  # noqa: E731
    names = sorted(data(o) for o in others)
    parts = [
        f"{plain_term(ctx.shapes, p)} {' '.join(sorted(map(data, vals))) if vals else '(none)'}"  # str-ok: text
        for p, vals in zip(props, shared)
    ]
    noun = "value" if len(props) == 1 and len(shared[0]) == 1 else "values"
    return f"{data(focus)} has the same {noun} as {', '.join(names)} for {', '.join(parts)}"  # str-ok: text


def _check_unique_values_for(shapes, shape, params) -> None:
    for spec in params[SH.uniqueValuesFor]:
        _properties(shapes, spec)


@component(SH.UniqueValuesForConstraintComponent, SH.uniqueValuesFor, check=_check_unique_values_for)
def unique_values_for(ctx, shape, params, focus, values):
    """No two focus nodes of the shape share the same combination of values for the properties. A focus node is
    exempt only when it has no value for any of the properties (W3C uniqueValuesFor-004); with a list, a node that
    lacks some of them is still compared, an empty value set equalling an empty value set, so two nodes sharing a first
    name and both lacking a last name clash."""
    for spec in params[SH.uniqueValuesFor]:
        props = _properties(ctx.shapes, spec)

        def key(node, props=props):
            sets = [frozenset(ctx.data.objects(node, p)) for p in props]
            return None if not any(sets) else tuple(sets)

        # Group the shape's target nodes by key once per (shape, parameter value). Core 6.10.9.5: the targets are those of the
        # shape even when the focus node was provided directly (sh:node), so a violation needs *another* target with the key.
        memo = ctx.cache.get(("uniqueValuesFor", shape.node, spec))
        if memo is None:
            groups: dict = {}
            for target in set(ctx.shape_focus(shape)):
                if (k := key(target)) is not None:
                    groups.setdefault(k, []).append(target)
            memo = ctx.cache[("uniqueValuesFor", shape.node, spec)] = groups
        mine = key(focus)
        if mine is not None and (others := [t for t in memo.get(mine, ()) if t != focus]):
            yield Violation(value=None, message=_clash_message(ctx, props, focus, others, mine))
