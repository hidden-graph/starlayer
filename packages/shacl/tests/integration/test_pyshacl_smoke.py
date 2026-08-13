import pytest
from rdflib import Literal, Namespace

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayergraph_graph import StarLayerGraph

from ._shape_loader import load_shape


EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")


pyshacl = pytest.importorskip("pyshacl")


def test_pyshacl_smoke_validation_passes_simple_shape() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.age, Literal(30)))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("smoke_person_age.ttl"), format="turtle")

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes)

    assert result.conforms is True
