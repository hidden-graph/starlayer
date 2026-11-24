"""The public namespace for SHACL 1.2 Profiling - `from starlayer.shacl
import profiling` then `profiling.declared_conformance_profile`/
`profiling.derive_conforms_to`.

A thin re-export of `profiling.py`'s own two functions - the real SHACL 1.2
Profiling spec (https://www.w3.org/TR/shacl12-profiling/) implementation.
The same two functions (and the `CONFORMANCE` namespace) are also importable from `starlayer.shacl` itself, so an
application imports everything from one place; `profiling` stays as the dedicated submodule for this spec document, as
`starlayer.sparql.srl`/`sqe` are for theirs.

For the unrelated validator-option-preset concept (the `"validation"`/
`"rules"`/`"debug"` presets selected via `validate(mode=...)`), see
`starlayer.shacl.validation_modes` instead - that concept has nothing to
do with this SHACL document despite the shared English word "profile."
"""

from __future__ import annotations

from starlayer.shacl.profiling.profiles import (
    declared_conformance_profile,
    derive_conforms_to,
)

__all__ = [
    "declared_conformance_profile",
    "derive_conforms_to",
]
