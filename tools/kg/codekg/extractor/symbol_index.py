"""codekg.extractor.symbol_index - a whole-project pre-pass that
resolves every function/method/class to its canonical dotted path and node
IRI, before any single file's own call sites are extracted.

``visitor.extract_module()`` processes one file at a time, with no view of
anything else in the project - that's sufficient for a function's own
shape (parameters, types, docstring), but not for resolving a call to a
function defined in a *different* file, or a ``self.foo()`` call whose
target is declared on a base class defined elsewhere. This module exists
to close exactly that gap: ``build_symbol_index()`` walks every target
file's AST once, structurally only (no triples emitted here - that's
still ``visitor.py``'s job), and returns a ``SymbolIndex`` two later
per-file extraction passes can consult.

Not real cross-package name resolution in the general Python sense - it
reuses this project's own existing annotation-resolution machinery
(``types.resolve_type_name()``, the same one ``visitor._resolve_annotation()``
already uses for parameter/return/base-class types) applied to base-class
expressions, and the live-``importlib``-introspection fallback that
machinery already has happens to also correctly resolve a cross-module
*local* base class (e.g. a class in ``validator.py`` subclassing one from
``adapters.py``) to its real ``module.ClassName`` dotted path - not just
external/stdlib ones. That's what makes a whole-project index possible
without a second, separate resolver: a base class's resolved canonical
path either lands inside this index (a real project class) or it doesn't
(external/unresolvable) - the index's own absence-is-the-answer lookup is
the only "is this external" check needed, no separate flag required.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path

from codekg import BLOB_BASE, TESTS_BLOB_BASE
from codekg.extractor import imports, nesting, types
from rdflib import URIRef

logger = logging.getLogger(__name__)


@dataclass
class ClassInfo:
    """One project class's own directly-declared methods and its bases'
    resolved dotted paths (declaration order) - enough to walk a
    ``self``/``cls`` method lookup up the inheritance chain without a
    second resolver. Not real C3 MRO: ``SymbolIndex.resolve_method_in_chain()``
    walks ``base_dotted_paths`` depth-first, first match wins - see this
    module's own docstring and the plan this was built against for why
    that's an accepted simplification, not an oversight."""

    iri: URIRef
    methods: dict[str, URIRef] = field(default_factory=dict)
    base_dotted_paths: list[str] = field(default_factory=list)


@dataclass
class SymbolIndex:
    """The whole-project lookup ``build_symbol_index()`` produces.

    ``functions_by_dotted_path`` covers every module-level function and
    every method (a method's dotted path already includes its class's own
    nesting, e.g. ``"starlayer.shacl.validator.StarShaclSchema.validate"``,
    so no separate method table is needed for bare-name/module-alias call
    resolution - only ``self``/``cls`` resolution needs ``classes_by_dotted_path``'s
    own per-class method view).
    """

    functions_by_dotted_path: dict[str, URIRef] = field(default_factory=dict)
    classes_by_dotted_path: dict[str, ClassInfo] = field(default_factory=dict)

    def resolve_method_in_chain(
        self, class_dotted_path: str, method_name: str, _seen: set[str] | None = None
    ) -> URIRef | None:
        """``class_dotted_path``'s own method named ``method_name``, or the
        first same-named method found walking its bases in declared order,
        depth-first (not real C3 MRO - see ``ClassInfo``'s own docstring).
        ``None`` if ``class_dotted_path`` isn't itself in this index (an
        external/unresolvable class) or no match is found anywhere in the
        chain. ``_seen`` guards against a pathological base-class cycle;
        never pass it explicitly - it's populated by the recursive calls
        this function makes to itself.
        """
        if _seen is None:
            _seen = set()
        if class_dotted_path in _seen:
            return None
        _seen.add(class_dotted_path)

        info = self.classes_by_dotted_path.get(class_dotted_path)
        if info is None:
            return None
        if method_name in info.methods:
            return info.methods[method_name]
        for base in info.base_dotted_paths:
            found = self.resolve_method_in_chain(base, method_name, _seen)
            if found is not None:
                return found
        return None


#: ``(subdirectory-under-repo_root, dotted-path-prefix, blob-base)`` for
#: every root this extractor knows how to identify a module under - tried
#: in order, first match wins. Source comes first deliberately: every
#: ``packages/starlayer/starlayer/...`` path is also, trivially, under
#: ``packages/starlayer/...`` so the two could never be confused the other
#: way, but keeping the more specific root first is the clearer intent.
_KNOWN_ROOTS: tuple[tuple[str, str, str], ...] = (
    ("packages/starlayer/starlayer", "starlayer", BLOB_BASE),
    ("packages/starlayer/tests", "tests", TESTS_BLOB_BASE),
)


def resolve_root(path: Path, repo_root: Path) -> tuple[Path, str, str] | None:
    """Which of this extractor's known roots ``path`` falls under.

    Args:
        path: The ``.py`` file to place.
        repo_root: The repository root.

    Returns:
        ``(root_path, dotted_prefix, blob_base)`` for the first matching
        root, or ``None`` if ``path`` isn't under any of them.
    """
    for rel_root, dotted_prefix, blob_base in _KNOWN_ROOTS:
        root_path = repo_root / rel_root
        try:
            path.relative_to(root_path)
        except ValueError:
            continue
        return root_path, dotted_prefix, blob_base
    return None


def module_identity(path: Path, repo_root: Path) -> tuple[URIRef, str]:
    """``(module_iri, module_dotted_path)`` for one file under any of this
    extractor's known roots (see ``resolve_root()``) - the identical rule
    ``build.py::refresh()`` already applies per target, factored out here
    so the two don't carry two independent copies that could drift apart.

    Args:
        path: The ``.py`` file.
        repo_root: The repository root.

    Returns:
        The module's blob-URL IRI and its fully dotted import path (the
        dotted path is a synthetic, consistently-applied convention for
        anything under ``packages/starlayer/tests/`` specifically, not a
        claim that it's *really* importable that way - several of that
        tree's own subdirectories have no ``__init__.py``. It's still
        enough for relative-import resolution within the tests tree to
        work correctly, which is all this extractor needs from it).

    Raises:
        ValueError: ``path`` isn't under any known root (the same
            exception ``resolve_root()``'s own failed
            ``Path.relative_to()`` calls raise internally) - callers
            processing a mix of known-root paths and anything else need
            to catch this themselves (``build_symbol_index()`` does).
    """
    resolved = resolve_root(path, repo_root)
    if resolved is None:
        raise ValueError(f"{path} is not under any known extraction root")
    root_path, dotted_prefix, blob_base = resolved
    rel_path = path.relative_to(root_path)
    module_iri = URIRef(blob_base + str(rel_path))
    module_dotted_path = dotted_prefix + "." + str(rel_path.with_suffix("")).replace("/", ".")
    return module_iri, module_dotted_path


def _resolve_base_dotted_path(
    base_expr: ast.expr,
    module_dotted_path: str,
    import_table: dict[str, str],
    local_classes: set[str],
    class_path_by_name: dict[str, str],
) -> list[str]:
    """One base-class expression -> the full project-wide dotted path(s)
    it mentions (usually one name, but a base expression can be any
    annotation-shaped expression, so this reuses the same name-extraction
    ``types.resolve_annotation_names()`` already provides for parameter/
    return annotations, rather than assuming a bare ``Name``/``Attribute``).

    A same-file local base name resolves via ``class_path_by_name`` to its
    full ``module_dotted_path``-prefixed path directly. Anything else goes
    through ``types.resolve_type_name()``'s own import-table + live-
    introspection resolution - its returned canonical path is already the
    correct full dotted path whether that turns out to be a genuine
    cross-module *local* class (introspection succeeds, resolving to e.g.
    ``starlayer.shacl.adapters.TripleTermAdapter``) or an external one
    (stdlib/third-party, or unresolvable) - this function doesn't need to
    tell those two apart itself; ``SymbolIndex``'s own lookup already does,
    simply by whether the resulting path is a key in it or not.
    """
    try:
        names = types.resolve_annotation_names(base_expr)
    except Exception as exc:
        logger.warning("Could not walk base-class expression %s: %s", ast.dump(base_expr), exc)
        return []

    paths: list[str] = []
    for name in names:
        try:
            canonical, is_local = types.resolve_type_name(name, import_table, local_classes)
        except Exception as exc:
            logger.warning("Could not resolve base class name %r: %s", name, exc)
            continue
        if is_local:
            full_nesting = class_path_by_name.get(canonical, canonical)
            paths.append(f"{module_dotted_path}.{full_nesting}")
        else:
            paths.append(canonical)
    return paths


def _index_body(
    body: list[ast.stmt],
    module_iri: URIRef,
    module_dotted_path: str,
    nesting_prefix: str,
    import_table: dict[str, str],
    local_classes: set[str],
    class_path_by_name: dict[str, str],
    index: SymbolIndex,
) -> None:
    """Recursive walk populating ``index`` from one file's already-parsed
    body - mirrors ``visitor._visit_body()``'s own nesting-prefix recursion
    (``ClassDef``/``FunctionDef``/``AsyncFunctionDef``, recursing into
    each), but records index entries instead of emitting triples."""
    for node in body:
        try:
            if isinstance(node, ast.ClassDef):
                dotted = nesting.dotted_nesting(nesting_prefix, node.name)
                full_dotted = f"{module_dotted_path}.{dotted}"
                class_iri = URIRef(f"{module_iri}#{dotted}")

                info = ClassInfo(iri=class_iri)
                for base in node.bases:
                    info.base_dotted_paths.extend(
                        _resolve_base_dotted_path(base, module_dotted_path, import_table, local_classes, class_path_by_name)
                    )
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_dotted = nesting.dotted_nesting(dotted, child.name)
                        info.methods[child.name] = URIRef(f"{module_iri}#{method_dotted}")
                index.classes_by_dotted_path[full_dotted] = info

                _index_body(node.body, module_iri, module_dotted_path, dotted, import_table, local_classes, class_path_by_name, index)
            elif (named := nesting.namedtuple_definition(node)) is not None:
                dotted = nesting.dotted_nesting(nesting_prefix, named[0])
                index.classes_by_dotted_path[f"{module_dotted_path}.{dotted}"] = ClassInfo(iri=URIRef(f"{module_iri}#{dotted}"))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                dotted = nesting.dotted_nesting(nesting_prefix, node.name)
                full_dotted = f"{module_dotted_path}.{dotted}"
                index.functions_by_dotted_path[full_dotted] = URIRef(f"{module_iri}#{dotted}")

                _index_body(node.body, module_iri, module_dotted_path, dotted, import_table, local_classes, class_path_by_name, index)
        except Exception as exc:
            logger.warning(
                "Could not index %s at line %s: %s",
                getattr(node, "name", type(node).__name__),
                getattr(node, "lineno", "?"),
                exc,
            )


def build_symbol_index(target_paths: list[Path], repo_root: Path) -> SymbolIndex:
    """Walk every file in ``target_paths`` once, structurally, building one
    project-wide ``SymbolIndex`` - run before any file's own triples are
    extracted (see ``build.py::refresh()``).

    Args:
        target_paths: The same ``.py`` files a real extraction run targets.
        repo_root: The repository root (see ``module_identity()``).

    Returns:
        A ``SymbolIndex`` covering every function/method/class found.
        Never raises - a file that fails to parse, or isn't under any
        known root (see ``resolve_root()`` - this index only covers roots
        this extractor recognizes), is logged and skipped, exactly like
        ``visitor.extract_module()``'s own per-file defensiveness.
    """
    index = SymbolIndex()

    for path in target_paths:
        try:
            module_iri, module_dotted_path = module_identity(path, repo_root)
        except ValueError:
            logger.warning("Skipping %s: not under any known extraction root", path)
            continue

        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except Exception as exc:
            logger.warning("Could not read/parse %s while building the symbol index: %s", path, exc)
            continue

        try:
            import_table = imports.build_import_table(tree, module_dotted_path)
        except Exception as exc:
            logger.warning("Could not build import table for %s: %s", path, exc)
            import_table = {}

        local_classes: set[str] = set()
        class_path_by_name: dict[str, str] = {}
        try:
            nesting.collect_local_classes(tree.body, "", local_classes, class_path_by_name)
        except Exception as exc:
            logger.warning("Could not collect local classes for %s: %s", path, exc)

        _index_body(tree.body, module_iri, module_dotted_path, "", import_table, local_classes, class_path_by_name, index)

    return index
