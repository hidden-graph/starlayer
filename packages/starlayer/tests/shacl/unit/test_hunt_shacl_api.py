"""Regression tests from the SHACL API bug hunt (public API, reports, plans, shapes graphs, modules)."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph.oxgraph.core import StarLayerGraph
from starlayer.shacl import validate

pytestmark = pytest.mark.filterwarnings("ignore")

PFX = (
    "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://e/> . @prefix owl: <http://www.w3.org/2002/07/owl#> . "
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . "
    "@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .\n"
)
RT = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
VR = ox.NamedNode("http://www.w3.org/ns/shacl#ValidationResult")


def g(text, identifier=None):
    x = StarLayerGraph(identifier=identifier) if identifier is not None else StarLayerGraph()
    x.parse(data=PFX + text, format="turtle12")
    return x


def n_results(outcome):
    return len(list(outcome.report_graph.subjects(RT, VR)))


def test_meta_shacl_with_sh_prefixes_on_default_graph():
    sg = g("""ex:S a sh:NodeShape ; sh:targetNode ex:a ;
      sh:sparql [ sh:message "no" ; sh:prefixes ex:decl ; sh:select "SELECT $this WHERE { $this ex:p ?v }" ] .
      ex:decl a owl:Ontology ; sh:declare [ sh:prefix "ex" ; sh:namespace "http://e/" ] .""")
    d = g("ex:a ex:p 1 .")
    assert validate(d, sg, meta_shacl=True).conforms is False
