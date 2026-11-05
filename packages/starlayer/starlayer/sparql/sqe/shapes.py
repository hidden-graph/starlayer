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
from collections.abc import Iterable
from typing import Any

import pyoxigraph as ox

from starlayer import starontology

SHAPES_TURTLE = starontology.get_ontology_graph("sqe_shacl").serialize(format="turtle12")


def _merge_into(dst, src):
    """``dst += src``."""
    dst.extend(src)


_RDFS = "http://www.w3.org/2000/01/rdf-schema#"
_RDF_TYPE = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")


def _closure(pairs: dict) -> dict:
    """The transitive closure of a ``{node: {direct supers}}`` map (a node is not its own super unless a cycle says so)."""
    out: dict = {}
    for start in pairs:
        seen: set = set()
        stack = list(pairs[start])
        while stack:
            node = stack.pop()
            if node not in seen:
                seen.add(node)
                stack.extend(pairs.get(node, ()))
        out[start] = seen
    return out


@functools.lru_cache(maxsize=1)
def _schema() -> tuple[dict, dict, dict, dict]:
    """``(super-properties, super-classes, domains, ranges)`` of the ``sqe:`` + ``spexpr:`` ontology, each transitively closed
    (RDFS rules 5, 11 as maps; 2, 3, 7, 9 are applied by ``_entailed_copy``)."""
    ontology = _ontology_graph()
    sub_prop: dict = {}
    sub_class: dict = {}
    domains: dict = {}
    ranges: dict = {}
    for s, p, o in ontology.triples((None, None, None)):
        if not isinstance(p, ox.NamedNode):
            continue
        target = {_RDFS + "subPropertyOf": sub_prop, _RDFS + "subClassOf": sub_class, _RDFS + "domain": domains, _RDFS + "range": ranges}.get(p.value)
        if target is not None:
            target.setdefault(s, set()).add(o)
    sub_prop, sub_class = _closure(sub_prop), _closure(sub_class)
    return sub_prop, sub_class, domains, ranges


def _entailed_copy(data_graph: Any) -> Any:
    """A copy of ``data_graph`` closed under the RDFS rules the ``sqe:`` shapes rely on: sub-property (rdfs7), domain (rdfs2),
    range (rdfs3) and sub-class (rdfs9) inference from the ontology. Done here, natively, because the general RDFS closure
    (``infer()``) runs on owlrl and so on rdflib."""
    sub_prop, sub_class, domains, ranges = _schema()
    copy = data_graph.copy()
    added: set = set()
    typed: list = []

    def type_it(node: Any, classes: Iterable) -> None:
        for cls in classes:
            typed.append((node, cls))

    for s, p, o in list(data_graph.triples((None, None, None))):
        for q in (p, *sub_prop.get(p, ())):
            if q != p:
                added.add((s, q, o))
            type_it(s, domains.get(q, ()))
            if not isinstance(o, (ox.Literal, ox.Triple)):
                type_it(o, ranges.get(q, ()))
        if p == _RDF_TYPE:
            type_it(s, [o])
    for node, cls in typed:
        for c in (cls, *sub_class.get(cls, ())):
            added.add((node, _RDF_TYPE, c))
    copy.extend(list(added))
    return copy


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

    result = starlayer.shacl.validate(
        _entailed_copy(data_graph),
        shacl_graph=_shapes_graph(),
        invalid_terms="lenient",  # query / ontology trees hold relative IRIs: opaque terms to the shapes
        advanced=True,
        max_validation_depth=100,
    )
    return result.conforms, result.report_graph, result.report_text
