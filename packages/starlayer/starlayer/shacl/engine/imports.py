"""``owl:imports`` resolution of a shapes graph (SHACL 1.2 Core): the generic rule of ``starlayer.graph.imports`` (``resolve_or_raise``).

``resolve_imports(shapes_graph, imports_loader, ignore_imports)`` returns the graph to validate against. The caller's graph is
never modified: the result is the caller's graph itself when nothing is added (a ``StarLayerGraph``), else a new ``StarLayerGraph`` (a copy of the caller's triples plus the imported ones).

The settings come from the graph itself (``StarLayerGraph.imports_loader`` / ``ignore_imports``, ``graph.imports.graph_imports``); a
``imports_loader`` or ``ignore_imports`` argument overrides them for the call. ``resolve_inputs`` does this for the three graphs of a run.

Every declared ``owl:imports`` must be satisfied (the IRI is a subject of the resulting graph, or a built-in ontology: ``sh:``, SHACL UI,
SHACL-SHACL, SKOS) or the call raises ``ExecutionError`` kind ``"import"`` with the IRIs on ``error.unresolved``: no loader, a loader that
returns ``None``, or one that returns a graph without the IRI as a subject. A loader that raises is wrapped in the same error. An
``owl:imports`` object that is not an IRI is a ``ShapeError`` (the shapes graph is wrong). ``ignore_imports=True`` loads and checks
nothing. A fetched graph is never fetched again (cycles end; a versioned and an unversioned name of one module are one fetch), and
further imports are read from every ``owl:imports`` triple of a fetched graph, whatever its subject.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from starlayer.errors import ShapeError
from starlayer.graph.imports import (
    SHACL_VOCABULARY,
    builtin_import_keys,
    is_builtin_import,
    graph_imports,
)
from starlayer.shacl.engine.graphs import new_graph
from starlayer.shacl.engine.terms import OWL, engine_view, text

Loader = Callable[[Any], Any]


def declared_imports(graph: Any) -> tuple[Any, ...]:
    """Every object of an ``owl:imports`` triple, deduplicated, in first-seen order."""
    seen: dict[Any, None] = {}
    for _, _, o in graph.triples((None, OWL.imports, None)):
        seen.setdefault(o, None)
    return tuple(seen)


def _malformed(term: Any) -> Exception:
    return ShapeError(f"owl:imports needs an IRI, not {text(term)}", context=f"owl:imports {text(term)}", kind="compile")


def _imports_of(graph: Any, imports_loader: Loader | None, ignore_imports: bool | None) -> frozenset:
    return graph_imports(
        graph, imports_loader, ignore_imports,
        view=lambda g: engine_view(g, "imported graph"),  # a loader may return a StarLayerGraph or StarLayerDataset, not an rdflib graph
        malformed=_malformed, loader_name="imports_loader",
    )


def resolve_imports(shapes_graph: Any, imports_loader: Loader | None = None, ignore_imports: bool | None = None) -> Any:
    """The shapes graph extended with its ``owl:imports`` closure (see the module docstring). Never mutates its input.
    ``imports_loader`` and ``ignore_imports`` override the graph's own settings; ``None``: the graph's."""
    shapes_graph = engine_view(shapes_graph, "shapes graph")
    imported = _imports_of(shapes_graph, imports_loader, ignore_imports)
    delta = [t for t in imported if t not in shapes_graph]
    if not delta:
        return shapes_graph
    result = new_graph(shapes_graph)
    result.extend(list(shapes_graph.triples((None, None, None))))
    result.extend(delta)
    return result


def resolve_inputs(
    data_graph: Any, shapes_graph: Any = None, ont_graph: Any = None, *, imports_loader: Loader | None = None,
    ignore_imports: bool | None = None,
) -> tuple[Any, Any]:
    """The ``owl:imports`` of the three graphs of a run, resolved or raising (``ExecutionError`` kind ``"import"``): ``(shapes, ont)`` to
    run with. ``shapes`` is ``shapes_graph`` extended with its imports (the shapes graph's import closure is part of the shapes), or, with no
    shapes graph, the data graph's own closure added to the data graph as shapes, and ``None`` when that adds nothing (the data graph is
    then the shapes graph). ``ont`` is ``ont_graph`` with its imports, and the data graph's imports too: they are visible to entailment
    only, like the ontology graph (a list of triples when anything was added to a graph; the data graph itself is never extended).
    Each graph's own ``imports_loader`` / ``ignore_imports`` apply; ``imports_loader`` and ``ignore_imports`` override them."""
    data_graph = engine_view(data_graph, "data graph")
    src = engine_view(shapes_graph, "shapes graph") if shapes_graph is not None else data_graph
    resolved = resolve_imports(src, imports_loader, ignore_imports)
    shapes = resolved if shapes_graph is not None else (resolved if resolved is not src else None)
    ont = engine_view(ont_graph, "ontology graph") if ont_graph is not None else None
    if ont is not None:
        ont = resolve_imports(ont, imports_loader, ignore_imports)
    return shapes, with_data_imports(ont, data_graph, imports_loader, ignore_imports)


def with_data_imports(ont: Any, data_graph: Any, imports_loader: Loader | None = None, ignore_imports: bool | None = None) -> Any:
    """``ont`` (an ontology graph, a list of triples or ``None``) with the triples the data graph's ``owl:imports`` load, for entailment
    only: ``ont`` itself when the data graph imports nothing, else a list of triples. Raises as ``resolve_imports`` does."""
    data_imports = _imports_of(engine_view(data_graph, "data graph"), imports_loader, ignore_imports)
    if not data_imports:
        return ont
    base = [] if ont is None else list(ont.triples((None, None, None)) if hasattr(ont, "triples") else ont)
    return list(dict.fromkeys([*base, *data_imports]))


def ignoring(ignore_imports: bool | None, *graphs: Any) -> bool:
    """Whether a run skipped imports: the call said so, or (with no say) every graph it read has the flag set."""
    if ignore_imports is not None:
        return bool(ignore_imports)
    read = [g for g in graphs if g is not None and hasattr(g, "ignore_imports")]
    return bool(read) and all(g.ignore_imports for g in read)


__all__ = ["SHACL_VOCABULARY", "builtin_import_keys", "declared_imports", "is_builtin_import", "ignoring", "resolve_imports", "resolve_inputs", "with_data_imports"]
