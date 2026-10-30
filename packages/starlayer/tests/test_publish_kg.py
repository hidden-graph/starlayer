"""The starlayer-kg data package and scripts/publish_kg.py: the package reads what the release script writes, and the
two versions stay equal."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages/starlayer-kg"))


def test_versions_of_the_library_and_the_data_package_are_equal() -> None:
    import publish_kg

    assert publish_kg._version(ROOT / "packages/starlayer-kg/pyproject.toml") == publish_kg._version(ROOT / "pyproject.toml")


def test_source_checkout_has_no_graph_and_says_how_to_get_one(monkeypatch, tmp_path) -> None:
    import starlayer_kg

    monkeypatch.setattr(starlayer_kg, "_HERE", tmp_path)
    with pytest.raises(FileNotFoundError, match="pip install starlayer-kg"):
        starlayer_kg.path()


def test_load_and_build_info_read_what_the_release_script_writes(monkeypatch, tmp_path) -> None:
    import starlayer_kg

    (tmp_path / "starlayer-kg.trig").write_text(
        '@prefix ex: <http://example.org/> .\nex:g { ex:a ex:p "x" . }\n', encoding="utf-8"
    )
    info = {"starlayer_version": "0.1.0", "commit": "abc", "built": "2026-10-30T00:00:00Z", "triples": 1, "named_graphs": 1}
    (tmp_path / "BUILD.json").write_text(json.dumps(info), encoding="utf-8")
    monkeypatch.setattr(starlayer_kg, "_HERE", tmp_path)
    assert starlayer_kg.build_info() == info
    assert len(starlayer_kg.load()) == 1
