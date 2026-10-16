"""``sqe:`` — a human-readable, editable SPARQL query tree, meant to be
paired with its own SHACL shapes to drive a UI editor. See ``vocab.py``'s
module docstring for the full design and the deliberate v1 scope
reduction (SELECT/ASK/CONSTRUCT only; no aggregates/subqueries/VALUES/
Update yet - property paths ARE covered).

Not flattened into the top-level ``starlayer.sparql`` namespace - same
precedent ``salg``/``srl`` already follow: ``from starlayer.sparql import
sqe``, then ``sqe.sqe_parse_to_tree(...)``/etc.

Four public functions, the whole functional surface: ``sqe_parse_to_tree``
(encode - validates the result and raises ``SQEValidationError`` on a
non-conforming tree, see below), ``sqe_tree_to_text`` (render back to
text), ``sqe_tree_to_query`` (decode to a real executable ``Query``),
``sqe_validate`` (SHACL - still needed standalone for re-validating a tree
edited by hand after parsing, since such edits bypass
``sqe_parse_to_tree`` entirely). ``to_rdf.py``'s own ``_query_to_sqe_rdf``
(takes an already-``parseQuery``'d tree rather than text, and skips
validation) stays private - a low-level input shape nothing outside this
package currently needs.

``SQEError``/``SQEValidationError`` are also exported - the latter is what
``sqe_parse_to_tree`` raises, carrying the full report as ``.report_text``/
``.report_graph`` attributes, the same "succeed with a usable object, or
raise" contract ``prepareQuery()``/``srl.parse_ruleset()`` already give
their own callers.

No separate ``ontology_graph()``/``shapes_graph()`` of its own either -
same choice ``srl.py``/`starontology.manchester` already made, to avoid
two paths to the same two graphs. Get them directly:
``starontology.get_ontology_graph("sqe_owl")``/``"sqe_shacl"``.
"""

from .from_rdf import sqe_tree_to_query
from .to_rdf import SQEError, SQEValidationError, sqe_parse_to_tree
from .to_text import sqe_tree_to_text
from .vocab import SQE

__all__ = [
    "SQE",
    "SQEError",
    "SQEValidationError",
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
