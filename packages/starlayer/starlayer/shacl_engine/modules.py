"""``sh:ShapesGraph`` modules (SHACL 1.2 Profiling section 2) for ``api.validate(shapes_graph_resource=...)``.

A shape belongs to a module via ``<module> rdfs:member <shape>``, ``<shape> rdfs:isDefinedBy <module>``, or the members of a
module it ``owl:imports`` when that module is in the same graph (transitively). The result is a new graph holding the
module nodes' and member shapes' concise bounded descriptions, without ``sh:property`` links to named property shapes
that are not members (their constraints are not part of the module).
"""

from __future__ import annotations

from typing import Any

from rdflib import OWL, RDF, RDFS, BNode, Literal, URIRef

from starlayer.shacl_engine.plan import SH, ShapeError

_GRAPH_TYPES = (SH.Graph, SH.ShapesGraph, SH.DataGraph, SH.RulesGraph)


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


def _module_nodes(graph: Any, module: Any) -> set:
    nodes = {module}
    pending = [module]
    while pending:
        current = pending.pop()
        for imported in graph.objects(current, OWL.imports):
            if imported in nodes:
                continue
            if not _is_graph_node(graph, imported):
                raise ShapeError(f"{current!r} declares owl:imports {imported!r}, which is not a sh:Graph in this graph")
            nodes.add(imported)
            pending.append(imported)
    return nodes


def module_members(graph: Any, module: Any) -> frozenset | None:
    """Members of ``module``; ``None`` when ``module`` is not typed ``sh:Graph`` (or a role) in ``graph``."""
    if not _is_graph_node(graph, module):
        return None
    members: set = set()
    for node in _module_nodes(graph, module):
        members.update(graph.objects(node, RDFS.member))
        members.update(graph.subjects(RDFS.isDefinedBy, node))
    return frozenset(members)


def _copy_cbd(src: Any, dst: Any, node: Any, seen: set) -> None:
    if node in seen:
        return
    seen.add(node)
    for p, o in src.predicate_objects(node):
        dst.add((node, p, o))
        if isinstance(o, BNode):
            _copy_cbd(src, dst, o, seen)


def extract_module(shapes: Any, module: Any) -> Any | None:
    """The module as a standalone graph, or ``None`` when ``module`` is not a ``sh:ShapesGraph``-like node of ``shapes``."""
    members = module_members(shapes, module)
    if members is None:
        return None
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph

    out = StarLayerGraph()
    for prefix, ns in shapes.namespaces():
        out.bind(prefix, ns)
    seen: set = set()
    for node in (*_module_nodes(shapes, module), *members):
        _copy_cbd(shapes, out, node, seen)
    for s, o in list(out.subject_objects(SH.property)):
        if not isinstance(o, BNode) and (o, SH.path, None) not in out:
            out.remove((s, SH.property, o))
    return out


def resolve_shapes_resource(shapes: Any, resource: Any) -> tuple[Any, Any]:
    """``(graph to validate against, identity for sh:usedShapesGraph)``. A real module is extracted and its IRI is the
    identity; any other IRI is only a provenance tag and the whole graph is used. Same two meanings as the old validator."""
    if shapes is None:
        raise ValueError("shapes_graph_resource= needs a shapes graph to check against")
    iri = resource if isinstance(resource, (URIRef, Literal)) or not isinstance(resource, str) else URIRef(resource)
    extracted = extract_module(shapes, iri)
    return (extracted, iri) if extracted is not None else (shapes, iri)
