"""The public SHACL 1.2 API: validation, rules, node expressions, shape fragments and SHACL UI helpers.

Applications import from here rather than from submodules; a need that only a submodule meets is a missing public
component, except for the items the comment below the imports lists as still submodule-only.
"""

from starlayer.shacl.candidates import Candidates
from starlayer.shacl.derive import derive_shape
from starlayer.shacl.engine.terms import SH
from starlayer.shacl.errors import (
    ExecutionError,
    FormatError,
    ShapeError,
)
from starlayer.shacl.form_model import (
    FieldConstraints,
    FormField,
    FormModel,
    FormSection,
    FormValue,
)
from starlayer.shacl.meta_shapes import MetaScope, meta_scope, meta_validate
from starlayer.shacl.node_expression_api import (
    evaluate_expression,
    node_expression_functions,
    node_expression_operators,
)
from starlayer.shacl.paths import is_inverse, path_values
from starlayer.shacl.profiling import declared_conformance_profile, derive_conforms_to
from starlayer.shacl.profiling.conformance import CONFORMANCE
from starlayer.shacl.report_results import (
    ReportDiff,
    ReportResult,
    diff_reports,
    report_results,
)
from starlayer.shacl.results import RulesResult, ValidationReport
from starlayer.shacl.shape_types import infer_types
from starlayer.shacl.shapes_graphs import (
    close_shape,
    extract_shapes_graph,
    referenced_shapes,
    rule_dependencies,
    shapes_graph_members,
)
from starlayer.shacl.subgraph_extraction import extract_subgraph
from starlayer.shacl.ui.widget_selection import (
    WidgetCondition,
    WidgetReport,
    WidgetTrace,
    WidgetTraceCandidate,
    explain_widgets,
    select_widget,
    select_widgets,
)
from starlayer.shacl.validator import (
    StarShaclProcessor,
    apply_rules,
    candidate_values,
    check_value,
    evaluate,
    form_model,
    target_nodes,
    target_shapes,
    validate,
    validate_each,
    value_form,
)
from starlayer.shacl.value_check import ValueCheck


def __getattr__(name: str):
    """``StarShaclSchema``, the old name of ``StarShaclProcessor``: the same class, with a DeprecationWarning."""
    if name == "StarShaclSchema":
        import warnings

        warnings.warn(
            "StarShaclSchema is renamed StarShaclProcessor; the old name will be removed",
            DeprecationWarning,
            stacklevel=2,
        )
        return StarShaclProcessor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Everything an application needs is importable from here: apps do not reach into submodules (a need to is a missing
# public component). Processing modes: validate / validate_each / apply_rules / evaluate / extract_subgraph, with the
# result classes (ValidationReport / RulesResult), StarShaclProcessor and target_nodes. Shapes graphs: close_shape, extract_shapes_graph. Shapes graph
# introspection: infer_types, shapes_graph_members, path_values, is_inverse.
# Node expressions: evaluate_expression, node_expression_functions, node_expression_operators. SHACL UI: select_widget(s).
# Deriving a shape from data (a StarLayer feature, not SHACL): derive_shape.
#
# Profiling (SHACL 1.2 Profiling): derive_conforms_to, declared_conformance_profile and the CONFORMANCE namespace; `profiling` is still importable as a
# submodule. Checking shapes: meta_validate, meta_scope.
#
# Still reached only through a submodule: `engine` (evaluate_component() and friends, deprecated); `starontology.get_raw_url(name)`.

__all__ = [
    "SH",
    "StarShaclProcessor",
    "validate",
    "validate_each",
    "apply_rules",
    "evaluate",
    "extract_subgraph",
    "close_shape",
    "extract_shapes_graph",
    "derive_shape",
    "meta_validate",
    "meta_scope",
    "MetaScope",
    "derive_conforms_to",
    "declared_conformance_profile",
    "CONFORMANCE",
    "ValidationReport",
    "ReportResult",
    "ReportDiff",
    "report_results",
    "diff_reports",
    "RulesResult",
    "target_nodes",
    "target_shapes",
    "candidate_values",
    "Candidates",
    "value_form",
    "check_value",
    "ValueCheck",
    "form_model",
    "FormModel",
    "FormSection",
    "FormField",
    "FormValue",
    "FieldConstraints",
    "select_widget",
    "select_widgets",
    "WidgetReport",
    "WidgetCondition",
    "WidgetTrace",
    "WidgetTraceCandidate",
    "explain_widgets",
    "evaluate_expression",
    "node_expression_functions",
    "node_expression_operators",
    "infer_types",
    "shapes_graph_members",
    "referenced_shapes",
    "rule_dependencies",
    "path_values",
    "is_inverse",
    "ShapeError",
    "ExecutionError",
    "FormatError",
]
