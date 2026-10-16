"""
SHACL validate()/apply_rules() against graphs backed by oxrdflib's
OxigraphStore in rdf-1.2 native mode (in-process, no server).

Regression: with meta_shacl on, a blank node in the shapes graph (e.g. an
inline sh:property [ ... ]) that appears in a violation report is looked up
via the find_node_named_graph fallback in starlayer.shacl.validator. A graph
built with no explicit identifier lives in the store's true default graph,
which that fallback's "GRAPH ?g" discovery query can never enumerate - it
used to raise LookupError.
"""
import pytest
from rdflib import RDF, BNode, Namespace
from starlayer.graph.graph import StarLayerGraph
from starlayer.shacl import apply_rules, validate

pyoxigraph = pytest.importorskip("pyoxigraph")
OxigraphStore = pytest.importorskip("oxrdflib").OxigraphStore

EX = Namespace("http://ex/")

SHAPES = """@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://ex/> .
ex:S a sh:NodeShape ; sh:targetClass ex:P ;
  sh:property [ sh:path ex:name ; sh:minCount 1 ] ;
  sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:seen ; sh:object ex:yes ] ."""


def _graph() -> StarLayerGraph:
    return StarLayerGraph(store=OxigraphStore(store=pyoxigraph.Store()), backend="rdf-1.2")


@pytest.mark.parametrize("bnode_focus", [False, True], ids=["uri_focus", "bnode_focus"])
@pytest.mark.parametrize("meta_shacl", [True, False], ids=["meta_on", "meta_off"])
def test_validate_and_apply_rules_with_default_graph_store(bnode_focus, meta_shacl):
    shapes, data = _graph(), _graph()
    shapes.parse(data=SHAPES, format="turtle")
    data.add((BNode() if bnode_focus else EX.x, RDF.type, EX.P))  # violates minCount

    result = validate(data, shapes, meta_shacl=meta_shacl)
    assert result.conforms is False

    rules = apply_rules(data, shapes, meta_shacl=meta_shacl)
    assert len(rules.inferred_graph) == 1
