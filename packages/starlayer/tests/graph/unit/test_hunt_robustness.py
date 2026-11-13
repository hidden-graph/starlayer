"""Regression tests for the robustness hunt: deep lists, init-binding injection, union rewrites, shared lists."""

from __future__ import annotations

import threading
import time

import pyoxigraph as ox
import pytest
from starlayer import StarLayerDataset
from starlayer.graph import StarLayerGraph


def test_cbd_of_a_long_rdf_list_does_not_recurse():
    n = 3000
    items = " ".join(str(i) for i in range(n))
    g = StarLayerGraph()
    g.parse(data=f"@prefix ex: <http://e/> . ex:a ex:list ({items}) .", format="turtle")
    d = g.cbd(ox.NamedNode("http://e/a"))
    assert len(d) == len(g) == 2 * n + 1


def test_init_bindings_with_exists_in_the_select_list():
    g = StarLayerGraph()
    g.parse(data="<http://a> <http://p> <http://x> . <http://b> <http://p> <http://y> .", format="turtle")
    q = "SELECT (EXISTS { ?z <http://p> ?w } AS ?e) ?y WHERE { ?s <http://p> ?y }"
    rows = list(g.query(q, initBindings={"s": ox.NamedNode("http://a")}))
    assert len(rows) == 1


def test_init_bindings_with_a_prefix_named_construct():
    g = StarLayerGraph()
    g.parse(data="<http://a> <http://p> <http://x> . <http://b> <http://p> <http://y> .", format="turtle")
    q = "PREFIX construct: <http://> SELECT ?o WHERE { ?s construct:p ?o }"
    rows = list(g.query(q, initBindings={"s": ox.NamedNode("http://a")}))
    assert len(rows) == 1


@pytest.mark.parametrize("pfx", ["using", "where"])
def test_union_update_with_a_prefix_named_like_a_keyword(pfx):
    ds = StarLayerDataset()
    ds.update("INSERT DATA { GRAPH <http://g1> { <http://a> <http://p> <http://b> } }")
    ds.update(f"PREFIX {pfx}: <http://x/> INSERT {{ ?s <http://q> ?o }} WHERE {{ ?s <http://p> ?o }}")
    assert len(list(ds.triples((None, None, None)))) - 1 == 1


def test_derive_shape_template_with_a_shared_in_list():
    P = (
        "@prefix sh:<http://www.w3.org/ns/shacl#> . @prefix ex:<http://e/> . "
        "@prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
    )
    tmpl = StarLayerGraph()
    tmpl.parse(
        data=P
        + """
ex:S a sh:NodeShape; sh:targetClass ex:C; sh:closed true; sh:ignoredProperties (rdf:type);
  sh:property [ sh:path ex:p; sh:in _:l ], [ sh:path ex:q; sh:in _:l ] .
_:l rdf:first "a"; rdf:rest _:m . _:m rdf:first "b"; rdf:rest rdf:nil .""",
        format="turtle",
    )
    data = StarLayerGraph()
    data.parse(data=P + 'ex:n a ex:C; ex:p "c"; ex:q "a" .', format="turtle")
    shapes = data.derive_shape(tmpl)
    firsts = {str(o.value) for _, _, o in shapes.triples((None, ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#first"), None))}
    assert {"a", "b", "c"} <= firsts  # p's list gained "c"; q's list is still there


def _race_once(n: int, count: str) -> int:
    ds = StarLayerDataset(default_union=True)
    ds.update("INSERT DATA { GRAPH <urn:g1> { <urn:a> <urn:p> 0 } }")
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            ds.query(count)

    readers = [threading.Thread(target=reader) for _ in range(3)]
    for t in readers:
        t.start()
    for i in range(n):
        s = ox.NamedNode(f"urn:x{i}")
        p, o = ox.NamedNode("urn:p"), ox.Literal("v")
        ds.addN([ox.Quad(s, p, o, ox.NamedNode("urn:g1")), ox.Quad(s, p, o, ox.NamedNode("urn:g2"))])
    stop.set()
    for t in readers:
        t.join()
    return int(next(iter(ds.query(count)))[0].value)


def test_union_cache_is_not_stale_after_concurrent_writes():
    n = 1500
    count = "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }"
    t0 = time.time()
    for _ in range(30):
        if time.time() - t0 > 40:
            break
        assert _race_once(n, count) == n + 1
