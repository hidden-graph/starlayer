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

import functools
from typing import Any

from starlayer import starontology

from ..expr_validation import rdfs_entailed_copy, rdfs_schema

SHAPES_TURTLE = starontology.get_ontology_graph("sqe_shacl").serialize(format="turtle12")


def _merge_into(dst, src):
    """``dst += src``."""
    dst.extend(src)


@functools.lru_cache(maxsize=1)
def _schema() -> tuple[dict, dict, dict, dict]:
    """The closed schema maps of the ``sqe:`` + ``spexpr:`` ontology (see ``expr_validation.rdfs_schema``)."""
    return rdfs_schema(_ontology_graph())


def _entailed_copy(data_graph: Any) -> Any:
    """``data_graph`` closed under the RDFS rules the ``sqe:`` shapes rely on (see ``expr_validation.rdfs_entailed_copy``)."""
    return rdfs_entailed_copy(data_graph, _schema())


def _shapes_graph() -> Any:
    """A fresh ``StarLayerGraph`` combining ``sqe:``'s own shapes with the shared expression shapes
    (``spexpr:``; see ``..expr_validation``). Callers get their own copy, so a validation never changes a shared
    instance. Nothing here comes from ``salg:``."""
    from ..expr_validation import shapes_graph as spexpr_shapes_graph

    g = spexpr_shapes_graph()
    g.parse(data=SHAPES_TURTLE, format="turtle")
    return g


def _ontology_graph() -> Any:
    """A fresh ``StarLayerGraph`` combining ``sqe:``'s own RDFS ontology with the shared ``spexpr:`` one, which
    the RDFS-subclass entailment behind ``sh:node spexpr:ExpressionShape`` depends on."""
    from ..expr_validation import ontology_graph as spexpr_ontology_graph

    g = spexpr_ontology_graph()
    _merge_into(g, starontology.get_ontology_graph("sqe_owl"))
    return g


def sqe_validate(data_graph: Any) -> tuple[bool, Any, str]:
    """Validate ``data_graph`` (e.g. from ``to_rdf.sqe_parse_to_tree``, or
    an LLM-/UI-authored ``sqe:`` graph not yet decoded) against the shapes
    above.

    Goes through ``starlayer.shacl`` (the native SHACL 1.2 engine): a ``sqe:`` graph may embed
    genuine RDF 1.2 content (a triple term).

    Args:
        data_graph: The ``sqe:`` RDF graph (a ``StarLayerGraph``) to validate.

    Returns:
        A ``(conforms, report_graph, report_text)`` tuple.
    """

    import starlayer.shacl  # lazy: avoids a circular-import deadlock at module load time

    from ._memtree import as_engine_graph

    data_graph, _ = as_engine_graph(data_graph)
    result = starlayer.shacl.validate(
        _entailed_copy(data_graph),
        shacl_graph=_shapes_graph(),
        invalid_terms="lenient",  # query / ontology trees hold relative IRIs: opaque terms to the shapes
        advanced=True,
        max_validation_depth=100,
    )
    return result.conforms, result.report_graph, result.report_text
