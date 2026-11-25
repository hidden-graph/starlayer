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
(encode - any text the parser understands gives a tree, with no
shape check; a ``FormatError`` or ``ExecutionError`` only when the text cannot be understood), ``sqe_tree_to_text`` (render back to
text; run the text with ``StarLayerGraph.query()``),
``sqe_validate`` (SHACL, then each query of a conforming tree is run on an empty graph in Oxigraph, as ``check_query`` does - where the problems of a parsed or
hand-edited tree are reported). ``to_rdf.py``'s own ``_query_to_sqe_rdf``
(takes an already-``parseQuery``'d tree rather than text, and does
no validation) stays private - a low-level input shape nothing outside this
package currently needs.

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
    "sqe_parse_to_tree": "to_rdf",
    "sqe_tree_to_text": "to_text",
    "sqe_validate": "shapes",
}

__all__ = sorted(_LAZY)


def __getattr__(name: str) -> Any:
    """Import a public ``sqe`` name from its submodule on first access and cache it in the module namespace."""
    if name in _LAZY:
        value = getattr(importlib.import_module(f"{__name__}.{_LAZY[name]}"), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """List the module's names including the public ones not imported yet."""
    return sorted(set(globals()) | set(_LAZY))
