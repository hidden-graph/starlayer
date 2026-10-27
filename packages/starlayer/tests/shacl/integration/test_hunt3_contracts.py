"""Hunt 3 (GitHub issues #138 and #139): a bad ``role`` or an unknown ``shape_node`` of ``select_widgets`` is an error, and
``extract_subgraph`` refuses a ``str`` where it needs a term (it was a bare KeyError, or a silently empty result)."""

import pytest
from rdflib import Namespace, URIRef
from starlayer import StarLayerGraph
from starlayer.shacl import StarShaclSchema, extract_subgraph

EX = Namespace("http://example.org/")

SHAPES = """@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P . ex:P sh:path ex:name .
ex:a a ex:T ; ex:name "n" ."""


def _schema():
    graph = StarLayerGraph()
    graph.parse(data=SHAPES, format="turtle12")
    return graph, StarShaclSchema(shacl_graph=graph)


def test_select_widgets_rejects_an_invalid_role():
    _, schema = _schema()
    with pytest.raises(ValueError, match="role"):
        schema.select_widgets(shape_node=EX.S, role="bogus")
    assert set(schema.select_widgets(shape_node=EX.S, role="viewer")) == {EX.P}


def test_select_widgets_rejects_an_unknown_shape():
    _, schema = _schema()
    with pytest.raises(ValueError, match="shape_node"):
        schema.select_widgets(shape_node=EX.Nope, role="editor")


def test_extract_subgraph_rejects_str_shape_and_focus_node():
    graph, _ = _schema()
    with pytest.raises(TypeError, match="shape"):
        extract_subgraph(graph, graph, shape="http://example.org/S")
    with pytest.raises(TypeError, match="focus_node"):
        extract_subgraph(graph, graph, focus_node="http://example.org/a")
    assert len(extract_subgraph(graph, graph, shape=URIRef("http://example.org/S"), focus_node=EX.a)) > 0
