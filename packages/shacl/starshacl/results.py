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
