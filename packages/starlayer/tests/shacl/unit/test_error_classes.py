"""Errors are classified by cause: ``ShapeError`` (the shapes graph or its setup is wrong, whenever the engine finds it) and
``ExecutionError`` (the shapes graph is fine and running it failed). ``ExecutionError`` is one plain ``Exception`` class whose ``kind``
says what failed; ``ShapeError`` is the base of ``ShapeCompileError`` (the engine cannot compile it) and ``MetaShaclError`` (the meta
check found it)."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl import (
    ExecutionError,
    MetaShaclError,
    ShapeCompileError,
    ShapeError,
    StarShaclProcessor,
    apply_rules,
    validate,
)
from tests.support.errors import raises_kind

PFX = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . "
)


def g(ttl: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=PFX + ttl, format="turtle")
    return graph


KINDS = ("rule", "expression", "nesting", "recursion", "constraint-query")


def test_execution_error_is_one_class_with_a_kind_and_the_message_as_its_text():
    error = ExecutionError("the message", kind="rule")
    assert error.kind == "rule" and str(error) == "the message"
    assert ExecutionError.KINDS == KINDS
    assert not issubclass(ExecutionError, ShapeError)
    assert not issubclass(ExecutionError, ValueError)  # an ``except ValueError`` must not swallow a run-time failure
    assert ExecutionError.__subclasses__() == []  # no subclass per kind


def test_the_kind_is_required_and_must_be_known():
    with pytest.raises(TypeError):
        ExecutionError("no kind")  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="unknown ExecutionError kind"):
        ExecutionError("odd", kind="other")


def test_an_execution_error_survives_pickle_and_copy():
    import copy
    import pickle

    error = ExecutionError("the message", kind="nesting")
    for clone in (pickle.loads(pickle.dumps(error)), copy.copy(error), copy.deepcopy(error)):
        assert type(clone) is ExecutionError and clone.kind == "nesting" and str(clone) == "the message"


def test_the_old_per_kind_classes_are_gone():
    import starlayer.shacl as shacl
    import starlayer.shacl.errors as errors

    for name in ("RuleError", "EvaluationFailure", "NestingTooDeep", "RecursionThroughNot", "ConstraintQueryFailure"):
        assert not hasattr(shacl, name) and not hasattr(errors, name)


def test_a_shape_error_is_not_an_execution_error():
    assert issubclass(ShapeError, ValueError)
    assert not issubclass(ShapeError, ExecutionError)
    assert not issubclass(MetaShaclError, ExecutionError)
    assert issubclass(ExecutionError, Exception) and not issubclass(ExecutionError, ValueError)


def test_an_expression_error_comes_out_of_validate_through_the_engines_except_clauses():
    shapes = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:expression [ shnex:sum ( 1 'a' ) ] ."
    with raises_kind("expression"):
        validate(g("ex:a ex:p 1 ."), g(shapes), meta_shacl=False)


def test_recursion_through_not_is_of_kind_recursion():
    shapes = "ex:N a sh:NodeShape ; sh:targetNode ex:a ; sh:not [ sh:property [ sh:path ex:next ; sh:node ex:N ] ] ."
    with raises_kind("recursion", match="sh:not"):
        validate(g("ex:a ex:next ex:a ."), g(shapes))


def test_a_constraint_query_reporting_failure_is_of_kind_constraint_query():
    shapes = 'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:select "SELECT $this (true AS ?failure) WHERE { }" ] .'
    with raises_kind("constraint-query", match="failure true") as exc:
        validate(g("ex:a ex:p 1 ."), g(shapes))
    assert "ex" in str(exc.value) and "S" in str(exc.value)  # names the shape


def test_a_cyclic_node_expression_is_of_kind_nesting():
    shapes = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:expression _:e . _:e shnex:exists _:e ."
    with raises_kind("nesting", match="nest deeper"):
        validate(g("ex:a ex:p 1 ."), g(shapes), meta_shacl=False)


def test_shapes_nested_past_the_limit_are_of_kind_nesting():
    from starlayer.shacl.engine.api import validate as engine_validate

    shapes = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:node [ sh:node [ sh:node [ sh:closed false ] ] ] ."
    with raises_kind("nesting", match="too deep"):
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


def test_a_rule_that_fails_while_running_is_of_kind_rule():
    shapes = g("ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:rule [ a sh:TripleRule ; sh:subject [ shnex:sum ( 1 'a' ) ] ; sh:predicate ex:q ; sh:object 1 ] .")
    with raises_kind("rule") as exc:
        apply_rules(g("ex:a ex:p 1 ."), shapes)
    assert not isinstance(exc.value, ValueError)


def test_an_unresolvable_import_is_a_shape_error_at_the_first_validate():
    shapes = g("<http://example.org/shapes> owl:imports <http://example.org/other> . ex:S a sh:NodeShape ; sh:targetNode ex:a .")
    processor = StarShaclProcessor(shacl_graph=shapes)  # nothing raised yet: a call may bring a loader
    with pytest.raises(ShapeError, match="owl:imports") as exc:
        processor.validate(data_graph=g("ex:a ex:p 1 ."), meta_shacl=False)
    assert not isinstance(exc.value, ExecutionError)


BAD_COUNT = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:minCount \"many\" ] ."


def test_the_shape_error_hierarchy():
    for cls in (ShapeCompileError, MetaShaclError):
        assert issubclass(cls, ShapeError) and issubclass(cls, ValueError)
        assert not issubclass(cls, ExecutionError)
    assert not issubclass(ShapeCompileError, MetaShaclError) and not issubclass(MetaShaclError, ShapeCompileError)
    assert not issubclass(ExecutionError, ShapeError)


def test_a_compile_error_is_a_shape_compile_error_and_not_a_meta_error():
    with pytest.raises(ShapeCompileError) as exc:
        StarShaclProcessor(shacl_graph=g(BAD_COUNT))
    assert type(exc.value) is ShapeCompileError and not isinstance(exc.value, MetaShaclError)


def test_the_meta_check_raises_a_meta_error_that_is_a_shape_error_and_not_a_compile_error():
    with pytest.raises(MetaShaclError) as exc:
        StarShaclProcessor(shacl_graph=g(BAD_COUNT), meta_shacl=True)
    assert isinstance(exc.value, ShapeError) and not isinstance(exc.value, ShapeCompileError)


def test_except_shape_error_catches_both_kinds():
    for kwargs in ({}, {"meta_shacl": True}):
        try:
            StarShaclProcessor(shacl_graph=g(BAD_COUNT), **kwargs)
        except ShapeError:
            pass
        else:
            raise AssertionError("no error raised")


def test_an_unresolvable_import_is_a_shape_compile_error():
    shapes = g("ex:SG a sh:Graph ; owl:imports <http://example.org/missing> . ex:S a sh:NodeShape ; sh:targetNode ex:a .")
    with pytest.raises(ShapeCompileError):
        validate(g("ex:a ex:p 1 ."), shapes, meta_shacl=False)


def test_a_malformed_rule_is_a_shape_compile_error():
    shapes = "ex:R a sh:SPARQLRule ; sh:construct 'not a query' ."
    with pytest.raises(ShapeCompileError):
        apply_rules(g("ex:a ex:p 1 ."), g(shapes))


def test_exceeding_max_iterations_and_max_triples_are_of_kind_rule():
    shapes = g("ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:rule [ a sh:TripleRule ; sh:subject [ shnex:var 'focusNode' ] ; sh:predicate ex:q ; sh:object 1 ] .")
    from starlayer.shacl.engine.rules import apply_rules as engine_apply_rules

    with raises_kind("rule", match="triples inferred"):
        engine_apply_rules(g("ex:a ex:p 1 ."), shapes, max_triples=0)
    chain = g(
        "ex:R a sh:NodeShape ; sh:targetClass ex:N ; sh:rule [ a sh:SPARQLRule ; "
        "sh:construct 'CONSTRUCT { ?s <http://example.org/next> [ a <http://example.org/N> ] } WHERE { $this a <http://example.org/N> . BIND($this AS ?s) }' ] ."
    )
    with raises_kind("rule", match="fixpoint"):
        apply_rules(g("ex:a a ex:N ."), chain, max_iterations=3)


# ---- the clauses that mean "no value" catch only kind "expression" -------------------------------------------------------------------


def _raiser(kind):
    def raise_it(*_args, **_kwargs):
        raise ExecutionError(f"a {kind} failure", kind=kind)

    return raise_it


OTHER_KINDS = [k for k in KINDS if k != "expression"]


def _expression_site_deactivation(monkeypatch, kind):
    from starlayer.shacl.engine import deactivation

    monkeypatch.setattr(deactivation, "evaluate_expression", _raiser(kind))
    return lambda: deactivation.any_true(object(), [object()], object())


def _expression_site_executor(monkeypatch, kind):
    from types import SimpleNamespace

    from starlayer.shacl.engine import executor

    monkeypatch.setattr(executor, "evaluate_expression", _raiser(kind))
    return lambda: executor.Context._expression_values(SimpleNamespace(), (object(),), None)


def _expression_site_sparql_constraint(monkeypatch, kind):
    from starlayer.shacl.engine.components import sparql_constraints

    monkeypatch.setattr(sparql_constraints, "evaluate_expression", _raiser(kind))
    return lambda: sparql_constraints._deactivated_at(object(), [object()], object())


def _expression_site_argument_state(monkeypatch, kind):
    from starlayer.shacl.engine import expressions

    monkeypatch.setattr(expressions, "_eval", _raiser(kind))
    return lambda: expressions._arg_state(object(), object(), object(), {})


def _expression_site_form_model(monkeypatch, kind):
    import importlib
    from types import SimpleNamespace

    from starlayer.shacl.engine import expressions

    form_model = importlib.import_module("starlayer.shacl.form_model")

    monkeypatch.setattr(expressions, "evaluate_expression", _raiser(kind))
    plan = SimpleNamespace(shape=lambda _prop: SimpleNamespace(values=(object(),)))
    builder = SimpleNamespace(plan=plan, ctx=object(), node=object())
    return lambda: form_model._Builder.expression_values(builder, [object()])


SITES = [
    _expression_site_deactivation,
    _expression_site_executor,
    _expression_site_sparql_constraint,
    _expression_site_argument_state,
    _expression_site_form_model,
]


@pytest.mark.parametrize("site", SITES, ids=lambda f: f.__name__.removeprefix("_expression_site_"))
def test_a_no_value_clause_swallows_an_expression_error(monkeypatch, site):
    run = site(monkeypatch, "expression")
    run()  # no error: the node expression has no value here


@pytest.mark.parametrize("kind", OTHER_KINDS)
@pytest.mark.parametrize("site", SITES, ids=lambda f: f.__name__.removeprefix("_expression_site_"))
def test_a_no_value_clause_lets_every_other_kind_through(monkeypatch, site, kind):
    run = site(monkeypatch, kind)
    with raises_kind(kind):
        run()


def test_the_sparql_custom_function_wrapper_gives_no_value_for_an_error_of_the_body(monkeypatch):
    """The wrapper keeps its broad clause on purpose: a function whose body cannot be evaluated is a SPARQL error, whatever the kind."""
    from types import SimpleNamespace

    from starlayer.shacl.engine import expressions
    from starlayer.shacl.engine.sparql_support import shacl_functions
    from starlayer.shacl.engine.terms import NamedNode

    fn = NamedNode("http://example.org/fn")
    shapes = g("ex:fn a sh:ListParameterExpressionFunction ; sh:bodyExpression [ shnex:sum ( ) ] .")
    for kind in KINDS:
        monkeypatch.setattr(expressions, "evaluate_expression", _raiser(kind))
        ctx = SimpleNamespace(cache={}, shapes=shapes, plan=SimpleNamespace(sparql_cache={}))
        assert shacl_functions(ctx)[fn](NamedNode("http://example.org/x")) is None


def test_a_sh_condition_check_that_fails_keeps_its_kind_and_names_the_rule():
    shapes = g(
        "ex:N a sh:NodeShape ; sh:not [ sh:property [ sh:path ex:next ; sh:node ex:N ] ] . "
        "ex:S a sh:NodeShape ; sh:targetNode ex:a ; "
        "sh:rule [ a sh:TripleRule ; sh:condition ex:N ; sh:subject [ shnex:var 'focusNode' ] ; sh:predicate ex:q ; sh:object 1 ] ."
    )
    with raises_kind("recursion", match="sh:condition check failed"):
        apply_rules(g("ex:a ex:next ex:a ."), shapes)



# ---- a ValueError raised while the shapes are compiled is a ShapeCompileError ----------------------------------------------------------


def test_an_invalid_xpath_regex_is_a_shape_compile_error():
    from starlayer.shacl.engine.xpath_regex import xpath_regex_to_python

    for pattern in (r"\p{NoSuchCategory}", r"\p{IsNoSuchBlock}", r"\p", r"\p{L", "[a-z-[aeiou]x]"):
        with pytest.raises(ShapeCompileError):
            xpath_regex_to_python(pattern)


def test_an_unknown_term_tag_in_a_plan_file_is_a_shape_compile_error():
    from starlayer.shacl.engine.plan_json import term_from_json

    with pytest.raises(ShapeCompileError, match="unknown term tag"):
        term_from_json({"t": "nonsense"})
