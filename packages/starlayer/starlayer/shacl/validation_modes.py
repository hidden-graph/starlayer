"""Named bundles of validator options ("validation"/"rules"/"debug" presets
for meta_shacl/advanced/inplace/etc.), selected via validate(mode=...).

2026-10-08: renamed from `profiles.py` (ValidationProfile -> ValidationMode,
etc.) - this had nothing to do with any SHACL spec and the shared word
"profile" with the *actual* SHACL 1.2 Profiling spec (starlayer.shacl's
profiling.py) was a real, flagged source of confusion. "Profile" is now
reserved exclusively for that spec concept across this project; this is an
ordinary option preset, so it's named that way instead. See
starlayer/shacl/CLAUDE.md's dated entry for the full rename.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationMode:
    name: str
    options: dict[str, Any]


_MODE_OPTIONS: dict[str, dict[str, Any]] = {
    "validation": {
        "advanced": True,
        "inplace": False,
        "meta_shacl": True,
    },
    "rules": {
        "advanced": True,
        "iterate_rules": True,
        "inplace": True,
        "meta_shacl": True,
    },
    "debug": {
        "advanced": True,
        "inplace": False,
        "debug": True,
        "meta_shacl": True,
    },
}


def available_modes() -> tuple[str, ...]:
    return tuple(sorted(_MODE_OPTIONS.keys()))


def get_mode(name: str) -> ValidationMode:
    key = name.strip().lower()
    if key not in _MODE_OPTIONS:
        raise ValueError(f"Unknown validation mode {name!r}. Expected one of {available_modes()}.")
    return ValidationMode(name=key, options=dict(_MODE_OPTIONS[key]))


def resolve_mode_options(
    mode: str | ValidationMode | None = None,
    *,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if mode is None:
        base = dict(_MODE_OPTIONS["validation"])
    elif isinstance(mode, ValidationMode):
        base = dict(mode.options)
    else:
        base = dict(get_mode(mode).options)

    if overrides:
        base.update(dict(overrides))

    return base
