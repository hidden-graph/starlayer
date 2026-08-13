import pytest
from rdflib import Namespace

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starlayergraph.model.triple import TripleTerm

from ._shape_loader import load_shape


EX = Namespace("http://example.org/")


pyshacl = pytest.importorskip("pyshacl")


def _build_reach_graph() -> StarLayerGraph:
    g = StarLayerGraph()
    g.add((EX.a, EX.reach, EX.b))
    g.add((EX.b, EX.reach, EX.c))
    g.add((EX.c, EX.reach, EX.d))
    return g


def _build_reach_shapes() -> StarLayerGraph:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rules_reach_sparql.ttl"), format="turtle")
    return shapes


def test_rule_iteration_reaches_fixed_point() -> None:
    shapes = _build_reach_shapes()

    validator = StarShaclValidator()

    data_single_pass = _build_reach_graph()
    _ = validator.validate(
        data_graph=data_single_pass,
        shacl_graph=shapes,
        advanced=True,
        inplace=True,
        iterate_rules=False,
    )

    data_iterative = _build_reach_graph()
    _ = validator.validate(
        data_graph=data_iterative,
        shacl_graph=shapes,
        advanced=True,
        inplace=True,
        iterate_rules=True,
    )

    assert (EX.a, EX.reach, EX.d) not in data_single_pass
    assert (EX.a, EX.reach, EX.d) in data_iterative


def test_rule_iteration_converges_with_cyclic_triple_term_identity() -> None:
    # A cyclic reach graph (4-node cycle) where each derived reach fact is also
    # reified as a triple term. This exercises both fixed-point convergence on
    # a cycle (which could loop unboundedly if identity weren't stable) and
    # triple-term identity (the same (s, ex:reach, o) fact re-derived across
    # iterations must collapse to the same content-addressed value, not
    # duplicate or grow without bound).
    data = StarLayerGraph()
    data.add((EX.a, EX.reach, EX.b))
    data.add((EX.b, EX.reach, EX.c))
    data.add((EX.c, EX.reach, EX.d))
    data.add((EX.d, EX.reach, EX.a))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rules_reach_witness_triple_term.ttl"), format="turtle")

    validator = StarShaclValidator()
    result = validator.apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False, iterate_rules=True)

    assert result.conforms is True

    # Full transitive closure of a 4-node cycle is all 16 ordered pairs
    # (including self-loops), each reified exactly once - no duplicates.
    witnesses = list(result.data_graph.triples((None, EX.reachWitness, None)))
    assert len(witnesses) == 16
    distinct = {o for _, _, o in witnesses}
    assert len(distinct) == 16
    assert all(isinstance(o, TripleTerm) and o.predicate == EX.reach for o in distinct)


def test_rule_iteration_converges_on_non_cyclic_multi_branch_diamond() -> None:
    # A diamond DAG (a -> b, a -> c, b -> d, c -> d): two independent paths
    # from a to d. Confirms the fixed-point convergence already proven for a
    # cycle also holds for ordinary branching/merging structure with no
    # cycle at all, and that a-reaches-d (derivable via two distinct paths)
    # appears exactly once, not duplicated per path.
    data = StarLayerGraph()
    data.add((EX.a, EX.reach, EX.b))
    data.add((EX.a, EX.reach, EX.c))
    data.add((EX.b, EX.reach, EX.d))
    data.add((EX.c, EX.reach, EX.d))

    shapes = _build_reach_shapes()

    validator = StarShaclValidator()
    _ = validator.validate(
        data_graph=data, shacl_graph=shapes, advanced=True, inplace=True, iterate_rules=True, meta_shacl=False
    )

    a_reaches = {o for _, _, o in data.triples((EX.a, EX.reach, None))}
    assert a_reaches == {EX.b, EX.c, EX.d}
    assert len(list(data.triples((EX.a, EX.reach, EX.d)))) == 1


def _build_linear_chain(length: int) -> StarLayerGraph:
    g = StarLayerGraph()
    for i in range(length):
        g.add((EX[f"n{i}"], EX.base, EX[f"n{i + 1}"]))
        g.add((EX[f"n{i}"], EX.reach, EX[f"n{i + 1}"]))
    return g


# rules_reach_linear_sparql.ttl's immutable-base-relation join grows ex:reach
# by exactly one hop per rule iteration (unlike rules_reach_sparql.ttl's
# self-referential join, which roughly doubles distance per iteration and so
# never approaches pySHACL's iteration cap at any practical chain length -
# confirmed empirically). That makes "iterations needed" == "chain length",
# but pySHACL's real default cap is 100 (pyshacl.rules.RULES_ITERATE_LIMIT /
# pyshacl.rules.sparql.SPARQL_RULE_ITERATE_LIMIT) - actually running a chain
# that long through starShacl's full validate() pipeline takes well over a
# minute (confirmed: ~8s at length 40, scaling worse than quadratically), far
# too slow for a unit test. Patching pySHACL's own module-level constants
# down to a small number exercises the exact same boundary-enforcement code
# path pySHACL uses at its real default, just at a scale that runs in
# milliseconds instead of minutes.
def _lower_iteration_limit(monkeypatch: pytest.MonkeyPatch, limit: int) -> None:
    import pyshacl.rules
    import pyshacl.rules.sparql

    monkeypatch.setattr(pyshacl.rules, "RULES_ITERATE_LIMIT", limit)
    monkeypatch.setattr(pyshacl.rules.sparql, "SPARQL_RULE_ITERATE_LIMIT", limit)


def test_rule_iteration_converges_within_iteration_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    _lower_iteration_limit(monkeypatch, 3)

    length = 3
    data = _build_linear_chain(length)

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rules_reach_linear_sparql.ttl"), format="turtle")

    validator = StarShaclValidator()
    _ = validator.validate(
        data_graph=data, shacl_graph=shapes, advanced=True, inplace=True, iterate_rules=True, meta_shacl=False
    )

    assert (EX.n0, EX.reach, EX[f"n{length}"]) in data


def test_rule_iteration_raises_when_exceeding_iteration_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    # A chain longer than the (lowered) cap can't fully propagate - confirms
    # starShacl propagates pySHACL's own ReportableRuntimeError unchanged
    # rather than hanging, silently truncating results, or masking it with
    # a different error.
    from pyshacl.errors import ReportableRuntimeError

    _lower_iteration_limit(monkeypatch, 3)

    data = _build_linear_chain(10)

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rules_reach_linear_sparql.ttl"), format="turtle")

    validator = StarShaclValidator()
    with pytest.raises(ReportableRuntimeError, match="iteration limit"):
        validator.validate(
            data_graph=data, shacl_graph=shapes, advanced=True, inplace=True, iterate_rules=True, meta_shacl=False
        )
