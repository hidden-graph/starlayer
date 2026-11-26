"""``owl:imports`` resolution of a shapes graph (SHACL 1.2 Core): the generic rule of ``starlayer.graph.imports`` (``resolve_or_raise``).

``resolve_imports(shapes_graph, loader, ignore_imports)`` returns the graph to validate against. The caller's graph is
never modified: the result is the caller's graph itself when nothing is added (a ``StarLayerGraph``), else a new ``StarLayerGraph`` (a copy of the caller's triples plus the imported ones).

Every declared ``owl:imports`` must be satisfied (the IRI is a subject of the resulting graph, or a built-in ontology: ``sh:``, SHACL UI,
SHACL-SHACL, SKOS) or the call raises ``ExecutionError`` kind ``"import"`` with the IRIs on ``error.unresolved``: no loader, a loader that
returns ``None``, or one that returns a graph without the IRI as a subject. A loader that raises is wrapped in the same error. An
``owl:imports`` object that is not an IRI is a ``ShapeCompileError`` (the shapes graph is wrong). ``ignore_imports=True`` loads and checks
nothing. A fetched graph is never fetched again (cycles end; a versioned and an unversioned name of one module are one fetch), and
further imports are read from every ``owl:imports`` triple of a fetched graph, whatever its subject.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from starlayer.errors import ShapeCompileError
from starlayer.graph.imports import (
    SHACL_VOCABULARY,
    builtin_import_keys,
    is_builtin_import,
    resolve_or_raise,
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
    return ShapeCompileError(f"owl:imports needs an IRI, not {text(term)}", context=f"owl:imports {text(term)}")


def resolve_imports(
    shapes_graph: Any, loader: Loader | None = None, ignore_imports: bool = False, *, shapes_graph_loader: Loader | None = None
) -> Any:
    """The shapes graph extended with its ``owl:imports`` closure (see the module docstring). Never mutates its input."""
    loader = loader if loader is not None else shapes_graph_loader  # (``shapes_graph_loader``: the validate() spelling)
    shapes_graph = engine_view(shapes_graph, "shapes graph")
    imported = resolve_or_raise(
        shapes_graph, loader, ignore_imports,
        view=lambda g: engine_view(g, "imported graph"),  # a loader may return a StarLayerGraph or StarLayerDataset, not an rdflib graph
        malformed=_malformed, loader_name="shapes_graph_loader",
    )
    delta = [t for t in imported if t not in shapes_graph]
    if not delta:
        return shapes_graph
    result = new_graph(shapes_graph)
    result.extend(list(shapes_graph.triples((None, None, None))))
    result.extend(delta)
    return result


__all__ = ["SHACL_VOCABULARY", "builtin_import_keys", "declared_imports", "is_builtin_import", "resolve_imports"]
