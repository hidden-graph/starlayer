"""One name for the imports loader on every call (maintainer decision 2026-11-26): ``imports_loader=``.

``loader=`` of ``resolve_imports()`` and ``shapes_graph_loader=`` of the SHACL calls are removed with no alias, so the old
spellings may not appear in the package, the tests or the tools.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.graph import imports as graph_imports_module
from starlayer.shacl import StarShaclProcessor, apply_rules, validate, validate_each
from starlayer.sparql import srl

ROOT = Path(__file__).resolve().parents[2]  # packages/starlayer
TOOLS = ROOT.parents[1] / "tools"
OLD_SHAPES_NAME = "shapes_graph_" + "loader"  # spelled in two parts so this file does not contain it
_OLD_KEYWORD = re.compile(r"(?<![\w])loader=")


def _files():
    for base in (ROOT / "starlayer", ROOT / "tests", TOOLS):
        for path in base.rglob("*"):
            if path.suffix in {".py", ".md", ".ttl"} and "__pycache__" not in path.parts and path != Path(__file__).resolve():
                yield path


def test_the_old_shapes_graph_loader_name_is_left_nowhere_in_the_package_the_tests_or_the_tools():
    found = [str(path.relative_to(ROOT.parents[1])) for path in _files() if OLD_SHAPES_NAME in path.read_text()]
    assert not found, found


def test_the_old_loader_keyword_is_left_nowhere_in_the_package_the_tests_or_the_tools():
    found = [str(path.relative_to(ROOT.parents[1])) for path in _files() if _OLD_KEYWORD.search(path.read_text())]
    assert not found, found


@pytest.mark.parametrize(
    "function",
    [
        StarLayerGraph.resolved_imports,
        graph_imports_module.resolve_imports,
        graph_imports_module.can_resolve_import,
        validate,
        validate_each,
        apply_rules,
        StarShaclProcessor.validate,
        srl.resolve_imports,
    ],
)
def test_the_loader_parameter_is_imports_loader(function):
    parameters = inspect.signature(function).parameters
    named = {name for name in parameters if "loader" in name}
    assert named <= {"imports_loader", "kwargs", "options"}, (function, named)
    assert "imports_loader" in parameters or "kwargs" in parameters or "options" in parameters


def test_srl_resolve_imports_takes_imports_loader_by_keyword():
    ruleset = srl.parse_ruleset("PREFIX : <http://e/>\nRULE { ?x :a ?y } WHERE { ?x :b ?y }")
    assert srl.resolve_imports(ruleset, imports_loader=lambda iri: None) is not None
