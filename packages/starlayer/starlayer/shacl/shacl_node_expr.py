"""The public namespace for SHACL 1.2 Node Expressions - `from starlayer.shacl
import shacl_node_expr` then `shacl_node_expr.EvaluationResult`/`.eval_expr`.

Not flattened into `starlayer.shacl`'s own top-level namespace (2026-10-06
decision, mirroring `starlayer.sparql.srl`/`sqe`'s own precedent) - this
name is deliberately distinct from the existing `node_expressions.py`
(the real implementation: `shnex:`/`sparql:` operator dispatch, the
pySHACL-patching machinery `StarLayerShaclProcessor.evaluate()` relies on),
so a caller importing the public surface for this spec document doesn't
also pull in - or need to know about - that module's own private
(`_`-prefixed) internals.

- `EvaluationResult` is defined in `results.py` (alongside every other
  processing mode's result type) - re-exported here under its own
  spec-document name, not moved.
- `eval_expr()` is `node_expressions.py`'s own already-public (no leading
  underscore) function for evaluating a single node expression directly,
  independent of `StarLayerShaclProcessor.evaluate()`'s own per-shape
  orchestration - re-exported here since it had no reachable public
  import path at all before this module existed (confirmed: not in
  `starlayer/shacl/__init__.py`'s own exports, found 2026-10-06 while
  building this namespace split).
"""

from __future__ import annotations

from starlayer.shacl.node_expressions import eval_expr
from starlayer.shacl.results import EvaluationResult

__all__ = ["EvaluationResult", "eval_expr"]
