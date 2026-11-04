import pyoxigraph as ox
import pytest
from rdflib import Namespace
from starlayer.graph.oxgraph import OxGraph
from starlayer.shacl import StarShaclSchema
from starlayer.shacl_engine.terms import to_engine

from ._rdflib_view import rd
from ._shape_loader import load_shape

EX = Namespace("http://example.org/")


def _build_reach_graph() -> OxGraph:
    g = OxGraph()
    g.add((EX.a, EX.reach, EX.b))
    g.add((EX.b, EX.reach, EX.c))
    g.add((EX.c, EX.reach, EX.d))
    return g


def _build_reach_shapes() -> OxGraph:
    shapes = OxGraph()
    shapes.parse(data=load_shape("rules_reach_sparql.ttl"), format="turtle")
    return shapes


def test_rule_iteration_reaches_fixed_point() -> None:
    shapes = _build_reach_shapes()

    validator = StarShaclSchema(shacl_graph=shapes)

    # The draft's rule iteration runs the rules to a fixpoint: a -> d needs a
    # second round (a-b-c, b-c-d first give a-c and b-d, then a-d).
    data_iterative = _build_reach_graph()
    _ = validator.validate(data_graph=data_iterative, mode="rules")

    assert (EX.a, EX.reach, EX.d) in data_iterative


def test_rule_iteration_converges_with_cyclic_triple_term_identity() -> None:
    # A cyclic reach graph (4-node cycle) where each derived reach fact is also
    # reified as a triple term. This exercises both fixed-point convergence on
    # a cycle (which could loop unboundedly if identity weren't stable) and
    # triple-term identity (the same (s, ex:reach, o) fact re-derived across
    # iterations must collapse to the same content-addressed value, not
    # duplicate or grow without bound).
    data = OxGraph()
    data.add((EX.a, EX.reach, EX.b))
    data.add((EX.b, EX.reach, EX.c))
    data.add((EX.c, EX.reach, EX.d))
    data.add((EX.d, EX.reach, EX.a))

    shapes = OxGraph()
    shapes.parse(data=load_shape("rules_reach_witness_triple_term.ttl"), format="turtle")

    validator = StarShaclSchema(shacl_graph=shapes)
    result = validator.apply_rules(data_graph=data, meta_shacl=False)

    assert result.validation.conforms is True

    # Full transitive closure of a 4-node cycle is all 16 ordered pairs
    # (including self-loops), each reified exactly once - no duplicates.
    witnesses = list(result.inferred_graph.triples((None, EX.reachWitness, None)))
    assert len(witnesses) == 16
    distinct = {o for _, _, o in witnesses}
    assert len(distinct) == 16
    assert all(isinstance(o, ox.Triple) and o.predicate == to_engine(EX.reach) for o in distinct)


def test_rule_iteration_converges_on_non_cyclic_multi_branch_diamond() -> None:
    # A diamond DAG (a -> b, a -> c, b -> d, c -> d): two independent paths
    # from a to d. Confirms the fixed-point convergence already proven for a
    # cycle also holds for ordinary branching/merging structure with no
    # cycle at all, and that a-reaches-d (derivable via two distinct paths)
    # appears exactly once, not duplicated per path.
    data = OxGraph()
    data.add((EX.a, EX.reach, EX.b))
    data.add((EX.a, EX.reach, EX.c))
    data.add((EX.b, EX.reach, EX.d))
    data.add((EX.c, EX.reach, EX.d))

    shapes = _build_reach_shapes()

    validator = StarShaclSchema(shacl_graph=shapes)
    _ = validator.validate(
        data_graph=data, mode="rules", meta_shacl=False
    )

    a_reaches = {o for _, _, o in rd(data).triples((EX.a, EX.reach, None))}
    assert a_reaches == {EX.b, EX.c, EX.d}
    assert len(list(data.triples((EX.a, EX.reach, EX.d)))) == 1


def _build_linear_chain(length: int) -> OxGraph:
    g = OxGraph()
    for i in range(length):
        g.add((EX[f"n{i}"], EX.base, EX[f"n{i + 1}"]))
        g.add((EX[f"n{i}"], EX.reach, EX[f"n{i + 1}"]))
    return g


# rules_reach_linear_sparql.ttl's immutable-base-relation join grows ex:reach
# by exactly one hop per rule iteration, so "iterations needed" == "chain
# length". The iteration cap (max_iterations, default 1000) is not an option of
# validate(); the tests use the engine's apply_rules directly with a small cap.
def _linear_rules(data, max_iterations):
    from starlayer.shacl_engine.rules import apply_rules

    shapes = OxGraph()
    shapes.parse(data=load_shape("rules_reach_linear_sparql.ttl"), format="turtle")
    return apply_rules(data, shapes, max_iterations=max_iterations)


def test_rule_iteration_converges_within_iteration_limit() -> None:
    length = 3
    data = _build_linear_chain(length)
    result = _linear_rules(data, max_iterations=length + 2)
    assert tuple(to_engine(t) for t in (EX.n0, EX.reach, EX[f"n{length}"])) in result.inferred


def test_rule_iteration_raises_when_exceeding_iteration_limit() -> None:
    from starlayer.shacl import RuleError

    data = _build_linear_chain(10)
    with pytest.raises(RuleError, match="fixpoint"):
        _linear_rules(data, max_iterations=3)
