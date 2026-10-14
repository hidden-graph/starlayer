from starlayer.shacl.adapters import TripleTermAdapter, TripleTermGraph, TripleTermValue
from starlayer.shacl.engine import (
    normalize_graph_inputs,
    normalize_to_starlayer_graph,
    target_nodes,
)
from starlayer.shacl.results import (
    ExecutionDiagnostics,
    RulesResult,
    ValidationResult,
)
from starlayer.shacl.subgraph_extraction import extract_subgraph
from starlayer.shacl.types import MutableStarLayerGraphProtocol, StarLayerGraphProtocol
from starlayer.shacl.validator import (
    StarShaclSchema,
    apply_rules,
    evaluate,
    validate,
    validate_each,
)

# Flat here: the five processing-mode functions (validate/validate_each/
# apply_rules/evaluate/extract_subgraph), the result classes that still
# carry real information (ValidationResult/RulesResult/
# ExecutionDiagnostics - EvaluationResult/SubgraphExtractionResult no
# longer exist; evaluate()/extract_subgraph() return a plain graph or None
# directly instead), StarShaclSchema, target_nodes (a standalone
# introspection question - "which nodes would this shape target?" - useful
# without running a full validate() pass), and the cross-cutting RDF 1.2/
# triple-term infrastructure every module depends on (TripleTermAdapter/
# Graph/Value, normalize_to_starlayer_graph/normalize_graph_inputs,
# StarLayerGraphProtocol/MutableStarLayerGraphProtocol).
#
# Reached only via an explicit submodule import: `shacl_profiling`
# (SHACL 1.2 Profiling's declared_conformance_profile()/
# derive_conforms_to() - self-declaration/report-annotation utilities, not
# a processing mode); `node_expressions.eval_expr` (a lower-level, one-
# expression-at-a-time primitive); `engine` (evaluate_component()/
# build_report()/ComponentRequest/STSH - evaluate_component() is a
# hardcoded dispatcher with no extension mechanism and no standalone use
# case, build_report() only pairs with its own output shape, STSH is only
# needed to define a new native component); and
# `StarShaclSchema.close_shape(shape)`, a method, not a bare function.

__all__ = [
    "StarShaclSchema",
    "validate",
    "validate_each",
    "apply_rules",
    "evaluate",
    "extract_subgraph",
    "TripleTermAdapter",
    "TripleTermGraph",
    "TripleTermValue",
    "normalize_to_starlayer_graph",
    "normalize_graph_inputs",
    "ExecutionDiagnostics",
    "ValidationResult",
    "RulesResult",
    "target_nodes",
    "StarLayerGraphProtocol",
    "MutableStarLayerGraphProtocol",
]
