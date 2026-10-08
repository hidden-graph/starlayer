"""The public namespace for SHACL 1.2 Inference Rules - `from starlayer.shacl
import shacl_inference` then `shacl_inference.apply_rules`/`RulesResult`.

**2026-10-07 - also flat now**: `apply_rules`/`RulesResult` are directly
`from starlayer.shacl import apply_rules, RulesResult`-able too (reverses
the 2026-10-06 "qualified submodule only" decision below, for every
processing-mode function/result class except Profiling's own two
helpers - see `starlayer/shacl/__init__.py`'s own comment for the full
reasoning). This module still exists and still works unchanged - nothing
was removed - it's just no longer the *only* way to reach these two names.

`apply_rules()`/`RulesResult` are both defined in `validator.py`/
`results.py` (alongside every other processing mode's own function/result
type, for a shared, simple file) - re-exported here under this spec
document's own name, not moved, since neither definition is otherwise
Inference-Rules-specific. `apply_rules(data_graph, shacl_graph=None,
ont_graph=None, **kwargs)` is the real implementation (2026-10-07) -
mirrors pyshacl's own module-level `shacl_rules()` entry point;
`StarShaclSchema.apply_rules()` delegates to it, binding its own
`shacl_graph`/`ont_graph` rather than duplicating the logic.
"""

from __future__ import annotations

from starlayer.shacl.results import RulesResult
from starlayer.shacl.validator import apply_rules

__all__ = ["apply_rules", "RulesResult"]
