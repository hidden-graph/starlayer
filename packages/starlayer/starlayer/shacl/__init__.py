from starlayer.shacl.adapters import TripleTermAdapter, TripleTermGraph, TripleTermValue
from starlayer.shacl.engine import normalize_graph_inputs, normalize_to_starlayer_graph
from starlayer.shacl.results import ExecutionDiagnostics, ValidationResult
from starlayer.shacl.subgraph_extraction import close_shape
from starlayer.shacl.types import MutableStarLayerGraphProtocol, StarLayerGraphProtocol
from starlayer.shacl.validator import StarLayerShaclProcessor, validate, validate_each

# SHACL 1.2 Inference Rules / Node Expressions / Profiling - deliberately
# NOT flattened into individual names here (2026-10-06 decision, mirroring
# `starlayer.sparql.srl`/`sqe`'s own precedent): `from starlayer.shacl
# import shacl_inference`/`shacl_node_expr`/`shacl_profiling`, then
# `shacl_inference.RulesResult`/etc. Only Core validation (`validate`/
# `validate_each`/`StarLayerShaclProcessor`/`ValidationResult`/
# `ExecutionDiagnostics`/`close_shape`) and the cross-cutting RDF 1.2/
# triple-term infrastructure every one of those spec-specific modules
# itself depends on (`TripleTermAdapter`/`Graph`/`Value`,
# `normalize_to_starlayer_graph`/`normalize_graph_inputs`,
# `StarLayerGraphProtocol`/`MutableStarLayerGraphProtocol`) stay flat.
# The native-component evaluation engine (`STSH`/`ComponentRequest`/
# `ComponentEvaluationResult`/`target_nodes`/`evaluate_component`/
# `build_report`) and subgraph extraction (`SubgraphExtractionResult`/
# `extract_subgraph`) aren't SHACL 1.2 spec documents either - reach them
# via `from starlayer.shacl import engine`/`subgraph_extraction` directly
# (ordinary Python submodule import, no wrapper needed).

__all__ = [
    "StarLayerShaclProcessor",
    "validate",
    "validate_each",
    "TripleTermAdapter",
    "TripleTermGraph",
    "TripleTermValue",
    "normalize_to_starlayer_graph",
    "normalize_graph_inputs",
    "ExecutionDiagnostics",
    "ValidationResult",
    "close_shape",
    "StarLayerGraphProtocol",
    "MutableStarLayerGraphProtocol",
]
