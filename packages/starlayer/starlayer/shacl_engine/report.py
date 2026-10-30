"""Result records -> ``sh:ValidationReport`` graph."""

from __future__ import annotations

from typing import Any

from rdflib import BNode, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from starlayer.shacl_engine.executor import Result
from starlayer.shacl_engine.plan import SH

_OPTION = Namespace("urn:starlayer:shacl-engine:option:")
_ORDER = {SH.Trace: 0, SH.Debug: 1, SH.Info: 2, SH.Warning: 3, SH.Violation: 4}


def conforms(results: list[Result], conformance_disallows: Any = None) -> bool:
    """No result blocks conformance. ``conformance_disallows`` (SHACL 1.2): the lowest severity that blocks; ``None``
    means Info and above block (Debug and Trace do not); an unknown severity blocks."""
    floor = _ORDER[SH.Info] if conformance_disallows is None else _ORDER.get(conformance_disallows, _ORDER[SH.Info])
    return not any(_ORDER.get(r.severity, _ORDER[SH.Violation]) >= floor for r in results)


def _copy_closure(src: Any, dst: Any, node: Any, seen: set) -> None:
    if not isinstance(node, BNode) or node in seen:
        return
    seen.add(node)
    for p, o in src.predicate_objects(node):
        dst.add((node, p, o))
        _copy_closure(src, dst, o, seen)


def _identity(value: Any) -> Any:
    """A graph identity as a term: IRIs and literals (a version IRI may be a literal) as they are, anything else as an IRI."""
    return value if isinstance(value, (URIRef, Literal)) else URIRef(str(value))


def annotate_provenance(
    report: Any,
    *,
    data_graph_iri: Any = None,
    shapes_graph_iri: Any = None,
    include_used_configuration: bool = False,
    configuration: dict[str, Any] | None = None,
    specification_graph: Any = None,
) -> None:
    """SHACL 1.2 Core 6.7.1.5-6.7.1.8 provenance on the report node: ``sh:usedDataGraph``, ``sh:usedShapesGraph`` and, on
    request, ``sh:usedConfiguration`` (a ``sh:ProcessorConfiguration``; the draft defines no properties for it, so the
    options of this run are recorded as ``sh:ProcessorConfiguration`` triples in the ``urn:starlayer:shacl-engine:option:``
    namespace). When both identities are known the Profiling S5.5 ``sh:conformsTo`` rule also runs on the report.
    """
    node = next(report.subjects(RDF.type, SH.ValidationReport), None)
    if node is None:
        return
    if data_graph_iri is not None:
        report.add((node, SH.usedDataGraph, _identity(data_graph_iri)))
    if shapes_graph_iri is not None:
        report.add((node, SH.usedShapesGraph, _identity(shapes_graph_iri)))
    if include_used_configuration:
        config = BNode()
        report.add((config, RDF.type, SH.ProcessorConfiguration))
        for name, value in sorted((configuration or {}).items()):
            if value is not None:
                report.add((config, _OPTION[name], value if isinstance(value, (Literal, URIRef)) else Literal(value)))
        report.add((node, SH.usedConfiguration, config))
    if data_graph_iri is not None and shapes_graph_iri is not None:
        # Profiling S5.5: lazy import, a pure function over the report graph (not the old validator)
        from starlayer.shacl.profiling import derive_conforms_to

        report += derive_conforms_to(report, specification_graph=specification_graph)


def build_report(results: list[Result], shapes: Any, data: Any, conformance_disallows: Any = None) -> Any:
    # a StarLayerGraph, not an rdflib Graph: only it can hold RDF 1.2 triple terms and directional literals
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph

    g = StarLayerGraph()
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
        for prop, value in r.annotations:
            g.add((node, prop, value))
            _copy_closure(shapes, g, value, seen)
        for m in r.messages:
            g.add((node, SH.resultMessage, m if not isinstance(m, str) else Literal(m)))
    return g
