"""The ``sh:ShapesGraph`` modules of a graph and what belongs to each (GitHub issue #17).

SHACL 1.2 Profiling section 2 packages shapes into ``sh:ShapesGraph`` resources. A shape (or any other element) belongs to one
in any of three ways, and all three are honored:

- ``<graph> rdfs:member <element>``: the shapes graph lists it (Profiling 2.5, also how a graph *uses* an element it does not
  define);
- ``<element> rdfs:isDefinedBy <graph>``: the element says which graph defines it (2.4);
- ``<graph> owl:imports <other>`` where ``<other>`` is itself a ``sh:ShapesGraph`` in the same graph: the other module's members
  count too, transitively (2.6). Only modules already in the graph are followed; nothing is fetched.

``StarShaclSchema.extract_shapes_graph()`` is built on these.
"""

from __future__ import annotations

from typing import Any

from rdflib import OWL, RDF, RDFS, Namespace

# not rdflib.namespace.SH: that one has no SHACL 1.2 terms such as ShapesGraph
SH = Namespace("http://www.w3.org/ns/shacl#")

__all__ = ["shapes_graphs", "shapes_graph_members"]


def shapes_graphs(graph: Any) -> list[Any]:
    """The nodes of ``graph`` typed ``sh:ShapesGraph``, sorted by their string form."""
    return sorted(set(graph.subjects(RDF.type, SH.ShapesGraph)), key=str)


def module_nodes(graph: Any, shapes_graph: Any) -> set[Any]:
    """``shapes_graph`` and every ``sh:ShapesGraph`` it imports, transitively, among the nodes already in ``graph``.

    Raises ``ValueError`` when an ``owl:imports`` target is not typed ``sh:ShapesGraph`` in ``graph``: a shapes graph that
    imports another is asserting a dependency, so a missing one is an error, not something to skip. Fetch it first with
    ``resolve_imports(loader=...)``."""
    nodes = {shapes_graph}
    pending = [shapes_graph]
    while pending:
        current = pending.pop()
        for imported in graph.objects(current, OWL.imports):
            if imported in nodes:
                continue
            if (imported, RDF.type, SH.ShapesGraph) not in graph:
                raise ValueError(
                    f"{current!r} declares owl:imports {imported!r}, but {imported!r} is not typed `a sh:ShapesGraph` in this "
                    "graph - either it has no triples describing it at all (call resolve_imports(loader=...) on the graph first "
                    "if it needs fetching from elsewhere), or it is present but is not itself a packaging module."
                )
            nodes.add(imported)
            pending.append(imported)
    return nodes


def shapes_graph_members(graph: Any, shapes_graph: Any) -> frozenset[Any] | None:
    """The elements that belong to ``shapes_graph`` by ``rdfs:member``, ``rdfs:isDefinedBy`` or ``owl:imports`` (see the module
    docstring): every kind of element, not only shapes (a property group or a constraint component says ``rdfs:isDefinedBy`` too).

    ``None`` when ``shapes_graph`` is not typed ``sh:ShapesGraph`` in ``graph``: not every graph declares this optional
    metadata, and a mistyped IRI should not look like an empty module. The shapes graph nodes themselves are not members.
    Raises ``ValueError`` for an ``owl:imports`` target that is not a ``sh:ShapesGraph`` in ``graph`` (see ``module_nodes``)."""
    if (shapes_graph, RDF.type, SH.ShapesGraph) not in graph:
        return None
    members: set[Any] = set()
    for node in module_nodes(graph, shapes_graph):
        members.update(graph.objects(node, RDFS.member))
        members.update(graph.subjects(RDFS.isDefinedBy, node))
    return frozenset(members)


# What a shape points at when it names another shape: a single shape, or a list of shapes
_SHAPE_REFERENCES = ("node", "property", "not", "qualifiedValueShape", "reifierShape", "someValue", "memberShape")
_SHAPE_LIST_REFERENCES = ("and", "or", "xone")


def referenced_shapes(graph: Any, starting_points: Any) -> set[Any]:
    """The named shapes that ``starting_points`` refer to, directly or through further shapes: what a self-contained
    extract must also hold (GitHub issue #19).

    Follows ``sh:node``, ``sh:property``, ``sh:not``, ``sh:qualifiedValueShape``, ``sh:reifierShape``, ``sh:someValue``,
    ``sh:memberShape`` and the shapes in the lists of ``sh:and``, ``sh:or`` and ``sh:xone``. Blank nodes are walked through
    but not returned (they come with a shape's concise bounded description); a starting point is not part of the result.
    Cycles are fine.
    """
    from rdflib import BNode
    from rdflib.namespace import Namespace

    sh = Namespace("http://www.w3.org/ns/shacl#")
    seen: set[Any] = set(starting_points)
    result: set[Any] = set()
    stack = list(starting_points)
    while stack:
        shape = stack.pop()
        targets = [o for name in _SHAPE_REFERENCES for o in graph.objects(shape, sh[name])]
        for name in _SHAPE_LIST_REFERENCES:
            for head in graph.objects(shape, sh[name]):
                targets.extend(graph.items(head))
        for target in targets:
            if target in seen:
                continue
            seen.add(target)
            if not isinstance(target, BNode):
                result.add(target)
            stack.append(target)
    return result
