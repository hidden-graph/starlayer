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


def importing(*iris: ox.NamedNode, **kw) -> StarLayerGraph:
    g = StarLayerGraph(**kw)
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


# ---- the graph's own settings (maintainer decision 2026-11-26) --------------------------------------------------------------

SUBCLASS = ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#subClassOf")


def _dog_world(**kw) -> tuple[StarLayerGraph, Loader]:
    loader = Loader({n("a"): ontology(n("a"), (n("fido"), RDF_TYPE, n("Dog")))})
    g = importing(n("a"), **kw)
    g.add((n("Dog"), SUBCLASS, n("Animal")))
    return g, loader


def test_infer_and_query_use_the_loader_the_graph_carries():
    pytest.importorskip("owlrl")
    g, loader = _dog_world()
    g.imports_loader = loader
    assert (n("fido"), RDF_TYPE, n("Animal")) in g.infer(OWL_RL)
    assert g.query("ASK { <http://example.org/fido> a <http://example.org/Animal> }", entailment=OWL_RL).askAnswer is True
    assert loader.calls == [n("a")]  # one resolution served both, kept until the graph changes


def test_the_call_overrides_the_graph_setting():
    pytest.importorskip("owlrl")
    g, loader = _dog_world()
    g.imports_loader = loader
    other = Loader({n("a"): ontology(n("a"), (n("rex"), RDF_TYPE, n("Dog")))})
    result = g.infer(OWL_RL, imports_loader=other)
    assert (n("rex"), RDF_TYPE, n("Animal")) in result and (n("fido"), RDF_TYPE, n("Animal")) not in result
    assert g.infer(OWL_RL, ignore_imports=True) is not None  # beats the graph's loader
    flagged, _ = _dog_world(ignore_imports=True)
    with pytest.raises(ExecutionError):
        flagged.infer(OWL_RL, ignore_imports=False)  # and beats the graph's flag


def test_a_graph_that_ignores_its_imports_skips_the_step():
    pytest.importorskip("owlrl")
    g, _ = _dog_world(ignore_imports=True)
    assert g.infer(OWL_RL) is not None
    assert g.query("ASK { ?s ?p ?o }", entailment=OWL_RL).askAnswer is True


def test_a_changed_loader_is_a_different_entailed_copy():
    pytest.importorskip("owlrl")
    g, loader = _dog_world()
    ask = "ASK { <http://example.org/rex> a <http://example.org/Animal> }"
    g.imports_loader = loader
    assert g.query(ask, entailment=OWL_RL).askAnswer is False
    g.imports_loader = Loader({n("a"): ontology(n("a"), (n("rex"), RDF_TYPE, n("Dog")))})
    assert g.query(ask, entailment=OWL_RL).askAnswer is True  # the same store, other imported triples: not the kept copy


def test_rdf_and_rdfs_never_ask_the_loader():
    loader = Loader({})
    g = importing(n("a"), imports_loader=loader)
    g.infer(ENTAILMENT.RDFS)
    g.query("ASK { ?s ?p ?o }", entailment=ENTAILMENT.RDFS)
    assert loader.calls == []
