"""SPARQL execution for the wrapper, on the same semantics as ``starlayer.graph.query.direct``: the text goes to
``Store.query`` / ``Store.update`` as it is, ``initNs`` -> ``prefixes=``, ``base`` -> ``base_iri=``, ``initBindings`` ->
``substitutions=`` with the documented ``VALUES`` fallback when the variable is not projected.

``direct.run_direct`` itself returns rdflib terms and an rdflib ``Result``, and cannot select a default graph, so this module
reuses its helpers (``_prefix_dict``, ``_guard``) and ``backends.native`` (``check_native_version_conformance``,
``inject_init_bindings``) and builds the wrapper's ``Result`` over pyoxigraph terms. They are imported lazily.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pyoxigraph as ox

from starlayer.graph.oxgraph import terms
from starlayer.graph.oxgraph.result import Result


class _Inline:
    """What ``inject_init_bindings`` needs of a term: ``.n3()``. A pyoxigraph term prints as SPARQL syntax."""

    def __init__(self, t: Any) -> None:
        self._t = t

    def n3(self) -> str:
        return str(self._t)


def merge_prefixes(*maps: Mapping[str, str] | None) -> dict[str, str] | None:
    out: dict[str, str] = {}
    for m in maps:
        if m:
            items = m.items() if hasattr(m, "items") else m
            out.update({str(k): str(v) for k, v in items})
    return out or None


def query(store: ox.Store, text: str, *, prefixes: Mapping[str, str] | None, init_ns: Any = None,
          init_bindings: Mapping[Any, Any] | None = None, base: str | None = None, default_graph: Any = None,
          union: bool = False) -> Result:
    from starlayer.graph.backends.native import (
        check_native_version_conformance,
        inject_init_bindings,
    )
    from starlayer.graph.query.direct import _guard

    if not isinstance(text, str):
        raise NotImplementedError("the wrapper runs query text, not a prepared Query object")
    check_native_version_conformance(text)
    sent = _guard(text)
    kwargs: dict[str, Any] = {}
    pfx = merge_prefixes(prefixes, init_ns)
    if pfx:
        kwargs["prefixes"] = pfx
    if base:
        kwargs["base_iri"] = base
    if union:
        kwargs["use_default_graph_as_union"] = True
    elif default_graph is not None:
        kwargs["default_graph"] = default_graph
    subs = None
    if init_bindings:
        subs = {ox.Variable(str(getattr(k, "value", k)).lstrip("?$")): terms.term(v) for k, v in init_bindings.items()}
    try:
        raw = store.query(sent, **kwargs, **({"substitutions": subs} if subs else {}))
    except RuntimeError as e:
        if not subs or "projection" not in str(e):
            raise
        injected = inject_init_bindings(sent, {k.value: _Inline(v) for k, v in subs.items()})
        raw = store.query(injected, **kwargs)
    return Result(raw, text)


def update(store: ox.Store, text: str, *, prefixes: Mapping[str, str] | None, init_ns: Any = None,
           base: str | None = None) -> None:
    from starlayer.graph.backends.native import check_native_version_conformance
    from starlayer.graph.query.direct import _guard

    if not isinstance(text, str):
        raise NotImplementedError("the wrapper runs update text, not a prepared Update object")
    check_native_version_conformance(text)
    kwargs: dict[str, Any] = {}
    pfx = merge_prefixes(prefixes, init_ns)
    if pfx:
        kwargs["prefixes"] = pfx
    if base:
        kwargs["base_iri"] = base
    store.update(_guard(text), **kwargs)
