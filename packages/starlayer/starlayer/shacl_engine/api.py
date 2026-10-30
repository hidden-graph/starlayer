"""``validate()``: data graph + shapes graph -> ``Outcome``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from starlayer.shacl_engine import components  # noqa: F401  (registers the constraint components)
from starlayer.shacl_engine.executor import Result, run
from starlayer.shacl_engine.plan import Plan
from starlayer.shacl_engine.report import build_report, conforms


@dataclass
class Outcome:
    conforms: bool
    report_graph: Any
    results: list[Result]


def validate(data_graph: Any, shapes_graph: Any = None, *, conformance_disallows: Any = None) -> Outcome:
    shapes = shapes_graph if shapes_graph is not None else data_graph
    results = run(Plan(shapes_graph=shapes), data_graph)
    return Outcome(
        conforms=conforms(results, conformance_disallows),
        report_graph=build_report(results, shapes, data_graph, conformance_disallows),
        results=results,
    )
