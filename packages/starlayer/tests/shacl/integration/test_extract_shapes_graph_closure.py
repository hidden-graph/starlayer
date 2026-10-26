"""``extract_shapes_graph(include_referenced=True)``: a self-contained extract (GitHub issue #19)."""

import warnings

import pytest
from rdflib import Namespace
from starlayer.graph import StarLayerGraph
from starlayer.shacl import StarShaclSchema, validate
from starlayer.shacl.shapes_graphs import referenced_shapes

pytest.importorskip("pyshacl")
warnings.simplefilter("ignore")
EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

SHAPES = """
@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex:ModuleA a sh:ShapesGraph ; rdfs:member ex:PersonShape .
ex:ModuleB a sh:ShapesGraph ; rdfs:member ex:PersonWorksFor, ex:Unrelated .
ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ;
  sh:property ex:PersonWorksFor ;
  sh:node ex:NamedNode ;
  sh:or ( ex:OrA ex:OrB ) .
ex:PersonWorksFor a sh:PropertyShape ; sh:path ex:worksFor ; sh:minCount 1 ; sh:node ex:Company .
ex:Company a sh:NodeShape ; sh:nodeKind sh:IRI ; sh:property ex:CompanyName .
ex:CompanyName a sh:PropertyShape ; sh:path ex:name ; sh:minCount 1 ; sh:node ex:PersonShape .
ex:NamedNode a sh:NodeShape ; sh:nodeKind sh:BlankNodeOrIRI .
ex:OrA a sh:NodeShape ; sh:nodeKind sh:IRI .
ex:OrB a sh:NodeShape ; sh:nodeKind sh:Literal .
ex:Unrelated a sh:NodeShape ; sh:nodeKind sh:Literal .
"""


def _schema():
    g = StarLayerGraph()
    g.parse(data=SHAPES, format="turtle12")
    return StarShaclSchema(shacl_graph=g)


def _names(graph):
    return {s for s in graph.subjects(None, None) if s.startswith("http://example.org/")}


def test_default_leaves_named_references_dangling():
    extract = _schema().extract_shapes_graph(EX.ModuleA)
    assert EX.NamedNode not in _names(extract)
    assert EX.PersonWorksFor not in _names(extract)


def test_include_referenced_copies_the_named_shapes_transitively():
    extract = _schema().extract_shapes_graph(EX.ModuleA, include_referenced=True)
    assert {EX.PersonWorksFor, EX.Company, EX.CompanyName, EX.NamedNode, EX.OrA, EX.OrB} <= _names(extract)
    assert EX.Unrelated not in _names(extract)  # nothing refers to it


def test_a_cycle_through_the_references_terminates():
    # PersonShape -> PersonWorksFor -> Company -> CompanyName -> PersonShape
    extract = _schema().extract_shapes_graph(EX.ModuleA, include_referenced=True)
    assert (EX.CompanyName, SH.node, EX.PersonShape) in extract


def test_the_extract_validates_on_its_own():
    extract = _schema().extract_shapes_graph(EX.ModuleA, include_referenced=True)
    data = StarLayerGraph()
    data.parse(data="@prefix ex: <http://example.org/> . ex:alice a ex:Person ; ex:worksFor ex:acme .", format="turtle12")
    result = validate(data, extract, meta_shacl=False)
    assert result.conforms is False  # acme has no ex:name: the referenced Company shape applied


def test_the_extract_without_the_option_cannot_be_validated_standalone():
    extract = _schema().extract_shapes_graph(EX.ModuleA)
    data = StarLayerGraph()
    data.parse(data="@prefix ex: <http://example.org/> . ex:alice a ex:Person .", format="turtle12")
    with pytest.raises(Exception, match="well-formed"):
        validate(data, extract, meta_shacl=False)


def test_referenced_shapes_function_ignores_blank_nodes_and_the_starting_points():
    graph = StarLayerGraph()
    graph.parse(
        data=SHAPES + "ex:Holder a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:node ex:OrA ] .", format="turtle12"
    )
    assert referenced_shapes(graph, {EX.Holder}) == {EX.OrA}
