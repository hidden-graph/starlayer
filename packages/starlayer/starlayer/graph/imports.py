"""``owl_imports``, ``has_import_locally``, ``unresolved_imports``, ``resolve_or_raise``, ``resolve_imports`` and ``can_resolve_import``: the
``owl:imports`` closure of a graph, and the one rule every path that resolves imports follows.

**The rule.** A graph (an ontology, a shapes graph, an ontology graph) that declares ``owl:imports`` must resolve them or raise. An import
is *satisfied* when, after resolution, its IRI is a subject of at least one triple in the resulting graph: already present, a built-in
ontology of the ``starontology`` registry (``builtin_import_keys``), loaded by the caller's loader, or named by an ``owl:versionIRI`` of an
ontology that is present. An import that is not satisfied raises ``ExecutionError`` kind ``"import"`` naming it, with the IRIs on
``error.unresolved``: there was no loader, it returned ``None``, or it returned a graph in which the IRI is not a subject. A loader that
raises is wrapped (kind ``"import"``, the loader's exception as ``__cause__``). ``ignore_imports=True`` loads nothing and checks nothing.
The library never retries: an application reads ``unresolved_imports(graph)`` and may call again with a loader that knows more. A graph
is fetched at most once in one resolution and cycles end.

**On the graph.** A graph carries its own import settings (``StarLayerGraph(imports_loader=..., ignore_imports=...)``, the ``imports_loader`` and
``ignore_imports`` properties), and every consumer asks the graph, once, through ``graph.resolved_imports()`` (``graph_imports`` for any graph
object): the triples its ``owl:imports`` closure loads, cached per store and kept until the store is written to or the loader or flag
changes. A per-call ``imports_loader=`` / ``ignore_imports=`` overrides the graph's setting for that
call. Resolution is lazy: nothing is loaded until an operation that reads imports asks, and a loader is called at most once per cached
result. A cached result is not kept when resolution raises. The imports of a graph are not copied into it (a graph holds only what was
added to it).

The loader maps an import IRI (a ``NamedNode``) to a graph, or ``None``; it may return an ``StarLayerGraph`` / ``StarLayerDataset`` or any
object with ``triples(pattern)`` (an old ``StarLayerGraph``'s terms are converted).
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

import pyoxigraph as ox

from starlayer.errors import ExecutionError, FormatError
from starlayer.graph import terms

OWL = "http://www.w3.org/2002/07/owl#"
OWL_IMPORTS = ox.NamedNode(OWL + "imports")
OWL_VERSION_IRI = ox.NamedNode(OWL + "versionIRI")
VALID_MODES = frozenset({"full", "delta", "in-place"})

#: The SHACL vocabulary graph. SHACL 1.2 Core recommends ``owl:imports sh:`` for a graph that uses ``sh:ShapeClass``; StarLayer has that
#: vocabulary built in, so the import is satisfied without a loader.
SHACL_VOCABULARY = ox.NamedNode("http://www.w3.org/ns/shacl#")
_OWL_ONTOLOGY = OWL + "Ontology"
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
    """Whether ``owl:imports iri`` names an ontology StarLayer already has (a registered ``starontology`` graph or the SHACL vocabulary): it is
    then satisfied, never passed to a loader and adds no triples."""
    return isinstance(iri, ox.NamedNode) and _import_key(iri.value) in builtin_import_keys()


def can_resolve_import(iri: Any, *, imports_loader: Callable[[Any], Any | None]) -> bool:
    """Whether ``imports_loader(iri)`` returns a graph (it is called once; there is no cheaper way to ask)."""
    return imports_loader(iri) is not None


def owl_imports(g: Any) -> tuple[Any, ...]:
    """The objects of the graph's own ``owl:imports`` triples, deduplicated, in first-seen order. Resolves nothing."""
    return tuple(dict.fromkeys(o for _, _, o in g.triples((None, OWL_IMPORTS, None))))


def has_import_locally(g: Any, iri: Any) -> bool:
    """True iff ``iri`` already has a triple as subject in the graph (its content is co-located, no loader needed)."""
    return next(iter(g.triples((terms.term(iri), None, None))), None) is not None


def _triples(x: Any, pattern: tuple = (None, None, None)) -> list[tuple[Any, Any, Any]]:
    return [(terms.term(s), terms.term(p), terms.term(o)) for s, p, o in x.triples(pattern)]


def _declared(g: Any, malformed: Callable[[Any], Exception] | None = None) -> tuple[Any, ...]:
    """The ``owl:imports`` objects of ``g`` (deduplicated, first seen first). One that is not an IRI is malformed: ``malformed(term)``
    gives the error to raise (a ``FormatError`` kind ``"owl"`` by default)."""
    out = owl_imports(g)
    for o in out:
        if not isinstance(o, ox.NamedNode):
            raise (malformed or _malformed_import)(o)
    return out


def _malformed_import(term: Any) -> Exception:
    return FormatError(f"owl:imports needs an IRI, not {term}", kind="owl", context=f"owl:imports {term}")


def unresolved_imports(g: Any) -> tuple[ox.NamedNode, ...]:
    """The imports ``g`` declares that are not satisfied as it is: an ``owl:imports`` IRI that is not a subject of any triple in ``g``, not a
    built-in ontology (``is_builtin_import``) and not the ``owl:versionIRI`` of a present ontology. Deduplicated, sorted by IRI (the same order as ``ExecutionError.unresolved``), ``()``
    when every import is satisfied. Loads nothing; an application reads it after ``resolve_imports()`` raised (or before) to decide what to
    load, and may call again. ``FormatError`` kind ``"owl"`` for an ``owl:imports`` object that is not an IRI."""
    return tuple(sorted((iri for iri in _declared(g) if not _satisfied(g, iri, frozenset(), frozenset())), key=lambda i: i.value))


def _satisfied(g: Any, iri: Any, subjects: Any, versions: Any) -> bool:
    """``iri`` is a subject of ``g`` or of the imported triples (``subjects``), the ``owl:versionIRI`` of a present ontology, or built in."""
    if iri in subjects or iri in versions or has_import_locally(g, iri):
        return True
    if next(iter(g.triples((None, OWL_VERSION_IRI, terms.term(iri)))), None) is not None:
        return True
    return is_builtin_import(iri)


def _unresolved_error(iris: tuple[Any, ...], why: str, loader_name: str) -> ExecutionError:
    names = ", ".join(f"<{i.value}>" for i in iris)
    return ExecutionError(
        f"owl:imports {names} {'is' if len(iris) == 1 else 'are'} not resolved: {why}. Give the graph an imports_loader (imports_loader= when "
        f"it is made, or graph.imports_loader = ...) or pass {loader_name}= to this call, a loader that returns a graph "
        "that has each of them as a subject, or set ignore_imports=True (on the graph or on the call) to skip them.",
        kind="import", context=f"owl:imports {names}", unresolved=iris,
    )


def resolve_or_raise(g: Any, imports_loader: Callable[[Any], Any | None] | None = None, ignore_imports: bool = False, *,
                     view: Callable[[Any], Any] | None = None, malformed: Callable[[Any], Exception] | None = None,
                     loader_name: str = "imports_loader") -> set[tuple[Any, Any, Any]]:
    """The one resolution every path calls: follow ``g``'s ``owl:imports`` transitively with ``imports_loader`` and return the triples that were
    loaded (the caller merges them as it needs), or raise ``ExecutionError`` kind ``"import"`` (see the module docstring). ``g`` is not changed.

    An import that is already satisfied (a subject of ``g`` or of what was loaded so far, a built-in ontology, a ``owl:versionIRI`` of a
    present ontology) never reaches the loader; one fetched once is not fetched again, and a versioned and an unversioned name of one
    module are fetched once. Further imports are read from every ``owl:imports`` triple of a loaded graph. ``ignore_imports=True`` returns
    ``set()`` and checks nothing. ``view`` turns a loader's result into a graph with ``triples(pattern)`` (default: as it is), ``malformed``
    builds the error for an ``owl:imports`` object that is not an IRI and ``loader_name`` is the name of the loader parameter in messages."""
    if ignore_imports:
        return set()
    fetched: set = set()
    canonical_seen: set = set()
    imported: set = set()
    subjects: set = set()
    versions: set = set()
    declared: list = list(_declared(g, malformed))
    pending = list(declared)
    while pending:
        iri = pending.pop(0)
        if iri in fetched:
            continue
        fetched.add(iri)
        if imports_loader is None or _satisfied(g, iri, subjects, versions):
            continue
        try:
            result = imports_loader(iri)
        except Exception as exc:
            raise ExecutionError(
                f"owl:imports <{iri.value}> cannot be loaded: {type(exc).__name__}: {exc}",
                kind="import", context=f"owl:imports <{iri.value}>", unresolved=(iri,),
            ) from exc
        if result is None:
            continue
        triples = _triples(view(result) if view is not None else result)
        canonical = next((s for s, p, o in triples if p == OWL_VERSION_IRI and o == iri), iri)
        if canonical in canonical_seen:
            continue
        canonical_seen.add(canonical)
        fetched.add(canonical)
        imported.update(triples)
        for s, p, o in triples:
            subjects.add(s)
            if p == OWL_VERSION_IRI:
                versions.add(o)
            elif p == OWL_IMPORTS:
                if not isinstance(o, ox.NamedNode):
                    raise (malformed or _malformed_import)(o)
                if o not in declared:
                    declared.append(o)
                if o not in fetched:
                    pending.append(o)
    missing = tuple(sorted((iri for iri in declared if not _satisfied(g, iri, subjects, versions)), key=lambda i: i.value))
    if missing:
        why = (f"no loader was given (neither {loader_name}= nor the graph's imports_loader)" if imports_loader is None
               else f"{loader_name} returned no graph that has {'it' if len(missing) == 1 else 'them'} as a subject")
        raise _unresolved_error(missing, why, loader_name)
    return imported


#: resolved imports kept per store (the most recently used first dropped last)
MAX_CACHED = 4


class ImportsCache:
    """The resolved imports of the graphs of one store (``StoreVersion.imports``): one lock, so a loader runs at most once for a graph
    that two threads ask for at the same time (it is called with the lock held, so it must not wait on another thread that asks this
    store for its imports)."""

    __slots__ = ("entries", "lock")

    def __init__(self) -> None:
        self.entries: OrderedDict[tuple, tuple[Any, Any, frozenset]] = OrderedDict()
        self.lock = threading.RLock()

    def clear(self) -> None:
        with self.lock:
            self.entries.clear()


def _read_key(g: Any) -> tuple | None:
    """What a graph object reads of its store (the cache key part), or ``None`` for an object that is not cached."""
    from starlayer.graph.core import StarLayerDataset, StarLayerGraph

    if isinstance(g, StarLayerDataset):
        return ("dataset", g.default_union)
    if isinstance(g, StarLayerGraph):
        return ("graph", g.identifier)
    name = getattr(g, "graph_name", None)
    if name is not None and hasattr(g, "store"):
        try:
            hash(name)
        except TypeError:
            return None
        return ("view", name)
    return None


def _cache_of(version: Any) -> ImportsCache:
    from starlayer.graph.execution import union

    with union._lock:
        if version.imports is None:
            version.imports = ImportsCache()
        return version.imports


def clear_cached_imports(g: Any) -> None:
    """Drop the resolved imports kept for the store of ``g`` (the next consumer resolves again)."""
    version = getattr(g, "_version", None)
    if version is not None and version.imports is not None:
        version.imports.clear()


def graph_imports(g: Any, imports_loader: Callable[[Any], Any | None] | None = None, ignore_imports: bool | None = None, *,
                  view: Callable[[Any], Any] | None = None, malformed: Callable[[Any], Exception] | None = None,
                  loader_name: str = "imports_loader") -> frozenset[tuple[Any, Any, Any]]:
    """The one accessor every consumer of ``g``'s ``owl:imports`` calls: the triples its import closure loads (``frozenset``, empty
    when nothing is imported; ``g`` itself is not changed and does not hold them), or ``ExecutionError`` kind ``"import"`` (see the
    module docstring). ``imports_loader`` and ``ignore_imports`` override ``g.imports_loader`` / ``g.ignore_imports`` for this call (``None``:
    the graph's own setting; a graph object that has none, for instance an engine view, has no loader and does not ignore).

    A graph of a store (``StarLayerGraph``, ``StarLayerDataset``, an engine view) keeps the result per store, keyed by what it reads
    (its graph, or the dataset and ``default_union``), the loader object and the flag, and valid while the store's write count
    (``execution/union.py``) is unchanged: a write made through this package, a ``parse``, ``clear`` or ``remove`` drops it; a write on a
    raw store reference does not (``union.touch()`` after it). A loader that returns different graphs later is not seen until then or
    ``clear_cached_imports``. ``view`` and ``malformed`` are the consumer's way of reading a loader's graph and of naming a malformed
    ``owl:imports`` object; they are not part of the key."""
    if imports_loader is None:
        imports_loader = getattr(g, "imports_loader", None)
    if ignore_imports is None:
        ignore_imports = bool(getattr(g, "ignore_imports", False))
    if ignore_imports:
        return frozenset()
    version = getattr(g, "_version", None)
    read = _read_key(g) if version is not None else None
    if read is None:
        return frozenset(resolve_or_raise(g, imports_loader, False, view=view, malformed=malformed, loader_name=loader_name))
    key = (read, id(imports_loader) if imports_loader is not None else None)
    cache = _cache_of(version)
    with cache.lock:
        stamp = version.stamp()  # before the loader runs: a write that lands during it leaves the result stale
        hit = cache.entries.get(key)
        if hit is not None and hit[0] == stamp:
            cache.entries.move_to_end(key)
            return hit[2]
        result = frozenset(resolve_or_raise(g, imports_loader, False, view=view, malformed=malformed, loader_name=loader_name))
        cache.entries[key] = (stamp, imports_loader, result)  # the loader is held, so its ``id`` in the key is not reused
        cache.entries.move_to_end(key)
        while len(cache.entries) > MAX_CACHED:
            cache.entries.popitem(last=False)
        return result


def resolve_imports(g: Any, *, imports_loader: Callable[[Any], Any | None] | None = None, mode: str = "full", target_graph: Any = None,
                    ignore_imports: bool | None = None) -> Any:
    """Follow the graph's ``owl:imports`` transitively and merge the result. ``mode`` is "full" (a new graph: self plus the
    imports), "delta" (a new graph with only the triples self lacks) or "in-place" (add the delta to self). Cycles and a
    versioned/unversioned pair of the same module are fetched once.

    Every declared import must be resolved or the call raises (``resolve_or_raise``): ``ExecutionError`` kind ``"import"`` for an import
    that is not a subject of the graph after loading (no ``imports_loader``, one that returns ``None`` or a graph without it, with the IRIs on
    ``error.unresolved``), the same kind wrapping a loader's own exception; ``ignore_imports=True`` returns the graph's own triples as they are.
    ``imports_loader`` and ``ignore_imports`` override the graph's own ``imports_loader`` / ``ignore_imports`` for this call (``graph_imports``)."""
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(VALID_MODES)}, got {mode!r}")
    if mode == "in-place" and target_graph is not None:
        raise ValueError("target_graph is meaningless with mode='in-place' - it mutates self directly.")

    all_imported = graph_imports(g, imports_loader, ignore_imports)

    delta = set(all_imported) - set(g.triples())
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
        from starlayer.graph.core import StarLayerGraph

        target_graph = StarLayerGraph(prefixes=dict(g.prefixes), imports_loader=g.imports_loader, ignore_imports=g.ignore_imports)
    elif not (hasattr(target_graph, "extend") and hasattr(target_graph, "store")):
        raise TypeError(f"resolve_imports() target_graph must be an StarLayerGraph or StarLayerDataset, not {type(target_graph).__name__}.")
    target_graph.extend(list(g.triples()) + list(delta))
    return target_graph
