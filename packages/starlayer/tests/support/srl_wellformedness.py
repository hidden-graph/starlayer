"""What ``validate_sparql_tree`` reports for the SRL §4.2 well-formedness shapes, as ``(kind, variable, focus node)`` rows.

``kind`` is the name the Python check (``srl_semantic_checks``) gives the same condition, so a test can compare the two.
"""

from __future__ import annotations

import re
from functools import lru_cache

from starlayer import starontology
from starlayer.shacl import SH
from starlayer.sparql import validate_sparql_tree

SRL = "https://github.com/hidden-graph/starlayer/ns/sparql/srl#"

# shape (local name) -> the kind srl_semantic_checks gives the condition
KIND_OF_SHAPE = {
    "TripleTermSubjectShape": "triple_term_in_subject",
    "TripleTermPredicateShape": "triple_term_in_predicate",
    "VariableInDataShape": "variable_in_data",
    "UnsupportedVariableNameShape": "unsupported_variable_name",
    "AggregateInExpressionShape": "aggregate_in_expression",
    "UnboundHeadVariableShape": "unbound_head_variable",
    "UnboundFilterVariableShape": "unbound_filter_variable",
    "UnboundAssignmentExpressionVariableShape": "unbound_assignment_expr_variable",
    "ReusedAssignmentVariableShape": "reused_assignment_variable",
    "VariableInUseShape": "variable_in_use",
    "GroupKeyUnboundShape": "group_key_unbound",
    "AggregationVariableInScopeShape": "aggregation_variable_in_scope",
    "DuplicateAggregationVariableShape": "duplicate_aggregation_variable",
    "UnboundAggregationArgumentShape": "unbound_aggregation_argument",
}
SHAPE_OF_KIND = {kind: shape for shape, kind in KIND_OF_SHAPE.items()}
NO_VARIABLE = {"triple_term_in_subject", "triple_term_in_predicate", "aggregate_in_expression"}  # the message names a term, or nothing


@lru_cache(maxsize=1)
def _message_patterns() -> dict[str, re.Pattern]:
    """Shape local name -> a pattern for its message, with the variable as group 1 (a message names it as ``{?v}`` or ``{?k}``)."""
    shapes = starontology.get_ontology_graph("srl_shacl")
    out = {}
    for subject, _p, constraint in shapes.triples((None, SH.sparql, None)):
        name = subject.value.removeprefix(SRL)
        if name not in KIND_OF_SHAPE:
            continue
        template = next(iter(shapes.objects(constraint, SH.message))).value
        escaped = re.escape(template)
        out[name] = re.compile(re.sub(r"\\\{\\\?\w+\\\}", "(.+?)", escaped, count=1) + "$", re.S)
    return out


def findings(tree_graph):
    """``(report, rows)``: ``rows`` has ``(kind, variable name or None, focus node)`` for each §4.2 shape result of ``validate_sparql_tree``."""
    report = validate_sparql_tree(tree_graph)
    graph = report.report_graph
    rows = []
    for result in graph.subjects(SH.resultSeverity, SH.Violation):
        source = next(iter(graph.objects(result, SH.sourceShape)), None)  # the ordering problem has none
        shape = source.value.removeprefix(SRL) if source is not None else None
        if shape not in KIND_OF_SHAPE:
            continue
        kind = KIND_OF_SHAPE[shape]
        focus = next(iter(graph.objects(result, SH.focusNode)))
        message = next(iter(graph.objects(result, SH.resultMessage))).value
        variable = None
        if kind not in NO_VARIABLE:
            match = _message_patterns()[shape].match(message)
            assert match, f"message of {shape} does not fit its template: {message!r}"
            variable = match.group(1)
        rows.append((kind, variable, focus))
    return report, rows
