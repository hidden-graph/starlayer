"""starlayer.codekg.extractor.imports - per-file import table extraction.

One function, ``build_import_table()``: walks an already-parsed module AST
and produces a flat ``{bound_name: dotted_path}`` mapping covering every
``import``/``from ... import ...`` statement in the file - not just the
ones at module top level. This codebase's own established convention is
lazy/deferred imports inside function bodies (e.g. ``from rdflib.term
import Node`` inside a function - see
``starlayer/graph/model/encoding.py::term_key``), so a visitor that only
looked at ``tree.body`` would silently miss every name bound that way. The
resulting table is what ``types.py``'s ``resolve_type_name()`` uses to turn
a bare annotation name like ``URIRef`` into a real, canonical dotted path.
"""

from __future__ import annotations

import ast


def build_import_table(tree: ast.Module, module_dotted_path: str) -> dict[str, str]:
    """Build a flat ``{bound_name: dotted_path}`` table for every import
    statement anywhere in ``tree`` (module-level and nested inside function/
    class bodies alike).

    Args:
        tree: The module's parsed AST (``ast.parse(source)``).
        module_dotted_path: This module's own fully dotted import path
            (e.g. ``"starlayer.graph.model.encoding"``), used to resolve
            any relative (``from .x import y``) imports found inside it.

    Returns:
        A dict mapping each bound local name to the dotted path it
        resolves to. Star imports (``from x import *``) contribute no
        binding at all, since there's no single name to bind.

    Known limitation: ``ast.walk()`` traverses breadth-first, not in exact
    source order, across different nesting depths. "Later imports in
    source order override earlier ones that bind the same name" (realistic
    shadowing) holds for the overwhelmingly common case - e.g. a module-
    level import shadowed by a later module-level import, or a module-level
    import shadowed by one deferred inside a function body - but an
    adversarial case with multiple shadowing imports of the same name
    nested at different depths in a specific source order could resolve
    against which one ``ast.walk()`` happens to visit last rather than
    which one is textually last. Getting the common case right matters
    more here than handling that rare edge case exactly.
    """
    table: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    table[alias.asname] = alias.name
                else:
                    # `import a.b.c` binds just the top-level name `a` in
                    # the namespace - the dotted path it maps to is that
                    # same top-level name, not the full `a.b.c` (accessing
                    # `a.b.c` works through attribute chaining off the
                    # bound `a`, it's not a separate binding).
                    top_level = alias.name.split(".")[0]
                    table[top_level] = top_level
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                base_components = module_dotted_path.split(".")
                # Strip `level` trailing components off module_dotted_path
                # to find the base package - e.g. module_dotted_path =
                # "starlayer.graph.model.encoding", level=1 -> base package
                # "starlayer.graph.model" (strips just "encoding"); level=2
                # would strip two trailing components instead of one.
                base_components = base_components[: len(base_components) - node.level] if node.level <= len(base_components) else []
                base = ".".join(base_components)
                if node.module:
                    base = f"{base}.{node.module}" if base else node.module
            else:
                base = node.module or ""

            for alias in node.names:
                if alias.name == "*":
                    # Can't resolve a star import to a specific name - skip,
                    # don't add a binding for it.
                    continue
                bound_name = alias.asname or alias.name
                dotted_path = f"{base}.{alias.name}" if base else alias.name
                table[bound_name] = dotted_path

    return table
