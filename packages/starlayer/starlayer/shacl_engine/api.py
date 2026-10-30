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
    rule_result: Any = None


def validate(
    data_graph: Any,
    shapes_graph: Any = None,
    *,
    conformance_disallows: Any = None,
    rules: bool | None = None,
    inference: Any = None,
    ont_graph: Any = None,
) -> Outcome:
    """Validate ``data_graph`` against ``shapes_graph`` (default: the data graph itself).

    ``rules``: ``None`` runs the inference rules first when the shapes graph declares ``sh:entailment``; ``True`` runs the
    default rule set; ``False`` never. Rules never modify ``data_graph``; validation then runs on data plus inferred
    triples, and the ``RuleResult`` is on ``Outcome.rule_result``.

    ``inference`` (an entailment regime such as ``"rdfs"`` or ``"owlrl"``) and ``sh:entailment`` declared in the shapes
    graph run the entailment closure first (see ``entailment.py``); ``ont_graph`` supplies axioms visible to entailment
    only. Neither modifies ``data_graph``.
    """
    from starlayer.shacl_engine.entailment import resolve_data_view

    shapes = shapes_graph if shapes_graph is not None else data_graph
    data_graph = resolve_data_view(data_graph, shapes, inference=inference, ont_graph=ont_graph)
    rule_result = None
    if rules is not False:
        from starlayer.shacl_engine.rules import apply_rules, entailment_selection

        active, sets = entailment_selection(shapes) if rules is None else (True, None)
        if active:
            rule_result = apply_rules(data_graph, shapes, rule_sets=sets or None)
            data_graph = rule_result.view
    results = run(Plan(shapes_graph=shapes), data_graph)
    return Outcome(
        conforms=conforms(results, conformance_disallows),
        report_graph=build_report(results, shapes, data_graph, conformance_disallows),
        results=results,
        rule_result=rule_result,
    )
