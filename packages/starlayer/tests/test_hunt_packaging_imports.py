"""Packaging, extras, import hygiene, CI definitions and the docs that describe them must agree with the code."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "packages" / "starlayer"
WORKFLOWS = ROOT / ".github" / "workflows"


def test_future_enhancements_widget_snippet_runs() -> None:
    """The maintainer snippet that regenerates the 04d appendix imported a name starlayer.graph does not export."""
    text = (PACKAGE / "docs" / "future_enhancements.md").read_text()
    after = text[text.index("Snippet that produced the 04d appendix tables"):]
    code = re.search(r"```python\n(.*?)```", after, re.S).group(1)
    namespace: dict = {}
    exec(compile(code, "future_enhancements.md", "exec"), namespace)
    assert (namespace["n_editors"], namespace["n_viewers"]) == (16, 10)
    assert "shui:AutoCompleteEditor" in namespace["editor_table"]


def _import_file(path: Path):
    spec = importlib.util.spec_from_file_location("hunt_bench_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    return module


def _test_marker_names() -> set[str]:
    names: set[str] = set()
    for f in (PACKAGE / "tests").rglob("*.py"):
        names.update(re.findall(r"pytest\.mark\.(\w+)", f.read_text()))
    return names
