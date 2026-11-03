"""The ``sh:ShapesGraph`` modules of a graph and what belongs to each (GitHub issue #17).

SHACL 1.2 Profiling section 2 packages shapes into ``sh:ShapesGraph`` resources. A shape (or any other element) belongs to one
in any of three ways, and all three are honored:

- ``<graph> rdfs:member <element>``: the shapes graph lists it (Profiling 2.5, also how a graph *uses* an element it does not
  define);
- ``<element> rdfs:isDefinedBy <graph>``: the element says which graph defines it (2.4);
- ``<graph> owl:imports <other>`` where ``<other>`` is itself a ``sh:ShapesGraph`` in the same graph: the other module's members
  count too, transitively (2.6). Only modules already in the graph are followed; nothing is fetched.

``StarShaclSchema.extract_shapes_graph()`` is built on these. Terms are pyoxigraph terms (an rdflib term is accepted).
"""

from __future__ import annotations

from typing import Any

from starlayer.shacl_engine import shapes_graphs as _engine
from starlayer.shacl_engine.terms import RDF, SH, engine_view, text, to_engine

__all__ = ["shapes_graphs", "graph_nodes", "shapes_graph_members"]


def shapes_graphs(graph: Any) -> list[Any]:
    """The nodes of ``graph`` typed ``sh:ShapesGraph``, sorted by their text."""
    graph = engine_view(graph, "graph")
    return sorted(set(graph.subjects(RDF.type, SH.ShapesGraph)), key=text)


def graph_nodes(graph: Any) -> list[Any]:
    """Every node of ``graph`` typed ``sh:Graph``, one of its roles (``sh:ShapesGraph``, ``sh:DataGraph``, ``sh:RulesGraph``) or a
    class ``graph`` declares a subclass of those, sorted by their text. ``shapes_graphs`` lists only the shapes graphs."""
    graph = engine_view(graph, "graph")
    types = _engine._graph_types(graph)
    return sorted({s for t in types for s in graph.subjects(RDF.type, t)}, key=text)


def module_nodes(graph: Any, shapes_graph: Any) -> set[Any]:
    """``shapes_graph`` and every ``sh:Graph`` it imports (see ``graph_nodes``), transitively, among the nodes already in ``graph``.

    Raises ``ValueError`` when an ``owl:imports`` target is not typed as a ``sh:Graph`` in ``graph``: a shapes graph that
    imports another is asserting a dependency, so a missing one is an error, not something to skip. Fetch it first with
    ``resolve_imports(loader=...)``."""
    return _engine.module_nodes(engine_view(graph, "graph"), to_engine(shapes_graph))


def shapes_graph_members(graph: Any, shapes_graph: Any) -> frozenset[Any] | None:
    """The elements that belong to ``shapes_graph`` by ``rdfs:member``, ``rdfs:isDefinedBy`` or ``owl:imports`` (see the module
    docstring): every kind of element, not only shapes (a property group or a constraint component says ``rdfs:isDefinedBy`` too).

    ``None`` when ``shapes_graph`` is not typed ``sh:Graph``, one of its roles or a declared subclass in ``graph``: not every graph
    declares this optional metadata, and a mistyped IRI should not look like an empty module. The graph nodes themselves are not
    members. Raises ``ValueError`` for an ``owl:imports`` target that is not such a graph in ``graph`` (see ``module_nodes``)."""
    return _engine.shapes_graph_members(engine_view(graph, "graph"), to_engine(shapes_graph))


def referenced_shapes(graph: Any, starting_points: Any) -> set[Any]:
    """The named shapes that ``starting_points`` refer to, directly or through further shapes: what a self-contained
    extract must also hold (GitHub issue #19).

    Follows ``sh:node``, ``sh:property``, ``sh:not``, ``sh:qualifiedValueShape``, ``sh:reifierShape``, ``sh:someValue``,
    ``sh:memberShape`` and the shapes in the lists of ``sh:and``, ``sh:or`` and ``sh:xone``. Blank nodes are walked through
    but not returned (they come with a shape's concise bounded description); a starting point is not part of the result.
    Cycles are fine.
    """
    return _engine.referenced_shapes(engine_view(graph, "graph"), [to_engine(n) for n in starting_points])
