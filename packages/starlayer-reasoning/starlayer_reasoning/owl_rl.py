"""The OWL 2 RL closure of a graph, computed by ``owlrl`` on an rdflib copy; what it adds comes back as pyoxigraph triples."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from starlayer.graph import rdflib_bridge as bridge

_ERROR_NS = "http://www.daml.org/2002/03/agents/agent-ont#"


def _semantics(rdfs: bool, owl_rl: bool) -> Any:
    import owlrl

    class _NoHiddenSameAsRDFSSemantics(owlrl.RDFSClosure.RDFS_Semantics):
        def one_time_rules(self) -> None:
            pass

    if rdfs and owl_rl:
        return owlrl.RDFS_OWLRL_Semantics
    if owl_rl:
        return owlrl.OWLRL_Semantics
    if rdfs:
        return _NoHiddenSameAsRDFSSemantics
    raise ValueError("owl_rl.delta needs rdfs or owl_rl")


def _drop_repeated_error_messages(graph: Any) -> None:
    """Keep one ``err:ErrorMessage`` node per message text (each owlrl pass mints a fresh blank node for the same inconsistency)."""
    from rdflib import RDF, BNode, URIRef

    message_class = URIRef(_ERROR_NS + "ErrorMessage")
    error = URIRef(_ERROR_NS + "error")
    seen = set()
    for node in sorted(graph.subjects(RDF.type, message_class), key=str):
        if not isinstance(node, BNode):
            continue
        key = tuple(sorted(str(o) for o in graph.objects(node, error)))
        if key in seen:
            graph.remove((node, None, None))
        else:
            seen.add(key)


def delta(triples: Iterable[tuple[Any, Any, Any]], *, rdfs: bool, owl_rl: bool) -> set[tuple[Any, Any, Any]]:
    """The triples owlrl adds, as pyoxigraph triples (generalized ones dropped)."""
    import owlrl
    from rdflib import Graph

    semantics = _semantics(rdfs, owl_rl)
    before = bridge.rdflib_graph(triples, decompose=True)
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
    added = (t for t in expanded if t not in before_set)
    return set(bridge.legal_rdf_triples(bridge.drop_decomposition(added, bridge.decomposition_nodes(before))))
