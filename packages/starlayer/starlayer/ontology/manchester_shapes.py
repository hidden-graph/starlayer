"""SHACL shapes over the ``manch:`` vocabulary - structural validation for a
Manchester-AST-as-RDF graph (LLM-authored or hand-authored) before attempting
``to_ast_rdf.rdf_ast_to_manchester_ast``. Mirrors the sibling ``starlayer.sparql``
package's ``ontology/sparql_shapes.py`` design exactly (same loader/validate
shape, same discipline) - see that module's own docstring for the full
design rationale, not re-derived here.

**Same known limitation as ``salg:``'s own shapes**: dispatch shapes
(``ClassExpressionShape``, ``PropertyExpressionShape``, ``DataRangeShape``,
``FrameShape``, ``ClauseShape``, ``MiscAxiomShape``) use ``sh:class``, never
``sh:or``/``sh:node`` of every concrete member - the same pyshacl
shape-recursion-guard reasoning ``salg:GraphPatternShape``'s own comment in
``sparql_shapes.ttl`` documents at length (shape-identity-based recursion
tracking misfires on ordinary, shallow nesting when a dispatch shape's own
alternatives loop back to it via ``sh:node``/``sh:or``; ``sh:class`` never
touches that stack at all). ``rdf:List`` structural checks
(``manch:operands``/``manch:items``/etc's own well-formedness) likewise use
a single ``sh:sparql`` constraint per list-of-X type, not a recursive
``NodeShape``, for the same reason.

Scope: structural well-formedness only, never cross-referential semantics
(e.g. whether a frame's own ``manch:subject`` is declared exactly once
elsewhere in the document) - the same accepted-limitation framing ``salg:``
documents for SPARQL.
"""

from __future__ import annotations

import warnings

import starontology
from rdflib import Graph

from . import ontology_graph

try:
    from pyshacl.errors import ShapeRecursionWarning
except ImportError as exc:  # pragma: no cover - exercised only when pyshacl isn't installed
    raise ImportError(
        "starlayer.ontology.manchester_shapes requires pyshacl - install with "
        "`pip install -e '.[test]'` or `pip install pyshacl`"
    ) from exc


def shapes_graph() -> Graph:
    """A fresh ``StarLayerGraph`` of the shapes above (SHACL graphs are
    mutated by pyshacl during validation, so callers get their own copy
    rather than a shared module-level instance)."""
    return starontology.get_ontology_graph("manchester_shacl")


def validate(data_graph: Graph) -> tuple[bool, Graph, str]:
    """Validate ``data_graph`` (e.g. from ``to_ast_rdf.parse_manchester_ast``,
    or an LLM-authored ``manch:`` graph not yet decoded) against the shapes
    above.

    Runs with RDFS reasoning enabled (``ont_graph=ontology_graph()``,
    ``inference="rdfs"``) - this is what lets ``ClassExpressionShape``/
    ``PropertyExpressionShape``/``DataRangeShape``/``FrameShape``/
    ``ClauseShape``/``MiscAxiomShape`` be a single ``sh:class`` check
    against an abstract superclass instead of enumerating every concrete
    tag by name, the same reasoning ``sparql_shapes.py::validate()``
    documents for ``salg:``.

    Goes through ``starlayer.shacl.validate()``, never bare ``pyshacl`` - this
    validates a caller-supplied ``data_graph`` that may be genuine RDF 1.2
    content, which only ``starlayer.shacl`` understands correctly (the same rule
    ``StarLayerGraph.derive_shape()`` follows).

    Returns ``(conforms, results_graph, results_text)`` for backward
    compatibility with every existing caller of this function, unpacked
    from ``starlayer.shacl``'s own ``ValidationResult``.
    """
    import starlayer.shacl  # lazy: avoids a circular-import deadlock at module load time

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=ShapeRecursionWarning)
        result = starlayer.shacl.validate(
            data_graph,
            shacl_graph=shapes_graph(),
            ont_graph=ontology_graph(),
            inference="rdfs",
            advanced=True,
            max_validation_depth=100,
        )
    return result.conforms, result.report_graph, result.report_text
