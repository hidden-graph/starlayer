"""Entailment regimes for the SHACL engine: ``entailed_view`` and ``resolve_data_view``.

The closure is the project's own (``StarLayerGraph.infer``: the RDFS closure by ``owlrl``'s ``RDFS_Semantics``, the OWL 2 RL
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

from rdflib import URIRef

from starlayer.graph.graph.entailment_regimes import ENTAILMENT, SUPPORTED_REGIMES
from starlayer.shacl_engine.rules import new_overlay
from starlayer.shacl_engine.terms import (
    RDF,
    SH,
    engine_view,
    from_engine,
    from_engine_triple,
    to_engine_triple,
)

_ALIASES = {
    "none": None,
    "rdf": ENTAILMENT.RDF,
    "rdfs": ENTAILMENT.RDFS,
    "owlrl": ENTAILMENT["OWL-RDF-Based"],
    "both": None,  # expanded below
}
_NATIVE = {ENTAILMENT.RDF, ENTAILMENT.RDFS, ENTAILMENT["OWL-RDF-Based"]}


def normalise_regimes(regime: Any) -> frozenset:
    """Regime IRIs for ``regime``: ``None`` / ``'none'`` (no entailment), a regime IRI, one of ``'rdf'``, ``'rdfs'``,
    ``'owlrl'``, ``'both'`` (rdfs + owlrl), or an iterable of these. An unsupported regime raises ``ValueError``."""
    if regime is None:
        return frozenset()
    if isinstance(regime, (str, URIRef)):
        items: Iterable = [regime]
    else:
        items = regime
    out: set = set()
    for item in items:
        if isinstance(item, str) and not isinstance(item, URIRef):
            key = item.lower()
            if key == "both":
                out |= {ENTAILMENT.RDFS, ENTAILMENT["OWL-RDF-Based"]}
                continue
            if key not in _ALIASES:
                raise ValueError(f"Unsupported entailment regime {item!r}")
            if _ALIASES[key] is not None:
                out.add(_ALIASES[key])
        else:
            out.add(item)
    unsupported = {r for r in out if r not in _NATIVE}
    if unsupported:
        raise ValueError(f"Unsupported entailment regime(s) {sorted(map(str, unsupported))!r}")
    return frozenset(out)


def entailed_view(data_graph: Any, regime: Any = "rdfs", ont_graph: Any = None) -> Any:
    """``data_graph`` closed under ``regime``, as an overlay; with no regime, ``data_graph`` itself. Never mutates
    ``data_graph`` or ``ont_graph``."""
    regimes = normalise_regimes(regime)
    data_graph = engine_view(data_graph)
    if not regimes:
        return data_graph
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph, legal_rdf_triples

    data_graph = engine_view(data_graph)
    combined = StarLayerGraph()
    for t in data_graph.triples((None, None, None)):  # engine terms -> the closure's rdflib terms (the boundary)
        combined.add(from_engine_triple(t))
    if ont_graph is not None:
        for t in ont_graph.triples((None, None, None)) if hasattr(ont_graph, "triples") else ont_graph:
            combined.add(t)
    delta = combined.infer(entailment=regimes, mode="delta")
    view = new_overlay(data_graph)
    for t in legal_rdf_triples(delta):
        view.add(to_engine_triple(tuple(t)))
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
        regime = from_engine(o)
        if regime not in SUPPORTED_REGIMES:
            raise ValueError(f"Unsupported entailment regime {str(regime)!r}")
        out.add(regime)
    return frozenset(out)


def resolve_data_view(data_graph: Any, shapes_graph: Any = None, *, inference: Any = None, ont_graph: Any = None) -> Any:
    """The data view ``validate`` should run on: ``data_graph`` closed under the regimes the shapes graph declares with
    ``sh:entailment`` plus those of ``inference`` (a regime IRI, ``'rdfs'`` / ``'owlrl'`` / ``'both'`` / ``'none'``, or an
    iterable). ``data_graph`` itself when there are none."""
    data_graph = engine_view(data_graph)
    shapes = engine_view(shapes_graph) if shapes_graph is not None else data_graph
    regimes = declared_regimes(shapes) | normalise_regimes(inference)
    return entailed_view(data_graph, regimes, ont_graph)


__all__ = ["declared_regimes", "entailed_view", "normalise_regimes", "resolve_data_view"]
