"""starlayer.codekg.extractor.nesting - the dotted-nesting-path convention
shared between ``visitor.py`` (per-file extraction) and ``symbol_index.py``
(the whole-project pre-pass) - factored out here, not defined in either
one and imported by the other, since those two modules otherwise form a
genuine import cycle (``symbol_index`` needs this to build its project-
wide index; ``visitor`` needs ``symbol_index.SymbolIndex`` as a type for
``extract_module()``'s own new parameter).

Two functions:

- ``dotted_nesting(prefix, name)`` - join one more name onto a nesting
  path.
- ``collect_local_classes(body, ...)`` - pre-pass walk recording every
  local class's bare name -> full nesting path, before any real
  extraction/indexing happens, so a forward reference (an annotation, or a
  base class, naming a class defined later in the same file) still
  resolves correctly.
"""

from __future__ import annotations

import ast


def dotted_nesting(nesting_prefix: str, name: str) -> str:
    return f"{nesting_prefix}.{name}" if nesting_prefix else name


def collect_local_classes(
    body: list[ast.stmt],
    nesting_prefix: str,
    local_classes: set[str],
    class_path_by_name: dict[str, str],
) -> None:
    """Pre-pass mirroring the main visit's own nesting-prefix construction
    (see ``dotted_nesting()``), run once before any triple is emitted (or,
    in ``symbol_index.py``'s case, before any index entry is recorded) so
    that an earlier definition's annotation/base-class can reference a
    class defined later in the same file."""
    for node in body:
        if isinstance(node, ast.ClassDef):
            dotted = dotted_nesting(nesting_prefix, node.name)
            local_classes.add(node.name)
            class_path_by_name.setdefault(node.name, dotted)
            collect_local_classes(node.body, dotted, local_classes, class_path_by_name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            dotted = dotted_nesting(nesting_prefix, node.name)
            collect_local_classes(node.body, dotted, local_classes, class_path_by_name)
