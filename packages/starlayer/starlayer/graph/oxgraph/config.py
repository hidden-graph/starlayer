"""Global settings of the Oxigraph-backed graph wrapper.

``DEFAULT_PREFIXES`` is empty by default (Oxigraph ships with no prefixes). It is COPIED into each graph's own ``prefixes``
dict when the graph is built, so later changes here do not reach graphs that already exist.
"""

from __future__ import annotations

from collections.abc import Mapping

DEFAULT_PREFIXES: dict[str, str] = {}


def set_default_prefixes(mapping: Mapping[str, str] | None) -> None:
    """Replace the global default prefixes (``None`` or an empty mapping clears them)."""
    DEFAULT_PREFIXES.clear()
    DEFAULT_PREFIXES.update({str(k): str(v) for k, v in (mapping or {}).items()})


def new_prefix_dict() -> dict[str, str]:
    """A fresh plain dict holding a copy of the current defaults."""
    return dict(DEFAULT_PREFIXES)
