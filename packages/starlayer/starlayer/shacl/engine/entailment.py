"""Entailment regimes for the SHACL engine: ``entailed_view`` and ``resolve_data_view``.

The closure is the project's own (``StarLayerGraph.infer``: the RDFS closure native on pyoxigraph, the OWL 2 RL
fragment by ``owlrl`` for ``OWL-RDF-Based``), computed over the data graph plus ``ont_graph`` and kept as an
``InferredView`` overlay: only the newly entailed triples are held, the caller's graphs are never mutated, and
``ont_graph``'s own triples are visible to the reasoning but never copied into the view. Class targets and ``sh:class`` read
``rdf:type`` / ``rdfs:subClassOf`` straight from the view, so the domain/range-inferred types and the subclass closure
are seen like any other triple.

``sh:entailment`` on the shapes graph (SHACL 1.2 Core 1.4) selects the regimes; ``sh:RulesEntailment`` and rule-set IRIs are
left to ``rules.entailment_selection``. Several regimes combine into one pass.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pyoxigraph as ox

from starlayer.graph.entailment.infer import ENTAILMENT, SUPPORTED_REGIMES
from starlayer.shacl.engine.rules import new_overlay
from starlayer.shacl.engine.terms import (
    RDF,
    SH,
    engine_view,
    text,
    to_engine,
)

_NATIVE = {ENTAILMENT.RDF, ENTAILMENT.RDFS, ENTAILMENT["OWL-RDF-Based"]}


def normalise_regimes(regime: Any) -> frozenset:
    """The entailment regime IRIs of ``regime``: ``None`` (no entailment), a regime IRI (the W3C entailment regime
    IRIs ``sh:entailment`` uses, e.g. ``ENTAILMENT.RDFS``), or an iterable of them. A plain string must itself be such an IRI;
    names such as ``'rdfs'`` or ``'owlrl'`` are not accepted. An unsupported regime raises ``ValueError``. The IRIs come
    back as pyoxigraph ``NamedNode``s (an IRI string is accepted)."""
    if regime is None:
        return frozenset()
    items: Iterable = [regime] if isinstance(regime, str) or not hasattr(regime, "__iter__") else regime
    supported = sorted(text(r) for r in _NATIVE)
    out = set()
    for item in items:
        try:
            out.add(ox.NamedNode(item) if isinstance(item, str) and type(item) is str else to_engine(item))
        except ValueError:
            raise ValueError(f"Unsupported entailment regime {item!r}, which is not an IRI; use one of {supported!r}") from None
    unsupported = {r for r in out if r not in _NATIVE}
    if unsupported:
        raise ValueError(f"Unsupported entailment regime(s) {sorted(text(r) for r in unsupported)!r}; use one of {supported!r}")
    return frozenset(out)


_KEPT_ATTRIBUTE = "_shacl_entailed"
_KEPT_VIEWS = 4  # regimes (and ontology graphs) kept per data graph


def _fingerprint(triples: Iterable[Any]) -> tuple[int, int]:
    """How many triples there are and a hash of their set (the sum of their hashes, wrapped to 64 bits): two graphs with the same
    triples give the same pair, any other change to the triples gives another one."""
    count = total = 0
    for t in triples:
        count += 1
        total += hash(t)
    return count, total & 0xFFFFFFFFFFFFFFFF


def entailed_view(data_graph: Any, regime: Any = ENTAILMENT.RDFS, ont_graph: Any = None) -> Any:
    """``data_graph`` closed under ``regime``, as an overlay; with no regime, ``data_graph`` itself. Never mutates
    ``data_graph`` or ``ont_graph``.

    The overlay is kept on ``data_graph`` and returned again while the triples of ``data_graph`` and ``ont_graph`` are the same
    (compared by content, not by the wrapper's write counter, which a validation's own report graph also moves), so validating
    unchanged data again does not run the closure again. Nothing writes to the overlay."""
    regimes = normalise_regimes(regime)
    data_graph = engine_view(data_graph)
    if not regimes:
        return data_graph
    ont = engine_view(ont_graph, "ontology graph") if ont_graph is not None and hasattr(ont_graph, "triples") else None
    ont_triples = ont.triples((None, None, None)) if ont is not None else ont_graph  # an iterable of triples is accepted too
    kept = getattr(data_graph, "__dict__", None)
    kept = kept.setdefault(_KEPT_ATTRIBUTE, {}) if kept is not None else None
    stamp = None
    if kept is not None:
        ont_triples = list(ont_triples) if ont_triples is not None else None
        stamp = (_fingerprint(data_graph.triples((None, None, None))), _fingerprint(ont_triples) if ont_triples is not None else None)
        hit = kept.get(regimes)
        if hit is not None and hit[0] == stamp:
            return hit[1]
    from starlayer.graph.entailment.infer import DEFAULT_TIMEOUT, _delta_for, _regime_iri

    from starlayer.graph.core import StarLayerGraph

    names = frozenset(_regime_iri(r) for r in regimes)
    if ont_triples is None and type(data_graph) is StarLayerGraph:
        delta = _delta_for(data_graph, names, "hermit", DEFAULT_TIMEOUT)  # reads only: no copy of the data is needed
    else:
        from starlayer.shacl.engine.graphs import new_graph

        combined = new_graph()
        combined.extend(list(data_graph.triples((None, None, None))))
        if ont_triples is not None:
            combined.extend([tuple(to_engine(x) for x in t) for t in ont_triples])
        delta = _delta_for(combined, names, "hermit", DEFAULT_TIMEOUT)
    view = new_overlay(data_graph)
    for t in delta:
        view.add(t)
    if kept is not None:
        if regimes not in kept and len(kept) >= _KEPT_VIEWS:
            kept.pop(next(iter(kept)))
        kept[regimes] = (stamp, view)
    return view


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


def resolve_data_view(data_graph: Any, shapes_graph: Any = None, *, inference: Any = None, ont_graph: Any = None) -> Any:
    """The data view ``validate`` should run on: ``data_graph`` closed under the regimes the shapes graph declares with
    ``sh:entailment`` plus those of ``inference`` (a regime IRI or an iterable of them; names such as ``'rdfs'`` are not
    accepted). ``data_graph`` itself when there are none."""
    data_graph = engine_view(data_graph)
    shapes = engine_view(shapes_graph) if shapes_graph is not None else data_graph
    regimes = declared_regimes(shapes) | normalise_regimes(inference)
    return entailed_view(data_graph, regimes, ont_graph)


__all__ = ["declared_regimes", "entailed_view", "normalise_regimes", "resolve_data_view"]
