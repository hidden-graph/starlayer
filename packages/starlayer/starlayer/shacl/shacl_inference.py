"""The public namespace for SHACL 1.2 Inference Rules - `from starlayer.shacl
import shacl_inference` then `shacl_inference.RulesResult`.

Not flattened into `starlayer.shacl`'s own top-level namespace (2026-10-06
decision, mirroring `starlayer.sparql.srl`/`sqe`'s own precedent): rule
execution itself is reached through `StarLayerShaclProcessor.apply_rules()`
(a method, not a free function here, since there's no module-level
function form to mirror - see that method's own docstring), but its result
type is real, independently-useful data a caller holds onto and inspects,
so it gets a real, spec-concept-named import path rather than living
unqualified alongside `starlayer.shacl`'s Core validation surface.

`RulesResult` itself is defined in `results.py` (alongside every other
processing mode's result type, for a shared, simple file) - re-exported
here under its own spec-document name, not moved, since nothing about its
own definition is Inference-Rules-specific.
"""

from __future__ import annotations

from starlayer.shacl.results import RulesResult

__all__ = ["RulesResult"]
