"""The validation data for the shared expression vocabulary (``spexpr:``): its SHACL shapes graph and RDFS
ontology, ready to combine with a vocabulary's own.

``sqe:``, ``srl:`` and ``salg:`` all embed ``spexpr:`` expressions (a ``FILTER``, a ``BIND``, an ``ORDER BY``
key), and validating one needs the same two things: the shapes for every expression builtin and the RDFS
subclass axioms the ``sh:class spexpr:Expression`` dispatch relies on. They live here, in one place that imports
nothing from any of those vocabularies, so a vocabulary can validate its own trees without importing a sibling's
package. (``salg`` imports this module; ``sqe`` must not import ``salg``.)

The per-builtin shapes are generated from ``expr_families._EXPR_NODE_FAMILY`` rather than written by hand, so
they cannot drift from the table the encoder uses. This module needs rdflib and ``starontology`` only, not
pyshacl.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pyoxigraph as ox

from starlayer import starontology

from .expr_families import _EXPR_NODE_FAMILY


def _merge_into(dst, src):
    """``dst += src`` for graphs of either kind (the ontology loaders return whatever class ``StarLayerGraph`` is)."""
    dst.extend(list(iter(src)))


def expression_shapes_turtle() -> str:
    """The short per-expression-node-name declarations (one per real builtin), each pointing at its family's
    reusable body shape (``spexpr:_<Family>ExprBodyShape``) with ``sh:node``.

    Targets ``spexpr:``: both the target class and the body shape live in the shared expression vocabulary, and
    a node typed ``spexpr:Name`` would never match a ``sh:targetClass salg:Name`` shape. Carries its own
    ``@prefix spexpr:`` line, so it is self-contained whatever it gets concatenated with.

    Returns:
        The generated Turtle declarations, newline-terminated, with their own leading ``@prefix`` line.
    """
    declarations = [
        f"spexpr:{name}Shape a sh:NodeShape ; sh:targetClass spexpr:{name} ; sh:node spexpr:_{family}ExprBodyShape ."
        for name, family in _EXPR_NODE_FAMILY.items()
    ]
    return (
        "@prefix spexpr: <https://github.com/hidden-graph/starlayer/ns/sparql/expr#> .\n"
        "@prefix sh: <http://www.w3.org/ns/shacl#> .\n"
        + "\n".join(declarations)
        + "\n"
    )


def shapes_graph() -> Any:
    """A fresh ``StarLayerGraph`` of the ``spexpr:`` shapes: the stored ``spexpr_shacl`` plus the generated per-builtin
    shapes. Callers get their own copy, because a shapes graph may be modified while validating."""
    from starlayer.graph.oxgraph.core import StarLayerGraph

    graph = StarLayerGraph(prefixes={})
    graph.parse(data=expression_shapes_turtle(), format="turtle")
    _merge_into(graph, starontology.get_ontology_graph("spexpr_shacl"))
    return graph


def ontology_graph() -> Any:
    """A fresh ``StarLayerGraph`` of the ``spexpr:`` RDFS ontology (the subclass axioms behind ``sh:class spexpr:Expression``
    and the variable and path classes)."""
    return starontology.get_ontology_graph("spexpr_owl")


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


def rdfs_schema(ontology: Any) -> tuple[dict, dict, dict, dict]:
    """``(super-properties, super-classes, domains, ranges)`` of ``ontology`` (a ``StarLayerGraph``), the first two
    transitively closed (RDFS rules 5, 11 as maps; 2, 3, 7, 9 are applied by :func:`rdfs_entailed_copy`)."""
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
    return _closure(sub_prop), _closure(sub_class), domains, ranges


def rdfs_entailed_copy(data_graph: Any, schema: tuple[dict, dict, dict, dict]) -> Any:
    """A copy of ``data_graph`` closed under the RDFS rules the ``sqe:`` / ``srl:`` shapes rely on: sub-property (rdfs7),
    domain (rdfs2), range (rdfs3) and sub-class (rdfs9) inference from the ontology ``schema`` was made from. Done here,
    natively, because the general RDFS closure (``infer()``) runs on owlrl and so on rdflib."""
    sub_prop, sub_class, domains, ranges = schema
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
