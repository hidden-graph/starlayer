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

import pyoxigraph as ox

from starlayer.graph.oxgraph.helpers.entailment import ENTAILMENT, SUPPORTED_REGIMES
from starlayer.shacl_engine.rules import new_overlay
from starlayer.shacl_engine.terms import (
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
    back as pyoxigraph ``NamedNode``s (an rdflib ``URIRef`` or an IRI string is accepted)."""
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


def entailed_view(data_graph: Any, regime: Any = ENTAILMENT.RDFS, ont_graph: Any = None) -> Any:
    """``data_graph`` closed under ``regime``, as an overlay; with no regime, ``data_graph`` itself. Never mutates
    ``data_graph`` or ``ont_graph``."""
    regimes = normalise_regimes(regime)
    data_graph = engine_view(data_graph)
    if not regimes:
        return data_graph
    from starlayer.shacl_engine.graphs import new_graph

    combined = new_graph()
    combined.extend(list(data_graph.triples((None, None, None))))
    if ont_graph is not None:
        ont_triples = engine_view(ont_graph, "ontology graph").triples((None, None, None)) if hasattr(ont_graph, "triples") else ont_graph
        combined.extend([tuple(to_engine(x) for x in t) for t in ont_triples])
    delta = combined.infer(entailment=regimes, mode="delta")
    view = new_overlay(data_graph)
    for t in delta.triples((None, None, None)):
        view.add(t)
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
