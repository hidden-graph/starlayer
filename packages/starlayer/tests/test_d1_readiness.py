"""D1 readiness: which live (non-test) modules still import the old rdflib-based ``StarLayerGraph`` / ``StarLayerDataset`` or the
old parsers, serializers, backends, query machinery and ``lower_rdf11``.

D1 renames ``OxGraph`` to ``StarLayerGraph`` and deletes the old classes and the modules only they use. It is a clean deletion
when nothing live imports them. This test walks every module of ``starlayer/``, ``scripts/``, ``tools/`` and
``packages/starlayer-kg`` with ``ast`` (lazy imports inside functions included; a name re-exported by a package facade is
followed) and requires the importers to be exactly ``ALLOWED`` below. It fails both ways: a new importer is a regression, and an
importer that is gone must be removed from ``ALLOWED`` so that the list shows what is left. See
``docs/working/d1-readiness.md`` for what each entry waits on.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCANNED = ("packages/starlayer/starlayer", "scripts", "tools", "packages/starlayer-kg")

# The modules D1 deletes (or renames over), and the package prefixes everything under which goes with them, minus ``KEPT``.
OLD_MODULES = frozenset({
    "starlayer.graph.graph.starlayer_graph",
    "starlayer.graph.graph.starlayer_dataset",
    "starlayer.graph.graph._rdflib_inherited_contract",
    "starlayer.graph.graph.prefixes",
    "starlayer.sparql.lower_rdf11",
    "starlayer.sparql.entailment_rdf",
    "starlayer.sparql.entailment_rdfs",
})
OLD_PACKAGES = (
    "starlayer.graph.parsers.",
    "starlayer.graph.serializers.",
    "starlayer.graph.backends.",
    "starlayer.graph.query.",
)
KEPT = frozenset({
    "starlayer.graph.parsers.manchester_parser",
    "starlayer.graph.parsers.errors",
    "starlayer.graph.serializers.manchester",
    "starlayer.graph.backends._versions",
})
# Package ``__init__`` modules that re-export the old classes; importing the class from one of them counts.
FACADES = frozenset({
    "starlayer",
    "starlayer.graph",
    "starlayer.graph.graph",
    "starlayer.graph.query",
    "starlayer.graph.parsers",
    "starlayer.graph.serializers",
    "starlayer.graph.backends",
})
OLD_NAMES = frozenset({"StarLayerGraph", "StarLayerDataset"})

#: module (or script path) -> what it still imports and why D1 has to touch it
ALLOWED: dict[str, str] = {
    "starlayer": "facade: re-exports StarLayerGraph / StarLayerDataset; D1 points the names at OxGraph / OxDataset",
    "starlayer.graph": "facade: re-exports the old classes, `used_prefixes`, the rdflib query patches and the old `prepareQuery` family; D1 rewrites it",
    "starlayer.graph.graph": "facade: re-exports the old classes; D1 rewrites it",
    "starlayer.graph.query": "facade: re-exports `parseQuery` / `prepareQuery` / ... from `sparql_api` (rdflib engine); deleted with the package",
    "starlayer.graph.serializers": "facade: re-exports the hand-written Turtle / N-Triples / RDF-XML / TriG writers; deleted with them",
    "starlayer.graph.oxgraph._rdflib_bridge": "`starlayer_graph()` builds an old-style graph for `oxgraph/helpers/shapes.py` (derive_shape); "
    "goes when `shape_derivation` is ported (branch mig-small-ports)",
}


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


def _is_old(module: str) -> bool:
    if module in KEPT:
        return False
    return module in OLD_MODULES or module.startswith(OLD_PACKAGES)


def old_imports(path: Path) -> set[str]:
    """What ``path`` imports from the old machinery, as dotted names."""
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
            if _is_old(module):
                found.add(module)
            elif module in FACADES:
                found.update(f"{module}.{a.name}" for a in node.names if a.name in OLD_NAMES or _is_old(f"{module}.{a.name}"))
        elif isinstance(node, ast.Import):
            found.update(a.name for a in node.names if _is_old(a.name))
    return found


def live_importers() -> dict[str, set[str]]:
    """Every live module (or script path) that imports the old machinery, with what it imports."""
    out: dict[str, set[str]] = {}
    for base in SCANNED:
        for path in sorted((REPO / base).rglob("*.py")):
            name = _module_name(path)
            if name is not None and _is_old(name) and name not in KEPT:
                continue  # an old module may import other old modules: it goes with them
            found = old_imports(path)
            if found:
                out[name or str(path.relative_to(REPO))] = found
    return out


def test_only_the_allowed_modules_import_the_old_classes_and_modules() -> None:
    importers = set(live_importers())
    new = sorted(importers - set(ALLOWED))
    gone = sorted(set(ALLOWED) - importers)
    assert not new, f"a live module imports the old graph machinery (D1 needs it gone, or add it to ALLOWED with the reason): {new}"
    assert not gone, f"these no longer import the old graph machinery: remove them from ALLOWED: {gone}"


def test_the_scan_sees_the_old_importers_it_is_meant_to_find(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "from starlayer.graph import StarLayerGraph\n"
        "def f():\n    from starlayer.graph.parsers.turtle_parser import _join\n"
        "from starlayer.graph.parsers.manchester_parser import parse_manchester\n"
        "from starlayer.graph.oxgraph import OxGraph\n",
        encoding="utf-8",
    )
    assert old_imports(sample) == {"starlayer.graph.StarLayerGraph", "starlayer.graph.parsers.turtle_parser"}
