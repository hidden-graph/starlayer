"""Portable, machine-independent identifiers for manifest entries.

Deliberately *not* ``str(entry.iri)`` - an entry's IRI is a ``file://``
absolute path (see manifest.py), which differs across machines/checkouts
(a different clone path, CI's checkout directory, ...). A stable id needs to
be relative to the vendored suite's own root instead, so it can be committed
in known_failures.py and still match on any machine. This is also used as
the pytest parametrize id, so a failing test's node id can be pasted
directly into known_failures.py's dict.
"""

from __future__ import annotations

from pathlib import Path

from .manifest import ManifestEntry


def portable_id(entry: ManifestEntry, vendor_root: Path) -> str:
    try:
        relative = entry.source_path.resolve().relative_to(vendor_root.resolve())
    except ValueError:
        relative = entry.source_path

    if entry.parse_error is not None:
        return str(relative)

    local_name = str(entry.iri).rsplit("/", 1)[-1]
    return f"{relative.with_suffix('')}::{local_name}"
