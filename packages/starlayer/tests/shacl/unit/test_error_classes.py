"""Errors are classified by cause: ``ShapeError`` (the shapes graph or its setup is wrong, whenever the engine finds it) and
``ExecutionError`` (the shapes graph is fine and running it failed). ``ExecutionError`` is a plain ``Exception``."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl import (
    ConstraintQueryFailure,
    EvaluationFailure,
    ExecutionError,
    MetaShaclError,
    NestingTooDeep,
    RecursionThroughNot,
    RuleError,
    ShapeError,
    StarShaclProcessor,
    apply_rules,
    validate,
)

PFX = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . "
)


def g(ttl: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=PFX + ttl, format="turtle")
    return graph


RUN_TIME = (RuleError, EvaluationFailure, NestingTooDeep, RecursionThroughNot, ConstraintQueryFailure)


@pytest.mark.parametrize("cls", RUN_TIME)
def test_every_run_time_error_is_an_execution_error_and_not_a_shape_error(cls):
    assert issubclass(cls, ExecutionError)
    assert not issubclass(cls, ShapeError)
    assert not issubclass(cls, ValueError)  # an ``except ValueError`` must not swallow a run-time failure


def test_a_shape_error_is_not_an_execution_error():
    assert issubclass(ShapeError, ValueError)
    assert not issubclass(ShapeError, ExecutionError)
    assert not issubclass(MetaShaclError, ExecutionError)
    assert issubclass(ExecutionError, Exception) and not issubclass(ExecutionError, ValueError)


def test_an_evaluation_failure_comes_out_of_validate_through_the_engines_except_clauses():
    shapes = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:expression [ shnex:sum ( 1 'a' ) ] ."
    with pytest.raises(EvaluationFailure) as exc:
        validate(g("ex:a ex:p 1 ."), g(shapes), meta_shacl=False)
    assert isinstance(exc.value, ExecutionError)


def test_recursion_through_not_is_a_recursion_through_not():
    shapes = "ex:N a sh:NodeShape ; sh:targetNode ex:a ; sh:not [ sh:property [ sh:path ex:next ; sh:node ex:N ] ] ."
    with pytest.raises(RecursionThroughNot, match="sh:not"):
        validate(g("ex:a ex:next ex:a ."), g(shapes))
    with pytest.raises(ExecutionError):
        validate(g("ex:a ex:next ex:a ."), g(shapes))


def test_a_constraint_query_reporting_failure_is_a_constraint_query_failure():
    shapes = 'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:select "SELECT $this (true AS ?failure) WHERE { }" ] .'
    with pytest.raises(ConstraintQueryFailure, match="failure true") as exc:
        validate(g("ex:a ex:p 1 ."), g(shapes))
    assert "ex" in str(exc.value) and "S" in str(exc.value)  # names the shape


def test_a_cyclic_node_expression_is_nesting_too_deep():
    shapes = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:expression _:e . _:e shnex:exists _:e ."
    with pytest.raises(NestingTooDeep, match="nest deeper"):
        validate(g("ex:a ex:p 1 ."), g(shapes), meta_shacl=False)


def test_shapes_nested_past_the_limit_are_nesting_too_deep():
    from starlayer.shacl.engine.api import validate as engine_validate

    shapes = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:node [ sh:node [ sh:node [ sh:closed false ] ] ] ."
    with pytest.raises(NestingTooDeep, match="too deep"):
        engine_validate(g("ex:a ex:p 1 ."), g(shapes), max_validation_depth=2)


@pytest.mark.parametrize(
    "rule",
    [
        "[ a sh:SPARQLRule ; sh:construct 'CONSTRUCT {{{ ' ]",  # does not parse
        "[ a sh:TripleRule ; sh:order 'a' ; sh:subject [ shnex:var 'focusNode' ] ; sh:predicate ex:q ; sh:object 1 ]",  # sh:order is not a number
        "[ a sh:SPARQLRule ]",  # no sh:construct
    ],
)
def test_a_malformed_rule_is_a_shape_error_not_an_execution_error(rule):
    shapes = g(f"ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:rule {rule} .")
    with pytest.raises(ShapeError) as exc:
        apply_rules(g("ex:a ex:p 1 ."), shapes)
    assert not isinstance(exc.value, ExecutionError)


def test_a_rule_that_fails_while_running_is_a_rule_error():
    shapes = g("ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:rule [ a sh:TripleRule ; sh:subject [ shnex:sum ( 1 'a' ) ] ; sh:predicate ex:q ; sh:object 1 ] .")
    with pytest.raises(RuleError) as exc:
        apply_rules(g("ex:a ex:p 1 ."), shapes)
    assert isinstance(exc.value, ExecutionError) and not isinstance(exc.value, ValueError)


def test_an_unresolvable_import_is_a_shape_error_at_the_first_validate():
    shapes = g("<http://example.org/shapes> owl:imports <http://example.org/other> . ex:S a sh:NodeShape ; sh:targetNode ex:a .")
    processor = StarShaclProcessor(shacl_graph=shapes)  # nothing raised yet: a call may bring a loader
    with pytest.raises(ShapeError, match="owl:imports") as exc:
        processor.validate(data_graph=g("ex:a ex:p 1 ."), meta_shacl=False)
    assert not isinstance(exc.value, ExecutionError)
