"""``max_validation_depth`` is an internal engine limit (decision 2026-11-24): the public ``validate()``,
``validate_each()``, ``apply_rules()`` and ``StarShaclProcessor`` refuse it, and the default it stood for is unchanged.
``max_iterations`` and ``max_triples`` (public again, decision 2026-11-25) are options of ``apply_rules()``. The limits' own behaviour is tested on the engine (``engine/test_api_options.py``,
``integration/test_rule_iteration.py``)."""

from __future__ import annotations

import inspect

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl import (
    StarShaclProcessor,
    apply_rules,
    validate,
    validate_each,
)
from starlayer.shacl.engine.api import DEFAULT_MAX_VALIDATION_DEPTH
from tests.shacl.integration._shape_loader import load_shape
from tests.support.datasets import dataset_of
from tests.support.errors import raises_kind
from tests.support.terms import Namespace

EX = Namespace("http://example.org/")
PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "


def g(ttl: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=PFX + ttl, format="turtle")
    return graph


DATA = "ex:a ex:p 1 ."
SHAPES = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:nodeKind sh:IRI ."
REMOVED = ("max_validation_depth",)


def chain(n: int) -> StarLayerGraph:
    return g(
        "ex:S0 a sh:NodeShape ; sh:targetNode ex:a ; sh:node ex:S1 .\n"
        + "".join(f"ex:S{i} a sh:NodeShape ; sh:node ex:S{i + 1} .\n" for i in range(1, n))
        + f"ex:S{n} a sh:NodeShape ; sh:nodeKind sh:IRI ."
    )


def linear_chain(length: int) -> StarLayerGraph:
    graph = StarLayerGraph()
    for i in range(length):
        graph.add((EX[f"n{i}"], EX.base, EX[f"n{i + 1}"]))
        graph.add((EX[f"n{i}"], EX.reach, EX[f"n{i + 1}"]))
    return graph


def linear_shapes() -> StarLayerGraph:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rules_reach_linear_sparql.ttl"), format="turtle")
    return shapes


@pytest.mark.parametrize("option", REMOVED)
def test_module_functions_refuse_the_internal_limits(option: str) -> None:
    kwargs = {option: 5}
    with pytest.raises(TypeError, match=option):
        validate(g(DATA), g(SHAPES), **kwargs)
    with pytest.raises(TypeError, match=option):
        apply_rules(g(DATA), g(SHAPES), **kwargs)
    with pytest.raises(TypeError, match=option):
        validate_each(dataset_of([g(DATA)]), g(SHAPES), **kwargs)


@pytest.mark.parametrize("option", REMOVED)
def test_the_message_says_it_is_not_a_public_option(option: str) -> None:
    for call in (lambda: validate(g(DATA), g(SHAPES), **{option: None}), lambda: apply_rules(g(DATA), g(SHAPES), **{option: None})):
        with pytest.raises(TypeError, match=rf"{option} is not an option of the public"):
            call()


@pytest.mark.parametrize("option", REMOVED)
def test_the_processor_refuses_the_internal_limits(option: str) -> None:
    with pytest.raises(TypeError, match=option):
        StarShaclProcessor(g(SHAPES), **{option: 5})  # type: ignore[arg-type]
    p = StarShaclProcessor(g(SHAPES))
    for call in (p.validate, p.apply_rules, p.validate_each):
        arg = dataset_of([g(DATA)]) if call == p.validate_each else g(DATA)
        with pytest.raises(TypeError, match=option):
            call(arg, **{option: 5})


def test_the_processor_signature_has_no_internal_limits_and_keeps_max_iterations() -> None:
    parameters = inspect.signature(StarShaclProcessor).parameters
    assert "max_iterations" in parameters
    assert not set(REMOVED) & set(parameters)


def test_the_default_depth_limit_is_500_through_public_validate() -> None:
    assert DEFAULT_MAX_VALIDATION_DEPTH == 500
    data = g(DATA)
    assert validate(data, chain(300)).conforms
    with raises_kind("nesting"):
        validate(data, chain(520))  # 520 nested sh:node shapes: past the default 500
    with raises_kind("nesting"):
        StarShaclProcessor(chain(520)).validate(data)


def test_max_iterations_stays_public_with_default_1000() -> None:
    data = linear_chain(10)  # one hop per iteration
    assert inspect.signature(StarShaclProcessor).parameters["max_iterations"].default is None
    assert len(apply_rules(data, linear_shapes()).inferred_graph) > 0  # built-in 1000, converges
    with raises_kind("limit", match="fixpoint"):
        apply_rules(data, linear_shapes(), max_iterations=3)
    with raises_kind("limit", match="fixpoint"):
        StarShaclProcessor(linear_shapes(), max_iterations=3).apply_rules(data)


def test_max_triples_is_public_with_default_5_million() -> None:
    from starlayer.shacl.engine import rules as engine_rules

    assert engine_rules.DEFAULT_MAX_TRIPLES == 5_000_000
    assert inspect.signature(engine_rules.apply_rules).parameters["max_triples"].default == engine_rules.DEFAULT_MAX_TRIPLES
    assert "max_triples" in inspect.signature(StarShaclProcessor).parameters
    assert len(list(apply_rules(linear_chain(10), linear_shapes()).inferred_graph)) > 5  # far below the default


def test_max_triples_caps_the_public_apply_rules_and_none_removes_the_cap() -> None:
    data = linear_chain(10)
    with raises_kind("limit", match="more than 5 triples inferred: raise max_triples= or pass None"):
        apply_rules(data, linear_shapes(), max_triples=5)
    with raises_kind("limit", match="more than 5 triples inferred"):
        StarShaclProcessor(linear_shapes()).apply_rules(data, max_triples=5)
    assert len(apply_rules(data, linear_shapes(), max_triples=None).inferred_graph) > 5
    assert len(apply_rules(data, linear_shapes(), max_triples=1000).inferred_graph) > 5


def test_max_triples_processor_default_and_call_override() -> None:
    data = linear_chain(10)
    p = StarShaclProcessor(linear_shapes(), max_triples=5)
    with raises_kind("limit", match="more than 5 triples"):
        p.apply_rules(data)
    assert len(p.apply_rules(data, max_triples=1000).inferred_graph) > 5  # the call beats the constructor
    assert len(p.apply_rules(data, max_triples=None).inferred_graph) > 5
    unlimited = StarShaclProcessor(linear_shapes(), max_triples=None)  # None at construction is a real value: no cap
    assert len(unlimited.apply_rules(data).inferred_graph) > 5
    with raises_kind("limit", match="more than 5 triples"):
        unlimited.apply_rules(data, max_triples=5)


@pytest.mark.parametrize("value", ["5", 1.5, True])
def test_max_triples_rejects_a_non_int(value: object) -> None:
    with pytest.raises(TypeError, match="max_triples"):
        apply_rules(linear_chain(2), linear_shapes(), max_triples=value)
    with pytest.raises(TypeError, match="max_triples"):
        StarShaclProcessor(linear_shapes(), max_triples=value)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="max_triples"):
        StarShaclProcessor(linear_shapes()).apply_rules(linear_chain(2), max_triples=value)


def test_max_triples_rejects_a_negative_value() -> None:
    with pytest.raises(ValueError, match="max_triples"):
        apply_rules(linear_chain(2), linear_shapes(), max_triples=-1)
    with pytest.raises(ValueError, match="max_triples"):
        StarShaclProcessor(linear_shapes(), max_triples=-1)


def test_max_triples_is_not_a_validate_option() -> None:
    with pytest.raises(TypeError, match="max_triples"):
        validate(g(DATA), g(SHAPES), max_triples=5)
    with pytest.raises(TypeError, match="max_triples"):
        StarShaclProcessor(g(SHAPES)).validate(g(DATA), max_triples=5)
