"""D1 is done: the rdflib-based ``StarLayerGraph`` / ``StarLayerDataset`` and the modules only they used are deleted.

This test keeps it that way. It requires that the modules D1 deleted do not exist, and walks every module of
``starlayer/``, ``scripts/``, ``tools/`` and ``packages/starlayer-kg`` with ``ast`` (lazy imports inside functions
included) to require that nothing imports them. ``StarLayerGraph`` / ``StarLayerDataset`` now name the Oxigraph-backed
classes of ``starlayer.graph.oxgraph.core``. See ``docs/working/d1-readiness.md``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCANNED = ("packages/starlayer/starlayer", "scripts", "tools", "packages/starlayer-kg")

#: The modules D1 deleted.
DELETED_MODULES = frozenset({
    "starlayer.graph.graph.starlayer_graph",
    "starlayer.graph.graph.starlayer_dataset",
    "starlayer.graph.graph._rdflib_inherited_contract",
    "starlayer.graph.graph.prefixes",
    "starlayer.sparql.lower_rdf11",
    "starlayer.sparql.entailment_rdf",
    "starlayer.sparql.entailment_rdfs",
    "starlayer.graph.parsers.turtle_parser",
    "starlayer.graph.parsers.syntax",
    "starlayer.graph.parsers.trig12",
    "starlayer.graph.parsers.ntriples12",
    "starlayer.graph.parsers.rdfxml12",
    "starlayer.graph.parsers.lexer",
    "starlayer.graph.parsers.faithful",
    "starlayer.graph.parsers.bnode_scope",
    "starlayer.graph.serializers.turtle12",
    "starlayer.graph.serializers.ntriples12",
    "starlayer.graph.serializers.rdfxml12",
    "starlayer.graph.serializers.trig12",
    "starlayer.graph.serializers._xml",
    "starlayer.graph.backends.native",
    "starlayer.graph.backends.skolem_semantics",
    "starlayer.graph.backends.native_oxigraph",
})
#: Packages deleted whole (``starlayer.graph.query`` held only the rdflib query machinery).
DELETED_PACKAGES = ("starlayer.graph.query",)


def _is_deleted(module: str) -> bool:
    return module in DELETED_MODULES or module == DELETED_PACKAGES[0] or module.startswith(tuple(p + "." for p in DELETED_PACKAGES))


def _module_name(path: Path) -> str | None:
    try:
        rel = path.relative_to(REPO)
    except ValueError:
        return None
    if rel.parts[:3] != ("packages", "starlayer", "starlayer"):
        return None
    parts = list(rel.with_suffix("").parts[2:])
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def deleted_imports(path: Path) -> set[str]:
    """What ``path`` imports from the deleted modules, as dotted names."""
    name = _module_name(path)
    is_package = path.name == "__init__.py"
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                if name is None:
                    continue
                parts = name.split(".")
                if not is_package:
                    parts = parts[:-1]
                parts = parts[: len(parts) - (node.level - 1)]
                module = ".".join(parts + ([module] if module else []))
            if _is_deleted(module):
                found.add(module)
            else:
                found.update(f"{module}.{a.name}" for a in node.names if _is_deleted(f"{module}.{a.name}"))
        elif isinstance(node, ast.Import):
            found.update(a.name for a in node.names if _is_deleted(a.name))
    return found


def live_importers() -> dict[str, set[str]]:
    """Every module (or script path) that imports a deleted module, with what it imports."""
    out: dict[str, set[str]] = {}
    for base in SCANNED:
        for path in sorted((REPO / base).rglob("*.py")):
            found = deleted_imports(path)
            if found:
                out[_module_name(path) or str(path.relative_to(REPO))] = found
    return out


@pytest.mark.parametrize("module", sorted(DELETED_MODULES))
def test_the_deleted_module_is_gone(module: str) -> None:
    base = REPO / "packages" / "starlayer" / Path(*module.split("."))
    assert not base.with_suffix(".py").exists(), f"{module} was deleted at D1 and must not come back"


def test_the_deleted_query_package_is_gone() -> None:
    assert not (REPO / "packages/starlayer/starlayer/graph/query").exists()


def test_nothing_imports_a_deleted_module() -> None:
    assert not live_importers()


def test_the_scan_sees_an_importer_of_a_deleted_module(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "from starlayer.graph.graph.starlayer_graph import StarLayerGraph\n"
        "def f():\n    from starlayer.graph.parsers.turtle_parser import _join\n"
        "from starlayer.graph.parsers.manchester_parser import parse_manchester\n"
        "from starlayer.graph.query import sparql_api\n"
        "from starlayer.graph import StarLayerGraph\n",
        encoding="utf-8",
    )
    assert deleted_imports(sample) == {
        "starlayer.graph.graph.starlayer_graph",
        "starlayer.graph.parsers.turtle_parser",
        "starlayer.graph.query",
    }
