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


def test_no_source_cites_removed_modules() -> None:
    for f in (PACKAGE / "starlayer").rglob("*.py"):
        text = f.read_text()
        for gone in ("starlayer.shacl.recursion", "starlayer.registry"):
            assert gone not in text, f"{f.relative_to(ROOT)} cites {gone}, which no longer exists"


def _test_marker_names() -> set[str]:
    names: set[str] = set()
    for f in (PACKAGE / "tests").rglob("*.py"):
        names.update(re.findall(r"pytest\.mark\.(\w+)", f.read_text()))
    return names


def test_ci_does_not_select_a_marker_no_test_carries() -> None:
    """`pytest -m integration` with no integration test exits 5 (nothing collected) and fails the CI job."""
    # the area markers conftest.py applies from the directory name
    applied = {"graph", "shacl", "shacl_engine", "sparql", "starontology", "codekg", "kg"}
    available = _test_marker_names() | applied
    for wf in WORKFLOWS.glob("*.yml"):
        for expr in re.findall(r'pytest [^\n]*? -m "([^"]+)"', wf.read_text()):
            if expr.startswith("not "):
                continue
            for word in re.findall(r"\w+", expr):
                if word not in ("and", "or", "not"):
                    assert word in available, f"{wf.name}: pytest -m {expr!r} selects {word!r}, which no test carries"


def test_to_rdflib_dataset_works_without_dataset_default_graph(monkeypatch) -> None:
    """rdflib 7.0 to 7.2 (allowed by the rdflib extra) have no Dataset.default_graph (new in 7.3)."""
    import warnings

    import pytest

    rdflib = pytest.importorskip("rdflib")
    from starlayer.graph import StarLayerDataset

    d = StarLayerDataset()
    d.update("INSERT DATA { <http://e/s> <http://e/p> <http://e/o> . GRAPH <http://e/g> { <http://e/a> <http://e/p> <http://e/b> } }")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if hasattr(rdflib.Dataset, "default_graph"):
            monkeypatch.delattr(rdflib.Dataset, "default_graph")
        out = d.to_rdflib()
        assert (rdflib.URIRef("http://e/s"), rdflib.URIRef("http://e/p"), rdflib.URIRef("http://e/o")) in out.default_context
        assert len(out.graph(rdflib.URIRef("http://e/g"))) == 1
