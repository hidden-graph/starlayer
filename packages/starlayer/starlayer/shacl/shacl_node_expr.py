"""The public namespace for SHACL 1.2 Node Expressions - `from starlayer.shacl
import shacl_node_expr` then `shacl_node_expr.evaluate`/`.eval_expr`.

**2026-10-07 - `evaluate` also flat now**: directly
`from starlayer.shacl import evaluate`-able too (reverses the 2026-10-06
"qualified submodule only" decision below, for every processing-mode
function except Profiling's own two helpers - see
`starlayer/shacl/__init__.py`'s own comment for the full reasoning). This
module still exists and still works unchanged - nothing was removed.
`eval_expr` deliberately stays qualified-only even now: it's a
lower-level, one-expression-at-a-time primitive, not a processing mode, so
it wasn't part of that promotion.

This name is deliberately distinct from the existing `node_expressions.py`
(the real implementation: `shnex:`/`sparql:` operator dispatch, the
pySHACL-patching machinery `evaluate()` relies on), so a caller importing
the public surface for this spec document doesn't also pull in - or need
to know about - that module's own private (`_`-prefixed) internals.

- `evaluate()` is defined in `validator.py` (2026-10-07: promoted to a
  real module-level function, mirroring `apply_rules()`'s own earlier
  flip - `StarShaclSchema.evaluate()` itself is unchanged for now, a
  separate later step) - re-exported here under this spec document's own
  name, not moved, matching `shacl_inference.apply_rules`'s own precedent
  for the identical situation. Returns a plain graph object directly
  (2026-10-08 - the now-removed `EvaluationResult` it used to return had
  shrunk to exactly this one field, with nothing else attached).
- `eval_expr()` is `node_expressions.py`'s own already-public (no leading
  underscore) function for evaluating a single node expression directly,
  independent of `evaluate()`'s own per-shape orchestration - re-exported
  here since it had no reachable public import path at all before this
  module existed (confirmed: not in `starlayer/shacl/__init__.py`'s own
  exports, found 2026-10-06 while building this namespace split).
"""

from __future__ import annotations

from starlayer.shacl.node_expressions import eval_expr
from starlayer.shacl.validator import evaluate

__all__ = ["evaluate", "eval_expr"]
