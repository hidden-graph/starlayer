from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationProfile:
    name: str
    options: dict[str, Any]


_PROFILE_OPTIONS: dict[str, dict[str, Any]] = {
    "validation": {
        "advanced": False,
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


def available_profiles() -> tuple[str, ...]:
    return tuple(sorted(_PROFILE_OPTIONS.keys()))


def get_profile(name: str) -> ValidationProfile:
    key = name.strip().lower()
    if key not in _PROFILE_OPTIONS:
        raise ValueError(f"Unknown validation profile {name!r}. Expected one of {available_profiles()}.")
    return ValidationProfile(name=key, options=dict(_PROFILE_OPTIONS[key]))


def resolve_profile_options(
    profile: str | ValidationProfile | None = None,
    *,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if profile is None:
        base = dict(_PROFILE_OPTIONS["validation"])
    elif isinstance(profile, ValidationProfile):
        base = dict(profile.options)
    else:
        base = dict(get_profile(profile).options)

    if overrides:
        base.update(dict(overrides))

    return base
