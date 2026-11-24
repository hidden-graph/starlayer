"""Entailment regimes for the SHACL engine: ``entailed_view`` and ``resolve_data_view``.

The closure is the project's own (``StarLayerGraph.infer``: the RDFS closure native on pyoxigraph, the OWL 2 RL fragment by ``owlrl``
for ``OWL-RDF-Based``, OWL 2 DL by HermiT or ``rustdl`` for ``OWL-Direct``), computed over the data graph plus ``ont_graph``. The
result is the entailed copy of the data's store that ``graph/entailment/cache.py`` keeps once per store and shares with SPARQL
query-time entailment: whichever of the two asks for a regime first computes it, the other finds it. The copy holds the data and the
entailed triples; ``ont_graph``'s own triples are visible to the reasoning but never stored in it. The caller's graphs are never mutated
and nothing may write to the copy (rules write to an overlay on top of it, ``rules.new_overlay``). Class targets and ``sh:class`` read
``rdf:type`` / ``rdfs:subClassOf`` straight from the copy, so the domain/range-inferred types and the subclass closure are seen like
any other triple.

The copy is kept until the store is written through this package (the write count of the store, ``union.version_of``; a write on a raw
store reference needs ``union.touch()``), or until ``clear_entailment_cache()``; ``recompute=`` ("onChange", "never", "always") says
when it is made again, as for ``query()``. RDF and RDFS are a copy here too: SHACL reads the data through triple lookups, not SPARQL
text, so the query rewrite that answers them for ``query()`` cannot serve it (``docs/working`` notes the measurement).

``sh:entailment`` on the shapes graph (SHACL 1.2 Core 1.4) selects the regimes; ``sh:RulesEntailment`` and rule-set IRIs are
left to ``rules.entailment_selection``. Several regimes combine into one entry, ``OWL-Direct`` too: the entailments of every
regime in the set, the others also seeing what OWL-Direct inferred (``infer._delta_for``; not a fixpoint over all of them).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pyoxigraph as ox

from starlayer.graph.entailment.cache import (
    RECOMPUTE,
    entailed_store_view,
)
from starlayer.graph.entailment.infer import (
    ENTAILMENT,
    OWL_DIRECT_REGIME,
    SUPPORTED_REGIMES,
)
from starlayer.shacl.engine.terms import (
    RDF,
    SH,
    engine_view,
    text,
    to_engine,
)

_SUPPORTED = frozenset(ox.NamedNode(r) for r in SUPPORTED_REGIMES)
_DIRECT = ox.NamedNode(OWL_DIRECT_REGIME)


def normalise_regimes(regime: Any) -> frozenset:
    """The entailment regime IRIs of ``regime``: ``None`` (no entailment), a regime IRI (the W3C entailment regime
    IRIs ``sh:entailment`` uses, e.g. ``ENTAILMENT.RDFS``), or an iterable of them. A plain string must itself be such an IRI;
    names such as ``'rdfs'`` or ``'owlrl'`` are not accepted. An unsupported regime raises ``ValueError``. The IRIs come
    back as pyoxigraph ``NamedNode``s (an IRI string is accepted)."""
    if regime is None:
        return frozenset()
    items: Iterable = [regime] if isinstance(regime, str) or not hasattr(regime, "__iter__") else regime
    supported = sorted(text(r) for r in _SUPPORTED)
    out = set()
    for item in items:
        try:
            out.add(ox.NamedNode(item) if isinstance(item, str) and type(item) is str else to_engine(item))
        except ValueError:
            raise ValueError(f"Unsupported entailment regime {item!r}, which is not an IRI; use one of {supported!r}") from None
    unsupported = {r for r in out if r not in _SUPPORTED}
    if unsupported:
        raise ValueError(f"Unsupported entailment regime(s) {sorted(text(r) for r in unsupported)!r}; use one of {supported!r}")
    return frozenset(out)


def _check_run_options(regimes: frozenset, engine: str, timeout: Any, recompute: str) -> None:
    """The checks ``query()`` makes of ``engine``, ``timeout`` and ``recompute``, """
    if recompute not in RECOMPUTE:
        raise ValueError(f"recompute must be one of ['always', 'never', 'onChange'], got {recompute!r}")
    if _DIRECT in regimes:
        if engine not in ("hermit", "rustdl"):
            raise ValueError(f"Unsupported engine {engine!r}; expected one of ['hermit', 'rustdl']")
        return
    if engine != "hermit":
        raise ValueError(
            f"engine={engine!r} is only meaningful for the OWL-Direct entailment regime (got {sorted(text(r) for r in regimes)!r}) - omit engine= otherwise."
        )
    if timeout is not None:
        raise ValueError(
            f"timeout={timeout!r} is only meaningful for the OWL-Direct entailment regime (got {sorted(text(r) for r in regimes)!r}) - omit timeout= otherwise."
        )


def entailed_view(
    data_graph: Any,
    regime: Any = ENTAILMENT.RDFS,
    ont_graph: Any = None,
    *,
    engine: str = "hermit",
    timeout: Any = None,
    recompute: str = "onChange",
) -> Any:
    """``data_graph`` closed under ``regime``, as the shared entailed copy of its store (``graph/entailment/cache.py``); with no
    regime, ``data_graph`` itself. Never mutates ``data_graph`` or ``ont_graph``, and nothing may write to the result.

    The copy is returned again until the store of ``data_graph`` (or of ``ont_graph``) is written to through this package, so
    validating unchanged data again, or running the same regime in a SPARQL query, does not run the closure again; ``recompute``
    is as for ``query()``. ``engine`` and ``timeout`` are for ``OWL-Direct`` (``ValueError`` for another regime)."""
    regimes = normalise_regimes(regime)
    data_graph = engine_view(data_graph)
    if not regimes:
        return data_graph
    _check_run_options(regimes, engine, timeout, recompute)
    ont = engine_view(ont_graph, "ontology graph") if ont_graph is not None and hasattr(ont_graph, "triples") else None
    if ont is None and ont_graph is not None:  # an iterable of triples is accepted too
        ont = [tuple(to_engine(x) for x in t) for t in ont_graph]
    return entailed_store_view(data_graph, regimes, engine=engine, timeout=timeout, ont_graph=ont, recompute=recompute)


def declared_regimes(shapes: Any) -> frozenset:
    """The entailment regime IRIs named by ``sh:entailment`` in ``shapes`` (rules entailment and rule sets excluded). An IRI
    that is neither a regime nor ``sh:RulesEntailment`` nor a ``sh:RuleSet`` raises ``ValueError``, as does a known but
    unsupported regime (D-entailment)."""
    out = set()
    shapes = engine_view(shapes)
    for _s, _p, o in shapes.triples((None, SH.entailment, None)):
        if o == SH.RulesEntailment or (o, RDF.type, SH.RuleSet) in shapes:
            continue
        if text(o) not in SUPPORTED_REGIMES:
            raise ValueError(f"Unsupported entailment regime {text(o)!r}")
        out.add(o)
    return frozenset(out)


def resolve_data_view(
    data_graph: Any,
    shapes_graph: Any = None,
    *,
    inference: Any = None,
    ont_graph: Any = None,
    engine: str = "hermit",
    timeout: Any = None,
    recompute: str = "onChange",
) -> Any:
    """The data view ``validate`` should run on: ``data_graph`` closed under the regimes the shapes graph declares with
    ``sh:entailment`` plus those of ``inference`` (a regime IRI or an iterable of them; names such as ``'rdfs'`` are not
    accepted). ``data_graph`` itself when there are none. The set of regimes is the cache key (``entailed_view``)."""
    data_graph = engine_view(data_graph)
    shapes = engine_view(shapes_graph) if shapes_graph is not None else data_graph
    regimes = declared_regimes(shapes) | normalise_regimes(inference)
    return entailed_view(data_graph, regimes, ont_graph, engine=engine, timeout=timeout, recompute=recompute)


__all__ = ["declared_regimes", "entailed_view", "normalise_regimes", "resolve_data_view"]
