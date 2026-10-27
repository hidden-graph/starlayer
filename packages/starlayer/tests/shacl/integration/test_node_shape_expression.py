"""sh:expression on a node shape (SHACL 1.2 Node Expressions 7.1: expression constraints "can be used in any shape").

A shape with sh:expression and no sh:path is a node shape (Core: a node shape is a shape that is not the subject of
sh:path). The meta-shapes used to forbid sh:expression on a node shape; the W3C test suite's own
node-expr/constraints/expression-001 uses `sh:expression false` on a node shape."""

import pytest
from pyshacl.errors import ReportableRuntimeError
from rdflib import Graph, Namespace
from starlayer import starontology
from starlayer.shacl import StarShaclSchema
from starlayer.shacl.meta_shapes import meta_validate

SH = Namespace("http://www.w3.org/ns/shacl#")
_PREFIXES = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> . @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . "
    "@prefix sparql: <http://www.w3.org/ns/sparql#> . "
)
_PEOPLE = "ex:alice a ex:Person ; ex:age 30 . ex:bob a ex:Person ; ex:age 12 . ex:rex a ex:Dog ; ex:age 3 ."


def _graph(ttl: str) -> Graph:
    g = Graph()
    g.parse(data=_PREFIXES + ttl, format="turtle")
    return g


def _validate(shapes_ttl: str, data_ttl: str = _PEOPLE, **kwargs):
    kwargs.setdefault("meta_shacl", True)
    return StarShaclSchema(shacl_graph=_graph(shapes_ttl)).validate(data_graph=_graph(data_ttl), **kwargs)


def _failures(result) -> dict[str, str]:
    """focus node -> source constraint component, for every violation."""
    report = result.report_graph if hasattr(result, "report_graph") else result.results_graph
    return {
        str(report.value(r, SH.focusNode)): str(report.value(r, SH.sourceConstraintComponent))
        for r in report.subjects(SH.resultSeverity, SH.Violation)
    }


def _meta(shapes_ttl: str) -> tuple[bool, str]:
    try:
        conforms, _, text = meta_validate(_graph(shapes_ttl))
    except ReportableRuntimeError as error:  # meta_validate raises when the shapes graph does not conform
        return False, str(error)
    return conforms, text


EXPR = str(SH.ExpressionConstraintComponent)


def test_a_constant_false_expression_on_a_node_shape_fails_every_person() -> None:
    result = _validate("ex:PeopleShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:expression false .")
    assert not result.conforms
    assert _failures(result) == {"http://example.org/alice": EXPR, "http://example.org/bob": EXPR}


def test_a_constant_true_expression_on_a_node_shape_passes() -> None:
    assert _validate("ex:PeopleShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:expression true .").conforms


def test_a_complex_expression_on_a_node_shape_checks_each_focus_node() -> None:
    """Adults only: the expression is true for alice (30), false for bob (12)."""
    result = _validate(
        "ex:PeopleShape a sh:NodeShape ; sh:targetClass ex:Person ; "
        "sh:expression [ sparql:greater-than-or-equal ( [ shnex:pathValues ex:age ] 18 ) ] ."
    )
    assert _failures(result) == {"http://example.org/bob": EXPR}


def test_a_node_shape_with_an_expression_passes_the_meta_shapes() -> None:
    conforms, text = _meta("ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:expression false .")
    assert conforms, text
    conforms, text = _meta("ex:S a sh:NodeShape ; sh:expression [ sparql:logical-not ( false ) ] .")
    assert conforms, text


def test_a_node_shape_nested_through_sh_node_may_carry_an_expression() -> None:
    assert _meta("ex:S a sh:NodeShape ; sh:node [ sh:expression false ] .")[0]


def test_a_malformed_expression_on_a_node_shape_is_rejected() -> None:
    conforms, _ = _meta("ex:S a sh:NodeShape ; sh:expression [ ex:notAnExpression 1 ] .")
    assert not conforms
    with pytest.raises(Exception, match="MetaSHACL"):
        _validate("ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:expression [ ex:notAnExpression 1 ] .")


def test_a_property_shape_may_carry_an_expression_too() -> None:
    assert _meta("ex:S a sh:NodeShape ; sh:property [ sh:path ex:age ; sh:expression true ] .")[0]


def test_a_shape_with_a_path_and_an_expression_is_a_property_shape_and_not_a_node_shape() -> None:
    """The Working Group's xone between node shape and property shape: a shape that has sh:path is one or the other,
    never both, so it is not also checked as a node shape."""
    assert _meta("ex:S a sh:NodeShape ; sh:property ex:P . ex:P sh:path ex:age ; sh:expression true .")[0]
    # as a node-shape-valued sh:node it is rejected: sh:node takes node shapes, and this one has sh:path
    assert not _meta("ex:S a sh:NodeShape ; sh:node [ sh:path ex:age ; sh:expression true ] .")[0]


def test_a_shape_with_neither_path_nor_expression_is_a_node_shape() -> None:
    assert _meta("ex:S a sh:NodeShape ; sh:targetClass ex:Person .")[0]
    assert not _meta("ex:S a sh:NodeShape ; sh:property [ sh:minCount 1 ] .")[0]  # a sh:property value needs sh:path


def test_a_sh_property_value_without_sh_path_is_still_rejected() -> None:
    """Such a value is a node shape by definition, and Core says each value of sh:property is a well-formed property
    shape (rule property-node)."""
    assert not _meta("ex:S a sh:NodeShape ; sh:property [ sh:expression false ] .")[0]


def test_no_meta_shape_caps_sh_expression_at_zero_on_node_shapes() -> None:
    meta = starontology.get_ontology_graph("shacl_shacl")
    capped = [ps for ps in meta.subjects(SH.path, SH.expression) if (ps, SH.maxCount, None) in meta]
    assert not capped
