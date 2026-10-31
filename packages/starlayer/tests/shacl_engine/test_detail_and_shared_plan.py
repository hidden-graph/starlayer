"""sh:detail for sh:memberShape / sh:uniqueMembers (Core 7.5.1, 7.5.4) and one shared Plan per validate_each batch."""

from __future__ import annotations

import pytest
from rdflib import Graph, Literal, URIRef
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl import StarShaclSchema, validate_each
from starlayer.shacl_engine import api
from starlayer.shacl_engine.plan import SH, Plan

PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "


def g(ttl: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=PFX + ttl, format="turtle12")
    return graph


def test_member_shape_nests_one_detail_per_bad_member() -> None:
    data = g('ex:l1 <http://example.org/p> ( ex:a "x" "y" ) .')
    shapes = g(
        'ex:IRIShape a sh:NodeShape ; sh:nodeKind sh:IRI .'
        ' ex:S a sh:NodeShape ; sh:targetNode ex:l1 ;'
        ' sh:property [ sh:path ex:p ; sh:memberShape ex:IRIShape ] .'
    )
    out = api.validate(data, shapes)
    rep = out.report_graph
    top = list(rep.objects(None, SH.result))
    assert len(top) == 1
    details = list(rep.objects(top[0], SH.detail))
    assert len(details) == 2
    assert {rep.value(d, SH.value) for d in details} == {Literal("x"), Literal("y")}
    for d in details:
        assert rep.value(d, SH.sourceConstraintComponent) == SH.NodeKindConstraintComponent
        assert rep.value(d, SH.sourceShape) == URIRef("http://example.org/IRIShape")
        assert d not in top  # nested, not top-level
    assert len(out.results) == 1 and len(out.results[0].details) == 2


def test_member_shape_malformed_list_has_no_detail() -> None:
    data = g("ex:l1 ex:p ex:notalist .")
    shapes = g("ex:S a sh:NodeShape ; sh:targetNode ex:l1 ; sh:property [ sh:path ex:p ; sh:memberShape [ sh:nodeKind sh:IRI ] ] .")
    rep = api.validate(data, shapes).report_graph
    assert not list(rep.objects(None, SH.detail))


def test_detail_does_not_block_conformance_by_itself() -> None:
    data = g('ex:l1 ex:p ( "x" ) .')
    shapes = g(
        "ex:S a sh:NodeShape ; sh:targetNode ex:l1 ; sh:property [ sh:path ex:p ; sh:severity sh:Warning ;"
        " sh:memberShape [ sh:nodeKind sh:IRI ] ] ."
    )
    out = api.validate(data, shapes, conformance_disallows=SH.Violation)
    assert out.conforms is True
    assert len(list(out.report_graph.objects(None, SH.detail))) == 1


def test_unique_members_details_are_the_duplicates() -> None:
    data = g("ex:l1 ex:p ( ex:a ex:b ex:a ex:b ex:b ex:c ) .")
    shapes = g("ex:S a sh:NodeShape ; sh:targetNode ex:l1 ; sh:property [ sh:path ex:p ; sh:uniqueMembers true ] .")
    rep = api.validate(data, shapes).report_graph
    (top,) = list(rep.objects(None, SH.result))
    details = list(rep.objects(top, SH.detail))
    assert {rep.value(d, SH.value) for d in details} == {URIRef("http://example.org/a"), URIRef("http://example.org/b")}


# ---- one Plan per validate_each batch ----------------------------------------------------------------------------------

SHAPES = "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:minCount 1 ] ."


@pytest.fixture
def plan_builds(monkeypatch):
    builds: list[int] = []
    real = Plan.__init__

    def counting(self, *a, **k):
        builds.append(1)
        real(self, *a, **k)

    monkeypatch.setattr(Plan, "__init__", counting)
    return builds


def _batch():
    return [g("ex:a a ex:T ."), g("ex:a a ex:T ; ex:p 1 ."), g("ex:b a ex:T .")]


def test_module_validate_each_builds_one_plan_in_engine_mode(plan_builds) -> None:
    shapes = g(SHAPES)
    out = validate_each(_batch(), shapes, engine="native")
    assert [out[i].conforms for i in range(3)] == [False, True, False]
    assert all(r.engine == "native" for r in out.values())
    assert len(plan_builds) == 1


def test_schema_validate_each_builds_one_plan_in_engine_mode(plan_builds) -> None:
    schema = StarShaclSchema(shacl_graph=g(SHAPES), engine="native")
    out = schema.validate_each(_batch())
    assert [out[i].conforms for i in range(3)] == [False, True, False]
    assert len(plan_builds) == 1


def test_plain_rdflib_shapes_graph_is_shared_too(plan_builds) -> None:
    shapes = Graph()
    shapes.parse(data=PFX + SHAPES, format="turtle")
    validate_each(_batch(), shapes, engine="native")
    assert len(plan_builds) == 1


def test_separate_validate_calls_still_build_their_own_plan(plan_builds) -> None:
    shapes = g(SHAPES)
    from starlayer.shacl import validate

    validate(g("ex:a a ex:T ."), shapes, engine="native")
    validate(g("ex:a a ex:T ."), shapes, engine="native")
    assert len(plan_builds) == 2
