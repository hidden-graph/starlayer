"""``owl:imports`` resolution of a shapes graph (SHACL 1.2 Core), same semantics as the old validator.

``resolve_imports(shapes_graph, loader, ignore_imports)`` returns the graph to validate against. The caller's graph is
never modified: the result is the caller's graph itself when nothing is added (a ``StarLayerGraph``), else a new ``StarLayerGraph`` (a copy of the caller's triples plus the imported ones).

Semantics (``StarLayerGraph.resolve_imports`` and ``validate(shapes_graph_loader=, ignore_imports=)``):

* With a ``loader`` (a callable: import IRI -> graph, or ``None``), the transitive closure is followed. An import the
  loader returns ``None`` for is skipped, not an error. An import whose IRI already has triples as a subject in the
  graph is satisfied locally and never reaches the loader, and so is an import of the SHACL vocabulary (``sh:``), which is built in. ``ignore_imports`` is irrelevant when a loader is given.
* Without a loader, and not ``ignore_imports``: a declared ``owl:imports`` target that is not satisfied locally raises
  ``ShapeError`` (silently skipping would make a shape that refers to the import never fire). ``ignore_imports=True``
  returns the graph unchanged.
* Cycles: an IRI already fetched is never fetched twice; a fetched graph that declares the IRI it was fetched under as
  its ``owl:versionIRI`` is identified by that graph's base IRI (the subject of the ``owl:versionIRI`` triple), so
  importing a versioned module and its unversioned base converge on one identity. Further imports are read from every
  ``owl:imports`` triple of the fetched graph, whatever its subject.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pyoxigraph as ox

from starlayer.errors import ShapeCompileError
from starlayer.shacl.engine.graphs import new_graph
from starlayer.shacl.engine.terms import OWL, engine_view, text

Loader = Callable[[Any], Any]

#: The SHACL vocabulary graph. Core recommends ``owl:imports sh:`` for a graph that uses ``sh:ShapeClass``, so software that does not
#: know SHACL can read the vocabulary; the engine has that vocabulary built in, so the import is satisfied without a loader.
SHACL_VOCABULARY = ox.NamedNode("http://www.w3.org/ns/shacl#")

_OWL_ONTOLOGY = "http://www.w3.org/2002/07/owl#Ontology"
_RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
_BUILTIN_KEYS: frozenset[str] | None = None


def _import_key(iri: str) -> str:
    """An ontology IRI without one trailing ``#`` or ``/``: ``http://www.w3.org/ns/shacl#``, ``.../shacl``, ``.../shacl-ui/`` and ``.../shacl-ui`` name
    the same ontology, and an author writes whichever form the namespace was given in."""
    return iri[:-1] if iri.endswith(("#", "/")) else iri


def builtin_import_keys() -> frozenset[str]:
    """The ontology IRIs StarLayer has built in, each without a trailing ``#`` or ``/``: every ``owl:Ontology`` a registered ``starontology`` graph
    declares, read from the registry (no list is kept here, so a new registered ontology is covered by registering it) plus the SHACL vocabulary.
    Computed on first use and cached; ``starontology`` is imported then, not when this module is."""
    global _BUILTIN_KEYS
    if _BUILTIN_KEYS is None:
        from starlayer.starontology import get_ontology_graph, get_ontology_list

        keys = {_import_key(SHACL_VOCABULARY.value)}
        for info in get_ontology_list():
            for s, p, o in get_ontology_graph(info.name).triples((None, None, None)):
                if isinstance(s, ox.NamedNode) and p.value == _RDF_TYPE and isinstance(o, ox.NamedNode) and o.value == _OWL_ONTOLOGY:
                    keys.add(_import_key(s.value))
        _BUILTIN_KEYS = frozenset(keys)
    return _BUILTIN_KEYS


def is_builtin_import(iri: Any) -> bool:
    """Whether ``owl:imports iri`` names an ontology the engine already has: it is then neither passed to a loader nor an error without one."""
    return isinstance(iri, ox.NamedNode) and _import_key(iri.value) in builtin_import_keys()


def declared_imports(graph: Any) -> tuple[Any, ...]:
    """Every object of an ``owl:imports`` triple, deduplicated, in first-seen order."""
    seen: dict[Any, None] = {}
    for _, _, o in graph.triples((None, OWL.imports, None)):
        seen.setdefault(o, None)
    return tuple(seen)


def _has_subject(graph: Any, iri: Any) -> bool:
    return any(True for _ in graph.triples((iri, None, None)))


def resolve_imports(
    shapes_graph: Any, loader: Loader | None = None, ignore_imports: bool = False, *, shapes_graph_loader: Loader | None = None
) -> Any:
    """The shapes graph extended with its ``owl:imports`` closure (see the module docstring). Never mutates its input."""
    loader = loader if loader is not None else shapes_graph_loader  # (``shapes_graph_loader``: the validate() spelling)
    shapes_graph = engine_view(shapes_graph, "shapes graph")
    if loader is None:
        if not ignore_imports:
            missing = [o for o in declared_imports(shapes_graph) if not is_builtin_import(o) and not _has_subject(shapes_graph, o)]
            if missing:
                raise ShapeCompileError(
                    f"shacl_graph declares owl:imports {[text(m) for m in missing]!r} that aren't already "
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
        if is_builtin_import(iri) or _has_subject(shapes_graph, iri):
            continue
        graph = engine_view(loader(iri), "imported graph")  # a loader may return an rdflib / StarLayer graph or an StarLayerGraph
        if graph is None:
            continue
        canonical = next((s for s, _, o in graph.triples((None, OWL.versionIRI, None)) if o == iri), iri)
        if canonical in canonical_seen:
            continue
        canonical_seen.add(canonical)
        fetched.add(canonical)
        for t in graph.triples((None, None, None)):
            imported.add(t)
        for _, _, nxt in graph.triples((None, OWL.imports, None)):
            if nxt not in fetched:
                pending.append(nxt)

    delta = [t for t in imported if t not in shapes_graph]
    if not delta:
        return shapes_graph
    result = new_graph(shapes_graph)
    result.extend(list(shapes_graph.triples((None, None, None))))
    result.extend(delta)
    return result


__all__ = ["builtin_import_keys", "declared_imports", "is_builtin_import", "resolve_imports"]
