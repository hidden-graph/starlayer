"""The public namespace for SHACL 1.2 Profiling - `from starlayer.shacl
import shacl_profiling` then `shacl_profiling.declared_conformance_profile`/
`shacl_profiling.derive_conforms_to`.

Not flattened into `starlayer.shacl`'s own top-level namespace (2026-10-06
decision, mirroring `starlayer.sparql.srl`/`sqe`'s own precedent). A thin
re-export of `profiling.py`'s own two functions - the real SHACL 1.2
Profiling spec (https://www.w3.org/TR/shacl12-profiling/) implementation.

2026-10-08: this module used to *also* re-export `starlayer.shacl.profiles`
(`ValidationProfile`/`available_profiles`/`get_profile`/
`resolve_profile_options`) under this same name, framed as "two sibling
implementation files" for "this one spec document." That framing was wrong
- `profiles.py` was never part of the SHACL 1.2 Profiling spec at all; it's
an internal bundle of validator options (`"validation"`/`"rules"`/`"debug"`
presets), unrelated to the W3C document this module is actually named
after. Confirmed as a real, flagged source of user confusion (the shared
English word "profile," nothing more). Renamed to `ValidationMode` etc. and
moved to its own module, `starlayer.shacl.validation_modes` - reach it via
`from starlayer.shacl import validation_modes`, not here. "Profile" is now
reserved, project-wide, for the actual SHACL spec concept this module
implements.
"""

from __future__ import annotations

from starlayer.shacl.profiling import declared_conformance_profile, derive_conforms_to

__all__ = [
    "declared_conformance_profile",
    "derive_conforms_to",
]
