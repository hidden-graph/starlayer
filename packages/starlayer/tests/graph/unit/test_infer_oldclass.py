"""
tests/unit/test_infer.py

Coverage for StarLayerGraph.infer(), which formalizes the manual
owlrl.DeductiveClosure workflow shown in docs/guides/02b-graphs-inferencing.ipynb
into real API. Per this project's own testing discipline (starlayer.sparql/CLAUDE.md:
"any new query/update shape needs an execution-comparison test, not just a
structural one"), every test here compares infer()'s output against owlrl
itself run directly - owlrl is the oracle, since plain rdflib has no
entailment of its own to compare against.

Requires the `reasoning` extra: pip install -e ".[reasoning]"
"""

import pytest
from rdflib import RDFS, URIRef
from starlayer.graph import RDF, Namespace, StarLayerGraph

try:
    import owlrl
    _OWLRL_AVAILABLE = True
except ImportError:
    _OWLRL_AVAILABLE = False

owlrl_extra = pytest.mark.skipif(
    not _OWLRL_AVAILABLE,
    reason='owlrl not installed — install with: pip install -e ".[reasoning]"',
)

EX = Namespace("http://example.org/")
REIFIES = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")



def _expand_to_fixpoint(semantics, graph):
    """owlrl to a fixpoint. One pass is not a closure (its axiomatic triples are typed rdfs:Resource only on the next
    pass), and infer() repeats it until nothing changes (GitHub issue #97)."""
    for _ in range(8):
        size = len(graph)
        owlrl.DeductiveClosure(semantics).expand(graph)
        if len(graph) == size:
            break


def _rdfs_graph() -> StarLayerGraph:
    g = StarLayerGraph()
    g.bind("ex", EX)
    g.add((EX.Dog, RDFS.subClassOf, EX.Animal))
    g.add((EX.fido, RDF.type, EX.Dog))
    return g
















@owlrl_extra
class TestInferInPlace:


    def test_native_self_no_longer_blocked_by_mode_itself(self) -> None:
        # mode="in-place" only ever adds the delta into self, never a
        # re-decomposed copy of self's own data - so it no longer needs to
        # refuse a native self outright. No live store is configured here,
        # so this still fails, but on the actual native operation (a
        # RuntimeError about the missing store), not a NotImplementedError
        # about entailment/mode - confirming the mode-level restriction is
        # gone.
        g = StarLayerGraph(backend="rdf-1.2")
        with pytest.raises(RuntimeError, match="store"):
            g.infer(mode="in-place")



