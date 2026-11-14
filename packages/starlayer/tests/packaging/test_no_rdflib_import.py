"""No ``import rdflib`` (or a reasoner) anywhere in the ``starlayer`` package.

The terms are pyoxigraph terms and the graphs are Oxigraph-backed (``StarLayerGraph``). rdflib, ``owlrl`` and the OWL-DL engines live in
the ``starlayer-reasoning`` package, which the core reaches only through ``starlayer.graph.entailment.infer._reasoning``. The one
exception is the rdflib conversion (``graph/rdflib_bridge.py`` and ``graph/rdflib_model/``): it imports rdflib inside its functions,
and ``StarLayerGraph.from_rdflib`` / ``to_rdflib`` reach it only when called. This test walks the AST of every other module
(function-level imports included) and fails on any import of them.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_FOREIGN = {"rdflib", "owlrl", "owlready2", "rustdl", "oxrdflib"}

PACKAGE = Path(__file__).resolve().parents[2] / "starlayer"
#: the modules that hold the rdflib conversion; they import rdflib inside functions
CONVERSION = {PACKAGE / "graph" / "rdflib_bridge.py", *(PACKAGE / "graph" / "rdflib_model").glob("*.py")}
FILES = sorted(p for p in PACKAGE.rglob("*.py") if p not in CONVERSION)


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
    assert rdflib_imports(path.read_text()) == [], f"{path.name} imports rdflib or a reasoner: that belongs in the rdflib conversion (graph/rdflib_bridge.py) or starlayer-reasoning"


def test_the_detector_catches_each_import_form():
    assert rdflib_imports("import rdflib") == [1]
    assert rdflib_imports("def f():\n    from rdflib.namespace import RDF\n") == [2]
    assert rdflib_imports("from rdflib import Graph") == [1]
    assert rdflib_imports("import pyoxigraph\nfrom starlayer.shacl.engine import terms") == []
