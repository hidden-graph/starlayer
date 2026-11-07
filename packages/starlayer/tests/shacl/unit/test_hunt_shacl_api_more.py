"""More regression tests from the SHACL API bug hunt (meta_shacl prefixes, apply_rules options, modules, reports)."""

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


def g(text, identifier=None):
    x = StarLayerGraph(identifier=identifier) if identifier is not None else StarLayerGraph()
    x.parse(data=PFX + text, format="turtle12")
    return x


_XA = '"http://ex/"^^xsd:anyURI'


def test_meta_shacl_prefix_through_owl_imports():
    sg = g(
        f"""<http://ex/Main> a owl:Ontology ; owl:imports <http://ex/Lib> ; sh:declare [ sh:prefix "a" ; sh:namespace {_XA} ] .
<http://ex/Lib> a owl:Ontology ; sh:declare [ sh:prefix "lib" ; sh:namespace "http://lib/"^^xsd:anyURI ] .
<http://ex/S> a sh:NodeShape ; sh:targetNode <http://ex/n> ;
  sh:sparql [ sh:prefixes <http://ex/Main> ; sh:select "SELECT $this WHERE {{ $this lib:p ?x }}" ; sh:message "m" ] .""",
        ox.NamedNode("http://ex/g"),
    )
    d = g("<http://ex/n> <http://lib/p> 1 .")
    assert validate(d, sg, ignore_imports=True, meta_shacl=True).conforms is False


def test_meta_shacl_prefix_from_shapes_graph_declare_without_sh_prefixes():
    sg = g(
        f"""<http://ex/G> a sh:ShapesGraph ; sh:declare [ sh:prefix "zz" ; sh:namespace {_XA} ] .
<http://ex/S> a sh:NodeShape ; sh:targetNode <http://ex/n> ;
  sh:sparql [ sh:select "SELECT $this WHERE {{ $this zz:p ?x }}" ; sh:message "m" ] .""",
        ox.NamedNode("http://ex/g"),
    )
    d = g("<http://ex/n> <http://ex/p> 1 .")
    assert validate(d, sg, meta_shacl=True).conforms is False


# --- imports and the shapes graph's identity


def test_validate_without_shapes_graph_resolves_imports_with_loader():
    imported = "ex:T a sh:NodeShape ; sh:targetNode ex:a ; sh:nodeKind sh:Literal ."
    data = g("ex:a ex:p 1 . <http://e/onto> a owl:Ontology ; owl:imports <http://e/imp> .")
    loader = lambda iri: g(imported)  # noqa: E731
    assert validate(data, shapes_graph_loader=loader).conforms is False
    assert validate(data, data, shapes_graph_loader=loader).conforms is False


def test_validate_without_shapes_graph_unresolved_import_raises():
    data = g("ex:a ex:p 1 . <http://e/onto> a owl:Ontology ; owl:imports <http://e/imp> .")
    with pytest.raises(ValueError):
        validate(data)


def test_used_shapes_graph_kept_when_imports_resolved_with_loader():
    shapes = g(
        "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:class ex:C . <http://e/shapesG> owl:imports <http://e/imp> .",
        ox.NamedNode("http://e/shapesG"),
    )
    loader = lambda iri: g("ex:T a sh:NodeShape ; sh:targetNode ex:a ; sh:minCount 1 .")  # noqa: E731
    data = g("ex:a ex:p 1 .")
    used = ox.NamedNode("http://www.w3.org/ns/shacl#usedShapesGraph")
    r = validate(data, shapes, shapes_graph_loader=loader)
    assert [o for _, _, o in r.report_graph.triples((None, used, None))] == [ox.NamedNode("http://e/shapesG")]
