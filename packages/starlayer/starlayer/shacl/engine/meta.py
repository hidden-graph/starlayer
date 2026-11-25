"""Meta-validation: check a shapes graph against SHACL-SHACL, run by this engine (dogfooding).

The meta-shapes are the project's stored ``shacl12-shacl.ttl`` (``starontology`` entry ``shacl_shacl``: the pinned W3C
SHACL-SHACL plus ``packages/starlayer/starlayer/starontology/_sources/shacl12-validation-shapes.ttl``, built by ``scripts/build_meta_shapes.py``), read through
``starlayer.shacl.meta_shapes.load_meta_shapes_graph`` exactly as the old preflight does, plus the parameter-value shapes
(SPARQL Extensions 4.2.1) and any ``extra`` graphs (``meta_shapes_extra``). The default is the draft's: a result of any severity makes the shapes graph invalid. The public
``meta_validate`` and the processor's ``meta_shacl`` never pass a floor; ``allow_warnings`` / ``allow_infos`` here exist only for
tests that read a warning's report without the check failing.

The engine's ``validate`` is imported lazily (``api`` may import this module).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import pyoxigraph as ox

from starlayer.shacl.engine.naming import describe, short
from starlayer.shacl.engine.plan import ShapeError
from starlayer.shacl.engine.terms import (
    SH,
    engine_view,
    iri_text,
    text,
    to_engine,
)

META_ERROR_PREFIX = "The shapes graph is not valid SHACL: it does not validate against the SHACL shapes for shapes (MetaSHACL)."


class MetaShaclError(ShapeError):
    """The shapes graph does not validate against the meta-shapes (the meta check found it, as against ``ShapeCompileError``, where the engine cannot compile it); the message says which shape and property each problem is about.

    ``problems`` has one line per result, ``report_text`` is the full validation report of the check and ``report_graph`` the same
    report as a graph, for a caller that shows each result next to its focus node. ``scope`` is the ``MetaScope`` the failed check
    used (``None`` for an error raised elsewhere), so a caller can tell a narrow check from a full one."""

    def __init__(self, message: str, problems: tuple[str, ...] = (), report_text: str = "", report_graph: Any = None,
                 scope: Any = None) -> None:
        super().__init__(message)
        self.scope = scope
        self.problems = problems
        self.report_text = report_text
        self.report_graph = report_graph


@dataclass
class MetaResult:
    """Outcome of validating a shapes graph against the meta-shapes, with a printable report."""

    conforms: bool
    report_graph: Any
    report_text: str
    results: list = field(default_factory=list)
    problems: tuple[str, ...] = ()  # one line per result: the shape it is about, the property and the message
    scope: Any = None  # the MetaScope the check used

    def raise_if_invalid(self) -> None:
        """Raise ``MetaShaclError`` naming each problem when the shapes graph did not conform."""
        if not self.conforms:
            n = len(self.problems)
            lines = "\n".join("- " + line for line in self.problems)
            raise MetaShaclError(f"{META_ERROR_PREFIX} {n} problem{'' if n == 1 else 's'}:\n{lines}", self.problems, self.report_text, self.report_graph, self.scope)


def _problems(shapes_graph: Any, results: list, prefixes: dict[str, str]) -> tuple[str, ...]:
    out = []
    for r in results:
        sev = iri_text(r.severity).rsplit("#", 1)[-1]
        component = iri_text(r.component).rsplit("#", 1)[-1].removesuffix("ConstraintComponent")
        msg = "; ".join(text(m) for m in r.messages) or "violates sh:" + component[:1].lower() + component[1:]
        where = describe(shapes_graph, r.focus, prefixes)
        prop = ", " + short(r.path, prefixes) if r.path is not None else ""
        out.append(("" if sev == "Violation" else sev + ": ") + where + prop + ": " + msg)
    return tuple(out)


def _report_text(conforms: bool, results: list) -> str:
    lines = [f"Validation Report\nConforms: {conforms}"]
    if results:
        lines.append(f"Results ({len(results)}):")
    for r in results:
        sev = iri_text(r.severity).rsplit("#", 1)[-1]
        msg = "; ".join(text(m) for m in r.messages)
        lines.append(f"{sev} in {iri_text(r.component).rsplit('#', 1)[-1]} ({text(r.shape)}):\n\tFocus Node: {text(r.focus)}"  # str-ok: report text
                     + (f"\n\tValue Node: {text(r.value)}" if r.has_value else "")
                     + (f"\n\tMessage: {msg}" if msg else ""))
    return "\n".join(lines)


_static_meta: Any = None
_static_meta_lock = threading.Lock()
_static_meta_plans: dict = {}  # the Plan of ``_static_meta``, kept across calls (see ``api.validate``'s ``plan_cache``)


def _static_meta_graph() -> Any:
    """The meta-shapes graph with no extra graphs and no parameter-value shapes, built once and shared: a validation never
    changes its shapes graph, and a shared graph lets the engine keep its parsed Plan (about 160 shapes, most of the cost of a
    meta check) instead of rebuilding it on every call."""
    global _static_meta
    with _static_meta_lock:
        if _static_meta is None:
            from starlayer.shacl.meta_shapes import load_meta_shapes_graph

            _static_meta = load_meta_shapes_graph(())
        return _static_meta


_META_CACHE_MAXSIZE = 8
_meta_cache: dict = {}  # key -> (combined meta graph, its plan_cache); insertion order is age, the oldest goes first
_meta_cache_lock = threading.Lock()
_meta_cache_stats = {"hits": 0, "misses": 0}


def _blank_free_fingerprint(triples: Iterable[Any]) -> tuple[int, int]:
    """A fingerprint of ``triples`` that does not depend on the labels of their blank nodes, so the same content read twice (a
    parameter-value shapes graph invents fresh blank nodes on every call; a re-parsed shapes graph labels them anew) is the same key.

    Each blank node is replaced by a colour: a hash of the triples it takes part in, refined until no more blank nodes are told apart.
    Two graphs of different structure can get one fingerprint only if refinement cannot separate them; for the small graphs a meta check
    adds, that is a regular structure such as two interchangeable blank nodes, which are then really the same shapes."""
    from starlayer.graph.entailment.cache import content_fingerprint

    triples = list(triples)
    blanks = {t for triple in triples for t in triple if isinstance(t, ox.BlankNode)}
    colour: dict = dict.fromkeys(blanks, 0)

    def seen(term: Any) -> Any:
        return ("_", colour[term]) if isinstance(term, ox.BlankNode) else term

    classes = 1 if blanks else 0
    for _ in range(len(blanks)):
        signature: dict = {b: [] for b in blanks}
        for s_, p_, o_ in triples:
            if s_ in signature:
                signature[s_].append(("s", p_, seen(o_)))
            if o_ in signature:
                signature[o_].append(("o", p_, seen(s_)))
        refined = {b: hash((colour[b], tuple(sorted(hash(x) for x in sig)))) for b, sig in signature.items()}
        if len(set(refined.values())) == classes:
            break
        classes, colour = len(set(refined.values())), refined
    return content_fingerprint((seen(s_), p_, seen(o_)) for s_, p_, o_ in triples)


def _extra_triples(extra: Any) -> list:
    if hasattr(extra, "triples"):
        return list(engine_view(extra, "extra meta-shapes graph").triples((None, None, None)))
    return [tuple(to_engine(x) for x in triple) for triple in extra]


def _combined_meta(extras: tuple, parameter_shapes: Any) -> tuple[Any, dict]:
    """The meta-shapes with ``extras`` and ``parameter_shapes`` added, and the plan cache that goes with it, built once per distinct content.

    Compiling the plan of about 160 shapes is most of a check's cost. The engine keys its plan cache on the identity of the shapes graph
    it is given and a validation does not change that graph, so a kept graph keeps its plan; each entry holds its own graph (so its
    identity cannot be reused while it is kept) and its own dict. The key is a fingerprint of the content, so a changed extra graph or
    parameter value is a different entry, never a stale one. At most ``_META_CACHE_MAXSIZE`` entries are kept, the oldest dropped first."""
    from starlayer.shacl.meta_shapes import load_meta_shapes_graph

    key = (tuple(_blank_free_fingerprint(_extra_triples(x)) for x in extras),
           _blank_free_fingerprint(parameter_shapes.triples((None, None, None))))
    with _meta_cache_lock:
        entry = _meta_cache.get(key)
        if entry is not None:
            _meta_cache_stats["hits"] += 1
            return entry
        _meta_cache_stats["misses"] += 1
    meta = load_meta_shapes_graph(extras)
    meta += parameter_shapes
    entry = (meta, {})
    with _meta_cache_lock:
        _meta_cache[key] = entry
        while len(_meta_cache) > _META_CACHE_MAXSIZE:
            del _meta_cache[next(iter(_meta_cache))]
    return entry


def meta_validate(
    shapes_graph: Any,
    *,
    extra: Iterable[Any] = (),
    engine_validate: Callable[..., Any] | None = None,
    meta_shapes_extra: Iterable[Any] | None = None,
    meta_shacl: Any = None,
    allow_warnings: Any = False,
    allow_infos: Any = None,
    add: Iterable[Any] = (),
    remove: Iterable[Any] = (),
    nodes: Iterable[Any] | None = None,
    with_dependents: bool = True,
    full: bool = False,
) -> MetaResult:
    """Validate ``shapes_graph`` against the SHACL-SHACL meta-shapes with the native engine.

    ``extra``: further graphs added to the meta-shapes (``meta_shapes_extra``). ``engine_validate``: replacement for the
    engine's ``validate`` (same signature; tests). Returns a ``MetaResult``; call ``raise_if_invalid()`` for the old
    preflight's raise. ``shapes_graph`` is never modified.

    ``allow_warnings`` / ``allow_infos`` choose which severities are tolerated (default: none, as in SHACL 1.2 Core's disallowed set); no public path sets them.
    ``meta_shapes_extra`` is an alias of ``extra`` and ``meta_shacl`` the validate-option spelling: when ``meta_shacl`` is
    truthy the call raises ``MetaShaclError`` on an invalid shapes graph (the preflight form ``api.validate`` uses).
    The meta-shapes include the layer ``shacl_shacl_starlayer``, whose shapes find the SPARQL text the shapes graph embeds that is not valid and the
    ``sh:pattern`` / ``sh:flags`` values the engine cannot compile; they are results like any other, so one error reports them all.

    ``add`` / ``remove`` (triples) propose an edit: the check runs on a copy of the shapes graph with the edit applied, and the
    caller's graph is not changed. ``nodes`` names nodes of the graph to check. With any of the three the check is scoped
    (``meta_scope`` says to which nodes, and when a risky edit makes it full); with none it is the whole graph. ``MetaResult.scope``
    is the scope used. ``full=True`` checks the whole graph as it would be after the edit, whatever the edit is.
    """
    from starlayer.shacl.engine.meta_scope import after_edit, compute_scope
    from starlayer.shacl.meta_shapes import parameter_value_shapes

    real_engine = engine_validate is None
    if real_engine:
        from starlayer.shacl.engine.api import validate as engine_validate

    prefixes = dict(getattr(shapes_graph, "prefixes", None) or {})
    shapes_graph = engine_view(shapes_graph, "shapes graph")
    scope, adds, removes = compute_scope(shapes_graph, add=add, remove=remove, nodes=nodes, with_dependents=with_dependents,
                                         prefixes=prefixes)
    if full and not scope.full:
        scope = _forced_full(scope)
    scoped = nodes is not None or bool(adds) or bool(removes)
    shapes_graph = after_edit(shapes_graph, adds, removes)

    extras = tuple(meta_shapes_extra if meta_shapes_extra is not None else extra)
    parameter_shapes = parameter_value_shapes(shapes_graph)
    reuse = not extras and len(parameter_shapes) == 0 and real_engine
    if reuse:
        meta, kwargs = _static_meta_graph(), {"plan_cache": _static_meta_plans}
    elif real_engine:
        meta, plans = _combined_meta(extras, parameter_shapes)
        kwargs = {"plan_cache": plans}
    else:  # an injected engine (tests) gets a fresh graph and nothing is kept
        from starlayer.shacl.meta_shapes import load_meta_shapes_graph

        meta, kwargs = load_meta_shapes_graph(extras), {}
        meta += parameter_shapes
    # allow_warnings tolerates Warning and Info, allow_infos only Info; None/False (what
    # ``validate(allow_warnings=None)`` forwards) makes them count
    disallows = SH.Violation if allow_warnings else SH.Warning if allow_infos else SH.Info
    if scoped and not scope.full:
        kwargs["focus_filter"] = frozenset(scope.nodes)
    outcome = engine_validate(shapes_graph, meta, conformance_disallows=disallows, rules=False,
                              meta_shacl=False, ignore_imports=True, **kwargs)
    result = MetaResult(
        conforms=outcome.conforms,
        report_graph=outcome.report_graph,
        report_text=_report_text(outcome.conforms, outcome.results),
        results=outcome.results,
        problems=_problems(shapes_graph, outcome.results, prefixes),
        scope=scope,
    )
    if meta_shacl:
        result.raise_if_invalid()
    return result


def _forced_full(scope: Any) -> Any:
    from starlayer.shacl.engine.meta_scope import MetaScope

    return MetaScope(True, (), ("full check: requested",))


def meta_scope(
    shapes_graph: Any,
    *,
    add: Iterable[Any] = (),
    remove: Iterable[Any] = (),
    nodes: Iterable[Any] | None = None,
    with_dependents: bool = True,
    full: bool = False,
) -> Any:
    """The ``MetaScope`` that ``meta_validate`` would use for the same arguments: nothing is validated and no copy is made, so it is
    cheap. An edit that gives a new subject a type or subclass triple (a new shape) is scoped, not full; the same triple on a node the
    graph has is full, because other nodes' checks can depend on it."""
    from starlayer.shacl.engine.meta_scope import compute_scope

    prefixes = dict(getattr(shapes_graph, "prefixes", None) or {})
    scope = compute_scope(engine_view(shapes_graph, "shapes graph"), add=add, remove=remove, nodes=nodes,
                          with_dependents=with_dependents, prefixes=prefixes)[0]
    return _forced_full(scope) if full and not scope.full else scope


__all__ = ["META_ERROR_PREFIX", "MetaResult", "MetaShaclError", "meta_scope", "meta_validate"]
