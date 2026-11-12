"""evaluate(validate=True): conformance-gated evaluation, the contract of extract_subgraph().

The default (validate=False) is a lens and is covered by test_evaluate_virtual_values.py; here the flag turns on the
gate: values are computed for a (shape, focus node) pair only when the node conforms to the shape that targets it,
checked as validate() does (computed sh:values included, #202).
"""

from __future__ import annotations

import pytest
from rdflib import Literal, Namespace
from starlayer import StarLayerGraph
from starlayer.shacl import StarShaclSchema, validate
from starlayer.shacl import evaluate as _evaluate

EX = Namespace("http://example.org/")


def evaluate(*args, **kwargs):
    """the result as an rdflib graph, so the comparisons below are on rdflib terms (the engine returns pyoxigraph terms)"""
    return _evaluate(*args, **kwargs).to_rdflib()

PREFIXES = """
@prefix ex: <http://example.org/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
@prefix sparql: <http://www.w3.org/ns/sparql#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""

COUNT = "sh:values [ shnex:count [ shnex:pathValues ex:friend ] ]"


def _g(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PREFIXES + ttl, format="turtle12")
    return g


def _counts(result, predicate=EX.friendCount) -> dict:
    return {s: o.toPython() for s, _, o in result.triples((None, predicate, None))}


# ex:ok has a name, ex:bad has none (fails the minCount of the same shape)
DATA = """
ex:ok a ex:Person ; ex:name "Ok" ; ex:friend ex:x, ex:y .
ex:bad a ex:Person ; ex:friend ex:x .
"""
SHAPES = f"""
ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
  sh:property [ sh:path ex:name ; sh:minCount 1 ] ;
  sh:property [ sh:path ex:friendCount ; {COUNT} ] .
"""


class TestGate:
    def test_default_is_a_lens(self) -> None:
        result = evaluate(_g(DATA), _g(SHAPES))
        assert _counts(result) == {EX.ok: 2, EX.bad: 1}

    def test_non_conforming_node_contributes_nothing(self) -> None:
        data, shapes = _g(DATA), _g(SHAPES)
        assert not validate(data, shapes).conforms
        result = evaluate(data, shapes, validate=True)
        assert _counts(result) == {EX.ok: 2}
        assert not set(result.triples((EX.bad, None, None)))

    def test_method_matches_function(self) -> None:
        data, shapes = _g(DATA), _g(SHAPES)
        by_method = StarShaclSchema(shacl_graph=shapes).evaluate(data_graph=data, validate=True).to_rdflib()
        assert set(by_method) == set(evaluate(data, shapes, validate=True))

    def test_focus_nodes_and_properties_still_restrict(self) -> None:
        result = evaluate(_g(DATA), _g(SHAPES), validate=True, focus_nodes=[EX.bad])
        assert len(result) == 0
        result = evaluate(_g(DATA), _g(SHAPES), validate=True, properties=[EX.name])
        assert set(result) == {(EX.ok, EX.name, Literal("Ok"))}

    def test_every_node_conforms_gives_the_same_graph(self) -> None:
        data = _g('ex:a a ex:Person ; ex:name "A" ; ex:friend ex:x . ex:b a ex:Person ; ex:name "B" .')
        shapes = _g(SHAPES)
        assert validate(data, shapes).conforms
        assert set(evaluate(data, shapes, validate=True)) == set(evaluate(data, shapes))

    def test_not_a_target_contributes_nothing_in_either_mode(self) -> None:
        data = _g(DATA + 'ex:other ex:name "O" ; ex:friend ex:x .')
        for flag in (False, True):
            result = evaluate(data, _g(SHAPES), validate=flag)
            assert not set(result.triples((EX.other, None, None)))


class TestSeveralShapes:
    def test_node_gets_the_values_of_the_shapes_it_conforms_to(self) -> None:
        data = _g('ex:n a ex:Person ; ex:name "N" ; ex:friend ex:x .')
        shapes = _g("""
            ex:A a sh:NodeShape ; sh:targetNode ex:n ;
              sh:property [ sh:path ex:missing ; sh:minCount 1 ] ;
              sh:property [ sh:path ex:fromA ; sh:values "a" ] .
            ex:B a sh:NodeShape ; sh:targetNode ex:n ;
              sh:property [ sh:path ex:fromB ; sh:values "b" ] .
            """)
        both = evaluate(data, shapes)
        assert set(both.objects(EX.n, EX.fromA)) and set(both.objects(EX.n, EX.fromB))
        gated = evaluate(data, shapes, validate=True)
        assert not set(gated.objects(EX.n, EX.fromA))
        assert {o.toPython() for o in gated.objects(EX.n, EX.fromB)} == {"b"}

    def test_same_value_from_two_conforming_shapes_appears_once(self) -> None:
        data = _g("ex:n ex:friend ex:x .")
        shapes = _g(f"""
            ex:A a sh:NodeShape ; sh:targetNode ex:n ; sh:property [ sh:path ex:friendCount ; {COUNT} ] .
            ex:B a sh:NodeShape ; sh:targetNode ex:n ; sh:property [ sh:path ex:friendCount ; {COUNT} ] .
            """)
        assert set(evaluate(data, shapes, validate=True).triples((EX.n, EX.friendCount, None))) == {
            (EX.n, EX.friendCount, Literal(1))
        }


class TestComputedValueDecidesConformance:
    def test_issue_202_repro_conforms_and_is_evaluated(self) -> None:
        shapes = _g("""
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property ex:Name, ex:Full .
            ex:Name a sh:PropertyShape ; sh:path ex:first ; sh:minCount 1 .
            ex:Full a sh:PropertyShape ; sh:path ex:fullName ; sh:minCount 1 ;
                sh:values [ sparql:concat ( [ shnex:pathValues ex:first ] " " [ shnex:pathValues ex:last ] ) ] .
            """)
        data = _g('ex:a a ex:Person ; ex:first "Ada" ; ex:last "Lovelace" .')
        assert validate(data, shapes).conforms
        result = evaluate(data, shapes, validate=True)
        assert {o.toPython() for o in result.objects(EX.a, EX.fullName)} == {"Ada Lovelace"}

    def test_fresh_process_does_not_depend_on_validate_having_run(self) -> None:
        import subprocess
        import sys

        code = (
            "from starlayer.graph import StarLayerGraph\n"
            "from starlayer.shacl import evaluate\n"
            f"P = {PREFIXES!r}\n"
            "s = StarLayerGraph(); s.parse(data=P + '''"
            "ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property "
            "[ sh:path ex:full ; sh:minCount 1 ; sh:values \"v\" ] .''', format='turtle12')\n"
            "d = StarLayerGraph(); d.parse(data=P + 'ex:a a ex:Person .', format='turtle12')\n"
            "print(len(evaluate(d, s, validate=True)))\n"
        )
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        assert int(out.stdout.strip().splitlines()[-1]) == 1


class TestDeactivated:
    def test_deactivated_shape_contributes_nothing(self) -> None:
        data = _g('ex:n ex:name "N" ; ex:friend ex:x .')
        shapes = _g(f"""
            ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:deactivated true ;
              sh:property [ sh:path ex:friendCount ; {COUNT} ] .
            """)
        for flag in (False, True):
            assert len(evaluate(data, shapes, validate=flag)) == 0

    def test_deactivated_failing_shape_does_not_block_an_active_one(self) -> None:
        data = _g("ex:n ex:friend ex:x .")
        shapes = _g(f"""
            ex:Off a sh:NodeShape ; sh:targetNode ex:n ; sh:deactivated true ;
              sh:property [ sh:path ex:missing ; sh:minCount 1 ] .
            ex:On a sh:NodeShape ; sh:targetNode ex:n ; sh:property [ sh:path ex:friendCount ; {COUNT} ] .
            """)
        assert _counts(evaluate(data, shapes, validate=True)) == {EX.n: 1}


@pytest.mark.parametrize("flag", [False, True])
def test_data_graph_is_not_mutated(flag: bool) -> None:
    data = _g(DATA)
    before = set(data)
    _evaluate(data, _g(SHAPES), validate=flag)
    assert set(data) == before
