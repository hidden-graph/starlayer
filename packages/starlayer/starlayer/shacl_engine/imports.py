"""``owl:imports`` resolution of a shapes graph (SHACL 1.2 Core), same semantics as the old validator.

``resolve_imports(shapes_graph, loader, ignore_imports)`` returns the graph to validate against. The caller's graph is
never modified: the result is the caller's graph itself when nothing is added, else a new graph (a copy of the caller's
triples plus the imported ones).

Semantics (``StarLayerGraph.resolve_imports`` and ``validate(shapes_graph_loader=, ignore_imports=)``):

* With a ``loader`` (a callable: import IRI -> graph, or ``None``), the transitive closure is followed. An import the
  loader returns ``None`` for is skipped, not an error. An import whose IRI already has triples as a subject in the
  graph is satisfied locally and never reaches the loader. ``ignore_imports`` is irrelevant when a loader is given.
* Without a loader, and not ``ignore_imports``: a declared ``owl:imports`` target that is not satisfied locally raises
  ``ValueError`` (silently skipping would make a shape that refers to the import never fire). ``ignore_imports=True``
  returns the graph unchanged.
* Cycles: an IRI already fetched is never fetched twice; a fetched graph that declares the IRI it was fetched under as
  its ``owl:versionIRI`` is identified by that graph's base IRI (the subject of the ``owl:versionIRI`` triple), so
  importing a versioned module and its unversioned base converge on one identity. Further imports are read from every
  ``owl:imports`` triple of the fetched graph, whatever its subject.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rdflib import Graph
from rdflib.namespace import OWL

Loader = Callable[[Any], Any]


def declared_imports(graph: Any) -> tuple[Any, ...]:
    """Every object of an ``owl:imports`` triple, deduplicated, in first-seen order."""
    seen: dict[Any, None] = {}
    for _, _, o in graph.triples((None, OWL.imports, None)):
        seen.setdefault(o, None)
    return tuple(seen)


def _has_subject(graph: Any, iri: Any) -> bool:
    return any(True for _ in graph.triples((iri, None, None)))


def _new_graph_like(graph: Any) -> Any:
    try:
        from starlayer.graph.graph.starlayer_graph import StarLayerGraph

        new = StarLayerGraph()
    except ImportError:  # pragma: no cover
        new = Graph()
    try:
        for prefix, ns in graph.namespaces():
            new.bind(prefix, ns)
    except AttributeError:
        pass
    return new


def resolve_imports(
    shapes_graph: Any, loader: Loader | None = None, ignore_imports: bool = False, *, shapes_graph_loader: Loader | None = None
) -> Any:
    """The shapes graph extended with its ``owl:imports`` closure (see the module docstring). Never mutates its input."""
    loader = loader if loader is not None else shapes_graph_loader  # (``shapes_graph_loader``: the validate() spelling)
    if loader is None:
        if not ignore_imports:
            missing = [o for o in declared_imports(shapes_graph) if not _has_subject(shapes_graph, o)]
            if missing:
                raise ValueError(
                    f"shacl_graph declares owl:imports {missing!r} that aren't already "
                    "locally satisfied, but no shapes_graph_loader was given to resolve them. "
                    "Pass shapes_graph_loader=... to resolve them, or ignore_imports=True if "
                    "you've already resolved them yourself (or don't need them)."
                )
        return shapes_graph

    fetched: set = set()
    canonical_seen: set = set()
    imported: set = set()
    pending = list(declared_imports(shapes_graph))
    while pending:
        iri = pending.pop(0)
        if iri in fetched:
            continue
        fetched.add(iri)
        if _has_subject(shapes_graph, iri):
            continue
        graph = loader(iri)
        if graph is None:
            continue
        canonical = next((s for s, _, o in graph.triples((None, OWL.versionIRI, None)) if o == iri), iri)
        if canonical in canonical_seen:
            continue
        canonical_seen.add(canonical)
        fetched.add(canonical)
        for t in graph:
            imported.add(t)
        for _, _, nxt in graph.triples((None, OWL.imports, None)):
            if nxt not in fetched:
                pending.append(nxt)

    delta = [t for t in imported if t not in shapes_graph]
    if not delta:
        return shapes_graph
    result = _new_graph_like(shapes_graph)
    for t in shapes_graph:
        result.add(t)
    for t in delta:
        result.add(t)
    return result


__all__ = ["declared_imports", "resolve_imports"]
