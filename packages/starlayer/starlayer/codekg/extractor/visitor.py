"""starlayer.codekg.extractor.visitor - the AST walker that turns one
Python module into a flat list of plain rdflib triples.

One public entry point, ``extract_module()``. Everything else here is
private plumbing shared between the class/function visiting branches
(nesting-path construction, type resolution, docstring attachment).

Defensive by construction: a single malformed construct anywhere in the
file (an annotation ``ast.unparse()`` can't handle, a base class that
resolves to garbage, a docstring that doesn't parse) is caught, logged,
and skipped - it never aborts extraction of the rest of the file. This is
what lets the extractor run unmodified against this project's own
not-yet-cleaned-up source (see ``starlayer/graph/model/__init__.py``,
``conformance.py``, ``dirlangstring.py``, ``triple.py``) in the same pass
it fully exploits the ``Args:``/``Returns:`` convention on a cleaned file.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from rdflib import Literal, URIRef
from rdflib.namespace import DCTERMS, RDF, RDFS

from starlayer.codekg import CODEKG_NS, EXTERNALTYPE_NS
from starlayer.codekg.extractor import docstrings, imports, nesting, types
from starlayer.codekg.extractor.symbol_index import SymbolIndex

logger = logging.getLogger(__name__)

SLKG = CODEKG_NS
EXT = EXTERNALTYPE_NS


class _ExtractionContext:
    """Mutable state threaded through one ``extract_module()`` call.

    ``class_path_by_name`` maps a bare local class name (as
    ``local_classes`` itself also only tracks bare names - see
    ``types.resolve_type_name()``'s own contract) to its full dotted
    nesting path (e.g. ``"Outer.Inner"``) - built by ``_collect_local_classes()``
    with the exact same nesting-prefix logic the main visit uses, so an
    annotation that resolves to a local class can be mapped back to the
    *same* IRI that class's own definition mints, even when it's nested
    and the annotation only ever spells its bare name. A same-named class
    nested at two different depths in one file is a real but rare
    ambiguity this can't disambiguate - first-seen wins, not revisited.

    ``emitted_external_types``/``emitted_external_modules`` dedupe the
    one-time descriptive triples for an ``slkg:ExternalType``/
    ``slkg:ExternalModule`` node within this one module-extraction call,
    per the plan's "only emit these descriptive triples for an external
    type ONCE per module-extraction call even if referenced multiple
    times" requirement. Across different modules a later call starts
    fresh (and re-emitting the same descriptive triples for the same
    external type from a different module is harmless - they're
    identical triples, deduplicated for real once written into an RDF
    graph).

    ``symbol_index`` is read-only here - the whole-project pre-pass
    ``symbol_index.build_symbol_index()`` already produced (see
    ``extract_module()``'s own new parameter) - used to resolve a call
    site's target function/method, including across files. Never mutated
    by anything in this module.
    """

    __slots__ = (
        "module_iri",
        "module_dotted_path",
        "file_path_literal",
        "import_table",
        "local_classes",
        "class_path_by_name",
        "triples",
        "emitted_external_types",
        "emitted_external_modules",
        "symbol_index",
    )

    def __init__(
        self,
        module_iri: URIRef,
        module_dotted_path: str,
        file_path_literal: str,
        import_table: dict[str, str],
        local_classes: set[str],
        class_path_by_name: dict[str, str],
        triples: list[tuple],
        symbol_index: SymbolIndex,
    ) -> None:
        self.module_iri = module_iri
        self.module_dotted_path = module_dotted_path
        self.file_path_literal = file_path_literal
        self.import_table = import_table
        self.local_classes = local_classes
        self.class_path_by_name = class_path_by_name
        self.triples = triples
        self.emitted_external_types: set[str] = set()
        self.emitted_external_modules: set[str] = set()
        self.symbol_index = symbol_index


def extract_module(
    path: Path,
    module_iri: URIRef,
    module_dotted_path: str,
    symbol_index: SymbolIndex | None = None,
) -> list[tuple]:
    """Extract one Python module's structure into a flat list of plain
    rdflib ``(subject, predicate, object)`` triples - not yet attached to
    any graph/context. The module's own top-of-file docstring (if any) is
    captured as ``rdfs:comment`` on the module node itself, the same
    predicate every class/function/method docstring already uses.

    Args:
        path: The ``.py`` file to parse.
        module_iri: This module's own named-graph-shaped identity (e.g.
            ``BLOB_BASE + "graph/model/encoding.py"``) - also used as the
            base for every class/function IRI minted below
            (``f"{module_iri}#{dotted_nesting_path}"``).
        module_dotted_path: This module's fully dotted import path (e.g.
            ``"starlayer.graph.model.encoding"``), used both for
            ``dcterms:identifier`` and to resolve relative imports via
            ``imports.build_import_table()``.
        symbol_index: The whole-project pre-pass result from
            ``symbol_index.build_symbol_index()``, used to resolve call
            sites (``slkg:calls``) to their target function/method,
            including ones defined in other files. ``None`` (the default)
            degrades gracefully rather than raising - every call site
            simply resolves against an empty index, so no ``slkg:calls``
            edges are emitted at all; every other extracted fact is
            unaffected. Pass the real index for a production extraction
            run (see ``build.py::refresh()``); omit it for a quick,
            single-file, call-graph-unaware extraction (e.g. in a test).

    Returns:
        A flat list of triples. Never raises - a file that fails to even
        parse returns whatever was collected before the failure (usually
        an empty list), logged as a warning rather than propagated.
    """
    triples: list[tuple] = []

    try:
        source = path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return triples

    try:
        tree = ast.parse(source, filename=str(path))
    except Exception as exc:
        logger.warning("Could not parse %s: %s", path, exc)
        return triples

    try:
        import_table = imports.build_import_table(tree, module_dotted_path)
    except Exception as exc:
        logger.warning("Could not build import table for %s: %s", path, exc)
        import_table = {}

    local_classes: set[str] = set()
    class_path_by_name: dict[str, str] = {}
    try:
        _collect_local_classes(tree.body, "", local_classes, class_path_by_name)
    except Exception as exc:
        logger.warning("Could not collect local classes for %s: %s", path, exc)

    triples.append((module_iri, RDF.type, SLKG.Module))
    triples.append((module_iri, RDFS.label, Literal(path.stem)))
    triples.append((module_iri, DCTERMS.identifier, Literal(module_dotted_path)))
    triples.append((module_iri, SLKG.filePath, Literal(str(path))))

    try:
        parsed = docstrings.parse_docstring(ast.get_docstring(tree, clean=False))
        if parsed["summary"]:
            triples.append((module_iri, RDFS.comment, Literal(parsed["summary"])))
    except Exception as exc:
        logger.warning("Could not parse module docstring for %s: %s", module_iri, exc)

    ctx = _ExtractionContext(
        module_iri=module_iri,
        module_dotted_path=module_dotted_path,
        file_path_literal=str(path),
        import_table=import_table,
        local_classes=local_classes,
        class_path_by_name=class_path_by_name,
        triples=triples,
        symbol_index=symbol_index if symbol_index is not None else SymbolIndex(),
    )

    try:
        _visit_module_imports(tree.body, module_iri, ctx)
    except Exception as exc:
        logger.warning("Could not process module-level imports for %s: %s", path, exc)

    _visit_body(tree.body, enclosing_iri=module_iri, enclosing_kind="module", nesting_prefix="", ctx=ctx)

    return triples


# ---------------------------------------------------------------------------
# First pass: nesting-path registry for every local class in the file
# ---------------------------------------------------------------------------

# _collect_local_classes()/_dotted_nesting() moved to nesting.py (2026-10-14)
# so symbol_index.py could share them without creating an import cycle
# (symbol_index needs this nesting logic; visitor needs symbol_index.SymbolIndex
# as a type) - kept as thin local aliases so every existing call site below
# (there are many) didn't need a mechanical rename.
_collect_local_classes = nesting.collect_local_classes
_dotted_nesting = nesting.dotted_nesting


# ---------------------------------------------------------------------------
# Module-level imports -> slkg:importsModule (external modules only)
# ---------------------------------------------------------------------------


def _is_internal_dotted_path(dotted: str) -> bool:
    return dotted == "starlayer" or dotted.startswith("starlayer.")


def _iter_module_level_import_nodes(body: list[ast.stmt]):
    """Yield every ``Import``/``ImportFrom`` node reachable from ``body``
    while staying at module level - descending into ``if``/``try`` blocks
    (both branches, handlers, orelse, finally) since those are still
    executed as part of module load (e.g. ``if TYPE_CHECKING:`` or a
    ``try:`` / ``except ImportError:`` fallback), but never into a
    ``FunctionDef``/``AsyncFunctionDef``/``ClassDef`` - an import nested
    inside one of those is lazy/scoped, not module-level."""
    for node in body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield node
        elif isinstance(node, ast.If):
            yield from _iter_module_level_import_nodes(node.body)
            yield from _iter_module_level_import_nodes(node.orelse)
        elif isinstance(node, ast.Try):
            yield from _iter_module_level_import_nodes(node.body)
            for handler in node.handlers:
                yield from _iter_module_level_import_nodes(handler.body)
            yield from _iter_module_level_import_nodes(node.orelse)
            yield from _iter_module_level_import_nodes(node.finalbody)


def _visit_module_imports(body: list[ast.stmt], module_iri: URIRef, ctx: _ExtractionContext) -> None:
    """Walks ``tree.body`` plus anything nested inside module-level
    ``if``/``try`` blocks (e.g. ``if TYPE_CHECKING:`` or a
    ``try:`` / ``except ImportError:`` fallback) via
    ``_iter_module_level_import_nodes()``, but never descends into a
    ``FunctionDef``/``AsyncFunctionDef``/``ClassDef`` - a nested/lazy
    import inside a function or class body deliberately gets no
    ``slkg:importsModule`` edge (see this module's own docstring and the
    plan's own "least load-bearing part of the ontology" guidance).
    Simplification, documented here: a local/internal import (dotted path
    ``"starlayer"`` or ``"starlayer.*"``) is skipped entirely rather than
    resolved to a real ``slkg:Module`` identity (that would require a
    full project-wide module map this extractor doesn't build); only
    genuinely external imports mint an ``slkg:ExternalModule`` node and
    an edge to it.
    """
    for node in _iter_module_level_import_nodes(body):
        try:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    dotted = alias.name
                    if not _is_internal_dotted_path(dotted):
                        _emit_external_module_import(dotted, module_iri, ctx)
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    # Relative import - always internal to this project.
                    continue
                if node.module and not _is_internal_dotted_path(node.module):
                    _emit_external_module_import(node.module, module_iri, ctx)
        except Exception as exc:
            logger.warning("Could not process import at line %s: %s", getattr(node, "lineno", "?"), exc)


def _emit_external_module_import(dotted: str, module_iri: URIRef, ctx: _ExtractionContext) -> None:
    ext_mod_iri = EXT[dotted]
    if dotted not in ctx.emitted_external_modules:
        ctx.emitted_external_modules.add(dotted)
        ctx.triples.append((ext_mod_iri, RDF.type, SLKG.ExternalModule))
    ctx.triples.append((module_iri, SLKG.importsModule, ext_mod_iri))


# ---------------------------------------------------------------------------
# Main recursive visit: classes and functions
# ---------------------------------------------------------------------------


def _visit_body(
    body: list[ast.stmt],
    enclosing_iri: URIRef,
    enclosing_kind: str,
    nesting_prefix: str,
    ctx: _ExtractionContext,
) -> None:
    """``enclosing_kind`` is one of ``"module"``/``"class"``/``"function"`` -
    it's the only thing that decides Method vs. Function (an immediate
    ``class`` parent) further down. Each node is extracted inside its own
    ``try``/``except`` so one malformed definition doesn't take down
    extraction of the rest of the file (or the rest of this body)."""
    for node in body:
        try:
            if isinstance(node, ast.ClassDef):
                _visit_class(node, enclosing_iri, nesting_prefix, ctx)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _visit_function(node, enclosing_iri, enclosing_kind, nesting_prefix, ctx)
        except Exception as exc:
            logger.warning(
                "Could not extract %s at line %s: %s",
                getattr(node, "name", type(node).__name__),
                getattr(node, "lineno", "?"),
                exc,
            )


def _visit_class(node: ast.ClassDef, enclosing_iri: URIRef, nesting_prefix: str, ctx: _ExtractionContext) -> None:
    dotted_nesting = _dotted_nesting(nesting_prefix, node.name)
    class_iri = URIRef(f"{ctx.module_iri}#{dotted_nesting}")

    ctx.triples.append((class_iri, RDF.type, SLKG.Class))
    ctx.triples.append((class_iri, RDFS.label, Literal(node.name)))
    ctx.triples.append((class_iri, DCTERMS.identifier, Literal(f"{ctx.module_dotted_path}.{dotted_nesting}")))
    ctx.triples.append((class_iri, SLKG.filePath, Literal(ctx.file_path_literal)))
    ctx.triples.append((class_iri, SLKG.lineStart, Literal(node.lineno)))
    if node.end_lineno is not None:
        ctx.triples.append((class_iri, SLKG.lineEnd, Literal(node.end_lineno)))
    _emit_visibility_flags(node.name, class_iri, ctx)

    ctx.triples.append((enclosing_iri, SLKG.declares, class_iri))

    try:
        parsed = docstrings.parse_docstring(ast.get_docstring(node, clean=False))
        if parsed["summary"]:
            ctx.triples.append((class_iri, RDFS.comment, Literal(parsed["summary"])))
    except Exception as exc:
        logger.warning("Could not parse docstring for class %s: %s", class_iri, exc)

    for base in node.bases:
        try:
            targets, _optional = _resolve_annotation(base, ctx)
        except Exception as exc:
            logger.warning("Could not resolve base class for %s: %s", class_iri, exc)
            targets = []
        for target in targets:
            ctx.triples.append((class_iri, RDFS.subClassOf, target))

    _emit_decorators(node.decorator_list, class_iri, ctx)

    _emit_class_attributes(node.body, class_iri, ctx)

    _visit_body(node.body, enclosing_iri=class_iri, enclosing_kind="class", nesting_prefix=dotted_nesting, ctx=ctx)


def _visit_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    enclosing_iri: URIRef,
    enclosing_kind: str,
    nesting_prefix: str,
    ctx: _ExtractionContext,
) -> None:
    dotted_nesting = _dotted_nesting(nesting_prefix, node.name)
    fn_iri = URIRef(f"{ctx.module_iri}#{dotted_nesting}")
    is_async = isinstance(node, ast.AsyncFunctionDef)
    fn_type = SLKG.Method if enclosing_kind == "class" else SLKG.Function

    ctx.triples.append((fn_iri, RDF.type, fn_type))
    ctx.triples.append((fn_iri, RDFS.label, Literal(node.name)))
    ctx.triples.append((fn_iri, DCTERMS.identifier, Literal(f"{ctx.module_dotted_path}.{dotted_nesting}")))
    ctx.triples.append((fn_iri, SLKG.filePath, Literal(ctx.file_path_literal)))
    ctx.triples.append((fn_iri, SLKG.lineStart, Literal(node.lineno)))
    if node.end_lineno is not None:
        ctx.triples.append((fn_iri, SLKG.lineEnd, Literal(node.end_lineno)))
    if is_async:
        ctx.triples.append((fn_iri, SLKG.isAsync, Literal(True)))
    _emit_visibility_flags(node.name, fn_iri, ctx)

    enclosing_class_dotted_path: str | None = None
    if fn_type == SLKG.Method:
        for flag_name, prop in (
            ("property", SLKG.isProperty),
            ("classmethod", SLKG.isClassmethod),
            ("staticmethod", SLKG.isStaticmethod),
        ):
            if _has_bare_decorator(node.decorator_list, flag_name):
                ctx.triples.append((fn_iri, prop, Literal(True)))

        # nesting_prefix, at this call, is exactly the enclosing class's
        # own dotted-nesting path (see _visit_class()'s call into
        # _visit_body() with nesting_prefix=dotted_nesting) - true even
        # when that class itself sits nested inside a function (e.g. every
        # `_build_*_component()` factory in shacl/native_components.py),
        # since the class's own nesting already folds that in.
        enclosing_class_dotted_path = f"{ctx.module_dotted_path}.{nesting_prefix}"
        _emit_override_edge(node.name, fn_iri, enclosing_class_dotted_path, ctx)

    ctx.triples.append((enclosing_iri, SLKG.declares, fn_iri))

    _emit_decorators(node.decorator_list, fn_iri, ctx)

    try:
        signature = f"def {node.name}({ast.unparse(node.args)})"
        if node.returns is not None:
            signature += f" -> {ast.unparse(node.returns)}"
        ctx.triples.append((fn_iri, SLKG.signature, Literal(signature)))
    except Exception as exc:
        logger.warning("Could not build signature for %s: %s", fn_iri, exc)

    try:
        parsed = docstrings.parse_docstring(ast.get_docstring(node, clean=False))
    except Exception as exc:
        logger.warning("Could not parse docstring for %s: %s", fn_iri, exc)
        parsed = {"summary": "", "params": {}, "returns": None}

    if parsed["summary"]:
        ctx.triples.append((fn_iri, RDFS.comment, Literal(parsed["summary"])))

    documented_params = dict(parsed["params"])
    _emit_parameters(node, fn_iri, ctx, documented_params, is_method=(enclosing_kind == "class"))

    for leftover in documented_params:
        logger.warning(
            "Docstring for %s documents parameter %r which does not appear in its signature",
            fn_iri,
            leftover,
        )

    _emit_return_value(node, fn_iri, ctx, parsed.get("returns"))

    _emit_calls(node.body, fn_iri, dotted_nesting, enclosing_class_dotted_path, ctx)

    _visit_body(node.body, enclosing_iri=fn_iri, enclosing_kind="function", nesting_prefix=dotted_nesting, ctx=ctx)


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


def _emit_decorators(decorator_list: list[ast.expr], entity_iri: URIRef, ctx: _ExtractionContext) -> None:
    for index, dec in enumerate(decorator_list):
        try:
            dec_iri = URIRef(f"{entity_iri}.decorator.{index}")
            ctx.triples.append((dec_iri, RDF.type, SLKG.Decorator))
            ctx.triples.append((dec_iri, SLKG.decoratorText, Literal(ast.unparse(dec))))
            ctx.triples.append((dec_iri, SLKG.position, Literal(index)))
            ctx.triples.append((entity_iri, SLKG.hasDecorator, dec_iri))
        except Exception as exc:
            logger.warning("Could not process decorator #%d on %s: %s", index, entity_iri, exc)


def _has_bare_decorator(decorator_list: list[ast.expr], name: str) -> bool:
    """True if decorator_list contains the decorator spelled as the bare
    name `name` (e.g. @property) - not a qualified (@functools.property) or
    aliased form. See ontology.ttl's own scope note on slkg:isProperty/
    isClassmethod/isStaticmethod."""
    return any(isinstance(dec, ast.Name) and dec.id == name for dec in decorator_list)


# ---------------------------------------------------------------------------
# Class attributes
# ---------------------------------------------------------------------------


def _emit_class_attributes(body: list[ast.stmt], class_iri: URIRef, ctx: _ExtractionContext) -> None:
    """Emit one slkg:Attribute per class-body-level ast.AnnAssign (e.g. a
    @dataclass field) - direct children of this ClassDef's own body only;
    a nested method's own local annotated assignment never reaches this
    function (_visit_body's recursion only ever hands a method's body to
    _visit_function, never back here)."""
    position = 0
    for node in body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        try:
            _emit_one_attribute(node, position, class_iri, ctx)
            position += 1
        except Exception as exc:
            logger.warning("Could not emit attribute %r on %s: %s", getattr(node.target, "id", "?"), class_iri, exc)


def _emit_one_attribute(node: ast.AnnAssign, position: int, class_iri: URIRef, ctx: _ExtractionContext) -> None:
    name = node.target.id
    attr_iri = URIRef(f"{class_iri}.attr.{name}")
    ctx.triples.append((attr_iri, RDF.type, SLKG.Attribute))
    ctx.triples.append((attr_iri, RDFS.label, Literal(name)))
    ctx.triples.append((attr_iri, SLKG.position, Literal(position)))

    if node.annotation is not None:
        try:
            ctx.triples.append((attr_iri, SLKG.annotationText, Literal(ast.unparse(node.annotation))))
        except Exception as exc:
            logger.warning("Could not unparse annotation for attribute %s: %s", attr_iri, exc)
        targets, optional = _resolve_annotation(node.annotation, ctx)
        for target in targets:
            ctx.triples.append((attr_iri, SLKG.hasType, target))
        if optional:
            ctx.triples.append((attr_iri, SLKG.optional, Literal(True)))

    if node.value is not None:
        try:
            ctx.triples.append((attr_iri, SLKG.defaultValue, Literal(ast.unparse(node.value))))
        except Exception as exc:
            logger.warning("Could not unparse default value for attribute %s: %s", attr_iri, exc)

    ctx.triples.append((class_iri, SLKG.hasAttribute, attr_iri))


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------


def _emit_parameters(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    fn_iri: URIRef,
    ctx: _ExtractionContext,
    documented_params: dict[str, str],
    is_method: bool = False,
) -> None:
    """Emit one ``slkg:Parameter`` per real formal parameter, in logical
    order (posonly, regular, vararg, kwonly, varkw). ``slkg:position`` is
    a running 0-based index across posonly+regular+kwonly only - ``*args``/
    ``**kwargs`` get no numeric position (there's no single meaningful
    index for either), simpler than inventing a sentinel value. When
    ``is_method`` is true, an unannotated ``self``/``cls`` in the very
    first positional slot is skipped entirely (no ``slkg:Parameter``, no
    position increment) - an annotated ``self``/``cls`` is kept as-is.
    """
    args = node.args
    position = 0

    positional = [(a, "posonly") for a in args.posonlyargs] + [(a, "positional") for a in args.args]
    defaults = args.defaults  # aligns to the END of posonlyargs + args
    num_no_default = len(positional) - len(defaults)
    default_by_index = {num_no_default + i: d for i, d in enumerate(defaults)}

    for i, (arg, kind) in enumerate(positional):
        if is_method and i == 0 and arg.annotation is None and arg.arg in ("self", "cls"):
            continue
        _emit_one_parameter(arg, kind, position, default_by_index.get(i), fn_iri, ctx, documented_params)
        position += 1

    if args.vararg is not None:
        _emit_one_parameter(args.vararg, "vararg", None, None, fn_iri, ctx, documented_params)

    for arg, kw_default in zip(args.kwonlyargs, args.kw_defaults):
        _emit_one_parameter(arg, "kwonly", position, kw_default, fn_iri, ctx, documented_params)
        position += 1

    if args.kwarg is not None:
        _emit_one_parameter(args.kwarg, "varkw", None, None, fn_iri, ctx, documented_params)


def _emit_one_parameter(
    arg: ast.arg,
    kind: str,
    position: int | None,
    default_node: ast.expr | None,
    fn_iri: URIRef,
    ctx: _ExtractionContext,
    documented_params: dict[str, str],
) -> None:
    try:
        param_iri = URIRef(f"{fn_iri}.param.{arg.arg}")
        ctx.triples.append((param_iri, RDF.type, SLKG.Parameter))
        ctx.triples.append((param_iri, RDFS.label, Literal(arg.arg)))
        ctx.triples.append((param_iri, SLKG.parameterKind, Literal(kind)))
        if position is not None:
            ctx.triples.append((param_iri, SLKG.position, Literal(position)))

        if arg.annotation is not None:
            try:
                ctx.triples.append((param_iri, SLKG.annotationText, Literal(ast.unparse(arg.annotation))))
            except Exception as exc:
                logger.warning("Could not unparse annotation for parameter %s: %s", param_iri, exc)
            targets, optional = _resolve_annotation(arg.annotation, ctx)
            for target in targets:
                ctx.triples.append((param_iri, SLKG.hasType, target))
            if optional:
                ctx.triples.append((param_iri, SLKG.optional, Literal(True)))

        if default_node is not None:
            try:
                ctx.triples.append((param_iri, SLKG.defaultValue, Literal(ast.unparse(default_node))))
            except Exception as exc:
                logger.warning("Could not unparse default value for parameter %s: %s", param_iri, exc)

        doc = documented_params.pop(arg.arg, None)
        if doc is not None:
            ctx.triples.append((param_iri, RDFS.comment, Literal(doc)))

        ctx.triples.append((fn_iri, SLKG.hasParameter, param_iri))
    except Exception as exc:
        logger.warning("Could not emit parameter %r on %s: %s", getattr(arg, "arg", "?"), fn_iri, exc)


# ---------------------------------------------------------------------------
# Return value
# ---------------------------------------------------------------------------


def _emit_return_value(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    fn_iri: URIRef,
    ctx: _ExtractionContext,
    returns_text: str | None,
) -> None:
    if node.returns is None and not returns_text:
        return
    try:
        ret_iri = URIRef(f"{fn_iri}.returns")
        ctx.triples.append((ret_iri, RDF.type, SLKG.ReturnValue))
        ctx.triples.append((fn_iri, SLKG.hasReturnValue, ret_iri))

        if node.returns is not None:
            try:
                ctx.triples.append((ret_iri, SLKG.annotationText, Literal(ast.unparse(node.returns))))
            except Exception as exc:
                logger.warning("Could not unparse return annotation for %s: %s", fn_iri, exc)
            targets, optional = _resolve_annotation(node.returns, ctx)
            for target in targets:
                ctx.triples.append((ret_iri, SLKG.hasType, target))
            if optional:
                ctx.triples.append((ret_iri, SLKG.optional, Literal(True)))

        if returns_text:
            ctx.triples.append((ret_iri, RDFS.comment, Literal(returns_text)))
    except Exception as exc:
        logger.warning("Could not emit return value for %s: %s", fn_iri, exc)


# ---------------------------------------------------------------------------
# Shared type resolution (parameter/return annotations and class bases alike)
# ---------------------------------------------------------------------------


def _resolve_annotation(expr: ast.expr, ctx: _ExtractionContext) -> tuple[list[URIRef], bool]:
    """Resolve one annotation/base-class expression to the list of
    ``slkg:Type``-ish node IRIs it mentions, plus whether it's an
    optional (contains a bare ``None`` union member) annotation. Never
    raises - a resolution failure for one name is logged and that one
    name simply contributes no target, rather than aborting the whole
    annotation."""
    try:
        names = types.resolve_annotation_names(expr)
    except Exception as exc:
        logger.warning("Could not walk annotation %s: %s", ast.dump(expr), exc)
        names = []

    try:
        optional = types.has_none_member(expr)
    except Exception as exc:
        logger.warning("Could not check has_none_member on %s: %s", ast.dump(expr), exc)
        optional = False

    targets: list[URIRef] = []
    for name in names:
        try:
            targets.append(_resolve_type_target(name, ctx))
        except Exception as exc:
            logger.warning("Could not resolve type %r: %s", name, exc)

    return targets, optional


def _resolve_type_target(name: str, ctx: _ExtractionContext) -> URIRef:
    """One resolved annotation name -> its node IRI, reusing this
    project's own local ``slkg:Class`` IRI when the name resolves to one
    of this file's local classes, else minting/reusing an
    ``slkg:ExternalType`` node under ``externaltype:``. See
    ``_ExtractionContext``'s own docstring for the dedup/nesting-path
    details.
    """
    canonical, is_local = types.resolve_type_name(name, ctx.import_table, ctx.local_classes)

    if is_local:
        full_path = ctx.class_path_by_name.get(canonical, canonical)
        return URIRef(f"{ctx.module_iri}#{full_path}")

    ext_iri = EXT[canonical]
    if canonical not in ctx.emitted_external_types:
        ctx.emitted_external_types.add(canonical)
        ctx.triples.append((ext_iri, RDF.type, SLKG.ExternalType))
        ctx.triples.append((ext_iri, RDFS.subClassOf, SLKG.Type))
        ctx.triples.append((ext_iri, RDFS.label, Literal(canonical.rsplit(".", 1)[-1])))
        ctx.triples.append((ext_iri, DCTERMS.identifier, Literal(canonical)))
    return ext_iri


# ---------------------------------------------------------------------------
# Visibility (slkg:isPrivate / slkg:isDunder)
# ---------------------------------------------------------------------------


def _is_dunder_name(name: str) -> bool:
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


def _is_private_name(name: str) -> bool:
    return name.startswith("_") and not _is_dunder_name(name)


def _emit_visibility_flags(name: str, entity_iri: URIRef, ctx: _ExtractionContext) -> None:
    """``slkg:isPrivate``/``slkg:isDunder`` on a Class/Function/Method,
    same "only ever asserted True" convention as ``slkg:isAsync``. A
    single leading underscore (``_foo``) and a double leading underscore
    with no matching trailing one (``__foo``, Python's own name-mangled
    form) both count as private; a dunder (``__foo__``) is its own,
    separate flag, never also marked private - the two are mutually
    exclusive by construction here."""
    if _is_dunder_name(name):
        ctx.triples.append((entity_iri, SLKG.isDunder, Literal(True)))
    elif _is_private_name(name):
        ctx.triples.append((entity_iri, SLKG.isPrivate, Literal(True)))


# ---------------------------------------------------------------------------
# Method overrides (slkg:overrides) - project-wide, same mechanism as
# self/cls call resolution
# ---------------------------------------------------------------------------


def _emit_override_edge(method_name: str, method_iri: URIRef, enclosing_class_dotted_path: str, ctx: _ExtractionContext) -> None:
    """Looks for ``method_name`` on each of the enclosing class's own
    bases, in declared order, via ``SymbolIndex.resolve_method_in_chain()``
    - the same project-wide, first-match-wins walk already used for
    ``self``/``cls`` call resolution. Checking the class's bases rather
    than the class itself (calling ``resolve_method_in_chain`` directly on
    ``enclosing_class_dotted_path`` would just return the class's own
    method) is what makes this an override check rather than a lookup."""
    class_info = ctx.symbol_index.classes_by_dotted_path.get(enclosing_class_dotted_path)
    if class_info is None:
        return
    try:
        base_method_iri = None
        for base_path in class_info.base_dotted_paths:
            base_method_iri = ctx.symbol_index.resolve_method_in_chain(base_path, method_name)
            if base_method_iri is not None:
                break
    except Exception as exc:
        logger.warning("Could not check override for %s: %s", method_iri, exc)
        return
    if base_method_iri is not None:
        ctx.triples.append((method_iri, SLKG.overrides, base_method_iri))


# ---------------------------------------------------------------------------
# Call graph (slkg:calls)
# ---------------------------------------------------------------------------


def _iter_nodes_stopping_at_nested_defs(node: ast.AST):
    """Every node reachable from ``node`` (``node`` itself included),
    never descending into a nested ``FunctionDef``/``AsyncFunctionDef``/
    ``ClassDef`` - that nested def gets its own, separate pass when
    ``_visit_body()`` recurses into it as its own function/class (mirrors
    ``_iter_module_level_import_nodes()``'s own "stop at a nested def
    boundary" shape). Shared by both call-site collection
    (``_iter_calls_in_function_body()``) and function-local lazy-import
    collection (``_local_import_table()``) - the identical "this
    function's own direct body, not anything nested deeper" scope applies
    to both."""
    yield node
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield from _iter_nodes_stopping_at_nested_defs(child)


def _iter_calls_in_function_body(body: list[ast.stmt]):
    for stmt in body:
        for node in _iter_nodes_stopping_at_nested_defs(stmt):
            if isinstance(node, ast.Call):
                yield node


def _local_import_table(body: list[ast.stmt], module_dotted_path: str) -> dict[str, str]:
    """This function's own direct-body lazy imports only (not a nested
    def's own further-lazy ones) - ``{bound_name: dotted_path}``, same
    shape as ``imports.build_import_table()``'s whole-file table but
    scoped to just one function, via ``imports.bindings_for_import_node()``.

    Needed because a function-local import shadows a same-named
    module-level function for the rest of that function's own body -
    confirmed via a real case in this project's own source, see this
    module's own docstring reference / ``imports.py``'s matching note."""
    table: dict[str, str] = {}
    for stmt in body:
        for node in _iter_nodes_stopping_at_nested_defs(stmt):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                table.update(imports.bindings_for_import_node(node, module_dotted_path))
    return table


def _bare_name_call_candidates(module_dotted_path: str, calling_fn_nesting_path: str, name: str) -> list[str]:
    """Candidate full dotted paths for a bare ``name()`` call, innermost
    scope outward: a helper nested directly inside the calling function
    itself, then each progressively-shallower enclosing scope (e.g. a
    sibling method on the same class), then the bare module level.
    Approximates Python's own lexical scoping for the common cases - not a
    full closure-resolution implementation (see this module's own
    docstring and the plan this was built against)."""
    candidates = []
    prefix = calling_fn_nesting_path
    while prefix:
        candidates.append(f"{module_dotted_path}.{prefix}.{name}")
        prefix = prefix.rsplit(".", 1)[0] if "." in prefix else ""
    candidates.append(f"{module_dotted_path}.{name}")
    return candidates


def _lookup_function_or_class(dotted_path: str, symbol_index: SymbolIndex) -> tuple[str, URIRef] | None:
    """One dotted path -> ``("function", iri)`` or ``("class", iri)``,
    whichever (if either) it resolves to in the project-wide index -
    classes and functions share the same ``module_dotted_path + nesting``
    keying scheme, so any dotted-path candidate worth checking against one
    is worth checking against the other too. Used wherever a bare-name or
    module-alias call site's candidate path might turn out to be a
    constructor call (``Thing()``) rather than an ordinary function call -
    see ``_resolve_call_target()``."""
    target = symbol_index.functions_by_dotted_path.get(dotted_path)
    if target is not None:
        return "function", target
    class_info = symbol_index.classes_by_dotted_path.get(dotted_path)
    if class_info is not None:
        return "class", class_info.iri
    return None


def _resolve_call_target(
    call: ast.Call,
    ctx: _ExtractionContext,
    calling_fn_nesting_path: str,
    enclosing_class_dotted_path: str | None,
    local_import_table: dict[str, str],
) -> tuple[str, URIRef] | None:
    """One call site's target - ``("function", iri)`` for an ordinary
    function/method call (emits ``slkg:calls``), ``("class", iri)`` for a
    constructor call (emits ``slkg:instantiates`` instead - see
    ``_emit_calls()``), or ``None`` if it can't be resolved with
    confidence. See this module's own docstring/the plan this was built
    against for the exact resolution order and what's deliberately never
    guessed at (a call through a plain local variable, a computed/dynamic
    call, anything on an unresolvable expression).

    ``local_import_table`` (this one calling function's own direct-body
    lazy imports - see ``_local_import_table()``) is checked BEFORE the
    same-file nesting candidates / the whole-file ``ctx.import_table`` -
    a function-local import shadows a same-named module-level function
    for the rest of that function's own body, so it has to win even
    though the same-file nesting walk would otherwise find a same-named
    match first. Confirmed as a real, not hypothetical, case in this
    project's own source (``shacl/validator.py::_default_validate()``
    does ``from pyshacl import validate`` then calls bare ``validate(...)``
    - genuinely pySHACL's function, not this module's own same-named
    ``validate()``, even though both exist in the same file)."""
    func = call.func

    if isinstance(func, ast.Name):
        name = func.id
        local_target = local_import_table.get(name)
        if local_target is not None:
            return _lookup_function_or_class(local_target, ctx.symbol_index)
        for candidate in _bare_name_call_candidates(ctx.module_dotted_path, calling_fn_nesting_path, name):
            found = _lookup_function_or_class(candidate, ctx.symbol_index)
            if found is not None:
                return found
        import_target = ctx.import_table.get(name)
        if import_target is not None:
            return _lookup_function_or_class(import_target, ctx.symbol_index)
        return None

    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        base_name = func.value.id
        attr = func.attr

        if base_name in ("self", "cls") and enclosing_class_dotted_path is not None:
            method_iri = ctx.symbol_index.resolve_method_in_chain(enclosing_class_dotted_path, attr)
            return ("function", method_iri) if method_iri is not None else None

        if base_name in ctx.local_classes:
            full_nesting = ctx.class_path_by_name.get(base_name, base_name)
            class_path = f"{ctx.module_dotted_path}.{full_nesting}"
            method_iri = ctx.symbol_index.resolve_method_in_chain(class_path, attr)
            return ("function", method_iri) if method_iri is not None else None

        base_path = local_import_table.get(base_name, ctx.import_table.get(base_name))
        if base_path is not None:
            class_info = ctx.symbol_index.classes_by_dotted_path.get(base_path)
            if class_info is not None:
                # base_name is itself a class (e.g. "from .mod import
                # SomeClass" then "SomeClass.classmethod()") - a method
                # dispatch on that class, same as the local_classes branch
                # above, never a constructor call for base_path itself.
                method_iri = class_info.methods.get(attr)
                return ("function", method_iri) if method_iri is not None else None
            return _lookup_function_or_class(f"{base_path}.{attr}", ctx.symbol_index)

        return None

    # Anything else (a call through a plain local variable, a call on the
    # result of another call/subscript, etc.) - no type inference here,
    # never guess.
    return None


def _emit_calls(
    body: list[ast.stmt],
    fn_iri: URIRef,
    calling_fn_nesting_path: str,
    enclosing_class_dotted_path: str | None,
    ctx: _ExtractionContext,
) -> None:
    try:
        local_import_table = _local_import_table(body, ctx.module_dotted_path)
    except Exception as exc:
        logger.warning("Could not build local import table for %s: %s", fn_iri, exc)
        local_import_table = {}
    for call in _iter_calls_in_function_body(body):
        try:
            found = _resolve_call_target(call, ctx, calling_fn_nesting_path, enclosing_class_dotted_path, local_import_table)
        except Exception as exc:
            logger.warning("Could not resolve call at line %s in %s: %s", getattr(call, "lineno", "?"), fn_iri, exc)
            continue
        if found is not None:
            kind, target = found
            predicate = SLKG.instantiates if kind == "class" else SLKG.calls
            ctx.triples.append((fn_iri, predicate, target))
