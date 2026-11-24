"""``owl:imports sh:`` (the import Core recommends for a graph that uses ``sh:ShapeClass``) needs no loader: the engine has the vocabulary."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl import StarShaclProcessor

PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix owl: <http://www.w3.org/2002/07/owl#> .\n"


def _graph(turtle: str) -> StarLayerGraph:
    return StarLayerGraph().parse(data=PFX + turtle, format="turtle")


SHAPES = "ex:Shapes a owl:Ontology ; owl:imports sh: . ex:Person a sh:ShapeClass ; sh:property [ sh:path ex:name ; sh:minCount 1 ] ."
DATA = "ex:alice a ex:Person ."


def test_the_import_of_the_shacl_vocabulary_is_satisfied_without_a_loader():
    result = StarShaclProcessor(shacl_graph=_graph(SHAPES)).validate(data_graph=_graph(DATA))
    assert result.conforms is False  # alice has no name: the shape ran, and no error about the import was raised


def test_the_loader_is_not_asked_for_the_shacl_vocabulary():
    asked = []
    StarShaclProcessor(shacl_graph=_graph(SHAPES), shapes_graph_loader=lambda iri: asked.append(iri.value)).validate(data_graph=_graph(DATA))
    assert asked == []


def test_another_import_that_nothing_supplies_still_raises():
    shapes = _graph("ex:Shapes a owl:Ontology ; owl:imports sh:, <http://example.org/other> . ex:S a sh:NodeShape .")
    with pytest.raises(ValueError, match="http://example.org/other"):
        StarShaclProcessor(shacl_graph=shapes).validate(data_graph=_graph(DATA))
