"""infer_types() types the node expressions under sh:values, and the argument lists inside them (GitHub issue #22).

Before, only the top-level expression of a sh:values had a shape that targeted it; the nested expressions and the cells of the
argument lists had none, so a tool that finds shapes by target found nothing for them.
"""

import pytest
from rdflib import RDF, BNode, Namespace
from starlayer import StarLayerGraph, starontology
from starlayer.shacl import StarShaclSchema
from starlayer.shacl.shape_types import infer_types

pytest.importorskip("owlrl")

SH = Namespace("http://www.w3.org/ns/shacl#")
EX = Namespace("http://example.org/")
PREFIXES = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . @prefix sparql: <http://www.w3.org/ns/sparql#> . "
)


def _graph(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PREFIXES + ttl, format="turtle12")
    return g


def _typed(graph, cls) -> set:
    return {s for s, _, o in infer_types(graph) if o == cls}


EXAMPLE = """
ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
  sh:property [ sh:path ex:fullName ;
     sh:values [ sparql:concat ( [ shnex:pathValues ex:givenName ] " " [ shnex:pathValues ex:familyName ] ) ] ] ,
    [ sh:path ex:born ; sh:values [ sparql:year ( [ shnex:pathValues ex:birthDate ] ) ] ] .
"""


def test_every_expression_under_sh_values_is_typed_including_the_nested_ones() -> None:
    graph = _graph(EXAMPLE)
    expressions = _typed(graph, SH.NodeExpression)
    functions = {s for s, p, _ in graph if str(p).endswith(("concat", "year"))}
    path_values = {s for s, p, _ in graph if str(p).endswith("pathValues")}
    assert functions <= expressions and path_values <= expressions
    assert len(expressions) == 5  # concat, year, and three pathValues


def test_the_cells_of_the_argument_lists_are_typed_rdf_list() -> None:
    graph = _graph(EXAMPLE)
    cells = {s for s, p, _ in graph if p == RDF.first}
    assert len(cells) == 4 and _typed(graph, RDF.List) == cells


def test_every_node_under_sh_values_has_a_shape_that_targets_it_once_typed() -> None:
    graph = _graph(EXAMPLE)
    typed = StarLayerGraph()
    for triple in graph:
        typed.add(triple)
    for triple in infer_types(graph):
        typed.add(triple)
    schema = StarShaclSchema(shacl_graph=starontology.get_ontology_graph("shacl_shacl"), data_graph=typed)
    covered = set()
    for shape in (EX_SHACL("NodeExpressionShape"), EX_SHACL("ExpressionArgumentListShape")):
        covered.update(schema.target_nodes(shape_node=shape))
    wanted = _typed(graph, SH.NodeExpression) | _typed(graph, RDF.List)
    assert wanted and wanted <= covered


def EX_SHACL(name: str):
    return Namespace("https://github.com/hidden-graph/starlayer/ns/shacl#")[name]


def _nest(depth: int) -> str:
    expression = "[ shnex:pathValues ex:leaf ]"
    for i in range(depth):
        expression = f"[ ex:fn{i} ( {expression} 1 [ shnex:pathValues ex:other ] ) ]"
    return f"ex:S sh:property [ sh:path ex:p ; sh:values {expression} ] ."


@pytest.mark.parametrize("depth", [0, 1, 3, 6])
def test_any_nesting_depth_is_reached(depth) -> None:
    graph = _graph(_nest(depth))
    # a function and one extra pathValues per level, plus the leaf
    assert len(_typed(graph, SH.NodeExpression)) == 1 + 2 * depth
    assert len(_typed(graph, RDF.List)) == 3 * depth


@pytest.mark.parametrize("predicate", ["sh:defaultValue", "sh:expression"])
def test_the_other_places_an_expression_can_start_are_typed_too(predicate) -> None:
    graph = _graph(f"ex:S sh:property [ sh:path ex:p ; {predicate} [ sparql:str ( [ shnex:pathValues ex:q ] ) ] ] .")
    assert len(_typed(graph, SH.NodeExpression)) == 2


def test_a_path_is_not_an_expression() -> None:
    graph = _graph("ex:S sh:property [ sh:path ex:p ; sh:values [ shnex:pathValues [ sh:inversePath ex:q ] ] ] .")
    expressions = _typed(graph, SH.NodeExpression)
    inverse = next(s for s, p, _ in graph if p == SH.inversePath)
    assert len(expressions) == 1 and inverse not in expressions


def test_a_shape_or_a_class_given_to_a_function_is_not_an_expression() -> None:
    graph = _graph(
        "ex:S sh:property [ sh:path ex:p ; sh:values [ shnex:nodesMatching [ sh:class ex:C ] ] ] , "
        "[ sh:path ex:r ; sh:values [ shnex:filterShape [ sh:class ex:C ] ] ] ."
    )
    shape_args = {s for s, p, _ in graph if p == SH["class"]}
    assert not shape_args & _typed(graph, SH.NodeExpression)


def test_constants_are_not_typed() -> None:
    graph = _graph('ex:S sh:property [ sh:path ex:p ; sh:values [ sparql:concat ( "a" ex:b 3 ) ] ] .')
    assert len(_typed(graph, SH.NodeExpression)) == 1
    assert all(isinstance(s, BNode) for s in _typed(graph, SH.NodeExpression) | _typed(graph, RDF.List))


def test_lists_outside_expressions_are_not_typed_rdf_list() -> None:
    graph = _graph("ex:S sh:or ( [ sh:class ex:A ] [ sh:class ex:B ] ) ; sh:property [ sh:path ex:p ; sh:values [ sparql:str ( 1 ) ] ] .")
    cells_of_or = {o for s, p, o in graph if p == SH["or"]}
    assert cells_of_or and not cells_of_or & _typed(graph, RDF.List)


def test_a_shapes_graph_without_expressions_gets_no_expression_types() -> None:
    graph = _graph("ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .")
    assert not _typed(graph, SH.NodeExpression) and not _typed(graph, RDF.List)
