from rdflib import Namespace
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.graph.model.triple import TripleTerm
from starlayer.shacl import StarShaclSchema

from ._rdflib_view import rd

EX = Namespace("http://example.org/")

# SHACL 1.2 Node Expressions (shnex:pathValues, shnex:intersection, shnex:concat/distinct for a union, custom
# functions) evaluated through sh:TripleRule's sh:object. These tests confirm that RDF 1.2 triple-term values (and plain
# RDF 1.1 values) flow through the native engine's evaluators unchanged.

PATH_SHAPE = '''\
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
@prefix ex: <http://example.org/> .

ex:PathExprShape a sh:NodeShape ;
  sh:targetNode ex:alice ;
  sh:rule [
    a sh:TripleRule ;
    sh:subject [ shnex:var "focusNode" ] ;
    sh:predicate ex:derivedSays ;
    sh:object [ shnex:pathValues ex:says ] ;
  ] .
'''

UNION_SHAPE = '''\
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
@prefix ex: <http://example.org/> .

ex:UnionExprShape a sh:NodeShape ;
  sh:targetNode ex:alice ;
  sh:rule [
    a sh:TripleRule ;
    sh:subject [ shnex:var "focusNode" ] ;
    sh:predicate ex:derivedUnion ;
    sh:object [ shnex:distinct [ shnex:concat ( [ shnex:pathValues ex:says ] [ shnex:pathValues ex:notes ] ) ] ] ;
  ] .
'''

INTERSECTION_SHAPE = '''\
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
@prefix ex: <http://example.org/> .

ex:InterExprShape a sh:NodeShape ;
  sh:targetNode ex:alice ;
  sh:rule [
    a sh:TripleRule ;
    sh:subject [ shnex:var "focusNode" ] ;
    sh:predicate ex:derivedIntersection ;
    sh:object [ shnex:intersection ( [ shnex:pathValues ex:says ] [ shnex:pathValues ex:notes ] ) ] ;
  ] .
'''

FUNCTION_SHAPE = '''\
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
@prefix ex: <http://example.org/> .

ex:identity a sh:ListParameterExpressionFunction ;
  sh:parameter [ a sh:Parameter ; sh:path shnex:arg0 ] ;
  sh:bodyExpression [ shnex:arg 0 ] .

ex:FunctionExprShape a sh:NodeShape ;
  sh:targetNode ex:alice ;
  sh:rule [
    a sh:TripleRule ;
    sh:subject [ shnex:var "focusNode" ] ;
    sh:predicate ex:derivedFn ;
    sh:object [ ex:identity ( [ shnex:pathValues ex:says ] ) ] ;
  ] .
'''



def test_node_expression_path_carries_triple_term_value() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))

    shapes = StarLayerGraph()
    shapes.parse(data=PATH_SHAPE, format="turtle12")

    validator = StarShaclSchema(shacl_graph=shapes)
    result = validator.apply_rules(data_graph=data, meta_shacl=False)

    assert result.validation.conforms is True
    derived = list(rd(result.inferred_graph).triples((EX.alice, EX.derivedSays, None)))
    assert len(derived) == 1
    assert derived[0][2] == TripleTerm(EX.bob, EX.knows, EX.carol)


def test_node_expression_union_carries_mixed_values() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))
    data.add((EX.alice, EX.notes, EX.plain_value))

    shapes = StarLayerGraph()
    shapes.parse(data=UNION_SHAPE, format="turtle12")

    validator = StarShaclSchema(shacl_graph=shapes)
    result = validator.apply_rules(data_graph=data, meta_shacl=False)

    assert result.validation.conforms is True
    derived = {o for _, _, o in rd(result.inferred_graph).triples((EX.alice, EX.derivedUnion, None))}
    assert derived == {TripleTerm(EX.bob, EX.knows, EX.carol), EX.plain_value}


def test_node_expression_intersection_carries_triple_term_value() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))
    data.add((EX.alice, EX.says, EX.plain_value))
    data.add((EX.alice, EX.notes, (EX.bob, EX.knows, EX.carol)))

    shapes = StarLayerGraph()
    shapes.parse(data=INTERSECTION_SHAPE, format="turtle12")

    validator = StarShaclSchema(shacl_graph=shapes)
    result = validator.apply_rules(data_graph=data, meta_shacl=False)

    assert result.validation.conforms is True
    derived = list(rd(result.inferred_graph).triples((EX.alice, EX.derivedIntersection, None)))
    assert len(derived) == 1
    assert derived[0][2] == TripleTerm(EX.bob, EX.knows, EX.carol)

    # No list-scaffolding triples should leak into the returned data graph.
    from rdflib.namespace import RDF

    assert not any(p in (RDF.first, RDF.rest) for _, p, _ in rd(result.inferred_graph))


def test_node_expression_intersection_carries_plain_rdf11_value() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, EX.commonval))
    data.add((EX.alice, EX.notes, EX.commonval))
    data.add((EX.alice, EX.notes, EX.otherval))

    shapes = StarLayerGraph()
    shapes.parse(data=INTERSECTION_SHAPE, format="turtle12")

    validator = StarShaclSchema(shacl_graph=shapes)
    result = validator.apply_rules(data_graph=data, meta_shacl=False)

    assert result.validation.conforms is True
    derived = {o for _, _, o in rd(result.inferred_graph).triples((EX.alice, EX.derivedIntersection, None))}
    assert derived == {EX.commonval}


def test_node_expression_shacl_function_carries_triple_term_value() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))

    shapes = StarLayerGraph()
    shapes.parse(data=FUNCTION_SHAPE, format="turtle12")

    validator = StarShaclSchema(shacl_graph=shapes)
    result = validator.apply_rules(data_graph=data, meta_shacl=False)

    assert result.validation.conforms is True
    derived = list(rd(result.inferred_graph).triples((EX.alice, EX.derivedFn, None)))
    assert len(derived) == 1
    assert derived[0][2] == TripleTerm(EX.bob, EX.knows, EX.carol)
