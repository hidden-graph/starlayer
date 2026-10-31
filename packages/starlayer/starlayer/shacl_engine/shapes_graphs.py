"""``extract_shapes_graph`` and ``close_shape`` on the native engine (no pyshacl, no old validator).

``extract_shapes_graph(shapes, iri, include_referenced=False)``: one ``sh:ShapesGraph`` module of a graph that bundles
several, as a standalone graph (SHACL 1.2 Profiling section 2: members by ``rdfs:member``, ``rdfs:isDefinedBy`` and the
members of locally present ``owl:imports`` modules). The result holds the concise bounded description of every involved
module node and every member; references to named shapes are left dangling unless ``include_referenced`` copies them
(the project's choice, see the old ``StarShaclSchema.extract_shapes_graph``; Profiling 2.7 "calculating dependencies" is a
TODO in the draft). Unlike ``modules.extract_module`` (used by ``validate(shapes_graph_resource=)``) it does not strip
``sh:property`` links to non-member named shapes, and an unresolvable ``owl:imports`` raises ``ValueError``.

``close_shape(shapes, shape)``: a *copy* of the shapes graph in which ``shape`` and every shape it reaches in a way that
describes a value node's complete property set (``sh:node``, ``sh:qualifiedValueShape``, members of ``sh:and`` /
``sh:or`` / ``sh:xone``) is ``sh:closed true`` with its ``sh:ignoredProperties`` removed, except that ``rdf:type``
(class targets, ``sh:class``) and the predicates of ``sh:targetSubjectsOf`` stay allowed, because ``extract_subgraph``
includes those triples. It turns a production shape into the strict form a fragment can be checked against. This is a
project extension; SHACL has no such operation.
"""

from __future__ import annotations

from typing import Any

from rdflib import OWL, RDF, RDFS, BNode, Literal, URIRef
from rdflib.collection import Collection

from starlayer.shacl_engine.plan import SH

_GRAPH_TYPES = (SH.Graph, SH.ShapesGraph, SH.DataGraph, SH.RulesGraph)
_SHAPE_REFERENCES = ("node", "property", "not", "qualifiedValueShape", "reifierShape", "someValue", "memberShape")
_SHAPE_LIST_REFERENCES = ("and", "or", "xone")


def _new_graph(source: Any) -> Any:
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph

    out = StarLayerGraph()
    if hasattr(source, "namespaces"):
        for prefix, ns in source.namespaces():
            out.bind(prefix, ns)
    return out


def _items(graph: Any, head: Any) -> list:
    out, seen = [], set()
    while head is not None and head != RDF.nil and head not in seen:
        seen.add(head)
        first = next(iter(graph.objects(head, RDF.first)), None)
        if first is None:
            break
        out.append(first)
        head = next(iter(graph.objects(head, RDF.rest)), None)
    return out


def _graph_types(graph: Any) -> set:
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


def module_nodes(graph: Any, shapes_graph: Any) -> set:
    """``shapes_graph`` and every ``sh:Graph`` it imports, transitively, among the nodes of ``graph``. ``ValueError`` when an
    ``owl:imports`` target is not a ``sh:Graph`` in ``graph``."""
    nodes = {shapes_graph}
    pending = [shapes_graph]
    while pending:
        current = pending.pop()
        for imported in graph.objects(current, OWL.imports):
            if imported in nodes:
                continue
            if not _is_graph_node(graph, imported):
                raise ValueError(
                    f"{current!r} declares owl:imports {imported!r}, but {imported!r} is not typed `a sh:Graph` (or "
                    "sh:ShapesGraph, sh:DataGraph, sh:RulesGraph) in this graph: it has no triples describing it, or is not a "
                    "packaging module (resolve the import first)."
                )
            nodes.add(imported)
            pending.append(imported)
    return nodes


def shapes_graph_members(graph: Any, shapes_graph: Any) -> frozenset | None:
    """Elements of ``shapes_graph`` by ``rdfs:member``, ``rdfs:isDefinedBy`` or ``owl:imports``; ``None`` if it is not a
    ``sh:Graph`` (or role) in ``graph``."""
    if not _is_graph_node(graph, shapes_graph):
        return None
    members: set = set()
    for node in module_nodes(graph, shapes_graph):
        members.update(graph.objects(node, RDFS.member))
        members.update(graph.subjects(RDFS.isDefinedBy, node))
    return frozenset(members)


def referenced_shapes(graph: Any, starting_points: Any) -> set:
    """Named shapes the starting points refer to, directly or through further shapes (``sh:node``, ``sh:property``,
    ``sh:not``, ``sh:qualifiedValueShape``, ``sh:reifierShape``, ``sh:someValue``, ``sh:memberShape``, the lists of
    ``sh:and`` / ``sh:or`` / ``sh:xone``). Blank nodes are walked but not returned; starting points are not part of the
    result; cycles are fine."""
    seen: set = set(starting_points)
    result: set = set()
    stack = list(starting_points)
    while stack:
        shape = stack.pop()
        targets = [o for name in _SHAPE_REFERENCES for o in graph.objects(shape, SH[name])]
        for name in _SHAPE_LIST_REFERENCES:
            for head in graph.objects(shape, SH[name]):
                targets.extend(_items(graph, head))
        for target in targets:
            if target in seen:
                continue
            seen.add(target)
            if not isinstance(target, BNode):
                result.add(target)
            stack.append(target)
    return result


def _copy_cbd(src: Any, dst: Any, node: Any, seen: set) -> None:
    """The concise bounded description of ``node``: its triples, recursing into blank-node objects."""
    if node in seen:
        return
    seen.add(node)
    for p, o in src.predicate_objects(node):
        dst.add((node, p, o))
        if isinstance(o, BNode):
            _copy_cbd(src, dst, o, seen)


def extract_shapes_graph(shapes_graph: Any, shapes_graph_iri: Any, *, include_referenced: bool = False) -> Any | None:
    """The ``sh:ShapesGraph`` module ``shapes_graph_iri`` of ``shapes_graph`` as a new standalone graph; ``None`` when the
    IRI is not typed ``sh:ShapesGraph`` there. ``include_referenced=True`` also copies the named shapes the members refer
    to, transitively, so the result validates on its own. ``ValueError`` for an unresolvable ``owl:imports`` or when
    ``shapes_graph`` is ``None``. The input is never changed."""
    if shapes_graph is None:
        raise ValueError("extract_shapes_graph() needs a shapes graph")
    members = shapes_graph_members(shapes_graph, shapes_graph_iri)
    if members is None:
        return None
    result = _new_graph(shapes_graph)
    seen: set = set()
    for node in module_nodes(shapes_graph, shapes_graph_iri):
        _copy_cbd(shapes_graph, result, node, seen)
    for member in members:
        _copy_cbd(shapes_graph, result, member, seen)
    if include_referenced:
        for shape in referenced_shapes(shapes_graph, members) - set(members):
            _copy_cbd(shapes_graph, result, shape, seen)
    return result


def _remove_rdf_list(graph: Any, list_node: Any) -> None:
    while list_node is not None and list_node != RDF.nil:
        next_node = next(iter(graph.objects(list_node, RDF.rest)), None)
        for p, o in list(graph.predicate_objects(list_node)):
            graph.remove((list_node, p, o))
        list_node = next_node


def _path_iris(graph: Any, path: Any, seen: set | None = None) -> set:
    """Every IRI a property path mentions (an over-approximation: forward and inverse alike)."""
    seen = set() if seen is None else seen
    if path in seen:
        return set()
    seen.add(path)
    if isinstance(path, URIRef):
        return {path}
    found: set = set()
    for pred in (SH.inversePath, SH.zeroOrMorePath, SH.oneOrMorePath, SH.zeroOrOnePath):
        for inner in graph.objects(path, pred):
            found |= _path_iris(graph, inner, seen)
    for head in graph.objects(path, SH.alternativePath):
        for member in _items(graph, head):
            found |= _path_iris(graph, member, seen)
    if (path, RDF.first, None) in graph:
        for member in _items(graph, path):
            found |= _path_iris(graph, member, seen)
    return found


def _property_shape_predicates(graph: Any, prop: Any) -> set:
    found: set = set()
    for path in graph.objects(prop, SH.path):
        found |= _path_iris(graph, path)
    for pred in (SH.equals, SH.disjoint, SH.lessThan, SH.lessThanOrEquals):
        found |= {o for o in graph.objects(prop, pred) if isinstance(o, URIRef)}
    return found


def close_shape(shapes_graph: Any, shape: Any) -> Any:
    """A copy of ``shapes_graph`` in which ``shape`` and the shapes it reaches through ``sh:node``,
    ``sh:qualifiedValueShape`` and the members of ``sh:and`` / ``sh:or`` / ``sh:xone`` are ``sh:closed true`` with no
    ``sh:ignoredProperties`` of their own, except what ``extract_subgraph`` adds: ``rdf:type`` where a class target,
    ``sh:class`` or class-typed shape is involved, and the predicates of ``sh:targetSubjectsOf``. Shapes reached only
    through ``sh:property`` are walked but not closed (they do not describe their value nodes' complete property set).
    Within an ``sh:and`` / ``sh:or`` / ``sh:xone`` group the members' property paths are let through the siblings. The
    input is never changed. ``ValueError`` when ``shapes_graph`` is ``None``."""
    if shapes_graph is None:
        raise ValueError("close_shape() needs a bound shapes graph")
    result = _new_graph(shapes_graph)
    for t in shapes_graph.triples((None, None, None)):
        result.add(t)

    to_close: set = set()
    visited: set = set()
    # a shape closed together with its and/or/xone members describes ONE node's property set: each such group shares the
    # predicates its closed forms must let through
    group_of: dict = {}

    def walk(node: Any, should_close: bool, group: set, is_property_shape: bool = False) -> None:
        if node in visited:
            return
        visited.add(node)
        if should_close:
            to_close.add(node)
            group_of[node] = group
        for nested in result.objects(node, SH.node):
            walk(nested, True, set())
        for prop in result.objects(node, SH.property):
            if not is_property_shape:
                group |= _property_shape_predicates(result, prop)
            walk(prop, False, set(), True)
        for q in result.objects(node, SH.qualifiedValueShape):
            walk(q, True, set())
        member_group = set() if is_property_shape else group
        for pred in (SH["and"], SH["or"], SH.xone):
            for head in result.objects(node, pred):
                for member in _items(result, head):
                    walk(member, True, member_group)

    walk(shape, True, set())

    for node in visited:
        for head in list(result.objects(node, SH.ignoredProperties)):
            result.remove((node, SH.ignoredProperties, head))
            _remove_rdf_list(result, head)

    allowed: set = set()
    for node in visited:
        if (
            list(result.objects(node, SH.targetClass))
            or list(result.objects(node, SH["class"]))
            or any(t in (RDFS.Class, SH.ShapeClass) for t in result.objects(node, RDF.type))
        ):
            allowed.add(RDF.type)
        allowed |= set(result.objects(node, SH.targetSubjectsOf))

    for node in to_close:
        result.remove((node, SH.closed, None))
        result.add((node, SH.closed, Literal(True)))
        own = {
            path
            for prop in result.objects(node, SH.property)
            for path in result.objects(prop, SH.path)
            if isinstance(path, URIRef)
        }
        node_allowed = allowed | (group_of[node] - own)
        if node_allowed:
            ignored = BNode()
            Collection(result, ignored, sorted(node_allowed, key=str))
            result.add((node, SH.ignoredProperties, ignored))
    return result


__all__ = ["close_shape", "extract_shapes_graph", "module_nodes", "referenced_shapes", "shapes_graph_members"]
