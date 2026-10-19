"""SHACL validation for ``sqe:`` graphs - a thin wrapper combining this
vocabulary's own hand-authored shapes (``sqe_shapes.ttl``) with the shared
expression shapes and ontology (``spexpr:``, from ``..expr_validation``),
since ``sqe:Filter``/``sqe:Bind`` reference ``spexpr:ExpressionShape`` by name
(``sh:node``) - that shape's own *definition* has to be present in the shapes
graph being validated against, not just its ontology class for RDFS reasoning.
Nothing here imports or loads ``salg``.

No public ``ontology_graph()``/``shapes_graph()`` of its own - same choice
``srl.py`` already made ("to avoid two paths to the same two graphs"; see
that module's own comment) and the same reason Manchester doesn't have
them either (`starontology.get_ontology_graph("sqe_owl")`/`"sqe_shacl"`
is the one real path to those graphs). ``sqe_validate()`` combines them
privately below.
"""

from __future__ import annotations

import warnings

from rdflib import Graph

from starlayer import starontology

SHAPES_TURTLE = starontology.get_ontology_graph("sqe_shacl").serialize(format="turtle12")


def _shapes_graph() -> Graph:
    """A fresh ``rdflib.Graph`` combining ``sqe:``'s own shapes with the shared expression shapes
    (``spexpr:``; see ``..expr_validation``). SHACL graphs are mutated by pyshacl during validation, so callers
    get their own copy rather than a shared module-level instance. Nothing here comes from ``salg:``."""
    from ..expr_validation import shapes_graph as spexpr_shapes_graph

    g = spexpr_shapes_graph()
    g.parse(data=SHAPES_TURTLE, format="turtle")
    return g


def _ontology_graph() -> Graph:
    """A fresh ``rdflib.Graph`` combining ``sqe:``'s own RDFS ontology with the shared ``spexpr:`` one, which
    the RDFS-subclass entailment behind ``sh:node spexpr:ExpressionShape`` depends on."""
    from ..expr_validation import ontology_graph as spexpr_ontology_graph

    g = spexpr_ontology_graph()
    g += starontology.get_ontology_graph("sqe_owl")
    return g


def sqe_validate(data_graph: Graph) -> tuple[bool, Graph, str]:
    """Validate ``data_graph`` (e.g. from ``to_rdf.sqe_parse_to_tree``, or
    an LLM-/UI-authored ``sqe:`` graph not yet decoded) against the shapes
    above.

    Goes through ``starlayer.shacl``, never bare ``pyshacl`` - same reason
    ``salg:``'s own ``validate_query()`` does: a ``sqe:`` graph may embed
    genuine RDF 1.2 content (a triple term) that only ``starlayer.shacl``
    understands correctly.

    Args:
        data_graph: The ``sqe:`` RDF graph to validate.

    Returns:
        A ``(conforms, report_graph, report_text)`` tuple.
    """
    from pyshacl.errors import ShapeRecursionWarning

    import starlayer.shacl  # lazy: avoids a circular-import deadlock at module load time
    from starlayer.graph.graph.entailment_regimes import ENTAILMENT

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=ShapeRecursionWarning)
        result = starlayer.shacl.validate(
            data_graph,
            shacl_graph=_shapes_graph(),
            ont_graph=_ontology_graph(),
            inference=ENTAILMENT.RDFS,
            advanced=True,
            max_validation_depth=100,
        )
    return result.conforms, result.report_graph, result.report_text
