"""starlayer.codekg.extractor.nesting - the dotted-nesting-path convention
shared between ``visitor.py`` (per-file extraction) and ``symbol_index.py``
(the whole-project pre-pass) - factored out here, not defined in either
one and imported by the other, since those two modules otherwise form a
genuine import cycle (``symbol_index`` needs this to build its project-
wide index; ``visitor`` needs ``symbol_index.SymbolIndex`` as a type for
``extract_module()``'s own new parameter).

Three functions:

- ``namedtuple_definition(node)`` - recognize ``Name = namedtuple("Name", [...])`` (or
  ``typing.NamedTuple``'s functional form) as a class definition.

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


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def namedtuple_definition(node: ast.stmt) -> tuple[str, list[str], dict[str, str]] | None:
    """``(class_name, field_names, default_text_by_field)`` when ``node`` is a functional named-tuple definition
    (``Name = namedtuple("Name", ["a", "b"], defaults=[None])``, ``collections.namedtuple`` or
    ``typing.NamedTuple`` spelled the same way), else ``None``.

    The class is named after the assignment target, which is what code imports and calls. A field list that
    cannot be read statically (not a literal list, tuple or string) gives an empty field list, so the class is
    still recorded. Defaults apply to the last fields, as ``namedtuple`` does.
    """
    if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
        return None
    call = node.value
    if not isinstance(call, ast.Call) or _call_name(call.func) not in ("namedtuple", "NamedTuple"):
        return None
    fields_node = call.args[1] if len(call.args) > 1 else next((k.value for k in call.keywords if k.arg == "field_names"), None)
    fields: list[str] = []
    if isinstance(fields_node, (ast.List, ast.Tuple)):
        for element in fields_node.elts:
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                fields.append(element.value)
            elif isinstance(element, (ast.Tuple, ast.List)) and element.elts and isinstance(element.elts[0], ast.Constant):
                fields.append(str(element.elts[0].value))  # NamedTuple("N", [("a", int)])
    elif isinstance(fields_node, ast.Constant) and isinstance(fields_node.value, str):
        fields = fields_node.value.replace(",", " ").split()
    defaults_node = next((k.value for k in call.keywords if k.arg == "defaults"), None)
    defaults: dict[str, str] = {}
    if isinstance(defaults_node, (ast.List, ast.Tuple)) and fields:
        values = [ast.unparse(e) for e in defaults_node.elts]
        for name, value in zip(fields[len(fields) - len(values) :], values, strict=False):
            defaults[name] = value
    return node.targets[0].id, fields, defaults


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
        elif (named := namedtuple_definition(node)) is not None:
            local_classes.add(named[0])
            class_path_by_name.setdefault(named[0], dotted_nesting(nesting_prefix, named[0]))
