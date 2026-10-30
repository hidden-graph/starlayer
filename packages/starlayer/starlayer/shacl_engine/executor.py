"""Focus nodes, value nodes and constraint dispatch. No global state; everything flows through ``Context``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from starlayer.shacl_engine.components import registry
from starlayer.shacl_engine.paths import eval_path
from starlayer.shacl_engine.plan import Path, Plan, Shape, Term
from starlayer.shacl_engine.targets import focus_nodes


@dataclass(frozen=True)
class Result:
    focus: Term
    path: Path | None
    value: Term
    has_value: bool
    component: Term
    shape: Term
    severity: Term
    messages: tuple[Any, ...] = ()


@dataclass
class Context:
    """What a component function sees: ``data`` (the data graph view), ``shapes`` (the shapes graph view), ``plan``."""

    data: Any
    plan: Plan
    _active: set = field(default_factory=set)

    @property
    def shapes(self) -> Any:
        return self.plan.shapes_graph

    def shape(self, node: Term) -> Shape:
        return self.plan.shape(node)

    def conforms(self, shape_node: Term, node: Term) -> bool:
        """True if ``node`` has no validation result against the shape. A recursive re-entry on the same
        (shape, node) pair counts as conforming (the recursion semantics are an open design question)."""
        key = (shape_node, node)
        if key in self._active:
            return True
        self._active.add(key)
        try:
            return not validate_shape_at(self, self.shape(shape_node), node)
        finally:
            self._active.discard(key)

    def value_nodes(self, shape: Shape, focus: Term) -> list[Term]:
        return eval_path(self.data, shape.path, focus) if shape.path is not None else [focus]


def validate_shape_at(ctx: Context, shape: Shape, focus: Term) -> list[Result]:
    if shape.deactivated:
        return []
    values = ctx.value_nodes(shape, focus)
    out: list[Result] = []
    for spec in registry.REGISTRY.values():
        present = {p: shape.params[p] for p in spec.predicates if p in shape.params}
        if not present:
            continue
        for v in spec.fn(ctx, shape, present, focus, tuple(values)) or ():
            out.append(
                Result(
                    focus=focus,
                    path=v.path if v.path is not None else shape.path,
                    value=v.value,
                    has_value=v.value is not None,
                    component=v.component or spec.iri,
                    shape=shape.node,
                    severity=shape.severity,
                    messages=shape.messages or ((v.message,) if v.message else ()),
                )
            )
    for ps in shape.property_shapes:
        pshape = ctx.shape(ps)
        for value in values:
            out.extend(validate_shape_at(ctx, pshape, value))
    return out


def run(plan: Plan, data: Any) -> list[Result]:
    ctx = Context(data=data, plan=plan)
    results: list[Result] = []
    for node in plan.all_shape_nodes():
        shape = plan.shape(node)
        if shape.deactivated:
            continue
        for focus in focus_nodes(data, plan.shapes_graph, shape.targets):
            results.extend(validate_shape_at(ctx, shape, focus))
    return results
