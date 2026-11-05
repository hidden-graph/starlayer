"""Result records -> ``sh:ValidationReport`` graph (an ``StarLayerGraph``)."""

from __future__ import annotations

from typing import Any

import pyoxigraph as ox

from starlayer.shacl_engine import terms as T
from starlayer.shacl_engine.executor import Result
from starlayer.shacl_engine.graphs import new_graph
from starlayer.shacl_engine.plan import SH

_OPTION = "urn:starlayer:shacl-engine:option:"
_ORDER: dict = {SH.Trace: 0, SH.Debug: 1, SH.Info: 2, SH.Warning: 3, SH.Violation: 4}


def conforms(results: list[Result], conformance_disallows: Any = None) -> bool:
    """No result blocks conformance. ``conformance_disallows`` (SHACL 1.2): the lowest severity that blocks; ``None``
    means Info and above block (Debug and Trace do not); an unknown severity blocks."""
    floor = _ORDER[SH.Info] if conformance_disallows is None else _ORDER.get(conformance_disallows, _ORDER[SH.Info])
    return not any(_ORDER.get(r.severity, _ORDER[SH.Violation]) >= floor for r in results)


def _copy_closure(src: Any, out: list, node: Any, seen: set) -> None:
    """Collect the blank-node closure of ``node`` from the graph ``src`` into the triple list ``out``."""
    pending = [node]
    while pending:
        current = pending.pop()
        if not isinstance(current, ox.BlankNode) or current in seen:
            continue
        seen.add(current)
        for p, o in src.predicate_objects(current):
            out.append((current, p, o))
            pending.append(o)


def identity_term(value: Any) -> Any:
    """A graph identity as a term: IRIs and literals (a version IRI may be a literal) as they are, anything else (a str) as an IRI."""
    if isinstance(value, (ox.NamedNode, ox.Literal)):
        return value
    converted = T.to_engine(value) if not isinstance(value, str) else None
    if isinstance(converted, (ox.NamedNode, ox.Literal)):
        return converted
    return ox.NamedNode(value if isinstance(value, str) else T.text(converted))


def _python_literal(value: Any) -> ox.Literal:
    if isinstance(value, ox.Literal):
        return value
    if isinstance(value, bool):
        return T.boolean(value)
    if isinstance(value, int):
        return T.integer(value)
    if isinstance(value, float):
        return ox.Literal(repr(value), datatype=T.XSD.double)
    return ox.Literal(f"{value}")  # str-ok: a plain Python value


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
    node = next(iter(report.subjects(T.RDF.type, SH.ValidationReport)), None)
    if node is None:
        return
    if data_graph_iri is not None:
        report.add((node, SH.usedDataGraph, identity_term(data_graph_iri)))
    if shapes_graph_iri is not None:
        report.add((node, SH.usedShapesGraph, identity_term(shapes_graph_iri)))
    if include_used_configuration:
        config = ox.BlankNode()
        report.add((config, T.RDF.type, SH.ProcessorConfiguration))
        for name, value in sorted((configuration or {}).items()):
            if value is not None:
                report.add((config, ox.NamedNode(_OPTION + name), _python_literal(value)))
        report.add((node, SH.usedConfiguration, config))
    if data_graph_iri is not None and shapes_graph_iri is not None:
        # Profiling S5.5: lazy import, a pure function over the report graph (not the old validator)
        from starlayer.shacl.profiling import derive_conforms_to

        report += derive_conforms_to(report, specification_graph=specification_graph)


def build_report(
    results: list[Result], shapes: Any, data: Any, conformance_disallows: Any = None, messages_for: Any = None
) -> Any:
    """The report as an ``StarLayerGraph``. ``messages_for(result)``, when given, supplies the ``sh:resultMessage`` values of a
    result in place of its own."""
    g = new_graph()
    g.bind("sh", str(SH))
    # The old validator binds the data and shapes graphs' prefixes on the report so IRIs print as prefixed names.
    for source in (shapes, data):
        namespaces = getattr(source, "namespaces", None)
        if namespaces is not None:
            try:
                for prefix, namespace in namespaces():
                    if prefix and prefix not in g.prefixes:
                        g.bind(prefix, namespace, override=False)
            except Exception:  # noqa: BLE001  (a view without namespace support just keeps the default prefixes)
                pass
    report = ox.BlankNode()
    out: list[tuple[Any, Any, Any]] = [
        (report, T.RDF.type, SH.ValidationReport),
        (report, SH.conforms, T.boolean(conforms(results, conformance_disallows))),
    ]
    if conformance_disallows is not None:
        out.append((report, SH.conformanceDisallows, conformance_disallows))
    seen: set = set()

    def add_result(r: Result) -> ox.BlankNode:
        node = ox.BlankNode()
        out.append((node, T.RDF.type, SH.ValidationResult))
        out.append((node, SH.focusNode, r.focus))
        _copy_closure(data, out, r.focus, seen)
        if r.path is not None and r.path.node is not None:
            out.append((node, SH.resultPath, r.path.node))
            _copy_closure(shapes, out, r.path.node, seen)
        if r.has_value:
            out.append((node, SH.value, r.value))
            _copy_closure(data, out, r.value, seen)
        out.append((node, SH.sourceConstraintComponent, r.component))
        out.append((node, SH.sourceShape, r.shape))
        if r.source_constraint is not None:
            out.append((node, SH.sourceConstraint, r.source_constraint))
            _copy_closure(shapes, out, r.source_constraint, seen)
        out.append((node, SH.resultSeverity, r.severity))
        for prop, value in r.annotations:
            out.append((node, prop, value))
            _copy_closure(shapes, out, value, seen)
        for m in r.messages if messages_for is None else messages_for(r):
            out.append((node, SH.resultMessage, ox.Literal(m) if isinstance(m, str) else m))
        for d in r.details:  # SHACL 1.2 Core 6.9.2.6: nested results linked by sh:detail, not by sh:result
            out.append((node, SH.detail, add_result(d)))
        return node

    for r in results:
        out.append((report, SH.result, add_result(r)))
    g.extend(out)
    return g
