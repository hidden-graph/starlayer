"""Result records -> ``sh:ValidationReport`` graph."""

from __future__ import annotations

from typing import Any

import pyoxigraph as ox
from rdflib import BNode, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from starlayer.shacl_engine import terms as T
from starlayer.shacl_engine.executor import Result
from starlayer.shacl_engine.plan import SH

# ``annotate_provenance`` works on the finished report graph, which is a StarLayerGraph in rdflib terms (the boundary):
RSH = Namespace("http://www.w3.org/ns/shacl#")

_OPTION = Namespace("urn:starlayer:shacl-engine:option:")
_ORDER: dict = {SH.Trace: 0, SH.Debug: 1, SH.Info: 2, SH.Warning: 3, SH.Violation: 4}


def conforms(results: list[Result], conformance_disallows: Any = None) -> bool:
    """No result blocks conformance. ``conformance_disallows`` (SHACL 1.2): the lowest severity that blocks; ``None``
    means Info and above block (Debug and Trace do not); an unknown severity blocks."""
    floor = _ORDER[SH.Info] if conformance_disallows is None else _ORDER.get(conformance_disallows, _ORDER[SH.Info])
    return not any(_ORDER.get(r.severity, _ORDER[SH.Violation]) >= floor for r in results)


def _copy_closure(src: Any, dst: Any, node: Any, seen: set) -> None:
    """Copy the blank-node closure of ``node`` from the engine-term view ``src`` into the rdflib-term graph ``dst``."""
    if not isinstance(node, ox.BlankNode) or node in seen:
        return
    seen.add(node)
    for p, o in src.predicate_objects(node):
        dst.add((T.from_engine(node), T.from_engine(p), T.from_engine(o)))
        _copy_closure(src, dst, o, seen)


def _identity(value: Any) -> Any:
    """A graph identity as a term: IRIs and literals (a version IRI may be a literal) as they are, anything else as an IRI."""
    value = T.from_engine(value)
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
    node = next(report.subjects(RDF.type, RSH.ValidationReport), None)
    if node is None:
        return
    if data_graph_iri is not None:
        report.add((node, RSH.usedDataGraph, _identity(data_graph_iri)))
    if shapes_graph_iri is not None:
        report.add((node, RSH.usedShapesGraph, _identity(shapes_graph_iri)))
    if include_used_configuration:
        config = BNode()
        report.add((config, RDF.type, RSH.ProcessorConfiguration))
        for name, value in sorted((configuration or {}).items()):
            if value is not None:
                report.add((config, _OPTION[name], value if isinstance(value, (Literal, URIRef)) else Literal(value)))
        report.add((node, RSH.usedConfiguration, config))
    if data_graph_iri is not None and shapes_graph_iri is not None:
        # Profiling S5.5: lazy import, a pure function over the report graph (not the old validator)
        from starlayer.shacl.profiling import derive_conforms_to

        report += derive_conforms_to(report, specification_graph=specification_graph)


def build_report(results: list[Result], shapes: Any, data: Any, conformance_disallows: Any = None) -> Any:
    # a StarLayerGraph, not an rdflib Graph: only it can hold RDF 1.2 triple terms and directional literals
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph

    g = StarLayerGraph()
    g.bind("sh", RSH)
    # The old validator binds the data and shapes graphs' prefixes on the report so IRIs print as prefixed names.
    for source in (shapes, data):
        namespaces = getattr(source, "namespaces", None)
        if namespaces is not None:
            try:
                for prefix, namespace in namespaces():
                    if prefix and not any(p == prefix for p, _ in g.namespaces()):
                        g.bind(prefix, namespace, override=False)
            except Exception:  # noqa: BLE001  (a view without namespace support just keeps the default prefixes)
                pass
    report = BNode()
    g.add((report, RDF.type, RSH.ValidationReport))
    g.add((report, RSH.conforms, Literal(conforms(results, conformance_disallows), datatype=XSD.boolean)))
    if conformance_disallows is not None:
        g.add((report, RSH.conformanceDisallows, T.from_engine(conformance_disallows)))
    seen: set = set()
    fe = T.from_engine

    def add_result(r: Result) -> BNode:
        node = BNode()
        g.add((node, RDF.type, RSH.ValidationResult))
        g.add((node, RSH.focusNode, fe(r.focus)))
        _copy_closure(data, g, r.focus, seen)
        if r.path is not None and r.path.node is not None:
            g.add((node, RSH.resultPath, fe(r.path.node)))
            _copy_closure(shapes, g, r.path.node, seen)
        if r.has_value:
            g.add((node, RSH.value, fe(r.value)))
            _copy_closure(data, g, r.value, seen)
        g.add((node, RSH.sourceConstraintComponent, fe(r.component)))
        g.add((node, RSH.sourceShape, fe(r.shape)))
        if r.source_constraint is not None:
            g.add((node, RSH.sourceConstraint, fe(r.source_constraint)))
            _copy_closure(shapes, g, r.source_constraint, seen)
        g.add((node, RSH.resultSeverity, fe(r.severity)))
        for prop, value in r.annotations:
            g.add((node, fe(prop), fe(value)))
            _copy_closure(shapes, g, value, seen)
        for m in r.messages:
            g.add((node, RSH.resultMessage, Literal(m) if isinstance(m, str) else fe(m)))
        for d in r.details:  # SHACL 1.2 Core 6.9.2.6: nested results linked by sh:detail, not by sh:result
            g.add((node, RSH.detail, add_result(d)))
        return node

    for r in results:
        g.add((report, RSH.result, add_result(r)))
    return g
