"""``check_value``: would a value be accepted for one field of one node, by the property shape alone.

The mechanism is the one of ``candidate_values(only_valid=True)``: on a scratch copy of the data the value replaces the field's current
values for the focus node, and the focus node is validated against the property shape only (its other shapes, targets and the
shapes-about-shapes layer are not run).
"""

from __future__ import annotations

from typing import Any

from starlayer.graph import StarLayerDataset
from starlayer.shacl.engine.candidates import _existing, _link, _property_shape
from starlayer.shacl.engine.executor import Context, validate_shape_at
from starlayer.shacl.engine.plan import Plan
from starlayer.shacl.engine.report import build_report, conforms
from starlayer.shacl.engine.terms import (
    Literal,
    engine_view,
    to_engine,
)
from starlayer.shacl.engine.text import result_messages


def check_value(
    data_graph: Any,
    shapes_graph: Any,
    property_shape: Any,
    focus: Any,
    value: Any,
    *,
    subclass_of_in_shapes_graph: bool = False,
    conformance_disallows: Any = None,
) -> tuple[bool, Any]:
    """``(conforms, report_graph)`` of ``property_shape`` at ``focus`` with ``value`` as the field's only value."""
    data = engine_view(data_graph, "data graph")
    plan = Plan(shapes_graph=engine_view(shapes_graph, "shapes graph"))
    node, focus, value = to_engine(property_shape), to_engine(focus), to_engine(value)
    shape = _property_shape(plan, node)
    triple = _link(shape, focus, value)  # a path that cannot be written is refused before any work
    if isinstance(value, Literal) and shape.path.kind == "inverse":
        raise ValueError("a literal cannot be the value of an inverse path: it would be the subject of the triple")
    if isinstance(data, StarLayerDataset):
        data = data.to_graph()
    scratch = data.copy()
    for pattern in _existing(shape, focus):
        scratch.remove(pattern)
    scratch.add(triple)
    ctx = Context(data=scratch, plan=plan, subclass_of_in_shapes_graph=subclass_of_in_shapes_graph)
    results = validate_shape_at(ctx, shape, focus)
    report = build_report(
        results, plan.shapes_graph, scratch, conformance_disallows, messages_for=lambda r: result_messages(r, plan.shapes_graph, scratch)
    )
    return conforms(results, conformance_disallows), report
