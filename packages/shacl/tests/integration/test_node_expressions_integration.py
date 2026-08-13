import pytest
from rdflib import Namespace

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayergraph_graph import StarLayerGraph
from starlayergraph.model.triple import TripleTerm

from ._shape_loader import load_shape


EX = Namespace("http://example.org/")

pyshacl = pytest.importorskip("pyshacl")

# pySHACL already implements the SHACL-AF node-expression grammar
# (constants, sh:this, sh:path with its full path-expression forms, sh:union,
# sh:filterShape, and SHACL functions) in
# pyshacl/helper/expression_helper.py::nodes_from_node_expression, used by
# sh:TripleRule's sh:subject/sh:predicate/sh:object. Because starShacl's
# generic validation path encodes triple terms as opaque URIRefs before
# handing the graph to pySHACL, and decodes them back afterward, triple-term
# values flow through this existing evaluator with no additional code -
# these tests confirm that end to end rather than building a new evaluator.
#
# sh:intersection was a confirmed pySHACL bug (reproduces even with plain
# RDF 1.1 data and no starShacl involvement - its node expression handler
# read the intersection's argument list's rdf:first/rdf:rest chain from the
# data graph instead of the shapes graph, unlike the otherwise-identical
# sh:union handler right next to it). Fixed upstream in pySHACL v0.40.1
# (pyproject.toml now requires >=0.40.1); starshacl's own former
# workaround for it has been removed. See docs/pyshacl-upstream-issues.md.


def test_node_expression_path_carries_triple_term_value() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rdf12_node_expression_path.ttl"), format="turtle12")

    validator = StarShaclValidator()
    result = validator.apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True
    derived = list(result.data_graph.triples((EX.alice, EX.derivedSays, None)))
    assert len(derived) == 1
    assert derived[0][2] == TripleTerm(EX.bob, EX.knows, EX.carol)


def test_node_expression_union_carries_mixed_values() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))
    data.add((EX.alice, EX.notes, EX.plain_value))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rdf12_node_expression_union.ttl"), format="turtle12")

    validator = StarShaclValidator()
    result = validator.apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True
    derived = {o for _, _, o in result.data_graph.triples((EX.alice, EX.derivedUnion, None))}
    assert derived == {TripleTerm(EX.bob, EX.knows, EX.carol), EX.plain_value}


def test_node_expression_intersection_carries_triple_term_value() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))
    data.add((EX.alice, EX.says, EX.plain_value))
    data.add((EX.alice, EX.notes, (EX.bob, EX.knows, EX.carol)))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rdf12_node_expression_intersection.ttl"), format="turtle12")

    validator = StarShaclValidator()
    result = validator.apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True
    derived = list(result.data_graph.triples((EX.alice, EX.derivedIntersection, None)))
    assert len(derived) == 1
    assert derived[0][2] == TripleTerm(EX.bob, EX.knows, EX.carol)

    # No list-scaffolding triples injected to work around the pySHACL bug
    # (see module docstring) should leak into the returned data graph.
    from rdflib.namespace import RDF

    assert not any(p in (RDF.first, RDF.rest) for _, p, _ in result.data_graph)


def test_node_expression_intersection_carries_plain_rdf11_value() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, EX.commonval))
    data.add((EX.alice, EX.notes, EX.commonval))
    data.add((EX.alice, EX.notes, EX.otherval))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rdf12_node_expression_intersection.ttl"), format="turtle12")

    validator = StarShaclValidator()
    result = validator.apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True
    derived = {o for _, _, o in result.data_graph.triples((EX.alice, EX.derivedIntersection, None))}
    assert derived == {EX.commonval}


def test_node_expression_shacl_function_carries_triple_term_value() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rdf12_node_expression_function.ttl"), format="turtle12")

    validator = StarShaclValidator()
    result = validator.apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True
    derived = list(result.data_graph.triples((EX.alice, EX.derivedFn, None)))
    assert len(derived) == 1
    assert derived[0][2] == TripleTerm(EX.bob, EX.knows, EX.carol)
