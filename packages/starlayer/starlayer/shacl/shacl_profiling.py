"""The public namespace for SHACL 1.2 Profiling - `from starlayer.shacl
import shacl_profiling` then `shacl_profiling.ValidationProfile`/etc.

Not flattened into `starlayer.shacl`'s own top-level namespace (2026-10-06
decision, mirroring `starlayer.sparql.srl`/`sqe`'s own precedent).
Aggregates two sibling implementation files that between them cover this
one spec document - `profiles.py` (the `ValidationProfile` data model,
used internally by `StarShaclSchema.validate()`'s own
`profile=` parameter) and `profiling.py` (the §3/§5.5-specific
conformance-declaration/`sh:conformsTo`-derivation helpers) - under one
spec-concept-named import, rather than a caller needing to know this
project's own two-file split to find everything Profiling-related.
"""

from __future__ import annotations

from starlayer.shacl.profiles import (
    ValidationProfile,
    available_profiles,
    get_profile,
    resolve_profile_options,
)
from starlayer.shacl.profiling import declared_conformance_profile, derive_conforms_to

__all__ = [
    "ValidationProfile",
    "available_profiles",
    "get_profile",
    "resolve_profile_options",
    "declared_conformance_profile",
    "derive_conforms_to",
]
