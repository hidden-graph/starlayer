"""SHACL shapes over the ``srl:`` vocabulary - structural validation for an
SRL rule-set graph (e.g. from ``srl_to_rdf.ruleset_to_rdf``, or an
LLM-authored ``srl:`` graph not yet decoded) before attempting
``srl_from_rdf.rdf_to_ruleset``.

Thin wrapper, same shape as ``sparql_shapes.py``: the real shapes live in
``starontology``'s ``srl_shapes.ttl``/``srl-ontology.ttl`` (edit those
directly, not this file). A ``filter.expr``/``assign.expr`` expression
tree is validated by the *existing* ``salg:`` shapes (``sh:class
salg:Expression``) - no separate ``srl:`` expression vocabulary exists, so
this loads the ``salg:`` shapes/ontology alongside the ``srl:`` ones and
runs with the same RDFS reasoning ``sparql_shapes.py.validate()`` already
relies on for exactly this kind of abstract-superclass dispatch.
"""

from __future__ import annotations

import warnings

import starontology
from rdflib import Graph

try:
    from pyshacl.errors import ShapeRecursionWarning
except ImportError as exc:  # pragma: no cover - exercised only when pyshacl isn't installed
    raise ImportError(
        "starsparql.ontology.srl_shapes requires pyshacl - install with "
        "`pip install -e '.[test]'` or `pip install pyshacl`"
    ) from exc


def ontology_graph() -> Graph:
    """The ``srl:`` RDFS ontology, combined with ``salg:``'s (needed for
    the ``sh:class salg:Expression``/``salg:Variable`` checks below)."""
    g = starontology.srl_ontology_graph()
    g += starontology.sparql_ontology_graph()
    return g


def shapes_graph() -> Graph:
    """A fresh ``rdflib.Graph`` of the ``srl:`` shapes, combined with
    ``salg:``'s (needed for the same reason as ``ontology_graph()`` above -
    an expression tree inside ``srl:expr`` is validated by the existing
    ``salg:ExpressionShape``, not reimplemented here)."""
    g = starontology.srl_shapes_graph()
    g += starontology.sparql_shapes_graph()
    return g


def validate(data_graph: Graph) -> tuple[bool, Graph, str]:
    """Validate ``data_graph`` against the ``srl:`` shapes above.

    Goes through ``starshacl.validate()``, never bare ``pyshacl`` - same
    rule every other shapes module in this stack follows, since a
    caller-supplied graph may carry genuine RDF 1.2 content (a triple
    term as a ``srl:subject``/``srl:object``) that only ``starshacl``
    understands correctly.

    Returns ``(conforms, results_graph, results_text)``, unpacked from
    ``starshacl``'s own ``ValidationResult`` - matching
    ``sparql_shapes.validate()``'s own return shape.
    """
    import starshacl  # lazy: avoids a circular-import deadlock at module load time

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=ShapeRecursionWarning)
        result = starshacl.validate(
            data_graph,
            shacl_graph=shapes_graph(),
            ont_graph=ontology_graph(),
            inference="rdfs",
            advanced=True,
            max_validation_depth=100,
        )
    return result.conforms, result.report_graph, result.report_text
