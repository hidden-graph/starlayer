"""``owl_imports``, ``has_import_locally``, ``resolve_imports`` and ``can_resolve_import``: the ``owl:imports`` closure of a graph.

Ported from ``StarLayerGraph``. The loader maps an import IRI (a ``NamedNode``) to a graph, or ``None``; it may return an
``StarLayerGraph`` / ``StarLayerDataset`` or any object with ``triples(pattern)`` (an old ``StarLayerGraph``'s terms are converted).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pyoxigraph as ox

from starlayer.graph.oxgraph import terms

OWL = "http://www.w3.org/2002/07/owl#"
OWL_IMPORTS = ox.NamedNode(OWL + "imports")
OWL_VERSION_IRI = ox.NamedNode(OWL + "versionIRI")
VALID_MODES = frozenset({"full", "delta", "in-place"})


def can_resolve_import(iri: Any, *, loader: Callable[[Any], Any | None]) -> bool:
    """Whether ``loader(iri)`` returns a graph (it is called once; there is no cheaper way to ask)."""
    return loader(iri) is not None


def owl_imports(g: Any) -> tuple[Any, ...]:
    """The objects of the graph's own ``owl:imports`` triples, deduplicated, in first-seen order. Resolves nothing."""
    return tuple(dict.fromkeys(o for _, _, o in g.triples((None, OWL_IMPORTS, None))))


def has_import_locally(g: Any, iri: Any) -> bool:
    """True iff ``iri`` already has a triple as subject in the graph (its content is co-located, no loader needed)."""
    return next(iter(g.triples((terms.term(iri), None, None))), None) is not None


def _triples(x: Any, pattern: tuple = (None, None, None)) -> list[tuple[Any, Any, Any]]:
    return [(terms.term(s), terms.term(p), terms.term(o)) for s, p, o in x.triples(pattern)]


def resolve_imports(g: Any, *, loader: Callable[[Any], Any | None] | None = None, mode: str = "full", target_graph: Any = None) -> Any:
    """Follow the graph's ``owl:imports`` transitively and merge the result. ``mode`` is "full" (a new graph: self plus the
    imports), "delta" (a new graph with only the triples self lacks) or "in-place" (add the delta to self). Cycles and a
    versioned/unversioned pair of the same module are fetched once. An import that is already local, or that ``loader``
    cannot resolve (or ``loader=None``), is skipped."""
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(VALID_MODES)}, got {mode!r}")
    if mode == "in-place" and target_graph is not None:
        raise ValueError("target_graph is meaningless with mode='in-place' - it mutates self directly.")

    fetched: set = set()
    imported_canonical: set = set()
    all_imported: set = set()
    pending = list(owl_imports(g))
    while pending:
        target_iri = pending.pop(0)
        if target_iri in fetched:
            continue
        fetched.add(target_iri)
        if has_import_locally(g, target_iri) or loader is None:
            continue
        imported = loader(target_iri)
        if imported is None:
            continue
        canonical_id = next((s for s, _, o in _triples(imported, (None, OWL_VERSION_IRI, None)) if o == target_iri), target_iri)
        if canonical_id in imported_canonical:
            continue
        imported_canonical.add(canonical_id)
        fetched.add(canonical_id)
        all_imported.update(_triples(imported))
        for _, _, next_iri in _triples(imported, (None, OWL_IMPORTS, None)):
            if next_iri not in fetched:
                pending.append(next_iri)

    delta = all_imported - set(g.triples())
    if mode == "in-place":
        g.extend(delta)
        return g
    if mode == "delta":
        if target_graph is None:
            result = g.empty_like()
        elif hasattr(target_graph, "extend") and hasattr(target_graph, "store"):
            result = target_graph
        else:
            raise TypeError(f"resolve_imports() target_graph must be an StarLayerGraph or StarLayerDataset, not {type(target_graph).__name__}.")
        result.extend(delta)
        return result
    if target_graph is None:
        from starlayer.graph.oxgraph.core import StarLayerGraph

        target_graph = StarLayerGraph(prefixes=dict(g.prefixes))
    elif not (hasattr(target_graph, "extend") and hasattr(target_graph, "store")):
        raise TypeError(f"resolve_imports() target_graph must be an StarLayerGraph or StarLayerDataset, not {type(target_graph).__name__}.")
    target_graph.extend(list(g.triples()) + list(delta))
    return target_graph
