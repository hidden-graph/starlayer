"""No ``import rdflib`` inside ``shacl_engine``.

The engine's terms are pyoxigraph terms and its graphs are Oxigraph-backed (``OxGraph``). The conversion to and from rdflib /
StarLayer terms lives in ``starlayer/graph/oxgraph/_rdflib_bridge.py``, which ``terms.to_engine`` / ``from_engine`` reach lazily.
This test walks the AST of every module under ``shacl_engine/`` (function-level imports included) and fails on any ``import
rdflib`` or ``from rdflib ... import``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2] / "starlayer" / "shacl_engine"
FILES = sorted(ENGINE.rglob("*.py"))


def rdflib_imports(source: str) -> list[int]:
    """The line numbers of the rdflib imports in ``source``."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import) and any(a.name.split(".")[0] == "rdflib" for a in node.names):
            found.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").split(".")[0] == "rdflib":
            found.append(node.lineno)
    return found


def test_the_scan_sees_the_engine():
    assert len(FILES) > 20


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ENGINE)))
def test_no_rdflib_import(path):
    assert rdflib_imports(path.read_text()) == [], f"{path.name} imports rdflib: use terms.py / graphs.py (pyoxigraph terms)"


def test_the_detector_catches_each_import_form():
    assert rdflib_imports("import rdflib") == [1]
    assert rdflib_imports("def f():\n    from rdflib.namespace import RDF\n") == [2]
    assert rdflib_imports("from rdflib import Graph") == [1]
    assert rdflib_imports("import pyoxigraph\nfrom starlayer.shacl_engine import terms") == []
