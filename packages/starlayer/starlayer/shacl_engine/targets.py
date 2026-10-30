"""Shape discovery and targets.

OWNER (agent D). Skeleton: ``sh:targetNode`` only. Implement sh:targetClass, sh:targetSubjectsOf, sh:targetObjectsOf,
implicit class targets (a shape that is also an rdfs:Class), sh:targetWhere, and ``focus_nodes`` with rdfs:subClassOf
expansion for class targets, per SHACL 1.2 Core section on targets. ``declared_shape_nodes`` lists the shapes to
validate: every node typed sh:NodeShape/sh:PropertyShape/sh:Shape, or with any target property, or an implicit class
target; deactivated shapes are still returned (the executor skips them).
"""

from __future__ import annotations

from typing import Any

from rdflib import RDF, URIRef

from starlayer.shacl_engine.plan import SH, Term


def shape_targets(graph: Any, node: Term) -> list[tuple[URIRef, Term]]:
    return [(SH.targetNode, v) for v in graph.objects(node, SH.targetNode)]


def declared_shape_nodes(graph: Any) -> list[Term]:
    nodes: list[Term] = []
    seen = set()
    for typ in (SH.NodeShape, SH.PropertyShape):
        for s in graph.subjects(RDF.type, typ):
            if s not in seen:
                seen.add(s)
                nodes.append(s)
    for s in graph.subjects(SH.targetNode, None):
        if s not in seen:
            seen.add(s)
            nodes.append(s)
    return nodes


def focus_nodes(data: Any, shapes: Any, targets: tuple[tuple[URIRef, Term], ...]) -> list[Term]:
    out: list[Term] = []
    for pred, value in targets:
        if pred == SH.targetNode and value not in out:
            out.append(value)
    return out
