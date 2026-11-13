"""No ``import rdflib`` (or a reasoner) anywhere in the ``starlayer`` package.

The terms are pyoxigraph terms and the graphs are Oxigraph-backed (``StarLayerGraph``). rdflib, ``owlrl`` and the OWL-DL engines live in
the ``starlayer-reasoning`` package, which the core reaches only through ``starlayer.graph.oxgraph.core._reasoning`` and
``starlayer.graph.oxgraph.helpers.entailment._reasoning``. This test walks the AST of every module (function-level imports included)
and fails on any import of them.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_FOREIGN = {"rdflib", "owlrl", "owlready2", "rustdl", "oxrdflib"}

PACKAGE = Path(__file__).resolve().parents[1] / "starlayer"
FILES = sorted(PACKAGE.rglob("*.py"))


def rdflib_imports(source: str) -> list[int]:
    """The line numbers of the rdflib imports in ``source``."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import) and any(a.name.split(".")[0] in _FOREIGN for a in node.names):
            found.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").split(".")[0] in _FOREIGN:
            found.append(node.lineno)
    return found


def test_the_scan_sees_the_package():
    assert len(FILES) > 100


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(PACKAGE)))
def test_no_rdflib_import(path):
    assert rdflib_imports(path.read_text()) == [], f"{path.name} imports rdflib or a reasoner: that belongs in starlayer-reasoning"


def test_the_detector_catches_each_import_form():
    assert rdflib_imports("import rdflib") == [1]
    assert rdflib_imports("def f():\n    from rdflib.namespace import RDF\n") == [2]
    assert rdflib_imports("from rdflib import Graph") == [1]
    assert rdflib_imports("import pyoxigraph\nfrom starlayer.shacl.engine import terms") == []
