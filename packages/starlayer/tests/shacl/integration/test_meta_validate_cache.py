"""``meta_validate`` keeps the meta graph and compiled plan of a check with extra graphs or parameter-value shapes."""

import pytest
from starlayer.graph import StarLayerGraph as Graph
from starlayer.graph.entailment.cache import content_fingerprint
from starlayer.shacl.engine import meta
from starlayer.shacl.engine.meta import meta_validate

PREFIX = "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.org/> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"


def shapes_with_parameter(datatype: str = "xsd:integer", value: str = "3") -> Graph:
    graph = Graph()
    graph.parse(
        data=PREFIX
        + f"""ex:C a sh:ConstraintComponent ; sh:parameter [ sh:path ex:minLen ; sh:datatype {datatype} ] ;
          sh:validator [ a sh:SPARQLAskValidator ; sh:ask "ASK {{ }}" ] .
        ex:S a sh:NodeShape ; sh:targetClass ex:T ; ex:minLen {value} .""",
        format="turtle",
    )
    return graph


def extra_graph(label: str) -> Graph:
    graph = Graph()
    graph.parse(data=PREFIX + f'ex:Extra{label} a sh:NodeShape ; sh:targetClass ex:Never{label} ; sh:closed true .', format="turtle")
    return graph


@pytest.fixture(autouse=True)
def empty_cache():
    with meta._meta_cache_lock:
        meta._meta_cache.clear()
        meta._meta_cache_stats.update(hits=0, misses=0)
    yield


def test_a_repeated_call_with_the_same_parameter_shapes_hits_the_cache_and_agrees():
    shapes = shapes_with_parameter()
    first = meta_validate(shapes)
    results = [meta_validate(shapes) for _ in range(3)]
    assert meta._meta_cache_stats == {"hits": 3, "misses": 1}
    assert all((r.conforms, r.problems) == (first.conforms, first.problems) for r in results)
    assert first.conforms


def test_the_same_content_read_again_is_the_same_entry_though_its_blank_nodes_are_labelled_anew():
    meta_validate(shapes_with_parameter())
    meta_validate(shapes_with_parameter())
    assert meta._meta_cache_stats == {"hits": 1, "misses": 1}
    assert len(meta._meta_cache) == 1


def test_a_repeated_call_with_the_same_extra_graph_hits_the_cache():
    shapes, extra = shapes_with_parameter(), extra_graph("A")
    first = meta_validate(shapes, extra=[extra])
    second = meta_validate(shapes, extra=[extra])
    assert meta._meta_cache_stats["hits"] == 1
    assert (first.conforms, first.problems) == (second.conforms, second.problems)


def test_a_changed_extra_graph_is_not_served_from_the_old_entry():
    shapes = shapes_with_parameter()
    extra = Graph()
    extra.parse(data=PREFIX + "[] a sh:NodeShape ; sh:targetClass sh:NodeShape ; sh:property [ sh:path ex:forbidden ; sh:maxCount 0 ] .", format="turtle")
    flagged = Graph()
    flagged.parse(data=PREFIX + "ex:S a sh:NodeShape ; ex:forbidden 1 .", format="turtle")
    assert meta_validate(flagged, extra=[extra]).conforms is False
    assert meta_validate(flagged).conforms is True  # no extra: a different entry (the shared static graph)
    other = Graph()
    other.parse(data=PREFIX + "[] a sh:NodeShape ; sh:targetClass sh:NodeShape ; sh:property [ sh:path ex:forbidden ; sh:maxCount 5 ] .", format="turtle")
    assert meta_validate(flagged, extra=[other]).conforms is True
    assert meta._meta_cache_stats["hits"] == 0 and len(meta._meta_cache) == 2
    del shapes


def test_a_changed_parameter_is_not_served_from_the_old_entry():
    assert meta_validate(shapes_with_parameter("xsd:integer", "3")).conforms is True
    assert meta_validate(shapes_with_parameter("xsd:integer", '"three"')).conforms is False
    assert meta_validate(shapes_with_parameter("xsd:string", '"three"')).conforms is True
    assert meta_validate(shapes_with_parameter("xsd:string", "3")).conforms is False
    assert meta._meta_cache_stats["misses"] == 2  # the two datatypes; the values do not change the parameter shapes
    assert meta._meta_cache_stats["hits"] == 2


def test_the_cache_is_bounded_and_drops_the_oldest_first():
    shapes = shapes_with_parameter()
    for i in range(meta._META_CACHE_MAXSIZE + 3):
        meta_validate(shapes, extra=[extra_graph(str(i))])
    assert len(meta._meta_cache) == meta._META_CACHE_MAXSIZE
    meta_validate(shapes, extra=[extra_graph("0")])  # the oldest was dropped: a miss again
    assert meta._meta_cache_stats["hits"] == 0
    meta_validate(shapes, extra=[extra_graph("10")])  # the newest is still there
    assert meta._meta_cache_stats["hits"] == 1


def test_a_validation_does_not_change_the_kept_meta_graph():
    shapes = shapes_with_parameter()
    meta_validate(shapes)
    ((graph, plans),) = meta._meta_cache.values()
    before = content_fingerprint(graph.triples((None, None, None)))
    for _ in range(3):
        meta_validate(shapes)
    assert content_fingerprint(graph.triples((None, None, None))) == before
    assert len(plans) == 1  # one plan, compiled once, under the identity of the kept graph


def test_an_injected_engine_is_never_cached():
    seen = []

    def fake(shapes, meta_graph, **kwargs):
        seen.append((meta_graph, kwargs))
        return _Outcome()

    class _Outcome:
        conforms = True
        results = []
        report_graph = Graph()

    shapes = shapes_with_parameter()
    meta_validate(shapes, engine_validate=fake)
    meta_validate(shapes, engine_validate=fake)
    assert not meta._meta_cache and "plan_cache" not in seen[0][1]
    assert seen[0][0] is not seen[1][0]
