from starlayer.shacl.adapters import TripleTermAdapter, TripleTermGraph, TripleTermValue
from starlayer.shacl.engine import (
    normalize_graph_inputs,
    normalize_to_starlayer_graph,
    target_nodes,
)
from starlayer.shacl.results import (
    ExecutionDiagnostics,
    RulesResult,
    ValidationResult,
)
from starlayer.shacl.subgraph_extraction import extract_subgraph
from starlayer.shacl.types import MutableStarLayerGraphProtocol, StarLayerGraphProtocol
from starlayer.shacl.validator import StarShaclSchema, apply_rules, evaluate, validate, validate_each

# Every public processing-mode function and remaining result class is flat
# here (2026-10-07 - reverses the 2026-10-06 "qualified submodule" decision
# below for everything except Profiling): `validate`/`validate_each`
# (Core), `apply_rules`/`RulesResult` (Inference Rules), `evaluate`
# (Node Expressions), `extract_subgraph` (subgraph extraction, not a spec
# document of its own) are all directly `from starlayer.shacl import ...`
# -able now, alongside `StarShaclSchema`/`ValidationResult`/
# `ExecutionDiagnostics`, which were already flat. None of the underlying
# implementations moved - `apply_rules`/`evaluate` still live in
# `validator.py`, `RulesResult` still in `results.py`, `extract_subgraph`
# still in `subgraph_extraction.py` - only this file's own import/export
# list changed. `shacl_inference`/`shacl_node_expr` (the former
# qualified-only namespaces for the first two) still exist and still work
# unchanged - nothing was removed - but the flat names above are the
# primary path now.
#
# `evaluate()`/`extract_subgraph()` return a plain graph object directly
# (or `None`, for `extract_subgraph()`) rather than a result class -
# `EvaluationResult`/`SubgraphExtractionResult` were removed entirely
# 2026-10-08, once both had shrunk, across the same day's earlier renames,
# to a single graph-or-`None` field with nothing else attached. See
# `starlayer/shacl/CLAUDE.md`'s dated entry.
#
# SHACL 1.2 Profiling remains the one deliberate exception, still
# qualified-only (`from starlayer.shacl import shacl_profiling`): its own
# two helpers (`declared_conformance_profile`/`derive_conforms_to`) are
# self-declaration/report-annotation utilities, not a fifth processing
# mode alongside the four above, so there's no case for promoting them to
# flat names just because these four were.
#
# `eval_expr()` (`node_expressions.py`, re-exported via `shacl_node_expr`)
# also stays qualified-only, deliberately: it's a lower-level, one-
# expression-at-a-time primitive, not a processing mode in its own right
# (see `docs/api-reference.md`'s "Lower-level" section for the same
# distinction) - the promotion here is scoped to the top-level processing
# surface specifically, not every public name in the package.
#
# `target_nodes` (2026-10-08) is flat too, for the same reason as the
# processing functions above: "which nodes would this shape target?" is a
# real, standalone introspection question (UI tooling, debugging) someone
# might reasonably want answered without running a full `validate()` pass.
#
# `evaluate_component`/`build_report` deliberately did **not** get the same
# promotion, despite initially being flattened alongside `target_nodes` and
# then reverted the same day on direct user challenge ("that does not
# sound like a public function"): unlike `target_nodes`, `evaluate_component`
# is a hardcoded dispatcher over a fixed set of component names
# (`hasValue`/`in`/`equals`/`disjoint`/etc.) with no extension mechanism - a
# caller can't register a new component type into it, and calling it
# standalone only ever reproduces behavior `validate()` already gives for
# free. `build_report` only makes sense paired with `evaluate_component()`'s
# own "events" output shape, so it inherits the same lack of a standalone
# use case. Both stay reachable via `from starlayer.shacl import engine`,
# alongside `ComponentRequest` (needed only to call `evaluate_component()`)
# and `STSH` (needed only to *define* a new native component). Their own
# return type, `_ComponentEvaluationResult`, is private - not re-exported
# even from `engine` - for the same reason: no standalone use case means
# no reason for its own type to be part of any public surface either.
#
# `close_shape` is no longer a bare function here at all (2026-10-07) -
# it's `StarShaclSchema.close_shape(shape)`, a method binding the
# instance's own `shacl_graph` rather than taking it as a parameter,
# matching every other processing mode on that class.

__all__ = [
    "StarShaclSchema",
    "validate",
    "validate_each",
    "apply_rules",
    "evaluate",
    "extract_subgraph",
    "TripleTermAdapter",
    "TripleTermGraph",
    "TripleTermValue",
    "normalize_to_starlayer_graph",
    "normalize_graph_inputs",
    "ExecutionDiagnostics",
    "ValidationResult",
    "RulesResult",
    "target_nodes",
    "StarLayerGraphProtocol",
    "MutableStarLayerGraphProtocol",
]
