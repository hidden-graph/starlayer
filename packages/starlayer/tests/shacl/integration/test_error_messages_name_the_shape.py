"""A ShapeError says which shape, property or rule it is about, not a blank node's label."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl import ShapeError, StarShaclProcessor
from starlayer.shacl.engine.naming import describe

PFX = ("@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
       "@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .\n")


def _graph(turtle: str) -> StarLayerGraph:
    return StarLayerGraph().parse(data=PFX + turtle, format="turtle")


DATA = "ex:a a ex:T ."


def test_a_constraint_value_names_the_property_shape_and_the_constraint():
    shapes = _graph('ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:minCount "many" ] .')
    with pytest.raises(ShapeError) as exc:
        StarShaclProcessor(shacl_graph=shapes)
    assert str(exc.value).startswith("the property shape of http://example.org/S for http://example.org/p: sh:minCount needs exactly one")


def test_unparsable_sparql_names_the_shape_it_is_in():
    shapes = _graph('ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:sparql [ sh:select "SELECT WHERE {{{" ] .')
    with pytest.raises(ShapeError) as exc:
        StarShaclProcessor(shacl_graph=shapes).validate(data_graph=_graph(DATA))
    assert str(exc.value).startswith("http://example.org/S: SPARQL query does not parse")


def test_a_malformed_node_expression_names_where_it_sits():
    shapes = _graph('ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:values [ shnex:noSuchOperator ex:x ] ] .')
    with pytest.raises(ShapeError) as exc:
        StarShaclProcessor(shacl_graph=shapes).validate(data_graph=_graph(DATA))
    text = str(exc.value)
    assert text.startswith("the sh:values of the property shape of http://example.org/S for http://example.org/p: a node expression needs exactly one")
    assert "BlankNode" not in text


def test_a_failing_rule_names_the_shape_that_holds_it():
    shapes = _graph('ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:rule [ a sh:SPARQLRule ; sh:construct "CONSTRUCT {{{ " ] .')
    with pytest.raises(ShapeError) as exc:
        StarShaclProcessor(shacl_graph=shapes).apply_rules(data_graph=_graph(DATA))
    assert str(exc.value).startswith("the sh:rule of http://example.org/S: SPARQL rule failed")
    assert "BlankNode" not in str(exc.value)


def test_describe_names_nodes_by_prefix_when_given():
    shapes = _graph("ex:S a sh:NodeShape ; sh:property [ sh:path ex:name ] .")
    from starlayer.shacl.engine.terms import SH, engine_view

    view = engine_view(shapes, "shapes graph")
    node = next(iter(view.objects(next(iter(view.subjects(None, SH.NodeShape)), None) or next(iter(view.subjects())), SH.property)))
    assert describe(view, node, {"ex": "http://example.org/"}) == "the property shape of ex:S for ex:name"
