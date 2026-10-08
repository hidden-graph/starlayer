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
    """Result of ``apply_rules()`` - executes ``sh:rule``/``sh:SPARQLRule``
    against a private working copy of the caller's ``data_graph`` (never
    mutated in place) and returns what the rules produced.

    ``inferred_graph`` (named this way, not ``data_graph``, since
    2026-10-08 - it is never the caller's own input graph) is strictly
    the SHACL 1.2 Inference Rules spec's own "inference graph" - only the
    triples rule execution itself produced (shape-attached ``sh:rule``,
    global ``sh:SPARQLRule``/``sh:RuleSet``, and ``sh:sourceRule``
    provenance reifiers). It contains neither the original base triples
    nor anything an entailment regime (``sh:entailment`` or
    ``inference=``) added - entailment is purely a computational device
    for correct rule matching and conformance checking here, never
    persisted into the result.

    ``validation`` (2026-10-08 - composed rather than flattened, since it
    really is nothing but the result of one real ``validate()`` call
    ``apply_rules()`` makes internally, over the *complete* evaluation
    graph: base ∪ every rule-produced triple ∪ every entailed triple).
    ``validation.conforms``/``.report_graph``/``.report_text`` correctly
    reflect everything that was true during execution, even though
    entailment's own triples don't appear in ``inferred_graph`` itself.
    ``validation.data_graph`` is always ``None`` in this context (that
    internal call always uses the ``"validation"`` profile's own
    ``inplace=False`` default) - harmless, just not meaningful here.
    """

    inferred_graph: Any
    validation: ValidationResult


# SubgraphExtractionResult/EvaluationResult removed 2026-10-08 - both had
# shrunk, across earlier same-day renames, to a single graph-or-None field
# with no other information attached (conforms/report_graph/report_text
# were already absent or, for SubgraphExtractionResult, dropped as
# redundant with "is the graph None"). Wrapping one value in a
# one-field frozen dataclass added a layer of indirection with nothing
# behind it - extract_subgraph()/evaluate() now just return that one
# value directly (the extracted/computed graph, or None) instead of a
# result object. See each function's own docstring (subgraph_extraction.py,
# validator.py) for what the returned graph actually contains - the
# design rationale previously recorded on these two classes lives there
# now.
