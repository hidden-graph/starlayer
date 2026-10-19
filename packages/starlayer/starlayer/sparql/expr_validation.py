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

from rdflib import Graph

from starlayer import starontology

from .expr_families import _EXPR_NODE_FAMILY


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


def shapes_graph() -> Graph:
    """A fresh graph of the ``spexpr:`` shapes: the stored ``spexpr_shacl`` plus the generated per-builtin
    shapes. Callers get their own copy, because pyshacl mutates a shapes graph while validating."""
    graph = Graph()
    graph.parse(data=expression_shapes_turtle(), format="turtle")
    graph += starontology.get_ontology_graph("spexpr_shacl")
    return graph


def ontology_graph() -> Graph:
    """A fresh graph of the ``spexpr:`` RDFS ontology (the subclass axioms behind ``sh:class spexpr:Expression``
    and the variable and path classes)."""
    return starontology.get_ontology_graph("spexpr_owl")
