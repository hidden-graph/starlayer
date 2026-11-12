"""SPARQL-based constraints (SHACL 1.2 SPARQL-Related Features, section 3): ``sh:sparql`` on a shape.

Each ``sh:sparql`` value has one ``sh:select`` projecting ``?this``; ``$this`` is pre-bound to the focus node and, on a
property shape, ``$PATH`` is replaced by the shape's path. One result per solution; see
``sparql_support.violations_from_solutions`` for the variable mapping.
"""

from __future__ import annotations

from starlayer.shacl_engine.components.registry import Violation, component
from starlayer.shacl_engine.expressions import EvaluationFailure, evaluate_expression
from starlayer.shacl_engine.plan import SH, ShapeError
from starlayer.shacl_engine.sparql_support import (
    is_true,
    run_select,
    substitute_path,
    violations_from_solutions,
    with_prefixes,
)
from starlayer.shacl_engine.terms import TRUE, Literal


def _prepared(ctx, shape, constraint):
    """What a ``sh:sparql`` constraint needs per focus node, read once per (shape, constraint) per run: ``None`` if it is
    deactivated by a literal, else ``(query text, severity, messages, sh:deactivated node expressions)``; the expressions are
    evaluated per focus node by the caller."""
    key = ("sparql-constraint", shape.node, constraint)
    if key in ctx.cache:
        return ctx.cache[key]
    graph = ctx.shapes
    if any(is_true(d) for d in graph.objects(constraint, SH.deactivated) if isinstance(d, Literal)):
        prepared = None
    else:
        selects = list(graph.objects(constraint, SH.select))
        if len(selects) != 1:
            raise ShapeError(f"{constraint!r}: a sh:sparql constraint needs exactly one sh:select")
        severities = list(graph.objects(constraint, SH.severity))
        text = substitute_path(with_prefixes(ctx.plan, constraint, selects[0].value), shape)
        prepared = (
            text,
            severities[0] if severities else None,
            tuple(graph.objects(constraint, SH.message)),
            tuple(d for d in graph.objects(constraint, SH.deactivated) if not isinstance(d, Literal)),
        )
    ctx.cache[key] = prepared
    return prepared


def _deactivated_at(ctx, exprs, focus) -> bool:
    """SPARQL-Related Features 3.2: a ``sh:deactivated`` node expression deactivates the constraint for a focus node when it
    yields ``true`` as its only output node."""
    for expr in exprs:
        try:
            if evaluate_expression(ctx, expr, focus) == [TRUE]:
                return True
        except EvaluationFailure:
            continue
    return False


@component(SH.SPARQLConstraintComponent, SH.sparql)
def sparql_constraint(ctx, shape, params, focus, values):
    """Validate a focus node against each non-deactivated ``sh:sparql`` constraint, one violation per solution row."""
    graph = ctx.shapes
    out: list[Violation] = []
    for constraint in params[SH.sparql]:
        prepared = _prepared(ctx, shape, constraint)
        if prepared is None:
            continue
        text, severity, messages, deactivated_exprs = prepared
        if _deactivated_at(ctx, deactivated_exprs, focus):
            continue
        bindings = {"this": focus}
        out.extend(
            violations_from_solutions(
                run_select(ctx, text, bindings),
                shape=shape,
                focus=focus,
                bindings=bindings,
                messages=messages,
                source_constraint=constraint,
                severity=severity,
                graph=graph,
                annotation_source=constraint,
            )
        )
    return out
