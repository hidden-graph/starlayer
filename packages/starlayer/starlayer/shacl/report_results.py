"""Reading a validation report: ``ReportResult``, ``report_results()`` and ``diff_reports()``.

An application shows each problem beside the node and field it is about; this module is the one place that reads the
``sh:ValidationResult`` nodes of a report graph (the ``report_graph`` of a ``ValidationReport``, of a ``MetaShaclError``, or any
graph holding ``sh:ValidationReport`` nodes), so the application does not re-read the vocabulary itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pyoxigraph as ox

from starlayer.shacl.engine.terms import SH, engine_view, n3, text

_RDF_TYPE = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")

# Most severe first; a user-defined severity sorts after these, by its IRI.
_SEVERITIES = ("Violation", "Warning", "Info", "Debug", "Trace")
_SEVERITY_RANK = {SH[name]: rank for rank, name in enumerate(_SEVERITIES)}

# What a result node says through its own fields; any other predicate on it is an annotation (sh:resultAnnotation of a shape).
_OWN_PREDICATES = frozenset(
    {
        _RDF_TYPE,
        SH.focusNode,
        SH.resultPath,
        SH.value,
        SH.sourceConstraintComponent,
        SH.sourceShape,
        SH.sourceConstraint,
        SH.resultSeverity,
        SH.resultMessage,
        SH.detail,
    }
)


def _key(term: Any) -> tuple[str, str]:
    """A total order for terms that may be absent: by text, then by the N-Triples form so equal text of different kinds stays ordered."""
    return ("", "") if term is None else (text(term), n3(term))


@dataclass(frozen=True)
class ReportResult:
    """One ``sh:ValidationResult`` of a report, read into plain fields.

    ``node`` is the result node in the report graph. ``path`` is the ``sh:resultPath`` term as written (a blank node for a complex
    path), ``None`` for a result about the node itself. ``value`` is only meaningful when ``has_value`` is true: a result such as
    ``sh:minCount`` has no value, which is different from a value that is ``None``. ``severity`` is ``sh:Violation`` when the result
    names none. ``messages`` and ``annotations`` are in a stable order. ``details`` are the nested ``sh:detail`` results, which are
    not results of the report on their own. ``focus``, ``component`` and ``source_shape`` are ``None`` only for a hand-written
    result that lacks them."""

    node: Any
    focus: Any
    path: Any
    value: Any
    has_value: bool
    component: Any
    source_shape: Any
    source_constraint: Any
    severity: Any
    messages: tuple[Any, ...]
    details: tuple[ReportResult, ...]
    annotations: tuple[tuple[Any, Any], ...] = ()

    @property
    def severity_name(self) -> str:
        """``"Violation"``, ``"Warning"``, ``"Info"``, ``"Debug"`` or ``"Trace"``; the IRI text for a user-defined severity."""
        rank = _SEVERITY_RANK.get(self.severity)
        return _SEVERITIES[rank] if rank is not None else text(self.severity)

    def identity(self) -> tuple:
        """What makes two results the same mistake: the node, field and value it is about, the constraint and the severity; not the
        result node's label and not the message text."""
        return (self.focus, self.path, self.value if self.has_value else None, self.has_value, self.component, self.source_shape, self.severity)

    def _sort_key(self) -> tuple:
        rank = _SEVERITY_RANK.get(self.severity, len(_SEVERITIES))
        return (
            rank,
            _key(self.severity) if rank == len(_SEVERITIES) else ("", ""),
            _key(self.focus),
            _key(self.path),
            _key(self.component),
            self.has_value,
            _key(self.value),
            _key(self.source_shape),
            _key(self.source_constraint),
            tuple(_key(m) for m in self.messages),
        )


def _one(graph: Any, node: Any, predicate: Any) -> Any:
    """The value of a property that has one; the first in text order when a hand-written result has several."""
    found = sorted(graph.objects(node, predicate), key=_key)
    return found[0] if found else None


def _read(graph: Any, node: Any, seen: frozenset = frozenset()) -> ReportResult:
    """``node`` as a ``ReportResult``; ``seen`` stops a ``sh:detail`` cycle in a hand-written graph."""
    values = list(graph.objects(node, SH.value))
    annotations = sorted(
        ((p, o) for _s, p, o in graph.triples((node, None, None)) if p not in _OWN_PREDICATES),
        key=lambda po: (_key(po[0]), _key(po[1])),
    )
    nested = seen | {node}
    details = sorted(
        (_read(graph, d, nested) for d in set(graph.objects(node, SH.detail)) if d not in nested),
        key=ReportResult._sort_key,
    )
    return ReportResult(
        node=node,
        focus=_one(graph, node, SH.focusNode),
        path=_one(graph, node, SH.resultPath),
        value=min(values, key=_key) if values else None,
        has_value=bool(values),
        component=_one(graph, node, SH.sourceConstraintComponent),
        source_shape=_one(graph, node, SH.sourceShape),
        source_constraint=_one(graph, node, SH.sourceConstraint),
        severity=_one(graph, node, SH.resultSeverity) or SH.Violation,
        messages=tuple(sorted(graph.objects(node, SH.resultMessage), key=_key)),
        details=tuple(details),
        annotations=tuple(annotations),
    )


def report_results(report_graph: Any) -> tuple[ReportResult, ...]:
    """The top-level results of every ``sh:ValidationReport`` in ``report_graph`` (its ``sh:result`` values), most severe first, then by
    focus, path, component, value and source shape text, so the order never depends on how the store enumerates.

    ``report_graph`` is a ``StarLayerGraph``, ``StarLayerDataset`` or store, as for the other entry points (an rdflib graph is a
    ``TypeError`` naming ``StarLayerGraph.from_rdflib``); it is not changed. Nested ``sh:detail`` results are in ``ReportResult.details``
    and are not listed here."""
    graph = engine_view(report_graph, "report graph")
    nodes = {
        result
        for report in graph.subjects(_RDF_TYPE, SH.ValidationReport)
        for result in graph.objects(report, SH.result)
    }
    return tuple(sorted((_read(graph, n) for n in nodes), key=ReportResult._sort_key))


def deduplicate(results: tuple[ReportResult, ...]) -> tuple[ReportResult, ...]:
    """``results`` without a result that repeats an earlier one in focus, path, value, component, source shape, severity and messages."""
    seen: set = set()
    kept = []
    for result in results:
        key = (result.identity(), result.messages)
        if key not in seen:
            seen.add(key)
            kept.append(result)
    return tuple(kept)


@dataclass(frozen=True)
class ReportDiff:
    """The difference between two validations of the same data: ``added`` results are in the new report only, ``fixed`` ones in the old
    report only, ``unchanged`` ones in both (taken from the new report)."""

    added: tuple[ReportResult, ...]
    fixed: tuple[ReportResult, ...]
    unchanged: tuple[ReportResult, ...]


def _distinct(report: Any) -> dict:
    """The de-duplicated results of a ``ValidationReport`` or a report graph by identity, the first of each."""
    graph = getattr(report, "report_graph", report)
    found: dict = {}
    for result in deduplicate(report_results(graph)):
        found.setdefault(result.identity(), result)
    return found


def diff_reports(old: Any, new: Any) -> ReportDiff:
    """Compare two validations by what each result is about (focus, path, value, component, source shape, severity), not by the
    result node's label or the message text; a mistake reported twice counts once. ``old`` and ``new`` are each a ``ValidationReport``
    or a report graph.

    A focus node (or value) that is a blank node compares by its label, so two validations of different parses of the same data do not
    line up on blank nodes: such results show as both ``fixed`` and ``added``. Compare validations of one loaded graph, or of graphs
    whose blank nodes keep their labels."""
    before, after = _distinct(old), _distinct(new)
    return ReportDiff(
        added=tuple(r for k, r in after.items() if k not in before),
        fixed=tuple(r for k, r in before.items() if k not in after),
        unchanged=tuple(r for k, r in after.items() if k in before),
    )
