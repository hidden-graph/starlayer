from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExecutionDiagnostics:
    """Counters of one validation run: the type of ``ValidationResult.diagnostics``. The engine handles RDF 1.2 triple terms
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
class ValidationResult:
    """Result of ``validate()``: whether the data conforms, the validation report as a graph and as text.

    ``data_graph`` is only populated when the call used ``inplace=True``
    (the ``"rules"`` mode's own default) - the caller's own data graph,
    mutated with any in-place changes decoded back; ``None`` otherwise,
    not an error. ``diagnostics`` is an ``ExecutionDiagnostics``.

    ``report_text`` is built on first read (it costs about as much as the validation itself on small data, and most callers only read
    ``conforms`` or the report graph); it may be passed to the constructor as a string or as a function that returns one. A lazily
    built text describes the graphs as they are when it is first read.
    """

    conforms: bool
    report_graph: Any
    data_graph: Any | None = None
    diagnostics: ExecutionDiagnostics | None = None
    _report_text: Any = field(default=None, repr=False, compare=False)

    def __init__(
        self,
        conforms: bool,
        report_graph: Any,
        report_text: str | Callable[[], str],
        data_graph: Any | None = None,
        diagnostics: ExecutionDiagnostics | None = None,
    ) -> None:
        for name, value in (
            ("conforms", conforms),
            ("report_graph", report_graph),
            ("data_graph", data_graph),
            ("diagnostics", diagnostics),
            ("_report_text", report_text),
        ):
            object.__setattr__(self, name, value)

    @property
    def report_text(self) -> str:
        text = self._report_text
        if callable(text):
            text = text()
            object.__setattr__(self, "_report_text", text)
        return text


@dataclass(frozen=True)
class RulesResult:
    """Result of ``apply_rules()``.

    ``apply_rules()`` executes ``sh:rule``/``sh:SPARQLRule`` against a
    private working copy of the caller's ``data_graph`` (never mutated
    in place) and returns what the rules produced.

    ``inferred_graph`` is strictly the SHACL 1.2 Inference Rules spec's own
    "inference graph" - only the triples rule execution itself produced
    (shape-attached ``sh:rule``, global ``sh:SPARQLRule``/``sh:RuleSet``,
    and ``sh:sourceRule`` provenance reifiers). It contains neither the
    original base triples nor anything an entailment regime
    (``sh:entailment`` or ``inference=``) added - entailment is purely a
    computational device for correct rule matching and conformance
    checking here, never persisted into the result.

    ``validation`` is the result of one real ``validate()`` call
    ``apply_rules()`` makes internally, over the *complete* evaluation
    graph: base ∪ every rule-produced triple ∪ every entailed triple.
    ``validation.conforms``/``.report_graph``/``.report_text`` correctly
    reflect everything that was true during execution, even though
    entailment's own triples don't appear in ``inferred_graph`` itself.
    ``validation.data_graph`` is always ``None`` in this context (that
    internal call always uses the ``"validation"`` mode's own
    ``inplace=False`` default) - harmless, just not meaningful here.
    """

    inferred_graph: Any
    validation: ValidationResult


# EvaluationResult/SubgraphExtractionResult were removed - evaluate()/
# extract_subgraph() return a plain graph (or None) directly instead of a
# wrapper dataclass. See each function's own docstring (subgraph_extraction.py,
# validator.py) for what the returned graph contains.
