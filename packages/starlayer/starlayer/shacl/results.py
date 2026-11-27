"""Result types returned by ``validate()`` and ``apply_rules()``."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

from starlayer.shacl.engine.terms import to_engine
from starlayer.shacl.report_results import ReportResult, deduplicate, report_results


@dataclass(frozen=True)
class ExecutionDiagnostics:
    """Counters of one validation run: the type of ``ValidationReport.diagnostics``. The engine handles RDF 1.2 triple terms
    natively, so the encode/decode counters stay 0 (kept so code that reads them keeps working). Not a type you'd construct
    directly."""

    encode_graph_calls: int = 0
    decode_graph_calls: int = 0
    encoded_triple_terms: int = 0
    decoded_triple_terms: int = 0
    generated_support_triples: int = 0
    encoded_data_triples: int = 0
    report_triples: int = 0
    inplace_data_triples: int = 0
    recursion_revisits: int = 0
    """How many (shape, node) pairs were already being evaluated further up and were assumed to conform: the number of times a
    recursive shape met a cycle in the data (a (shape, node) pair already being evaluated further up is assumed to conform). 0 for data with no cycle."""


@dataclass(frozen=True, init=False)
class ValidationReport:
    """StarLayer's object holding the whole outcome of ``validate()``: ``conforms``, the ``sh:ValidationReport`` as a graph
    (``report_graph``) and as text (``report_text``), and ``diagnostics``. An individual result inside the report is an
    ``sh:ValidationResult`` node in ``report_graph``, not an instance of this class.

    ``data_graph`` is only populated when the call used ``inplace=True``
    (the ``"rules"`` mode's own default) - the caller's own data graph,
    mutated with any in-place changes decoded back; ``None`` otherwise,
    not an error. ``diagnostics`` is an ``ExecutionDiagnostics``.

    ``report_text`` is built on first read (it costs about as much as the validation itself on small data, and most callers only read
    ``conforms`` or the report graph); it may be passed to the constructor as a string or as a function that returns one. A lazily
    built text describes the graphs as they are when it is first read. ``report_graph`` and ``diagnostics`` may likewise be passed as a
    function; ``validate()`` does, and writes the graph when it is first read (or in the call, with ``build="graph"``), so a caller
    that never reads it never pays for it. The report graph is the same either way and is written once.
    """

    conforms: bool
    _report_graph: Any = field(repr=False)
    data_graph: Any | None = None
    _diagnostics: Any = field(default=None, repr=False)
    _report_text: Any = field(default=None, repr=False, compare=False)

    def __init__(
        self,
        conforms: bool,
        report_graph: Any,
        report_text: str | Callable[[], str],
        data_graph: Any | None = None,
        diagnostics: ExecutionDiagnostics | Callable[[], ExecutionDiagnostics] | None = None,
    ) -> None:
        """Build a result; ``report_text`` may be a string or a function that builds it on first read.

        Args:
            report_graph: the report graph, or a zero-argument function that writes and returns it on first read.
            report_text: the report text, or a zero-argument function that returns it; the result is cached after the first successful call.
            diagnostics: the diagnostics, or a zero-argument function that returns them on first read.
        """
        for name, value in (
            ("conforms", conforms),
            ("_report_graph", report_graph),
            ("data_graph", data_graph),
            ("_diagnostics", diagnostics),
            ("_report_text", report_text),
        ):
            object.__setattr__(self, name, value)

    @staticmethod
    def _is_function(value: Any) -> bool:
        return callable(value) and not hasattr(value, "triples")  # (a graph is a value, even one that can be called)

    @property
    def report_graph(self) -> Any:
        """The ``sh:ValidationReport`` as a graph, written on first read and kept."""
        graph = self._report_graph
        if self._is_function(graph):
            graph = graph()
            object.__setattr__(self, "_report_graph", graph)
        return graph

    @property
    def diagnostics(self) -> ExecutionDiagnostics | None:
        """The ``ExecutionDiagnostics`` of the run (``report_triples`` counts the report graph, so reading it writes the graph)."""
        found = self._diagnostics
        if self._is_function(found):
            found = found()
            object.__setattr__(self, "_diagnostics", found)
        return found

    @property
    def report_text(self) -> str:
        """The validation report as text, built on first read and cached."""
        text = self._report_text
        if callable(text):
            text = text()
            object.__setattr__(self, "_report_text", text)
        return text

    @cached_property
    def results(self) -> tuple[ReportResult, ...]:
        """The top-level results of ``report_graph``, most severe first (see ``report_results``); read once."""
        return report_results(self.report_graph)

    def for_node(self, node: Any) -> tuple[ReportResult, ...]:
        """The results whose focus node is ``node``."""
        node = to_engine(node)
        return tuple(r for r in self.results if r.focus == node)

    def for_field(self, node: Any, path: Any) -> tuple[ReportResult, ...]:
        """The results about ``node`` whose ``sh:resultPath`` is the term ``path`` (an IRI matches a result whose path is that IRI)."""
        node, path = to_engine(node), to_engine(path)
        return tuple(r for r in self.results if r.focus == node and r.path == path)

    def node_level(self, node: Any) -> tuple[ReportResult, ...]:
        """The results about ``node`` itself: its focus is ``node`` and they have no ``sh:resultPath``."""
        node = to_engine(node)
        return tuple(r for r in self.results if r.focus == node and r.path is None)

    def counts(self) -> dict[str, int]:
        """Top-level results per severity name, in severity order and only for severities present, plus ``"total"``."""
        found: dict[str, int] = {}
        for r in self.results:
            found[r.severity_name] = found.get(r.severity_name, 0) + 1
        found["total"] = len(self.results)
        return found

    def deduplicated(self) -> tuple[ReportResult, ...]:
        """``results`` without a result that repeats an earlier one (same focus, path, value, component, source shape, severity and
        messages). A property shape that several shapes targeting the same node share is evaluated, and reported, once per
        targeting shape; a mistake inside a nested ``sh:node`` / ``sh:memberShape`` is reported once, as ``sh:detail``, not as
        a top-level result for each level."""
        return deduplicate(self.results)


@dataclass(frozen=True)
class RulesResult:
    """Result of ``apply_rules()``: what the rules produced, and nothing else (nothing is validated).

    The rules run on an overlay over the caller's data, which is neither copied nor changed.

    ``inferred_graph`` is strictly the SHACL 1.2 Inference Rules spec's own "inference graph": only the triples rule execution
    produced (shape-attached ``sh:rule``, global ``sh:SPARQLRule`` / ``sh:RuleSet``, and ``sh:sourceRule`` provenance reifiers when
    asked for). It holds neither the base triples nor anything an entailment regime (``sh:entailment`` or ``inference=``) added:
    entailment only lets the rules match correctly and is never persisted into the result.
    """

    inferred_graph: Any


@dataclass(frozen=True)
class CheckedInferenceResult(RulesResult):
    """A ``RulesResult`` that also carries a validation: what an SRL ``RuleSet.infer(schema=...)`` returns. ``apply_rules()`` never
    returns one, because it validates nothing; SRL's ``schema=`` keyword validates the base data together with the inferred triples
    against the shapes it was given, and ``validation`` is that report."""

    validation: ValidationReport


# EvaluationResult/SubgraphExtractionResult were removed - evaluate()/
# extract_subgraph() return a plain graph (or None) directly instead of a
# wrapper dataclass. See each function's own docstring (subgraph_extraction.py,
# validator.py) for what the returned graph contains.
