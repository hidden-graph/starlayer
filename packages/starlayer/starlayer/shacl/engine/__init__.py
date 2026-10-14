from starlayer.shacl.engine.contracts import ComponentRequest
from starlayer.shacl.engine.core import (
    STSH,
    build_report,
    evaluate_component,
    target_nodes,
)
from starlayer.shacl.engine.normalization import (
    normalize_graph_inputs,
    normalize_to_starlayer_graph,
)

# _ComponentEvaluationResult (engine/core.py) is not re-exported here:
# evaluate_component() is a hardcoded dispatcher over a fixed set of
# component names, with no extension mechanism for a caller to register a
# new component type - so its own return type has no reason to be part of
# the public surface either. A caller importing evaluate_component
# directly still gets a real instance back and can read .conforms/
# .violations off it - just not a clean type-hintable import path.

__all__ = [
    "ComponentRequest",
    "STSH",
    "target_nodes",
    "evaluate_component",
    "build_report",
    "normalize_to_starlayer_graph",
    "normalize_graph_inputs",
]
