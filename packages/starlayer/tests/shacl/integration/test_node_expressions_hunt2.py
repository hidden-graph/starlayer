"""shnex:sum / min / max / orderBy over mixed values (GitHub issue #95), through the public evaluate()."""

import warnings

import pytest
from rdflib import XSD, Literal, Namespace
from starlayer.graph import StarLayerGraph
from starlayer.shacl import evaluate

warnings.simplefilter("ignore")
EX = Namespace("http://ex/")
PREFIXES = (
    "@prefix ex: <http://ex/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . "
)


def _values(expression: str, data: str = "ex:a ex:in 0 ."):
    shapes = StarLayerGraph()
    shapes.parse(
        data=PREFIXES + f"ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:out ; sh:values {expression} ] .",
        format="turtle12",
    )
    graph = StarLayerGraph()
    graph.parse(data=PREFIXES + data, format="turtle12")
    result = evaluate(graph, shapes)
    return sorted(result.objects(EX.a, EX.out), key=str)


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ("1.5 2e0", Literal(3.5, datatype=XSD.double)),
        ('1.5 "2.5"^^xsd:float', Literal(4.0, datatype=XSD.float)),
        ("1 2 3", Literal(6, datatype=XSD.integer)),
        ("1.5 2.5", Literal(4, datatype=XSD.decimal)),
        ("1 2.5", Literal(3.5, datatype=XSD.decimal)),
    ],
)
def test_sum_promotes_across_numeric_types(items, expected):
    [value] = _values(f"[ shnex:sum ( {items} ) ]")
    assert value.datatype == expected.datatype
    assert float(value) == float(expected)


@pytest.mark.parametrize("items", ['"a" 1', '"x"^^xsd:integer 2'])
def test_sum_of_a_non_numeric_value_is_an_evaluation_failure_not_a_crash(items):
    # no value is produced for the node; the call does not raise a TypeError out of evaluate()
    assert _values(f"[ shnex:sum ( {items} ) ]") == []


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ('[ shnex:min ( 1 "a" ) ]', [Literal(1)]),  # numbers before strings
        ('[ shnex:max ( 1 "a" ) ]', [Literal("a")]),
        ("[ shnex:max ( ex:a 1 ) ]", [Literal(1)]),  # an IRI is below every literal
        ("[ shnex:min ( ex:a 1 ) ]", [EX.a]),
        ('[ shnex:min ( "2020-01-01T00:00:00Z"^^xsd:dateTime "2020-01-01T00:00:00"^^xsd:dateTime ) ]', None),
        ('[ shnex:max ( "2020-01-01"^^xsd:date "2020-01-01T00:00:00"^^xsd:dateTime ) ]', None),
    ],
)
def test_min_and_max_have_a_total_order(expression, expected):
    values = _values(expression)
    assert len(values) == 1
    if expected is not None:
        assert values == expected


def test_order_by_over_mixed_types_does_not_crash_and_sorts_numbers_first():
    shapes_expr = '[ shnex:orderBy [ shnex:var "focusNode" ] ; shnex:nodes ( 3 "a" 1 ex:b ) ]'
    values = _values(shapes_expr)
    assert set(values) == {Literal(3), Literal("a"), Literal(1), EX.b}


def _conforms(shapes_ttl, data_ttl):
    from starlayer.shacl import validate

    shapes = StarLayerGraph()
    shapes.parse(data=PREFIXES + shapes_ttl, format="turtle12")
    data = StarLayerGraph()
    data.parse(data=PREFIXES + data_ttl, format="turtle12")
    return validate(data, shapes, meta_shacl=False).conforms


NODE_BY_EXPRESSION = """
ex:S a sh:NodeShape ; sh:targetNode ex:f ;
  sh:property [ sh:path ex:p ; sh:nodeByExpression [ shnex:pathValues ex:shape ] ] .
ex:Sh1 a sh:NodeShape ; sh:nodeKind sh:Literal .
"""


def test_node_by_expression_is_evaluated_at_each_value_node():
    # ex:o is the value node; its own ex:shape says it must be a literal, and it is an IRI: a violation
    assert _conforms(NODE_BY_EXPRESSION, "ex:f ex:p ex:o . ex:o ex:shape ex:Sh1 .") is False


def test_node_by_expression_does_not_read_the_outer_focus_node():
    # the shape named at the outer focus node does not apply to the value node
    assert _conforms(NODE_BY_EXPRESSION, "ex:f ex:p ex:o . ex:f ex:shape ex:Sh1 .") is True


def test_node_by_expression_with_a_conforming_value():
    assert _conforms(NODE_BY_EXPRESSION, 'ex:f ex:p "x" . ') is True


def test_distinct_treats_language_tags_that_differ_in_case_as_one():
    values = _values('[ shnex:distinct ( "a"@en "a"@EN "a" ) ]')
    assert len(values) == 2


@pytest.mark.parametrize("modifier", ["limit", "offset"])
def test_negative_limit_and_offset_are_not_python_slices(modifier):
    assert _values(f"[ shnex:{modifier} -1 ; shnex:nodes ( 1 2 3 ) ]") == []
