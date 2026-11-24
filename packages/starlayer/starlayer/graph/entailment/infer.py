"""``infer()``: RDF and RDFS closure natively; OWL-RL and OWL-DL through the ``starlayer-reasoning`` package.

The RDF and RDFS regimes are computed on pyoxigraph terms (``rdfs_closure.py``). The OWL-RL and combined regimes (``owlrl``) and
OWL-DL (HermiT, rustdl) work on rdflib graphs, so they live in ``starlayer-reasoning``, which this module calls only for those
regimes and which must be installed for them.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

import pyoxigraph as ox

from starlayer.graph import terms
from starlayer.graph.entailment import (
    D_REGIME,
    ENTAILMENT,
    KNOWN_REGIMES,  # noqa: F401  (re-exported)
    OWL_DIRECT_REGIME,
    OWL_RL_REGIME,
    RDF_REGIME,
    RDFS_REGIME,
    SUPPORTED_REGIMES,
)
from starlayer.graph.entailment.rdfs_closure import rdfs_delta

VALID_INFER_RETURN_MODES = frozenset({"full", "delta", "in-place"})
#: the default ``timeout=`` of ``infer()`` for OWL-DL (seconds); the same value as ``starlayer_reasoning``'s own default
DEFAULT_TIMEOUT = 120.0

#: rdf:_n for a positive decimal integer without leading zeros (RDF Semantics, container membership properties); ASCII digits only
_CONTAINER_MEMBERSHIP = re.compile(re.escape(terms.RDF) + r"_[1-9][0-9]*")
_RDF = terms.RDF
_RDF_AXIOMATIC = tuple(ox.NamedNode(_RDF + n) for n in ("type", "subject", "predicate", "object", "reifies", "first", "rest", "value"))


def _regime_iri(x: Any) -> str:
    return x.value if isinstance(x, ox.NamedNode) else str(x)


def _reasoning() -> Any:
    """The ``starlayer_reasoning`` package, or an ``ImportError`` that says how to install it."""
    try:
        import starlayer_reasoning
    except ImportError as exc:
        raise ImportError(
            "infer() with the OWL-RL or OWL-DL regimes needs the starlayer-reasoning package: `pip install starlayer-reasoning`"
        ) from exc
    return starlayer_reasoning


def _rdf_delta(g: Any) -> set[tuple[Any, Any, Any]]:
    """RDF entailment natively: rdfD2 (each predicate used is an ``rdf:Property``) and the RDF axiomatic triples for terms present.
    rdfD1/rdfD1a (datatype well-typing) are a deliberate scope reduction, as in the old code."""
    delta: set = set()
    existing = set(g.triples())
    all_terms: set = set()
    seen_predicates: set = set()
    fresh: list = []
    rdf_type, rdf_property = terms.RDF_TYPE, ox.NamedNode(_RDF + "Property")

    def add(candidate: tuple) -> None:
        if candidate not in existing and candidate not in delta:
            delta.add(candidate)
            fresh.append(candidate)

    def consider(triples: Iterable[tuple]) -> None:
        new_terms = []
        for s, p, o in triples:
            for t in (s, p, o):
                if t not in all_terms:
                    all_terms.add(t)
                    new_terms.append(t)
            if p not in seen_predicates:
                seen_predicates.add(p)
                add((p, rdf_type, rdf_property))
        for t in new_terms:
            if t in _RDF_AXIOMATIC:
                add((t, rdf_type, rdf_property))
            elif t == terms.RDF_NIL:
                add((t, rdf_type, ox.NamedNode(_RDF + "List")))
            elif isinstance(t, ox.NamedNode) and _CONTAINER_MEMBERSHIP.fullmatch(t.value):
                add((t, rdf_type, rdf_property))

    consider(list(existing))
    while fresh:
        batch, fresh[:] = list(fresh), []
        consider(batch)
    return delta


def _owl_direct_delta(g: Any, engine: str, timeout: Any) -> set[tuple[Any, Any, Any]]:
    if engine not in ("hermit", "rustdl"):
        raise ValueError(f"Unsupported engine {engine!r}; expected one of ['hermit', 'rustdl']")
    return _reasoning().owl_direct_delta(g.triples(), engine=engine, timeout=timeout)


def _delta_for(g: Any, regimes: frozenset[str], engine: str, timeout: Any) -> set[tuple[Any, Any, Any]]:
    """The triples ``regimes`` entail that ``g`` does not hold: no input triple, no duplicate.

    A set with ``OWL-Direct`` and other regimes is the Direct delta (``engine``, ``timeout``) first, then the delta of the remaining
    regimes over ``g`` plus the Direct delta, so RDFS / OWL-RL rules see the subclass and type triples the DL reasoner found; the result is
    the union of the two. It is the entailments of every regime in the set with the others also seeing what OWL-Direct inferred, not a
    fixpoint over all the regimes (what RDFS or OWL-RL derive is not given back to the DL reasoner). Direct runs first because it is the
    one run that is slow and is given the data as it is, without the RDFS axiomatic triples; the cheap rule closures then run on its
    output. The SHACL engine uses this; ``infer()`` itself rejects the combination (``infer`` below)."""
    if OWL_DIRECT_REGIME in regimes:
        rest = regimes - {OWL_DIRECT_REGIME}
        if not rest:
            return _owl_direct_delta(g, engine, timeout)
        # the input may already be closed under RDFS (the final pass of ``apply_rules`` reads a view of an entailed copy): the closure's
        # vocabulary triples (rdfs:Class subClassOf rdfs:Resource, every node typed rdfs:Resource, ...) make owlready2 fail with an
        # inheritance cycle and say nothing about the ontology, so the DL reasoner is not given them
        direct = _owl_direct_delta(_without_rdf_vocabulary(g), engine, timeout)
        from starlayer.graph import core

        seen = core.StarLayerGraph()
        seen.extend(list(g.triples()) + list(direct))
        # the data's own triples are never in a delta, and the rest's delta is read over data + direct, so subtract direct too
        return direct | (_rules_delta(seen, rest) - direct)
    return _rules_delta(g, regimes)


_RDFS_NS = "http://www.w3.org/2000/01/rdf-schema#"
_RESOURCE = ox.NamedNode(_RDFS_NS + "Resource")


class _without_rdf_vocabulary:
    """``g`` without the triples about the RDF and RDFS vocabulary itself and without ``x rdf:type rdfs:Resource``."""

    def __init__(self, g: Any) -> None:
        self._g = g

    def triples(self) -> Iterable[tuple[Any, Any, Any]]:
        for t in self._g.triples():
            s, p, o = t
            if isinstance(s, ox.NamedNode) and s.value.startswith((_RDF, _RDFS_NS)):
                continue
            if p == terms.RDF_TYPE and o == _RESOURCE:
                continue
            yield t


def _rules_delta(g: Any, regimes: frozenset[str]) -> set[tuple[Any, Any, Any]]:
    """The delta of the RDF, RDFS and OWL-RL regimes in ``regimes`` (none of them OWL-Direct)."""
    delta: set = set()
    if RDF_REGIME in regimes:
        delta |= _rdf_delta(g)
    rest = regimes - {RDF_REGIME}
    if rest == {RDFS_REGIME}:
        delta |= rdfs_delta(g.triples())
    elif rest:
        delta |= _reasoning().owl_rl_delta(g.triples(), rdfs=RDFS_REGIME in rest, owl_rl=OWL_RL_REGIME in rest)
    return delta


def infer(g: Any, entailment: Any = ENTAILMENT.RDFS, *, mode: str = "full", target_graph: Any = None, engine: str = "hermit",
          timeout: Any = DEFAULT_TIMEOUT) -> Any:
    """Materialize an RDFS / RDF / OWL-RL / OWL-DL entailment closure. See ``StarLayerGraph.infer`` for the contract.

    ``mode`` "full" returns a new graph with the originals plus the entailed triples, "delta" one with only the new triples,
    "in-place" adds the new triples to ``g`` and returns it. ``entailment`` is a regime IRI (``NamedNode`` or ``str``) or an
    iterable of them. ``target_graph`` must be an ``StarLayerGraph`` / ``StarLayerDataset``.
    """
    if mode not in VALID_INFER_RETURN_MODES:
        raise ValueError(f"mode must be one of {sorted(VALID_INFER_RETURN_MODES)}, got {mode!r}")
    regimes = frozenset({_regime_iri(entailment)}) if isinstance(entailment, (str, ox.NamedNode)) else frozenset(_regime_iri(e) for e in entailment)
    if not regimes:
        raise ValueError("entailment must name at least one entailment regime IRI.")
    unsupported = regimes - SUPPORTED_REGIMES
    if unsupported:
        message = f"Unsupported entailment regime(s) {sorted(unsupported)!r} - expected a combination of {sorted(SUPPORTED_REGIMES)!r}."
        if D_REGIME in unsupported:
            message += " ENTAILMENT.D (D-Entailment) is a recognized regime IRI but not implemented."
        raise ValueError(message)
    if OWL_DIRECT_REGIME in regimes and len(regimes) > 1:
        raise ValueError(f"Unsupported entailment regime combination {sorted(regimes)!r}: OWL-Direct cannot be combined with another regime in infer() (the SHACL engine combines them).")
    direct = regimes == frozenset({OWL_DIRECT_REGIME})
    if not direct and engine != "hermit":
        raise ValueError(f"engine={engine!r} is only meaningful for entailment=ENTAILMENT['OWL-Direct'] (got entailment={sorted(regimes)!r}) - omit engine= for owlrl-backed regimes.")
    if not direct and timeout != DEFAULT_TIMEOUT:
        raise ValueError(f"timeout={timeout!r} is only meaningful for entailment=ENTAILMENT['OWL-Direct'] (got entailment={sorted(regimes)!r}) - omit timeout= for owlrl-backed regimes.")

    if mode == "in-place":
        if target_graph is not None:
            raise ValueError("target_graph is meaningless with mode='in-place' - it mutates self directly.")
        g.extend(_delta_for(g, regimes, engine, timeout))
        return g
    if target_graph is None:
        target_graph = g.empty_like()
    elif not hasattr(target_graph, "extend") or not hasattr(target_graph, "store"):
        raise TypeError(f"infer() target_graph must be an StarLayerGraph or StarLayerDataset, not {type(target_graph).__name__}.")
    delta = _delta_for(g, regimes, engine, timeout)
    target_graph.extend(list(g.triples()) + list(delta) if mode == "full" else delta)
    return target_graph
