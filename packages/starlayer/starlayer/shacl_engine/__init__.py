"""Native SHACL 1.2 engine (branch ``shacl-engine``): no pyshacl, no rdflib object model in the core.

See ``docs/working/shacl-engine-design.md``. ``validate()`` is the entry point; ``validate_each()`` validates several data
graphs against one shapes graph; ``evaluate()`` is the ``sh:values`` / ``sh:defaultValue`` processing mode; ``extract_subgraph()``, ``extract_shapes_graph()``
and ``close_shape()`` are the shape-model consumers.
``starlayer.shacl`` keeps working beside it as the differential oracle until cut-over.
"""

from starlayer.shacl_engine.api import validate, validate_each
from starlayer.shacl_engine.evaluate import evaluate
from starlayer.shacl_engine.shapes_graphs import close_shape, extract_shapes_graph
from starlayer.shacl_engine.subgraph import extract_subgraph

__all__ = ["close_shape", "evaluate", "extract_shapes_graph", "extract_subgraph", "validate", "validate_each"]
