from __future__ import annotations

from pathlib import Path

_SHAPES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "shapes"


def load_shape(name: str) -> str:
    return (_SHAPES_DIR / name).read_text(encoding="utf-8")
