"""Components that compare a focus node with the other focus nodes of the same shape."""

from __future__ import annotations

from collections import Counter

from starlayer.shacl_engine.components.registry import Violation, component
from starlayer.shacl_engine.plan import SH, ShapeError
from starlayer.shacl_engine.terms import RDF
from starlayer.shacl_engine.terms import NamedNode as URIRef


def _properties(shapes, value) -> list[URIRef]:
    """A property IRI, or an rdf:List of property IRIs (the composite key)."""
    if isinstance(value, URIRef):
        return [value]
    items, node, seen = [], value, set()
    while node != RDF.nil:
        if node in seen:
            raise ShapeError("cyclic list in sh:uniqueValuesFor")
        seen.add(node)
        first = list(shapes.objects(node, RDF.first))
        rest = list(shapes.objects(node, RDF.rest))
        if len(first) != 1 or len(rest) != 1 or not isinstance(first[0], URIRef):
            raise ShapeError("sh:uniqueValuesFor must be an IRI or a list of IRIs")
        items.append(first[0])
        node = rest[0]
    if not items:
        raise ShapeError("sh:uniqueValuesFor list is empty")
    return items


@component(SH.UniqueValuesForConstraintComponent, SH.uniqueValuesFor)
def unique_values_for(ctx, shape, params, focus, values):
    """No two focus nodes of the shape share the same combination of values for the properties. A focus node with no
    value for any of the properties is not compared (W3C uniqueValuesFor-004)."""
    for spec in params[SH.uniqueValuesFor]:
        props = _properties(ctx.shapes, spec)

        def key(node, props=props):
            sets = [frozenset(ctx.data.objects(node, p)) for p in props]
            return None if any(not s for s in sets) else tuple(sets)

        # Group the shape's focus nodes by key once per (shape, parameter value); a node violates when its key is shared.
        memo = ctx.cache.get(("uniqueValuesFor", shape.node, spec))
        if memo is None:
            memo = Counter(k for k in map(key, ctx.shape_focus(shape)) if k is not None)
            ctx.cache[("uniqueValuesFor", shape.node, spec)] = memo
        mine = key(focus)
        if mine is not None and memo[mine] > 1:
            yield Violation(value=None)
