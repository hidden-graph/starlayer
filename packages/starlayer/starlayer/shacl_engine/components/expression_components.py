"""Node Expressions constraint components (SHACL 1.2 Node Expressions, section 7): ``sh:expression`` and
``sh:nodeByExpression``."""

from __future__ import annotations

from starlayer.shacl_engine.components.registry import Violation, component
from starlayer.shacl_engine.expressions import evaluate_expression
from starlayer.shacl_engine.plan import SH
from starlayer.shacl_engine.terms import TRUE


@component(SH.ExpressionConstraintComponent, SH.expression)
def expression(ctx, shape, params, focus, values):
    """Each value node ``v``: evaluate the expression at the focus node with scope ``value = v``; a result other than
    exactly ``(true)`` is a violation whose ``sh:sourceConstraint`` is the expression. Evaluation failure propagates."""
    for expr in params[SH.expression]:
        for v in values:
            if evaluate_expression(ctx, expr, focus, {"value": [v]}) != [TRUE]:
                yield Violation(value=v, source_constraint=expr)


@component(SH.NodeByExpressionConstraintComponent, SH.nodeByExpression)
def node_by_expression(ctx, shape, params, focus, values):
    """Each value node ``v``: evaluate the expression with ``v`` as focus node and an empty scope; every output node is
    a shape ``v`` must conform to (like ``sh:node`` but computed; the violation carries the shape as sourceConstraint)."""
    for expr in params[SH.nodeByExpression]:
        for v in values:
            for s in evaluate_expression(ctx, expr, v):
                if not ctx.conforms(s, v):
                    yield Violation(value=v, source_constraint=s)
