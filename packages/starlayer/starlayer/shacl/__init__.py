from starlayer.shacl.errors import (
    EvaluationFailure,
    MetaShaclError,
    RuleError,
    ShapeError,
)
from starlayer.shacl.meta_shapes import parameter_value_shapes, sparql_query_problems
from starlayer.shacl.node_expression_api import (
    evaluate_expression,
    node_expression_functions,
    node_expression_operators,
)
from starlayer.shacl.normalization import (
    normalize_graph_inputs,
    normalize_to_starlayer_graph,
)
from starlayer.shacl.paths import is_inverse, path_values
from starlayer.shacl.results import (
    ExecutionDiagnostics,
    RulesResult,
    ValidationResult,
)
from starlayer.shacl.shape_types import infer_types
from starlayer.shacl.shapes_graphs import shapes_graph_members
from starlayer.shacl.subgraph_extraction import extract_subgraph
from starlayer.shacl.types import MutableStarLayerGraphProtocol, StarLayerGraphProtocol
from starlayer.shacl.ui_widget_selection import select_widget, select_widgets
from starlayer.shacl.validator import (
    StarShaclSchema,
    apply_rules,
    evaluate,
    target_nodes,
    validate,
    validate_each,
)

# Everything an application needs is importable from here: apps do not reach into submodules (a need to is a missing
# public component). Processing modes: validate / validate_each / apply_rules / evaluate / extract_subgraph, with the
# result classes (ValidationResult / RulesResult / ExecutionDiagnostics), StarShaclSchema and target_nodes. Shapes graph
# introspection: infer_types, shapes_graph_members, path_values, is_inverse, sparql_query_problems, parameter_value_shapes.
# Node expressions: evaluate_expression, node_expression_functions, node_expression_operators. SHACL UI: select_widget(s).
# Graph normalisation: normalize_to_starlayer_graph /
# normalize_graph_inputs, StarLayerGraphProtocol / MutableStarLayerGraphProtocol.
#
# Still reached only through a submodule: `shacl_profiling` (Profiling's declared_conformance_profile() /
# derive_conforms_to()); `engine` (evaluate_component() and friends, deprecated); `starontology.get_raw_url(name)`;
# `StarShaclSchema.close_shape(shape)`, a method.

__all__ = [
    "StarShaclSchema",
    "validate",
    "validate_each",
    "apply_rules",
    "evaluate",
    "extract_subgraph",
    "normalize_to_starlayer_graph",
    "normalize_graph_inputs",
    "ExecutionDiagnostics",
    "ValidationResult",
    "RulesResult",
    "target_nodes",
    "StarLayerGraphProtocol",
    "MutableStarLayerGraphProtocol",
    "evaluate_expression",
    "node_expression_functions",
    "node_expression_operators",
    "infer_types",
    "shapes_graph_members",
    "path_values",
    "is_inverse",
    "sparql_query_problems",
    "parameter_value_shapes",
    "select_widget",
    "select_widgets",
    "ShapeError",
    "RuleError",
    "EvaluationFailure",
    "MetaShaclError",
]
