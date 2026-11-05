"""``sqe:`` — a human-readable, editable SPARQL query tree, meant to be
paired with its own SHACL shapes to drive a UI editor. See ``vocab.py``'s
module docstring for the full design and its coverage: SELECT, ASK and
CONSTRUCT with every WHERE-clause element, aggregates, solution modifiers,
subqueries, VALUES, property paths and the SPARQL 1.2 additions (triple
terms, reifiers, annotations, base-direction strings), plus DESCRIBE, FROM /
FROM NAMED, SERVICE and VERSION for trees from ``parse_sparql.sparql_to_tree``.
SPARQL Update trees (``sqe:UpdateRequest``, from ``parse_sparql.sparql_update_to_tree``) are validated and rendered by
``sqe_validate`` and ``sqe_tree_to_text``; anything else raises rather than being dropped.

Not flattened into the top-level ``starlayer.sparql`` namespace - same
precedent ``srl`` already follows: ``from starlayer.sparql import
sqe``, then ``sqe.sqe_parse_to_tree(...)``/etc.

Three public functions, the whole functional surface: ``sqe_parse_to_tree``
(encode - validates the result and raises ``SQEValidationError`` on a
non-conforming tree, see below), ``sqe_tree_to_text`` (render back to
text; run the text with ``StarLayerGraph.query()``),
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

from __future__ import annotations

import importlib
from typing import Any

# Names are imported on first use (PEP 562), so ``import starlayer.sparql.sqe`` stays cheap. The trees are ``StarLayerGraph``s of
# pyoxigraph terms and nothing here needs rdflib.
_LAZY = {
    "SQE": "vocab",
    "SQEError": "to_rdf",
    "SQEValidationError": "to_rdf",
    "sqe_parse_to_tree": "to_rdf",
    "sqe_tree_to_text": "to_text",
    "sqe_validate": "shapes",
}

__all__ = sorted(_LAZY)


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        value = getattr(importlib.import_module(f"{__name__}.{_LAZY[name]}"), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))
