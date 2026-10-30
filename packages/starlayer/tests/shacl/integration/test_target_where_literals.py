"""sh:targetWhere targets literal nodes that conform to the where-shape (GitHub issue #104).

SHACL 1.2 Core: the target is "the set of nodes in a data graph DG that conform to w", and nothing excludes literals, just as
sh:targetObjectsOf can yield them.
"""

import pytest
from rdflib import Graph, Literal, Namespace
from starlayer.shacl import StarShaclSchema, validate

SH = Namespace("http://www.w3.org/ns/shacl#")
P = "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://ex/> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . "
SHAPES = "ex:S a sh:NodeShape ; sh:targetWhere [ sh:datatype xsd:integer ] ; sh:property [ sh:path ex:z ; sh:minCount 1 ] ."


def _g(ttl: str) -> Graph:
    return Graph().parse(data=P + ttl, format="turtle")


def _focus(data: str, method: bool) -> set:
    d, s = _g(data), _g(SHAPES)
    result = StarShaclSchema(shacl_graph=s).validate(data_graph=d, meta_shacl=False) if method else validate(d, s, meta_shacl=False)
    return set(result.report_graph.objects(None, SH.focusNode)), result.conforms


BOTH = pytest.mark.parametrize("method", [False, True], ids=["function", "method"])


@BOTH
def test_conforming_literal_is_a_target(method):
    focus, conforms = _focus("ex:a ex:q 5 .", method)
    assert not conforms
    assert focus == {Literal(5)}


@BOTH
def test_non_conforming_literal_is_not_a_target(method):
    focus, conforms = _focus("ex:a ex:q 'x' .", method)
    assert conforms
    assert not focus


@BOTH
def test_iris_and_literals_are_both_candidates(method):
    focus, _ = _focus("ex:a ex:q 5 . ex:b ex:q 6 .", method)
    assert focus == {Literal(5), Literal(6)}


def test_target_nodes_agrees_with_validate():
    d, s = _g("ex:a ex:q 5 ."), _g(SHAPES)
    schema = StarShaclSchema(shacl_graph=s)
    shape = next(s.subjects(SH.targetWhere, None))
    assert Literal(5) in set(schema.target_nodes(data_graph=d, shape_node=shape))
