"""Meta-validation: check a shapes graph against SHACL-SHACL, run by this engine (dogfooding).

The meta-shapes are the project's stored ``shacl12-shacl.ttl`` (``starontology`` entry ``shacl_shacl``: the pinned W3C
SHACL-SHACL plus ``scripts/assets/shacl12-validation-shapes.ttl``, built by ``scripts/build_meta_shapes.py``), read through
``starlayer.shacl.meta_shapes.load_meta_shapes_graph`` exactly as the old preflight does, plus the parameter-value shapes
(SPARQL Extensions 4.2.1) and any ``extra`` graphs (``meta_shapes_extra``). Only warnings and infos are tolerated, as in the
old preflight (``allow_warnings=True``).

The engine's ``validate`` is imported lazily (``api`` may import this module).
"""

# str-ok-file: formats boundary results (legacy_result): rdflib terms only

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from rdflib import Namespace

SH = Namespace("http://www.w3.org/ns/shacl#")  # rdflib terms: this module works on the caller's graphs
META_ERROR_PREFIX = "SHACL File does not validate against the SHACL Shapes SHACL (MetaSHACL) file."


class MetaShaclError(ValueError):
    """The shapes graph does not validate against the meta-shapes; the message starts with the old preflight's text."""


@dataclass
class MetaResult:
    conforms: bool
    report_graph: Any
    report_text: str
    results: list = field(default_factory=list)

    def raise_if_invalid(self) -> None:
        if not self.conforms:
            raise MetaShaclError(f"{META_ERROR_PREFIX}\n{self.report_text}")


def _report_text(conforms: bool, results: list) -> str:
    lines = [f"Validation Report\nConforms: {conforms}"]
    if results:
        lines.append(f"Results ({len(results)}):")
    for r in results:
        sev = str(r.severity).rsplit("#", 1)[-1]
        msg = "; ".join(str(m) for m in r.messages)
        lines.append(f"{sev} in {str(r.component).rsplit('#', 1)[-1]} ({r.shape}):\n\tFocus Node: {r.focus}"
                     + (f"\n\tValue Node: {r.value}" if r.has_value else "")
                     + (f"\n\tMessage: {msg}" if msg else ""))
    return "\n".join(lines)


def meta_validate(
    shapes_graph: Any,
    *,
    extra: Iterable[Any] = (),
    engine_validate: Callable[..., Any] | None = None,
    meta_shapes_extra: Iterable[Any] | None = None,
    meta_shacl: Any = None,
    allow_warnings: Any = True,
    allow_infos: Any = None,
) -> MetaResult:
    """Validate ``shapes_graph`` against the SHACL-SHACL meta-shapes with the native engine.

    ``extra``: further graphs added to the meta-shapes (``meta_shapes_extra``). ``engine_validate``: replacement for the
    engine's ``validate`` (same signature; tests). Returns a ``MetaResult``; call ``raise_if_invalid()`` for the old
    preflight's raise. ``shapes_graph`` is never modified.

    ``allow_warnings`` (default True when called directly) / ``allow_infos`` choose which severities are tolerated.
    ``meta_shapes_extra`` is an alias of ``extra`` and ``meta_shacl`` the validate-option spelling: when ``meta_shacl`` is
    truthy the call raises ``MetaShaclError`` on an invalid shapes graph (the preflight form ``api.validate`` uses).
    """
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph
    from starlayer.shacl.meta_shapes import (
        load_meta_shapes_graph,
        parameter_value_shapes,
    )

    if engine_validate is None:
        from starlayer.shacl_engine.api import validate as engine_validate

    meta = load_meta_shapes_graph(tuple(meta_shapes_extra if meta_shapes_extra is not None else extra))
    meta += parameter_value_shapes(shapes_graph)
    meta_view = StarLayerGraph()
    for t in meta:
        meta_view.add(t)
    # old preflight: allow_warnings tolerates Warning and Info, allow_infos only Info; passing None/False (what
    # ``validate(allow_warnings=None)`` forwards) makes them count
    disallows = SH.Violation if allow_warnings else SH.Warning if allow_infos else SH.Info
    outcome = engine_validate(shapes_graph, meta_view, conformance_disallows=disallows, rules=False,
                              meta_shacl=False, ignore_imports=True)
    result = MetaResult(
        conforms=outcome.conforms,
        report_graph=outcome.report_graph,
        report_text=_report_text(outcome.conforms, outcome.results),
        results=outcome.results,
    )
    if meta_shacl:
        result.raise_if_invalid()
    return result


__all__ = ["META_ERROR_PREFIX", "MetaResult", "MetaShaclError", "meta_validate"]
