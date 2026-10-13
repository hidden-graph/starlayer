"""starlayer.codekg.extractor.types - annotation -> resolved Type node(s).

Implements the code-KG plan's "Type resolution" design: walk a parameter/
return annotation expression, pull out every ``Name``/``Attribute``-derived
dotted name it mentions, and resolve each one through the file's own import
table (see ``imports.py``) plus live ``importlib`` introspection to a
canonical dotted path - the same path for ``rdflib.Literal`` written
directly and for ``Literal`` imported from ``rdflib.term``, so both
converge on one real graph node instead of minting two.

Three functions:

- ``resolve_annotation_names(node)`` - every distinct type name mentioned.
- ``has_none_member(node)`` - whether the annotation is an optional union.
- ``resolve_type_name(name, import_table, local_classes)`` - one name ->
  ``(canonical_dotted_path, is_local)``.
"""

from __future__ import annotations

import ast
import builtins
import importlib
import logging

logger = logging.getLogger(__name__)


def _dotted_name(node: ast.expr) -> str | None:
    """Reconstruct a dotted name string from a pure ``Name``/``Attribute``
    chain (e.g. ``rdflib.term.Literal``), or ``None`` if ``node`` isn't one
    (e.g. it's a call, a subscript, anything else)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        if base is None:
            return None
        return f"{base}.{node.attr}"
    return None


def _is_optional_marker(dotted: str | None) -> bool:
    """True if `dotted` is exactly ``"Optional"`` or ends in ``".Optional"``
    (e.g. ``"typing.Optional"``) - the two ways a subscript's own value can
    spell ``typing.Optional``."""
    return dotted is not None and (dotted == "Optional" or dotted.endswith(".Optional"))


def _is_union_marker(dotted: str | None) -> bool:
    """Same idea as ``_is_optional_marker`` but for ``typing.Union``."""
    return dotted is not None and (dotted == "Union" or dotted.endswith(".Union"))


def resolve_annotation_names(node: ast.expr) -> list[str]:
    """Every distinct dotted type name mentioned in annotation expression
    ``node``, deduplicated (first-seen order preserved).

    Walks ``Name``, ``Attribute`` (reconstructed into a dotted chain),
    ``Subscript`` (recurses into ``.slice``), ``BinOp`` with ``BitOr``
    (``X | Y`` union syntax), and ``Tuple`` (e.g. inside
    ``tuple[str, str]``'s subscript slice). A bare ``None`` constant is
    never added as a name to resolve - see ``has_none_member`` instead.

    ``typing.Optional[X]`` is special-cased: ``Optional`` itself is never
    emitted as a name (it isn't a real type, just a wrapper) - this
    function still recurses into its slice to pick up ``X``.
    """
    names: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        if name not in seen:
            seen.add(name)
            names.append(name)

    def walk(n: ast.expr | None) -> None:
        if n is None:
            return
        if isinstance(n, ast.Name):
            add(n.id)
        elif isinstance(n, ast.Attribute):
            dotted = _dotted_name(n)
            if dotted is not None:
                add(dotted)
            else:
                walk(n.value)
        elif isinstance(n, ast.Subscript):
            value_dotted = _dotted_name(n.value)
            if _is_optional_marker(value_dotted):
                # Optional[X] - don't emit "Optional" itself, just recurse
                # into the slice to find X. (has_none_member() is what
                # records the None-member fact this implies.)
                pass
            else:
                walk(n.value)
            walk(n.slice)
        elif isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr):
            walk(n.left)
            walk(n.right)
        elif isinstance(n, ast.Tuple):
            for elt in n.elts:
                walk(elt)
        elif isinstance(n, ast.Constant):
            # A bare `None` contributes no name (see has_none_member); any
            # other constant (e.g. a string forward-reference annotation)
            # is out of scope for this function - not resolved as a name.
            pass
        else:
            # Anything else unexpected (future syntax, a weird node this
            # function doesn't specifically know about): fall back to a
            # generic child walk rather than silently dropping it.
            for child in ast.iter_child_nodes(n):
                walk(child)  # type: ignore[arg-type]

    walk(node)
    return names


def has_none_member(node: ast.expr) -> bool:
    """True if annotation expression ``node`` contains a literal ``None``
    in a top-level union position: ``X | None``, ``None | X``,
    ``Optional[X]``, or ``Union[X, None]``.

    Deliberately shallow/simple, matching the plan's "keep this simple,
    don't over-engineer" guidance: it checks the immediate union shape, not
    an arbitrarily nested one (e.g. ``list[X | None]``'s inner ``None`` is
    not a *top-level* union member of the outer annotation, and correctly
    returns ``False`` for the outer call).
    """
    if node is None:
        return False
    if isinstance(node, ast.Constant) and node.value is None:
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return has_none_member(node.left) or has_none_member(node.right)
    if isinstance(node, ast.Subscript):
        value_dotted = _dotted_name(node.value)
        if _is_optional_marker(value_dotted):
            return True
        if _is_union_marker(value_dotted):
            slice_node = node.slice
            elts = slice_node.elts if isinstance(slice_node, ast.Tuple) else [slice_node]
            return any(isinstance(elt, ast.Constant) and elt.value is None for elt in elts)
    return False


def _introspect(candidate: str) -> object:
    """Resolve dotted path ``candidate`` to a real live object via
    ``importlib``: try progressively shorter dotted prefixes as a module
    name until one actually imports, then ``getattr``-walk the remainder.

    Raises (``ImportError``/``AttributeError``) if no prefix imports at
    all, or if the remainder doesn't resolve once a module is found -
    callers are expected to catch this and fall back gracefully, per
    ``resolve_type_name``'s own contract.
    """
    parts = candidate.split(".")
    module = None
    split_index = None
    last_error: Exception | None = None

    for i in range(len(parts), 0, -1):
        module_name = ".".join(parts[:i])
        try:
            module = importlib.import_module(module_name)
            split_index = i
            break
        except ImportError as exc:
            last_error = exc
            continue

    if module is None:
        raise ImportError(f"no importable module prefix found for {candidate!r}") from last_error

    obj: object = module
    for attr in parts[split_index:]:
        obj = getattr(obj, attr)
    return obj


def resolve_type_name(name: str, import_table: dict[str, str], local_classes: set[str]) -> tuple[str, bool]:
    """Resolve one dotted type name (as returned by
    ``resolve_annotation_names``) to ``(canonical_dotted_path, is_local)``.

    Args:
        name: One dotted name, e.g. ``"URIRef"`` or ``"rdflib.Literal"``.
        import_table: This file's own ``{bound_name: dotted_path}`` table
            (see ``imports.build_import_table``).
        local_classes: Bare class names declared in the same file being
            processed - a name found here is reused as-is rather than
            re-minted as an external type.

    Returns:
        A pair: the canonical dotted path, and whether it's one of this
        project's own local classes (``True``) or an external/builtin
        type (``False``). Never raises - any introspection failure is
        logged as a warning and falls back to the best-guess candidate
        path, still with ``is_local=False``.
    """
    if "." not in name and name in local_classes:
        return (name, True)

    leftmost, _sep, rest = name.partition(".")

    if leftmost in import_table:
        mapped = import_table[leftmost]
        candidate = f"{mapped}.{rest}" if rest else mapped
    elif hasattr(builtins, leftmost):
        # A bare builtin name (e.g. "str") has no entry in any import
        # table (builtins need no import statement) - mint "builtins.X"
        # directly. A dotted name whose leftmost happens to be a builtin
        # name (exceedingly rare - builtins aren't modules) is left as-is.
        candidate = f"builtins.{name}" if "." not in name else name
    else:
        # Fallback: `name` might already be a fully-qualified dotted path
        # written directly with no import needed to look it up (e.g.
        # someone wrote `rdflib.Literal` in an annotation without ever
        # importing bare `rdflib`) - handed to introspection as-is below.
        candidate = name

    try:
        obj = _introspect(candidate)
        final_path = f"{obj.__module__}.{obj.__qualname__}"
    except Exception as exc:
        logger.warning(
            "Could not resolve type %r (candidate %r) via live introspection: %s",
            name,
            candidate,
            exc,
        )
        return (candidate, False)

    return (final_path, False)
