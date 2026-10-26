"""scripts/build_meta_shapes.py - builds the SHACL 1.2 meta-shapes graph that
``starlayer.shacl.meta_validate()`` checks shapes graphs against.

Build-time only: the library never imports this. It reads the stored result,
``starontology/shacl12-shacl.ttl``, which ``scripts/build_starontology.py``
regenerates from ``build_meta_shapes_graph()`` below.

The graph is the W3C Data Shapes Working Group's own SHACL-for-SHACL
(``assets/vendor/w3c-shacl-shacl.ttl``, a pinned verbatim copy, see
``assets/vendor/VENDORED_FROM.md``) **plus additions only - nothing in the
Working Group's file is deleted or edited**, so a newer upstream copy can be
dropped in and compared. The additions are:

1. ``assets/shacl12-validation-shapes.ttl``: rules for the SHACL 1.2 predicates
   the Working Group's file has no rule for yet (``sh:someValue``,
   ``sh:uniqueValuesFor``, ``sh:subsetOf``, ``sh:rootClass``, ``sh:reifierShape``,
   ``sh:reificationRequired``, SPARQL, rules, ...), our ``stsh:`` shapes, and
   documentation of the terms.
2. ``sh:deactivated true`` on the Working Group rules that are still stricter
   than SHACL 1.2 allows (``RELAXED_PATHS``). SHACL constraints combine by AND,
   so a looser rule added beside a strict one would change nothing; the
   Working Group's own file says to customise it this way ("this graph should
   be supplemented with 'shsh:xoneSubjectsShape sh:deactivated true'"). The
   replacement rules are in (1).
3. Expression-based property shapes (``sh:expression`` instead of ``sh:path``):
   the Working Group's ``shsh:PropertyShapeShape`` requires ``sh:path``, so that
   rule is deactivated (its replacement, "path or expression", is in (1)), and
   ``shsh:NodeShapeShape`` is told a node shape carries no ``sh:expression``,
   which keeps the Working Group's ``sh:xone`` between node shapes and property
   shapes exclusive.
4. The ``rdf:type`` the shape-valued predicates of the native components need
   (``sh:memberShape``), which starlayer otherwise adds at validation time.

``tests/shacl/integration/test_wg_overrides.py`` checks that each deactivation
is still needed, so when upstream fixes one the test fails and prompts a review.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from typing import Any

from rdflib import BNode, Graph, Literal, Namespace, URIRef

SH = Namespace("http://www.w3.org/ns/shacl#")
SHSH = Namespace("http://www.w3.org/ns/shacl-shacl#")

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
VALIDATION_SHAPES_PATH = os.path.join(_ASSETS_DIR, "shacl12-validation-shapes.ttl")
WG_SHAPES_PATH = os.path.join(_ASSETS_DIR, "vendor", "w3c-shacl-shacl.ttl")
WG_VENDORED_FROM_PATH = os.path.join(_ASSETS_DIR, "vendor", "VENDORED_FROM.md")

# The predicates whose Working Group rule on shsh:ShapeShape is still stricter than SHACL 1.2 allows (list-valued
# sh:nodeKind, path-valued sh:equals/sh:disjoint/sh:lessThan/sh:lessThanOrEquals). As of the pinned copy the Working
# Group has already fixed sh:class, sh:datatype and sh:closed; test_wg_overrides.py fails when one of these is fixed too.
RELAXED_PATHS: tuple[URIRef, ...] = (
    SH.nodeKind,
    SH.disjoint,
    SH.equals,
    SH.lessThan,
    SH.lessThanOrEquals,
    SH.targetNode,  # sh:nodeKind sh:IRIOrLiteral rejects a node expression (GitHub issue #66)
)


def wg_file_sha256() -> str:
    """The SHA-256 of the pinned Working Group file (compared with ``VENDORED_FROM.md`` by a test)."""
    with open(WG_SHAPES_PATH, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def load_wg_shapes() -> Graph:
    """A fresh copy of the pinned Working Group file, unchanged."""
    graph = Graph()
    graph.parse(WG_SHAPES_PATH, format="turtle")
    return graph


def _property_shapes_of(graph: Graph, shape: URIRef, path: URIRef) -> list[Any]:
    """The blank-node property shapes of ``shape`` whose ``sh:path`` is ``path``, found by structure - the blank
    node labels differ on every parse, so they cannot be hard-coded."""
    return [bn for bn in graph.objects(shape, SH.property) if (bn, SH.path, path) in graph]


def _add_overrides(graph: Graph) -> Graph:
    """Add (never remove) the deactivations and the node-shape rule described in the module docstring."""
    for path in RELAXED_PATHS:
        for property_shape in _property_shapes_of(graph, SHSH.ShapeShape, path):
            graph.add((property_shape, SH.deactivated, Literal(True)))
    for property_shape in _property_shapes_of(graph, SHSH.PropertyShapeShape, SH.path):
        graph.add((property_shape, SH.deactivated, Literal(True)))
    no_expression = BNode()
    graph.add((SHSH.NodeShapeShape, SH.property, no_expression))
    graph.add((no_expression, SH.path, SH.expression))
    graph.add((no_expression, SH.maxCount, Literal(0)))
    return graph


def _type_shape_values(graph: Graph) -> Graph:
    """Add the ``rdf:type`` triples starlayer adds before handing a shapes graph to pySHACL (the Working Group's
    file uses ``sh:memberShape``, which pySHACL does not know). Only adds."""
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph
    from starlayer.shacl.validator import _ensure_native_component_shapes_typed

    working = StarLayerGraph()
    for triple in graph:
        working.add(triple)
    typed = _ensure_native_component_shapes_typed(working)
    result = Graph()
    for prefix, namespace in graph.namespaces():
        result.bind(prefix, namespace)
    for triple in typed:
        result.add(triple)
    return result


def build_meta_shapes_graph(extra_graphs: Iterable[Any] = (), *, wg_graph: Graph | None = None) -> Graph:
    """Assemble the complete meta-shapes graph: the Working Group's file, ``shacl12-validation-shapes.ttl``, the
    overrides above, and every graph in ``extra_graphs`` (plain triple addition, so a caller such as a SHACL editor
    can add its own rules without this function knowing what they are for). ``wg_graph`` is for tests: a
    Working Group graph already loaded, copied with its blank nodes unchanged so the result can be compared with it."""
    if wg_graph is None:
        graph = load_wg_shapes()
    else:
        graph = Graph()
        for triple in wg_graph:
            graph.add(triple)
    graph.parse(VALIDATION_SHAPES_PATH, format="turtle")
    _add_overrides(graph)
    graph = _type_shape_values(graph)
    for extra in extra_graphs:
        for triple in extra:
            graph.add(triple)
    return graph
