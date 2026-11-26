"""The shapes of the library's own meta checks (SHACL-SHACL for ``meta_shacl``, the ``sqe:`` and ``srl:`` shapes) are parsed into a Plan
once per process, not on every call (a call used to rebuild about 160 shapes, 50 to 90 ms, to check a few triples)."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl import MetaShaclError, validate
from starlayer.shacl.engine import builder, meta
from starlayer.sparql import sparql_to_tree, sqe, srl

PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
QUERY = "PREFIX ex: <http://example.org/> SELECT * WHERE { ?s ex:p ?v }"
RULES = "PREFIX : <http://example.org/> RULE { ?a :r ?b } WHERE { ?a :e ?b }"


def g(ttl: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=PFX + ttl, format="turtle")
    return graph


GOOD = g("ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .")
BAD = g("ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:p ; sh:minCount \"one\" ] .")
DATA = g("ex:a a ex:C ; ex:p 1 .")


@pytest.fixture
def built(monkeypatch):
    """The nodes ``Plan`` builds a shape for, in order."""
    nodes: list = []
    real = builder.build_shape

    def counting(shapes_graph, node, *args, **kwargs):
        nodes.append(node)
        return real(shapes_graph, node, *args, **kwargs)

    monkeypatch.setattr(builder, "build_shape", counting)
    return nodes


def test_the_second_meta_check_builds_no_shape(built):
    validate(DATA, GOOD, meta_shacl=True)  # may build them
    built.clear()
    validate(DATA, GOOD, meta_shacl=True)
    # the shapes being checked are built for the validation itself (2 here); the 160 or so of the meta-shapes are not
    assert len(built) < 10, f"{len(built)} shapes built on the second call"


def test_the_count_notices_a_rebuild(built, monkeypatch):
    """Mutation check: if every call got a fresh meta-shapes graph (and so a fresh Plan), the count above would be about 160."""
    validate(DATA, GOOD, meta_shacl=True)
    monkeypatch.setattr(meta, "_static_meta_graph", lambda: __import__("starlayer.shacl.meta_shapes", fromlist=["x"]).load_meta_shapes_graph(()))
    built.clear()
    validate(DATA, GOOD, meta_shacl=True)
    assert len(built) > 100


def test_an_invalid_shapes_graph_is_still_refused_every_time():
    for _ in range(3):
        with pytest.raises(MetaShaclError):
            validate(DATA, BAD, meta_shacl=True)
        validate(DATA, GOOD, meta_shacl=True)  # and a valid one in between is accepted


def test_the_shared_meta_shapes_are_not_changed_by_use():
    shared = meta._static_meta_graph()
    before = set(shared.triples((None, None, None)))
    for shapes in (GOOD, BAD):
        try:
            validate(DATA, shapes, meta_shacl=True)
        except MetaShaclError:
            pass
    assert set(meta._static_meta_graph().triples((None, None, None))) == before


def test_an_extra_meta_shape_still_applies_and_leaves_no_trace():
    """``meta_shapes_extra`` makes a one-off graph; it must neither be skipped nor stay in the shared one."""
    extra = g("ex:NoExtras a sh:NodeShape ; sh:targetClass sh:NodeShape ; sh:property [ sh:path sh:targetClass ; sh:maxCount 0 ] .")
    plain = meta.meta_validate(GOOD)
    assert plain.conforms
    with_extra = meta.meta_validate(GOOD, extra=[extra])
    assert not with_extra.conforms  # GOOD has a sh:targetClass, which the extra shape forbids
    assert meta.meta_validate(GOOD).conforms  # nothing of the extra stayed behind


def test_a_stubbed_engine_is_called_without_the_plan_cache():
    seen = {}

    def stub(shapes, meta_graph, **kwargs):
        seen.update(kwargs)
        from starlayer.shacl.engine.api import validate as real

        return real(shapes, meta_graph, **{k: v for k, v in kwargs.items() if k != "plan_cache"})

    meta.meta_validate(GOOD, engine_validate=stub)
    assert "plan_cache" not in seen


def test_the_sqe_and_srl_checks_reuse_their_plans(built):
    sparql_to_tree(QUERY)
    srl.parse_ruleset(RULES)
    built.clear()
    sparql_to_tree(QUERY)
    srl.parse_ruleset(RULES)
    assert len(built) < 10, f"{len(built)} shapes built on the second round"
