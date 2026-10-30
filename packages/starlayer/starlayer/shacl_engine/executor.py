"""Focus nodes, value nodes and constraint dispatch. No global state; everything flows through ``Context``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from starlayer.shacl_engine.deactivation import deactivated_at
from starlayer.shacl_engine.expressions import EvaluationFailure, evaluate_expression
from starlayer.shacl_engine.paths import eval_path
from starlayer.shacl_engine.plan import SH, Path, Plan, Shape, Term
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
    source_constraint: Term = None


@dataclass
class Context:
    """What a component function sees: ``data`` (the data graph view), ``shapes`` (the shapes graph view), ``plan``."""

    data: Any
    plan: Plan
    _active: set = field(default_factory=set)
    _focus_cache: dict = field(default_factory=dict)

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

    def shape_focus(self, shape: Shape) -> list[Term]:
        """The shape's focus nodes, cached (cross-node components such as sh:uniqueValuesFor need the whole set)."""
        if shape.node not in self._focus_cache:
            self._focus_cache[shape.node] = focus_nodes(
                self.data, self.plan.shapes_graph, shape.targets, self.conforms, self.target_expression
            )
        return self._focus_cache[shape.node]

    def value_nodes(self, shape: Shape, focus: Term) -> list[Term]:
        """Path values, plus ``sh:values`` outputs, plus (only if that is still empty) ``sh:defaultValue`` outputs. An
        expression that fails on this focus node contributes no values."""
        if shape.path is None:
            return [focus]
        nodes = eval_path(self.data, shape.path, focus)
        if shape.values:
            nodes = list(dict.fromkeys([*nodes, *self._expression_values(shape.values, focus)]))
        if not nodes and shape.default_values:
            nodes = list(dict.fromkeys(self._expression_values(shape.default_values, focus)))
        return nodes

    def _expression_values(self, exprs: tuple, focus: Term | None) -> list[Term]:
        out: list[Term] = []
        for expr in exprs:
            try:
                out.extend(evaluate_expression(self, expr, focus))
            except EvaluationFailure:
                pass
        return out

    def target_expression(self, expr: Term) -> list[Term]:
        """Focus nodes of a node-expression target (``sh:targetNode [ shnex:... ]``): evaluated without a focus node."""
        return self._expression_values((expr,), None)


def _deactivated(shape: Shape, pred: Term, value: Term) -> bool:
    a = shape.annotations.get((pred, value))
    return bool(a and a["deactivated"])


def validate_shape_at(ctx: Context, shape: Shape, focus: Term) -> list[Result]:
    if shape.deactivated or deactivated_at(ctx, shape, focus):
        return []
    values = ctx.value_nodes(shape, focus)
    out: list[Result] = []
    for spec in ctx.plan.components():
        present = {
            p: kept
            for p in spec.predicates
            if p in shape.params and (kept := tuple(v for v in shape.params[p] if not _deactivated(shape, p, v)))
        }
        if not present or not all(r in present for r in spec.required):
            continue
        severity = next(
            (a["severity"] for p, vs in present.items() for v in vs if (a := shape.annotations.get((p, v))) and a["severity"]),
            shape.severity,
        )
        for v in spec.fn(ctx, shape, present, focus, tuple(values)) or ():
            out.append(
                Result(
                    focus=focus,
                    path=v.path if v.path is not None else shape.path,
                    value=v.value,
                    has_value=v.value is not None,
                    component=v.component or spec.iri,
                    shape=shape.node,
                    severity=v.severity or severity,
                    messages=v.messages or shape.messages or ((v.message,) if v.message else ()),
                    source_constraint=v.source_constraint,
                )
            )
    for ps in shape.property_shapes:
        if _deactivated(shape, SH.property, ps):
            continue
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
        for focus in ctx.shape_focus(shape):
            results.extend(validate_shape_at(ctx, shape, focus))
    return results
