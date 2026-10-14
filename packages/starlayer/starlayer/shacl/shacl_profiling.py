"""The public namespace for SHACL 1.2 Profiling - `from starlayer.shacl
import shacl_profiling` then `shacl_profiling.declared_conformance_profile`/
`shacl_profiling.derive_conforms_to`.

A thin re-export of `profiling.py`'s own two functions - the real SHACL 1.2
Profiling spec (https://www.w3.org/TR/shacl12-profiling/) implementation.
Not flattened into `starlayer.shacl`'s own top-level namespace, mirroring
`starlayer.sparql.srl`/`sqe`'s own precedent of a dedicated submodule per
spec document.

For the unrelated validator-option-preset concept (the `"validation"`/
`"rules"`/`"debug"` presets selected via `validate(mode=...)`), see
`starlayer.shacl.validation_modes` instead - that concept has nothing to
do with this SHACL document despite the shared English word "profile."
"""

from __future__ import annotations

from starlayer.shacl.profiling import declared_conformance_profile, derive_conforms_to

__all__ = [
    "declared_conformance_profile",
    "derive_conforms_to",
]
