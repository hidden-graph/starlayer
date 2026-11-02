"""Evaluate a SHACL 1.2 node expression, and list what one can call: the public face of the engine's expression evaluator.

An application that previews an expression (an editor, a debugger) uses these instead of reaching into the evaluator's
modules. Terms go in and come out in the caller's term model (rdflib / StarLayer terms, or pyoxigraph terms); the
evaluation itself is the native engine's (``starlayer.shacl_engine.expressions``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = ["evaluate_expression", "node_expression_functions", "node_expression_operators"]

_SPARQL_NS = "http://www.w3.org/ns/sparql#"
_SHNEX_NS = "http://www.w3.org/ns/shacl-node-expr#"


def evaluate_expression(
    shapes_graph: Any,
    data_graph: Any,
    expression: Any,
    focus: Any = None,
    *,
    scope: Mapping[Any, Any] | None = None,
) -> list:
    """The nodes ``expression`` gives for ``focus`` over ``data_graph``, in order.

    ``shapes_graph`` holds the expression and what it refers to (shapes, declared functions). ``scope`` binds variables
    (``shnex:var "name"``) by name to a term or a list of terms, and the arguments of a function call by position (``0``, ``1``,
    ...); ``focusNode`` is the focus node unless given. An expression that has an evaluation failure raises ``ValueError``
    (SHACL 1.2 Node Expressions 3.2). A ``sh:targetNode`` expression is evaluated with the shape as the focus node
    (Core 3.1.3.1): pass the shape."""
    from starlayer.shacl_engine import expressions
    from starlayer.shacl_engine.executor import Context
    from starlayer.shacl_engine.plan import Plan
    from starlayer.shacl_engine.terms import check_graphs, engine_view, from_engine, to_engine

    check_graphs((data_graph, "data graph"), (shapes_graph, "shapes graph"))
    plan = Plan(shapes_graph=engine_view(shapes_graph, "shapes graph"))
    ctx = Context(data=engine_view(data_graph, "data graph"), plan=plan)

    def bound(value: Any) -> Any:
        return [to_engine(v) for v in value] if isinstance(value, (list, tuple)) else to_engine(value)

    bindings = {key: bound(value) for key, value in (scope or {}).items()}
    nodes = expressions.evaluate_expression(
        ctx, to_engine(expression), None if focus is None else to_engine(focus), bindings
    )
    return [from_engine(n) for n in nodes]


def node_expression_functions() -> list[str]:
    """The SPARQL functions and operators a node expression can call (``[ sparql:concat ( ... ) ]``), as IRIs, sorted."""
    from starlayer.shacl_engine.component_table import operator_rows

    return sorted(row["operator"] for row in operator_rows() if row["namespace"] == "sparql")


def node_expression_operators() -> list[str]:
    """The SHACL node expression operators (``shnex:filterShape``, ``shnex:pathValues``, ``shnex:if``, ...), as IRIs, sorted."""
    from starlayer.shacl_engine.component_table import operator_rows

    return sorted(row["operator"] for row in operator_rows() if row["namespace"] == "shnex")
