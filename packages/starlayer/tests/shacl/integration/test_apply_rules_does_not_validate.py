"""``apply_rules()`` runs the rules and validates nothing (decision 2026-11-24): ``RulesResult`` has only ``inferred_graph``, the options that
describe a validation are refused, and the check of a rule's outcome is ``validate(rules=True)`` or ``validate()`` over the data together
with ``result.inferred_graph`` against any shapes."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl import RulesResult, StarShaclProcessor, apply_rules, validate

PFX = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .\n"
)

# a rule that gives every person the level 7, and a shape (in the same graph) that holds levels to at most 10
RULE = (
    "ex:R a sh:NodeShape ; sh:targetClass ex:Person ; "
    "sh:rule [ a sh:TripleRule ; sh:subject [ shnex:var 'focusNode' ] ; sh:predicate ex:level ; sh:object 7 ] ."
)
OWN_SHAPES = RULE + " ex:Limit a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:level ; sh:maxInclusive 10 ] ."
# the same rule where the shape in the same graph holds levels to at most 5, which the inferred level 7 breaks
TIGHT_SHAPES = RULE + " ex:Limit a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:level ; sh:maxInclusive 5 ] ."
# shapes of their own, apart from the rules
OTHER_SHAPES = "ex:Other a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:level ; sh:maxInclusive 5 ] ."
DATA = "ex:alice a ex:Person ; ex:name 'Alice' ."


def g(turtle: str) -> StarLayerGraph:
    return StarLayerGraph().parse(data=PFX + turtle, format="turtle")


def union(*graphs: StarLayerGraph) -> StarLayerGraph:
    out = StarLayerGraph()
    for graph in graphs:
        out.extend(list(graph.triples((None, None, None))))
    return out


def test_the_result_has_no_validation() -> None:
    for result in (apply_rules(g(DATA), g(OWN_SHAPES)), StarShaclProcessor(g(OWN_SHAPES)).apply_rules(g(DATA))):
        assert isinstance(result, RulesResult)
        assert not hasattr(result, "validation")
        assert len(result.inferred_graph) == 1


REMOVED = {
    "allow_warnings": True,
    "allow_infos": True,
    "abort_on_first": True,
    "max_validation_depth": 5,
    "include_used_configuration": True,
    "data_graph_iri": "http://example.org/d",
    "inplace": True,
    "rules": True,
}


@pytest.mark.parametrize("option", REMOVED)
def test_an_option_that_describes_a_validation_is_refused(option: str) -> None:
    kwargs = {option: REMOVED[option]}
    with pytest.raises(TypeError, match="validate"):
        apply_rules(g(DATA), g(OWN_SHAPES), **kwargs)
    with pytest.raises(TypeError, match="validate"):
        StarShaclProcessor(g(OWN_SHAPES)).apply_rules(g(DATA), **kwargs)


def test_shapes_graph_resource_as_a_report_tag_is_refused_on_the_function() -> None:
    """On a processor ``shapes_graph_resource`` still picks a module of the bound shapes (test_extract_shapes_graph.py)."""
    with pytest.raises(TypeError, match="validate"):
        apply_rules(g(DATA), g(OWN_SHAPES), shapes_graph_resource="http://example.org/r")


def test_a_misspelt_option_is_still_unknown() -> None:
    with pytest.raises(TypeError, match="unknown option"):
        apply_rules(g(DATA), g(OWN_SHAPES), max_iteration=5)


def test_the_options_rule_execution_uses_are_accepted() -> None:
    from starlayer.graph import ENTAILMENT

    result = apply_rules(
        g(DATA),
        g(OWN_SHAPES),
        inference=ENTAILMENT.RDFS,
        recompute="onChange",
        subclass_of_in_shapes_graph=False,
        meta_shacl=False,
        meta_shapes_extra=(),
        ignore_imports=False,
        shapes_graph_loader=None,
        max_iterations=10,
        max_triples=100,
    )
    assert len(result.inferred_graph) == 1


def test_a_processor_with_validation_defaults_runs_apply_rules_and_validate_still_uses_them() -> None:
    shapes = "ex:W a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:nick ; sh:minCount 1 ; sh:severity sh:Warning ] ."
    processor = StarShaclProcessor(g(RULE + shapes), allow_warnings=False, allow_infos=False, max_validation_depth=3)
    assert len(processor.apply_rules(g(DATA)).inferred_graph) == 1
    assert processor.validate(g(DATA)).conforms is False  # the Warning blocks
    assert StarShaclProcessor(g(RULE + shapes), allow_warnings=True).validate(g(DATA)).conforms is True


def test_the_data_graph_is_unchanged() -> None:
    data = g(DATA)
    before = set(data.triples((None, None, None)))
    apply_rules(data, g(OWN_SHAPES), include_source_rule_provenance=True)
    StarShaclProcessor(g(OWN_SHAPES)).apply_rules(data)
    assert set(data.triples((None, None, None))) == before
    assert len(data) == len(before)


def test_validate_with_rules_gives_the_old_combined_verdict() -> None:
    """The replacement of ``apply_rules(...).validation``: the rules, then one validation of data plus inferred triples, same shapes."""
    shapes, data = g(TIGHT_SHAPES), g(DATA)
    result = apply_rules(data, shapes)
    combined = validate(union(data, result.inferred_graph), shapes, rules=False)  # what apply_rules(...).validation used to be
    assert combined.conforms is False  # the inferred level 7 breaks the shape that holds the rule
    by_rules = validate(data, shapes, rules=True)
    assert by_rules.conforms is combined.conforms
    assert by_rules.counts() == combined.counts()
    assert validate(data, shapes, rules=False).conforms is True  # without the rules there is nothing to break
    assert validate(g(DATA), g(OWN_SHAPES), rules=True).conforms is True  # a level of 7 is within 10


def test_the_union_of_data_and_inferred_triples_is_checked_against_different_shapes() -> None:
    """The motivating case: the shapes that check the outcome need not be the shapes that hold the rules."""
    rules_shapes, other_shapes, data = g(OWN_SHAPES), g(OTHER_SHAPES), g(DATA)
    result = apply_rules(data, rules_shapes)
    assert validate(union(data, result.inferred_graph), rules_shapes, rules=False).conforms is True  # the rules' own shapes allow 7
    report = validate(union(data, result.inferred_graph), other_shapes)
    assert report.conforms is False  # the other shapes allow at most 5
    assert [r.focus.value for r in report.results] == ["http://example.org/alice"]
    assert validate(data, other_shapes).conforms is True  # the data alone does not break them: it is the rule's triple
