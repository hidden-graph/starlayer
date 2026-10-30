"""The StarLayer code knowledge graph as installed data.

``starlayer-kg.trig`` and ``BUILD.json`` are written into this package by ``scripts/publish_kg.py`` when a release is
made; nothing here builds anything.
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["path", "load", "build_info"]

_HERE = Path(__file__).parent


def path() -> Path:
    """The TriG file. Plain TriG that any RDF library can read; StarLayer's ``trig12`` format is the one tested."""
    trig = _HERE / "starlayer-kg.trig"
    if not trig.exists():
        raise FileNotFoundError(
            f"{trig} is missing: this is a source checkout, not a built starlayer-kg release. "
            "Install the release (pip install starlayer-kg) or run `python scripts/publish_kg.py`."
        )
    return trig


def build_info() -> dict:
    """What the graph was built from: ``starlayer_version``, ``commit``, ``built`` (UTC), ``triples``, ``named_graphs``."""
    return json.loads((_HERE / "BUILD.json").read_text(encoding="utf-8"))


def load():
    """A ``StarLayerDataset`` (``default_union=True``) holding the whole graph."""
    from starlayer import StarLayerDataset

    kg = StarLayerDataset(default_union=True)
    kg.parse(str(path()), format="trig12")
    return kg
