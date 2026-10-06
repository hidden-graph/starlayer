"""``sqe:`` — a human-readable, editable SPARQL query tree, meant to be
paired with its own SHACL shapes to drive a UI editor. See ``vocab.py``'s
module docstring for the full design and the deliberate v1 scope
reduction (SELECT/ASK/CONSTRUCT only; no aggregates/subqueries/VALUES/
Update yet - property paths ARE covered).

Not flattened into the top-level ``starlayer.sparql`` namespace - same
precedent ``salg``/``srl`` already follow: ``from starlayer.sparql import
sqe``, then ``sqe.sqe_parse_to_tree(...)``/etc.

Four public entry points, the whole public surface: ``sqe_parse_to_tree``
(encode), ``sqe_tree_to_text`` (render back to text), ``sqe_tree_to_query``
(decode to a real executable ``Query``), ``sqe_validate`` (SHACL).
``to_rdf.py``'s own ``_query_to_sqe_rdf`` (takes an already-``parseQuery``
'd tree rather than text) stays private - a low-level input shape nothing
outside this package currently needs.

No separate ``ontology_graph()``/``shapes_graph()`` of its own either -
same choice ``srl.py``/`starontology.manchester` already made, to avoid
two paths to the same two graphs. Get them directly:
``starontology.get_ontology_graph("sqe_owl")``/``"sqe_shacl"``.
"""

from .from_rdf import sqe_tree_to_query
from .to_rdf import sqe_parse_to_tree
from .to_text import sqe_tree_to_text
from .vocab import SQE

__all__ = [
    "SQE",
    "sqe_parse_to_tree",
    "sqe_tree_to_query",
    "sqe_tree_to_text",
]

try:
    from .shapes import sqe_validate

    __all__ += ["sqe_validate"]
except ImportError:
    # pyshacl is a test/optional dependency - shapes.py is unusable
    # without it, but the rest of this submodule must still import fine.
    pass
