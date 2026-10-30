"""Result records -> ``sh:ValidationReport`` graph."""

from __future__ import annotations

from typing import Any

from rdflib import BNode, Graph, Literal
from rdflib.namespace import RDF, XSD

from starlayer.shacl_engine.executor import Result
from starlayer.shacl_engine.plan import SH

_ORDER = {SH.Trace: 0, SH.Debug: 1, SH.Info: 2, SH.Warning: 3, SH.Violation: 4}


def conforms(results: list[Result], conformance_disallows: Any = None) -> bool:
    """No result blocks conformance. ``conformance_disallows`` (SHACL 1.2): the lowest severity that blocks; ``None``
    means Info and above block (Debug and Trace do not); an unknown severity blocks."""
    floor = _ORDER[SH.Info] if conformance_disallows is None else _ORDER.get(conformance_disallows, _ORDER[SH.Info])
    return not any(_ORDER.get(r.severity, _ORDER[SH.Violation]) >= floor for r in results)


def _copy_closure(src: Any, dst: Graph, node: Any, seen: set) -> None:
    if not isinstance(node, BNode) or node in seen:
        return
    seen.add(node)
    for p, o in src.predicate_objects(node):
        dst.add((node, p, o))
        _copy_closure(src, dst, o, seen)


def build_report(results: list[Result], shapes: Any, data: Any, conformance_disallows: Any = None) -> Graph:
    g = Graph()
    g.bind("sh", SH)
    report = BNode()
    g.add((report, RDF.type, SH.ValidationReport))
    g.add((report, SH.conforms, Literal(conforms(results, conformance_disallows), datatype=XSD.boolean)))
    if conformance_disallows is not None:
        g.add((report, SH.conformanceDisallows, conformance_disallows))
    seen: set = set()
    for r in results:
        node = BNode()
        g.add((report, SH.result, node))
        g.add((node, RDF.type, SH.ValidationResult))
        g.add((node, SH.focusNode, r.focus))
        _copy_closure(data, g, r.focus, seen)
        if r.path is not None and r.path.node is not None:
            g.add((node, SH.resultPath, r.path.node))
            _copy_closure(shapes, g, r.path.node, seen)
        if r.has_value:
            g.add((node, SH.value, r.value))
            _copy_closure(data, g, r.value, seen)
        g.add((node, SH.sourceConstraintComponent, r.component))
        g.add((node, SH.sourceShape, r.shape))
        if r.source_constraint is not None:
            g.add((node, SH.sourceConstraint, r.source_constraint))
            _copy_closure(shapes, g, r.source_constraint, seen)
        g.add((node, SH.resultSeverity, r.severity))
        for m in r.messages:
            g.add((node, SH.resultMessage, m if not isinstance(m, str) else Literal(m)))
    return g
