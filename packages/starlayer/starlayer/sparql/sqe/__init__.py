"""``sqe:`` — a human-readable, editable SPARQL query tree, meant to be
paired with its own SHACL shapes to drive a UI editor. See ``vocab.py``'s
module docstring for the full design and its coverage: SELECT, ASK and
CONSTRUCT with every WHERE-clause element, aggregates, solution modifiers,
subqueries, VALUES, property paths and the SPARQL 1.2 additions (triple
terms, reifiers, annotations, base-direction strings), plus DESCRIBE, FROM /
FROM NAMED, SERVICE and VERSION, and SPARQL Update (``sqe:UpdateRequest``).

This package holds the vocabulary (``sqe.SQE``) and the pieces behind the public functions, which live in
``starlayer.sparql`` and cover SPARQL, Update and SRL alike: ``sparql_to_tree`` (text to tree), ``tree_to_sparql`` (tree to text; run
the text with ``StarLayerGraph.query()``) and ``validate_sparql_tree`` (SHACL, then each query of a conforming tree is run on an
empty graph in Oxigraph, as ``check_query`` does). ``to_text.render_sqe_tree`` and ``shapes.validate_sqe_tree`` are the ``sqe:`` halves
those two call.

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
    "render_sqe_tree": "to_text",
    "validate_sqe_tree": "shapes",
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
