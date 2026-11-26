"""The one import rule for the OWL regimes of ``infer()`` and ``query(entailment=)`` (maintainer decision 2026-11-26): an ontology that
declares ``owl:imports`` must resolve them (``imports_loader=``) or raise ``ExecutionError`` kind ``"import"``; RDF and RDFS give imports no
meaning; ``ignore_imports=True`` skips the step. The rule itself is tested in ``test_import_resolution.py``."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.errors import ExecutionError
from starlayer.graph import ENTAILMENT, StarLayerGraph

EX = "http://example.org/"
OWL = "http://www.w3.org/2002/07/owl#"
RDF_TYPE = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
IMPORTS = ox.NamedNode(OWL + "imports")
ONTOLOGY = ox.NamedNode(OWL + "Ontology")


def n(local: str) -> ox.NamedNode:
    return ox.NamedNode(EX + local)


def ontology(iri: ox.NamedNode, *more: tuple) -> StarLayerGraph:
    g = StarLayerGraph()
    g.add((iri, RDF_TYPE, ONTOLOGY))
    for t in more:
        g.add(t)
    return g


def importing(*iris: ox.NamedNode) -> StarLayerGraph:
    g = StarLayerGraph()
    g.add((n("root"), RDF_TYPE, ONTOLOGY))
    for iri in iris:
        g.add((n("root"), IMPORTS, iri))
    return g


class Loader:
    def __init__(self, graphs: dict) -> None:
        self.graphs = graphs
        self.calls: list = []

    def __call__(self, iri):
        self.calls.append(iri)
        return self.graphs.get(iri)


# ---- infer() and query(entailment=) -----------------------------------------------------------------------------------

OWL_RL = ENTAILMENT["OWL-RDF-Based"]


@pytest.mark.parametrize("regime", [ENTAILMENT.RDF, ENTAILMENT.RDFS])
def test_rdf_and_rdfs_entailment_give_imports_no_meaning(regime):
    g = importing(n("a"))
    g.add((n("x"), n("p"), n("y")))
    assert g.infer(regime) is not None  # no error: neither a loader nor ignore_imports needed


def test_infer_with_an_owl_regime_raises_for_an_unresolved_import_and_accepts_a_loader():
    pytest.importorskip("owlrl")
    g = importing(n("a"))
    g.add((n("Dog"), ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#subClassOf"), n("Animal")))
    with pytest.raises(ExecutionError) as caught:
        g.infer(OWL_RL)
    assert caught.value.kind == "import" and caught.value.unresolved == (n("a"),)
    assert g.infer(OWL_RL, ignore_imports=True) is not None
    loader = Loader({n("a"): ontology(n("a"), (n("fido"), RDF_TYPE, n("Dog")))})
    result = g.infer(OWL_RL, imports_loader=loader)
    assert (n("fido"), RDF_TYPE, n("Animal")) in result  # the imported fact took part in the reasoning
    assert (n("fido"), RDF_TYPE, n("Dog")) not in result  # and is not part of the result


def test_query_with_an_owl_regime_raises_for_an_unresolved_import():
    pytest.importorskip("owlrl")
    g = importing(n("a"))
    with pytest.raises(ExecutionError) as caught:
        g.query("ASK { ?s ?p ?o }", entailment=OWL_RL)
    assert caught.value.kind == "import"
    assert g.query("ASK { ?s ?p ?o }", entailment=OWL_RL, ignore_imports=True).askAnswer is True
