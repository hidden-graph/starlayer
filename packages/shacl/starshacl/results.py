from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionDiagnostics:
    encode_graph_calls: int = 0
    decode_graph_calls: int = 0
    encoded_triple_terms: int = 0
    decoded_triple_terms: int = 0
    generated_support_triples: int = 0
    encoded_data_triples: int = 0
    report_triples: int = 0
    inplace_data_triples: int = 0


@dataclass(frozen=True)
class ValidationResult:
    conforms: bool
    report_graph: Any
    report_text: str
    data_graph: Any | None = None
    diagnostics: ExecutionDiagnostics | None = None


@dataclass(frozen=True)
class RulesResult:
    data_graph: Any
    report_graph: Any
    report_text: str
    conforms: bool
    diagnostics: ExecutionDiagnostics | None = None


@dataclass(frozen=True)
class EvaluationResult:
    """Result of ``StarShaclValidator.evaluate()`` - a third, independent
    processing mode alongside ``validate()`` (checks conformance, never
    mutates) and ``apply_rules()`` (executes ``sh:rule``, materializes real
    triples). ``evaluate()`` computes every ``sh:values``-declared virtual
    property across the shapes graph, for every focus node it applies to,
    and returns them merged into a *throwaway* copy of the data graph -
    never the caller's own ``data_graph`` object, and not meant to be
    persisted (the SHACL 1.2 Node Expressions spec's own framing: computed
    "only on demand", never creating real triples in the data graph or
    shapes graph). No ``conforms``/``report_graph`` here - ``evaluate()``
    never validates anything, so those concepts don't apply.
    """

    data_graph: Any
