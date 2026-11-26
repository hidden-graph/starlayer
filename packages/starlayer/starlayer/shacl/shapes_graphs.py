"""The ``sh:ShapesGraph`` modules of a graph and what belongs to each (GitHub issue #17).

SHACL 1.2 Profiling section 2 packages shapes into ``sh:ShapesGraph`` resources. A shape (or any other element) belongs to one
in any of three ways, and all three are honored:

- ``<graph> rdfs:member <element>``: the shapes graph lists it (Profiling 2.5, also how a graph *uses* an element it does not
  define);
- ``<element> rdfs:isDefinedBy <graph>``: the element says which graph defines it (2.4);
- ``<graph> owl:imports <other>`` where ``<other>`` is itself a ``sh:ShapesGraph`` in the same graph: the other module's members
  count too, transitively (2.6). Only modules already in the graph are followed; nothing is fetched.

``StarShaclProcessor.extract_shapes_graph()`` is built on these. Terms are pyoxigraph terms.
"""

from __future__ import annotations

from typing import Any

from starlayer.shacl.engine import shapes_graphs as _engine
from starlayer.shacl.engine.terms import RDF, SH, engine_view, text, to_engine

__all__ = [
    "shapes_graphs",
    "graph_nodes",
    "shapes_graph_members",
    "referenced_shapes",
    "rule_dependencies",
    "close_shape",
    "extract_shapes_graph",
]


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


def rule_dependencies(graph: Any, starting_points: Any) -> set[Any]:
    """What the rules of ``starting_points`` need to run, beyond ``referenced_shapes``: the shapes in a list given to a rule's
    ``sh:condition``, the prefix declarations their SPARQL uses (``sh:prefixes``, ``sh:declare`` and the ``owl:imports`` of those, transitively),
    and, for an instance of a rule template, the template and the classes it specialises. Those nodes' own references are followed too.

    Named nodes only, starting points not included; with ``referenced_shapes`` it is the set to copy to make shapes and their rules
    self-contained."""
    return _engine.rule_dependencies(engine_view(graph, "graph"), [to_engine(n) for n in starting_points])


def close_shape(shapes_graph: Any, shape: Any, *, shapes_graph_loader: Any | None = None, ignore_imports: bool | None = None) -> Any:
    """A copy of the whole ``shapes_graph`` in which ``shape`` and the shapes it reaches as a value node's complete description
    (``sh:node``, ``sh:qualifiedValueShape``, the members of ``sh:and`` / ``sh:or`` / ``sh:xone``) are ``sh:closed true``: the strict form
    an ``extract_subgraph`` fragment is checked against. Shapes that are not reached stay as they are; nothing is removed. The method of the
    same name of ``StarShaclProcessor`` does this on its bound shapes graph. The shapes graph's ``owl:imports`` are resolved first (its own
    ``imports_loader`` / ``ignore_imports``, overridden for the call by ``shapes_graph_loader`` / ``ignore_imports``), so the copy holds the
    imported shapes too; an import that is not resolved raises ``ExecutionError`` kind ``"import"``."""
    from starlayer.shacl import _adapter
    from starlayer.shacl.normalization import normalize_to_starlayer_graph

    return _adapter.close_shape(
        normalize_to_starlayer_graph(shapes_graph, name="shapes_graph"), shape, shapes_graph_loader=shapes_graph_loader, ignore_imports=ignore_imports
    )


def extract_shapes_graph(shapes_graph: Any, shapes_graph_iri: Any, *, include_referenced: bool = False) -> Any | None:
    """The ``sh:ShapesGraph`` named ``shapes_graph_iri`` as a standalone graph (its members, with their blank-node closures and the declared
    prefixes), or ``None`` when ``shapes_graph`` has no such resource. With ``include_referenced=True`` the extract also holds every shape the
    members reference, so it can be validated on its own. The method of the same name of ``StarShaclProcessor`` does this on its bound shapes
    graph."""
    from starlayer.shacl import _adapter
    from starlayer.shacl.normalization import normalize_to_starlayer_graph

    return _adapter.extract_shapes_graph(
        normalize_to_starlayer_graph(shapes_graph, name="shapes_graph"), shapes_graph_iri, include_referenced=include_referenced
    )
