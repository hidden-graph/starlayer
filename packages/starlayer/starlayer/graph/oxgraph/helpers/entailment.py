"""``infer()``: RDFS / RDF / OWL-RL (owlrl) and OWL-DL (HermiT, rustdl) closure over an ``StarLayerGraph`` / ``StarLayerDataset``.

Ported from ``StarLayerGraph.infer`` and ``graph/graph/entailment_regimes.py``. The RDF regime is computed natively on pyoxigraph
terms. owlrl and the OWL-DL bridges work on rdflib graphs, so the store is copied to one inside the call
(``_rdflib_bridge``) and the delta is converted back. The OWL-DL engines (``graph/graph/owl_dl*.py``, ``_timeout.py``) are
reused as they are, lazily, with their optional-dependency errors and their subprocess timeout.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pyoxigraph as ox

from starlayer.graph.oxgraph import _rdflib_bridge as bridge
from starlayer.graph.oxgraph import terms

VALID_INFER_RETURN_MODES = frozenset({"full", "delta", "in-place"})
#: same value as ``graph.graph._timeout.DEFAULT_TIMEOUT_SECONDS`` (tested); not imported so the wrapper stays rdflib-free
DEFAULT_TIMEOUT = 120.0

_ENTAILMENT_BASE = "http://www.w3.org/ns/entailment/"


class _EntailmentNamespace:
    """``ENTAILMENT.RDFS``, ``ENTAILMENT["OWL-Direct"]``: the regime IRIs of the SPARQL 1.2 Entailment Regimes spec, as
    ``NamedNode``s. Same IRIs as ``graph/graph/entailment_regimes.py`` (which holds an rdflib ``Namespace``)."""

    def __getitem__(self, name: str) -> ox.NamedNode:
        return ox.NamedNode(_ENTAILMENT_BASE + name)

    def __getattr__(self, name: str) -> ox.NamedNode:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]


ENTAILMENT = _EntailmentNamespace()
RDF_REGIME = ENTAILMENT.RDF.value
RDFS_REGIME = ENTAILMENT.RDFS.value
D_REGIME = ENTAILMENT.D.value
OWL_RL_REGIME = ENTAILMENT["OWL-RDF-Based"].value
OWL_DIRECT_REGIME = ENTAILMENT["OWL-Direct"].value
KNOWN_REGIMES = frozenset({RDF_REGIME, RDFS_REGIME, D_REGIME, OWL_RL_REGIME, OWL_DIRECT_REGIME})
SUPPORTED_REGIMES = frozenset({RDF_REGIME, RDFS_REGIME, OWL_RL_REGIME, OWL_DIRECT_REGIME})

_OWLRL_ERROR_NS = "http://www.daml.org/2002/03/agents/agent-ont#"
_RDF = terms.RDF
_RDF_AXIOMATIC = tuple(ox.NamedNode(_RDF + n) for n in ("type", "subject", "predicate", "object", "reifies", "first", "rest", "value"))


def _regime_iri(x: Any) -> str:
    return x.value if isinstance(x, ox.NamedNode) else str(x)


def _resolve_owlrl_semantics(regimes: frozenset[str]) -> Any:
    try:
        import owlrl
    except ImportError as exc:
        raise ImportError(
            "infer() requires the optional 'owlrl' dependency - install via `pip install starlayer[reasoning]` "
            "(or `pip install owlrl` directly)."
        ) from exc

    class _NoHiddenSameAsRDFSSemantics(owlrl.RDFSClosure.RDFS_Semantics):
        def one_time_rules(self) -> None:
            pass

    by_regime = {
        frozenset({RDFS_REGIME}): _NoHiddenSameAsRDFSSemantics,
        frozenset({OWL_RL_REGIME}): owlrl.OWLRL_Semantics,
        frozenset({RDFS_REGIME, OWL_RL_REGIME}): owlrl.RDFS_OWLRL_Semantics,
    }
    semantics = by_regime.get(regimes)
    if semantics is None:
        raise ValueError(f"Unsupported entailment regime combination {sorted(regimes)!r}; expected one of {[sorted(k) for k in by_regime]}")
    return semantics


def _drop_repeated_error_messages(graph: Any) -> None:
    """Keep one ``err:ErrorMessage`` node per message text (each owlrl pass mints a fresh blank node for the same inconsistency)."""
    from rdflib import RDF, BNode, URIRef

    message_class = URIRef(_OWLRL_ERROR_NS + "ErrorMessage")
    error = URIRef(_OWLRL_ERROR_NS + "error")
    seen = set()
    for node in sorted(graph.subjects(RDF.type, message_class), key=str):
        if not isinstance(node, BNode):
            continue
        key = tuple(sorted(str(o) for o in graph.objects(node, error)))
        if key in seen:
            graph.remove((node, None, None))
        else:
            seen.add(key)


def _owlrl_delta(g: Any, regimes: frozenset[str]) -> set[tuple[Any, Any, Any]]:
    """The triples owlrl adds, as pyoxigraph triples (generalized ones dropped)."""
    semantics = _resolve_owlrl_semantics(regimes)
    import owlrl
    from rdflib import Graph

    before = bridge.rdflib_graph(g.triples(), decompose=True)
    expanded = Graph()
    for t in before:
        expanded.add(t)
    # One owlrl pass is not a closure (GitHub issue #97): repeat to a fixpoint.
    for _ in range(8):
        size = len(expanded)
        owlrl.DeductiveClosure(semantics).expand(expanded)
        _drop_repeated_error_messages(expanded)
        if len(expanded) == size:
            break
    before_set = set(before)
    return set(bridge.legal_rdf_triples(t for t in expanded if t not in before_set))


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
            elif isinstance(t, ox.NamedNode) and t.value.startswith(_RDF + "_") and t.value[len(_RDF) + 1 :].isdigit():
                add((t, rdf_type, rdf_property))

    consider(list(existing))
    while fresh:
        batch, fresh[:] = list(fresh), []
        consider(batch)
    return delta


def _owl_direct_delta(g: Any, engine: str, timeout: Any) -> set[tuple[Any, Any, Any]]:
    if engine not in ("hermit", "rustdl"):
        raise ValueError(f"Unsupported engine {engine!r}; expected one of ['hermit', 'rustdl']")
    if engine == "hermit":
        from starlayer.graph.graph import owl_dl

        classify = owl_dl.classify_owl_dl
    else:
        from starlayer.graph.graph import owl_dl_rustdl

        classify = owl_dl_rustdl.classify_owl_dl_rustdl
    _before, delta = classify(bridge.rdflib_graph(g.triples(), decompose=True), timeout=timeout)
    return set(bridge.legal_rdf_triples(delta))


def _delta_for(g: Any, regimes: frozenset[str], engine: str, timeout: Any) -> set[tuple[Any, Any, Any]]:
    if regimes == frozenset({OWL_DIRECT_REGIME}):
        return _owl_direct_delta(g, engine, timeout)
    delta: set = set()
    if RDF_REGIME in regimes:
        delta |= _rdf_delta(g)
    rest = regimes - {RDF_REGIME}
    if rest:
        delta |= _owlrl_delta(g, rest)
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
