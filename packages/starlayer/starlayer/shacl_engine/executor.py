"""Focus nodes, value nodes and constraint dispatch. No global state; everything flows through ``Context``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from starlayer.shacl_engine.deactivation import deactivated_at
from starlayer.shacl_engine.expressions import EvaluationFailure, evaluate_expression
from starlayer.shacl_engine.paths import eval_path
from starlayer.shacl_engine.plan import SH, Path, Plan, Shape, ShapeError, Term
from starlayer.shacl_engine.targets import focus_nodes
from starlayer.shacl_engine.terms import engine_view


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
    annotations: tuple[tuple[Any, Any], ...] = ()  # (property, value) pairs: sh:resultAnnotation
    details: tuple[Result, ...] = ()  # nested results reported as sh:detail (SHACL 1.2 Core 6.9.2.6); never block conformance


@dataclass
class Context:
    """What a component function sees: ``data`` (the data graph view), ``shapes`` (the shapes graph view), ``plan``."""

    data: Any
    plan: Plan
    abort_on_first: bool = False  # stop at the first shape that produces a result (and the first component within it)
    max_validation_depth: int | None = None  # bound on shape nesting; exceeding it raises ShapeError (failure)
    _active: dict = field(default_factory=dict)  # (shape, node) pairs being evaluated -> sh:not crossings at entry
    _negations: int = 0  # sh:not crossings on the current evaluation stack
    _depth: int = 0
    _focus_cache: dict = field(default_factory=dict)
    recursion_revisits: int = 0  # times conforms() re-entered a (shape, node) pair already being evaluated
    cache: dict = field(default_factory=dict)  # per-run memo for components (keyed by the component's own tuple)
    _detail_memo: dict = field(default_factory=dict)  # (shape, node) -> the results reported as sh:detail (assumption-free only)
    _conforms_memo: dict = field(default_factory=dict)  # (shape, node) -> (bool, nesting height), assumption-free only
    _peak: int = 0  # deepest ``_depth`` at which a shape was entered since the enclosing conforms() started
    _assumed: int = 0  # how many times a re-entry assumed 'conforms' (the greatest-fixpoint reading) so far

    def __post_init__(self) -> None:
        self.data = engine_view(self.data, "data graph")

    @property
    def shapes(self) -> Any:
        return self.plan.shapes_graph

    def shape(self, node: Term) -> Shape:
        return self.plan.shape(node)

    def conforms(self, shape_node: Term, node: Term, *, negated: bool = False) -> bool:
        """True if ``node`` has no validation result against the shape.

        SHACL 1.2 Core 6.7.3: "The validation with recursive shapes is not defined in SHACL and is left to SHACL
        processor implementations." Choice made here: a re-entry on the same (shape, node) pair is assumed to conform
        (the greatest-fixpoint reading, as ``starlayer.shacl.recursion``), except when the cycle passes through ``sh:not``
        (``negated=True`` callers). Such a cycle is not stratified: it has no fixpoint (odd number of negations) or
        several (even number: ``ex:N sh:not [ sh:not [ ... sh:node ex:N ] ]`` is consistent both as conforming and as
        violating), so the answer would depend on evaluation order. It raises ``ShapeError`` (a validation failure).
        A cycle that meets the data only at positive links (sh:node, sh:property, sh:and, sh:or) keeps 'conforms'.
        """
        key = (shape_node, node)
        memo = self._conforms_memo.get(key)
        if memo is not None:
            limit = self.max_validation_depth
            # The evaluation entered shapes up to ``height`` levels below its start; replayed here it must not cross the
            # depth limit, else fall through and evaluate (which raises exactly as it would have without the memo).
            if limit is None or self._depth + memo[1] < limit:
                self._peak = max(self._peak, self._depth + memo[1])
                return memo[0]
        if key in self._active:
            self.recursion_revisits += 1
            if self._negations != self._active[key]:
                raise ShapeError(f"recursive shape {shape_node!r} reaches itself on {node!r} through sh:not")
            self._assumed += 1
            return True
        self._active[key] = self._negations
        if negated:
            self._negations += 1
        assumed_before = self._assumed
        start = self._depth
        outer_peak = self._peak
        self._peak = start
        try:
            answer = not validate_shape_at(self, self.shape(shape_node), node)
            height = self._peak - start
        finally:
            self._peak = max(outer_peak, self._peak)
            if negated:
                self._negations -= 1
            del self._active[key]
        # Memoise only an answer that did not lean on a recursion assumption, so it does not depend on which (shape, node)
        # pairs happened to be active. Its nesting height is kept so max_validation_depth is still enforced on replay.
        if self._assumed == assumed_before:
            self._conforms_memo[key] = (answer, height)
        return answer

    def detail_results(self, shape_node: Term, node: Term) -> tuple[Result, ...]:
        """The results of validating ``node`` against ``shape_node``, for use as ``sh:detail`` of an enclosing result. A
        (shape, node) pair already being evaluated yields none (the recursion assumption of ``conforms`` applies)."""
        key = (shape_node, node)
        if key in self._active:
            return ()
        memoise = self._negations == 0 and not self._active  # only an answer that leaned on no recursion assumption is reusable
        if memoise and key in self._detail_memo:
            return self._detail_memo[key]
        self._active[key] = self._negations
        try:
            results = tuple(validate_shape_at(self, self.shape(shape_node), node))
        finally:
            del self._active[key]
        if memoise:
            self._detail_memo[key] = results
        return results

    def shape_focus(self, shape: Shape) -> list[Term]:
        """The shape's focus nodes, cached (cross-node components such as sh:uniqueValuesFor need the whole set)."""
        if shape.node not in self._focus_cache:
            self._focus_cache[shape.node] = focus_nodes(
                self.data,
                self.plan.shapes_graph,
                shape.targets,
                self.conforms,
                lambda expr, shape_node=shape.node: self.target_expression(expr, shape_node),
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

    def target_expression(self, expr: Term, shape_node: Term) -> list[Term]:
        """Focus nodes of a node-expression target (``sh:targetNode [ shnex:... ]``). Core 3.1.3.1: "the output nodes of
        evalExpr(expr, data graph, s, {}) are targets", so the focus node during evaluation is the shape ``s``."""
        return self._expression_values((expr,), shape_node)


def _deactivated(shape: Shape, pred: Term, value: Term) -> bool:
    a = shape.annotations.get((pred, value))
    return bool(a and a["deactivated"])


def validate_shape_at(ctx: Context, shape: Shape, focus: Term) -> list[Result]:
    if shape.deactivated or deactivated_at(ctx, shape, focus):
        return []
    limit = ctx.max_validation_depth
    if limit is not None and ctx._depth >= limit:
        raise ShapeError(f"Validation path too deep: more than {limit} nested shapes at {shape.node!r}")
    if ctx._depth > ctx._peak:
        ctx._peak = ctx._depth
    ctx._depth += 1
    try:
        return _validate_shape_at(ctx, shape, focus)
    finally:
        ctx._depth -= 1


def _shape_components(ctx: Context, shape: Shape) -> list:
    """The (component spec, present parameters, severity) triples that apply to ``shape``: independent of the focus node,
    so computed once per shape per run."""
    key = ("components", shape.node)
    cached = ctx.cache.get(key)
    if cached is not None:
        return cached
    out = []
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
        out.append((spec, present, severity))
    ctx.cache[key] = out
    return out


def _validate_shape_at(ctx: Context, shape: Shape, focus: Term) -> list[Result]:
    values = ctx.value_nodes(shape, focus)
    out: list[Result] = []
    for spec, present, severity in _shape_components(ctx, shape):
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
                    annotations=v.annotations,
                    details=v.details,
                )
            )
        if out and ctx.abort_on_first:
            return out
    for ps in shape.property_shapes:
        if out and ctx.abort_on_first:
            break
        if _deactivated(shape, SH.property, ps):
            continue
        pshape = ctx.shape(ps)
        for value in values:
            out.extend(validate_shape_at(ctx, pshape, value))
    return out


def run(
    plan: Plan,
    data: Any,
    *,
    abort_on_first: bool = False,
    max_validation_depth: int | None = None,
    stats: dict | None = None,
) -> list[Result]:
    """Validate every declared shape. ``stats`` (optional) receives ``recursion_revisits`` for the run's diagnostics."""
    ctx = Context(data=data, plan=plan, abort_on_first=abort_on_first, max_validation_depth=max_validation_depth)
    results: list[Result] = []
    try:
        for node in plan.all_shape_nodes():
            shape = plan.shape(node)
            if shape.deactivated:
                continue
            for focus in ctx.shape_focus(shape):
                results.extend(validate_shape_at(ctx, shape, focus))
                if results and abort_on_first:
                    return results
        return results
    finally:
        if stats is not None:
            stats["recursion_revisits"] = ctx.recursion_revisits
