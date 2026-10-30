"""A literal sh:targetWhere is a ShapeLoadError (GitHub issue #172); packaging graphs of any sh:Graph role (GitHub issue #169)."""

import pytest
from pyshacl.errors import ShapeLoadError
from rdflib import Namespace
from starlayer import StarLayerGraph
from starlayer.shacl import StarShaclSchema, validate
from starlayer.shacl.shapes_graphs import graph_nodes, shapes_graph_members, shapes_graphs

EX = Namespace("http://e/")
PREFIXES = (
    "@prefix ex: <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix owl: <http://www.w3.org/2002/07/owl#> . "
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "
)


def _graph(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PREFIXES + ttl, format="turtle12")
    return g


LITERAL_WHERE = "ex:S a sh:NodeShape ; sh:targetWhere 'x' ."
DATA = "ex:r1 a ex:Record ."


def test_a_literal_target_where_raises_shape_load_error_with_the_function() -> None:
    with pytest.raises(ShapeLoadError, match="targetWhere"):
        validate(_graph(DATA), _graph(LITERAL_WHERE), meta_shacl=False)


def test_a_literal_target_where_raises_shape_load_error_with_the_method() -> None:
    with pytest.raises(ShapeLoadError, match="targetWhere"):
        StarShaclSchema(shacl_graph=_graph(LITERAL_WHERE)).validate(data_graph=_graph(DATA), meta_shacl=False)


def test_a_shape_as_target_where_still_conforms() -> None:
    assert validate(_graph(DATA), _graph("ex:S a sh:NodeShape ; sh:targetWhere ex:T . ex:T a sh:NodeShape ."), meta_shacl=False).conforms


ROLES = """
ex:D a sh:DataGraph ; rdfs:member ex:ByMember .
ex:R a sh:RulesGraph ; owl:imports ex:D .
ex:G a sh:Graph ; rdfs:member ex:Plain .
ex:Mine rdfs:subClassOf sh:Graph .
ex:M a ex:Mine ; rdfs:member ex:ByMine .
ex:Deeper rdfs:subClassOf ex:Mine .
ex:N a ex:Deeper ; owl:imports ex:M .
ex:S a sh:ShapesGraph ; rdfs:member ex:ByShapes .
ex:Loose rdfs:isDefinedBy ex:Nowhere .
"""


@pytest.mark.parametrize(
    ("graph_node", "members"),
    [
        (EX.D, {EX.ByMember}),
        (EX.R, {EX.ByMember}),
        (EX.G, {EX.Plain}),
        (EX.M, {EX.ByMine}),
        (EX.N, {EX.ByMine}),
        (EX.S, {EX.ByShapes}),
    ],
)
def test_members_of_any_graph_role(graph_node, members) -> None:
    assert shapes_graph_members(_graph(ROLES), graph_node) == frozenset(members)


def test_a_node_with_no_graph_type_still_has_no_members() -> None:
    assert shapes_graph_members(_graph(ROLES), EX.Loose) is None


def test_an_import_of_an_untyped_node_still_raises() -> None:
    with pytest.raises(ValueError, match="not typed"):
        shapes_graph_members(_graph("ex:G a sh:DataGraph ; owl:imports ex:Untyped ."), EX.G)


def test_graph_nodes_lists_every_role_and_shapes_graphs_stays_shapes_only() -> None:
    graph = _graph(ROLES)
    assert graph_nodes(graph) == [EX.D, EX.G, EX.M, EX.N, EX.R, EX.S]
    assert shapes_graphs(graph) == [EX.S]
