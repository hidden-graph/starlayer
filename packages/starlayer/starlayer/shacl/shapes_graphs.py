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

__all__ = ["shapes_graphs", "graph_nodes", "shapes_graph_members"]

# sh:Graph and its three roles (a data graph and a rules graph package elements the same way a shapes graph does, GitHub issue #169)
_GRAPH_TYPES = (SH.Graph, SH.ShapesGraph, SH.DataGraph, SH.RulesGraph)


def shapes_graphs(graph: Any) -> list[Any]:
    """The nodes of ``graph`` typed ``sh:ShapesGraph``, sorted by their string form."""
    return sorted(set(graph.subjects(RDF.type, SH.ShapesGraph)), key=str)


def _graph_types(graph: Any) -> set[Any]:
    """``sh:Graph``, its roles, and every class ``graph`` declares a (transitive) ``rdfs:subClassOf`` of one of them."""
    types = set(_GRAPH_TYPES)
    pending = list(types)
    while pending:
        for sub in graph.subjects(RDFS.subClassOf, pending.pop()):
            if sub not in types:
                types.add(sub)
                pending.append(sub)
    return types


def _is_graph_node(graph: Any, node: Any) -> bool:
    types = _graph_types(graph)
    return any(t in types for t in graph.objects(node, RDF.type))


def graph_nodes(graph: Any) -> list[Any]:
    """Every node of ``graph`` typed ``sh:Graph``, one of its roles (``sh:ShapesGraph``, ``sh:DataGraph``, ``sh:RulesGraph``) or a
    class ``graph`` declares a subclass of those, sorted by their string form. ``shapes_graphs`` lists only the shapes graphs."""
    types = _graph_types(graph)
    return sorted({s for t in types for s in graph.subjects(RDF.type, t)}, key=str)


def module_nodes(graph: Any, shapes_graph: Any) -> set[Any]:
    """``shapes_graph`` and every ``sh:Graph`` it imports (see ``graph_nodes``), transitively, among the nodes already in ``graph``.

    Raises ``ValueError`` when an ``owl:imports`` target is not typed as a ``sh:Graph`` in ``graph``: a shapes graph that
    imports another is asserting a dependency, so a missing one is an error, not something to skip. Fetch it first with
    ``resolve_imports(loader=...)``."""
    nodes = {shapes_graph}
    pending = [shapes_graph]
    while pending:
        current = pending.pop()
        for imported in graph.objects(current, OWL.imports):
            if imported in nodes:
                continue
            if not _is_graph_node(graph, imported):
                raise ValueError(
                    f"{current!r} declares owl:imports {imported!r}, but {imported!r} is not typed `a sh:Graph` (or sh:ShapesGraph, "
                    "sh:DataGraph, sh:RulesGraph) in this "
                    "graph - either it has no triples describing it at all (call resolve_imports(loader=...) on the graph first "
                    "if it needs fetching from elsewhere), or it is present but is not itself a packaging module."
                )
            nodes.add(imported)
            pending.append(imported)
    return nodes


def shapes_graph_members(graph: Any, shapes_graph: Any) -> frozenset[Any] | None:
    """The elements that belong to ``shapes_graph`` by ``rdfs:member``, ``rdfs:isDefinedBy`` or ``owl:imports`` (see the module
    docstring): every kind of element, not only shapes (a property group or a constraint component says ``rdfs:isDefinedBy`` too).

    ``None`` when ``shapes_graph`` is not typed ``sh:Graph``, one of its roles or a declared subclass in ``graph``: not every graph
    declares this optional metadata, and a mistyped IRI should not look like an empty module. The graph nodes themselves are not
    members. Raises ``ValueError`` for an ``owl:imports`` target that is not such a graph in ``graph`` (see ``module_nodes``)."""
    if not _is_graph_node(graph, shapes_graph):
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
