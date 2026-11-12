"""``sh:deactivated`` given as a node expression (SHACL 1.2 Core, "Deactivating Shapes and Constraints"): the expression is
evaluated with the data graph as focus graph, the focus node, and an empty scope; the shape is deactivated for that focus node
exactly when the output is the single node ``true``. A literal ``"true"^^xsd:boolean`` is handled by the builder."""

from __future__ import annotations

from typing import Any

from starlayer.shacl_engine.expressions import (
    EvaluationFailure,
    evaluate_expression,
)
from starlayer.shacl_engine.plan import Shape, Term
from starlayer.shacl_engine.terms import TRUE


def any_true(ctx: Any, exprs: Any, focus: Term) -> bool:
    """True if some expression's output at ``focus`` is the single node ``true``; a failing expression counts as false."""
    for expr in exprs:
        try:
            if evaluate_expression(ctx, expr, focus) == [TRUE]:
                return True
        except EvaluationFailure:
            continue  # no result for this focus node: not deactivated
    return False


def deactivated_at(ctx: Any, shape: Shape, focus: Term) -> bool:
    """True if one of the shape's ``sh:deactivated`` node expressions yields true at ``focus``; a literal ``true`` is not checked here."""
    return any_true(ctx, shape.deactivated_exprs, focus)
