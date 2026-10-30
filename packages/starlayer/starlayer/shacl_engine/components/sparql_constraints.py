"""SPARQL-based constraints (SHACL 1.2 SPARQL-Related Features, section 3): ``sh:sparql`` on a shape.

Each ``sh:sparql`` value has one ``sh:select`` projecting ``?this``; ``$this`` is pre-bound to the focus node and, on a
property shape, ``$PATH`` is replaced by the shape's path. One result per solution; see
``sparql_support.violations_from_solutions`` for the variable mapping.
"""

from __future__ import annotations

from starlayer.shacl_engine.components.registry import Violation, component
from starlayer.shacl_engine.plan import SH, ShapeError
from starlayer.shacl_engine.sparql_support import (
    is_true,
    run_select,
    substitute_path,
    violations_from_solutions,
    with_prefixes,
)


@component(SH.SPARQLConstraintComponent, SH.sparql)
def sparql_constraint(ctx, shape, params, focus, values):
    graph = ctx.shapes
    out: list[Violation] = []
    for constraint in params[SH.sparql]:
        if any(is_true(d) for d in graph.objects(constraint, SH.deactivated)):
            continue
        selects = list(graph.objects(constraint, SH.select))
        if len(selects) != 1:
            raise ShapeError(f"{constraint!r}: a sh:sparql constraint needs exactly one sh:select")
        severities = list(graph.objects(constraint, SH.severity))
        text = substitute_path(with_prefixes(ctx.plan, constraint, str(selects[0])), shape)
        bindings = {"this": focus}
        out.extend(
            violations_from_solutions(
                run_select(ctx, text, bindings),
                shape=shape,
                focus=focus,
                bindings=bindings,
                messages=graph.objects(constraint, SH.message),
                source_constraint=constraint,
                severity=severities[0] if severities else None,
            )
        )
    return out
