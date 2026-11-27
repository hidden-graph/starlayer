"""Result records -> ``sh:ValidationReport`` graph (an ``StarLayerGraph``)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pyoxigraph as ox

from starlayer.graph.namespaces import PROV
from starlayer.shacl.engine import terms as T
from starlayer.shacl.engine.executor import Result
from starlayer.shacl.engine.graphs import new_graph
from starlayer.shacl.engine.plan import SH
from starlayer.shacl.engine.terms import text

# The processor as a ``sh:ValidationAgent``: the same IRI the conformance-profile declaration (profiling/profiles.py) is about.
PROCESSOR_IRI = ox.NamedNode("https://github.com/hidden-graph/starlayer/tree/main/packages/starlayer/starlayer/shacl")
_OPTION = "urn:starlayer:shacl-engine:option:"
_ENTAILMENT = "http://www.w3.org/ns/entailment/"
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


def _python_literal(value: Any) -> Any:
    if isinstance(value, (ox.Literal, ox.NamedNode)):  # an option that is an IRI (an entailment regime) stays one
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
    """Validation provenance in the Profiling draft's activity form ("Persisting validation results with context"): a blank
    ``sh:ValidationActivity`` that ``prov:generated`` the report, ``sh:usedDataGraph`` / ``sh:usedShapesGraph`` (only the names
    that are known), on request ``sh:usedConfiguration`` (a ``sh:ProcessorConfiguration``; the draft defines no properties for it,
    so the options of this run are ``urn:starlayer:shacl-engine:option:`` triples) and ``prov:wasAssociatedWith`` the processor.
    The report node itself carries none of these. Nothing is written when there is no name and no configuration request. No
    time is recorded, so a report stays reproducible. When both names are known the Profiling S5.7
    ``sh:conformsToShapesGraph`` rule also runs on the report.
    """
    node = next(iter(report.subjects(T.RDF.type, SH.ValidationReport)), None)
    if node is None:
        return
    if data_graph_iri is None and shapes_graph_iri is None and not include_used_configuration:
        return
    activity = ox.BlankNode()
    report.add((activity, T.RDF.type, SH.ValidationActivity))
    report.add((activity, PROV.generated, node))
    if data_graph_iri is not None:
        report.add((activity, SH.usedDataGraph, identity_term(data_graph_iri)))
    if shapes_graph_iri is not None:
        report.add((activity, SH.usedShapesGraph, identity_term(shapes_graph_iri)))
    if include_used_configuration:
        config = ox.BlankNode()
        report.add((config, T.RDF.type, SH.ProcessorConfiguration))
        for name, value in sorted((configuration or {}).items()):
            for item in value if isinstance(value, (list, tuple, set, frozenset)) else (value,):
                if item is not None:
                    report.add((config, ox.NamedNode(_OPTION + name), _python_literal(item)))
        report.add((activity, SH.usedConfiguration, config))
    report.bind("prov", str(PROV), override=False)  # the prefixes the activity uses, and only those, so a report stays light
    report.bind("starlayer", PROCESSOR_IRI.value[: -len("shacl")], override=False)
    if include_used_configuration:
        report.bind("slopt", _OPTION, override=False)
        if any(isinstance(v, (str, ox.NamedNode)) and text(v).startswith(_ENTAILMENT) for v in _flat((configuration or {}).values())):
            report.bind("ent", _ENTAILMENT, override=False)
    report.add((activity, PROV.wasAssociatedWith, PROCESSOR_IRI))
    report.add((PROCESSOR_IRI, T.RDF.type, SH.ValidationAgent))
    if data_graph_iri is not None and shapes_graph_iri is not None:
        # Profiling S5.7: lazy import, a pure function over the report graph (not the old validator)
        from starlayer.shacl.profiling.profiles import derive_conforms_to

        report += derive_conforms_to(report, specification_graph=specification_graph)


def _flat(values: Any) -> Any:
    """The items of configuration values, a list or set of them flattened."""
    for value in values:
        if isinstance(value, (list, tuple, set, frozenset)):
            yield from value
        else:
            yield value


@dataclass(frozen=True)
class ReportContent:
    """What a report graph will hold, collected while the shapes and data graphs are as the validation read them: the triples (the closures
    of the nodes the results name and the messages are already in them) and the prefixes of the two graphs. ``write_report`` turns it into
    the graph, at once or later; it reads neither graph, so a graph written later is the one that would have been written then."""

    triples: list
    prefixes: list  # one list of (prefix, namespace) for each of the shapes graph and the data graph


def collect_report(
    results: list[Result], shapes: Any, data: Any, conformance_disallows: Any = None, messages_for: Any = None
) -> ReportContent:
    """The content of the report graph of ``results``. ``messages_for(result)``, when given, supplies the ``sh:resultMessage`` values of a
    result in place of its own."""
    # The old validator binds the data and shapes graphs' prefixes on the report so IRIs print as prefixed names.
    prefixes: list = []
    for source in (shapes, data):
        namespaces = getattr(source, "namespaces", None)
        found: list = []
        if namespaces is not None:
            try:
                found = list(namespaces())
            except Exception:  # noqa: BLE001  (a view without namespace support just keeps the default prefixes)
                found = []
        prefixes.append(found)
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
    return ReportContent(out, prefixes)


def write_report(content: ReportContent) -> Any:
    """The report as an ``StarLayerGraph``, from what ``collect_report`` gathered."""
    g = new_graph()
    g.bind("sh", str(SH))
    for found in content.prefixes:
        try:
            for prefix, namespace in found:
                if prefix and prefix not in g.prefixes:
                    g.bind(prefix, namespace, override=False)
        except Exception:  # noqa: BLE001  (as when the prefixes were read: one that cannot be bound leaves the rest of that graph's out)
            pass
    g.extend(content.triples)
    return g


def build_report(
    results: list[Result], shapes: Any, data: Any, conformance_disallows: Any = None, messages_for: Any = None
) -> Any:
    """The report as an ``StarLayerGraph``. ``messages_for(result)``, when given, supplies the ``sh:resultMessage`` values of a
    result in place of its own."""
    return write_report(collect_report(results, shapes, data, conformance_disallows, messages_for))
