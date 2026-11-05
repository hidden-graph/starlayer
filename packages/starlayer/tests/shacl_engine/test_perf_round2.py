"""Round-2 performance work: conforms memo, term-conversion caches, path de-duplication, per-constraint SPARQL caching.

Every test pins behaviour (same answers as the uncached path), not speed, plus a count that proves the work was cut.
"""

from __future__ import annotations

import pyoxigraph as ox
import pytest
import rdflib
from pyoxigraph import NamedNode as URIRef
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.shacl_engine import executor
from starlayer.shacl_engine.api import validate
from starlayer.shacl_engine.oxigraph_view import OxigraphGraph, from_ox, to_ox
from starlayer.shacl_engine.paths import _dedupe
from starlayer.shacl_engine.plan import ShapeError
from starlayer.shacl_engine.terms import text

PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "


def g(ttl: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=PFX + ttl, format="turtle")
    return graph


def keys(outcome):
    return sorted((text(r.focus), text(r.value), text(r.component)) for r in outcome.results)


@pytest.fixture
def count_evaluations(monkeypatch):
    calls = []
    real = executor.validate_shape_at

    def counting(ctx, shape, focus):
        calls.append((shape.node, focus))
        return real(ctx, shape, focus)

    monkeypatch.setattr(executor, "validate_shape_at", counting)
    return calls


SHARED = """
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:node ex:Common .
ex:Common a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .
"""
# five focus nodes all point at the same hub through sh:class-free sh:node via a property shape
HUB = """
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:link ; sh:node ex:Common ] .
ex:Common a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .
"""


def test_conforms_is_evaluated_once_per_shape_and_node(count_evaluations):
    data = "ex:hub ex:q 1 . " + " ".join(f"ex:n{i} a ex:T ; ex:link ex:hub ." for i in range(5))
    out = validate(g(data), g(HUB))
    hub_visits = [c for c in count_evaluations if c[0].value.endswith("Common") and c[1].value.endswith("hub")]
    assert len(hub_visits) <= 2  # five focus nodes reach the hub: once to decide conformance, once for the sh:detail of its results
    assert len(out.results) == 5


def test_memoised_answers_equal_unmemoised(monkeypatch):
    data = "ex:hub ex:q 1 . ex:ok ex:p 1 . " + " ".join(f"ex:n{i} a ex:T ; ex:link {'ex:hub' if i % 2 else 'ex:ok'} ." for i in range(6))
    memoised = validate(g(data), g(HUB))

    class Forgetful(dict):
        def __setitem__(self, key, value):
            pass

    real_init = executor.Context.__init__

    def init(self, *a, **kw):
        real_init(self, *a, **kw)
        self._conforms_memo = Forgetful()

    monkeypatch.setattr(executor.Context, "__init__", init)
    plain = validate(g(data), g(HUB))
    assert keys(memoised) == keys(plain)
    assert not memoised.conforms


RECURSIVE = """
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:node ex:Tree .
ex:Tree a sh:NodeShape ; sh:property [ sh:path ex:child ; sh:node ex:Tree ] ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .
"""


def test_recursive_shapes_keep_the_greatest_fixpoint_answer():
    # a -> b -> a is a cycle (assumed conforming); c lacks ex:p and is reached through the cycle's child
    data = "ex:a a ex:T ; ex:p 1 ; ex:child ex:b . ex:b ex:p 1 ; ex:child ex:a . ex:c a ex:T ; ex:child ex:a ."
    out = validate(g(data), g(RECURSIVE))
    assert [text(r.focus) for r in out.results if text(r.component).endswith("NodeConstraintComponent")] == ["http://example.org/c"]


def test_recursion_through_not_still_fails():
    shapes = "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:not [ sh:property [ sh:path ex:next ; sh:node ex:S ] ] ."
    with pytest.raises(ShapeError):
        validate(g("ex:a a ex:T ; ex:next ex:a ."), g(shapes))


def test_depth_limit_is_enforced_on_a_memoised_replay():
    chain = "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:node ex:L0 .\n"
    chain += "".join(f"ex:L{i} a sh:NodeShape ; sh:property [ sh:path ex:next ; sh:node ex:L{i + 1} ] .\n" for i in range(6))
    chain += "ex:L6 a sh:NodeShape ."
    data = "ex:a a ex:T ; ex:next ex:b . ex:b ex:next ex:c . ex:c ex:next ex:d . ex:d ex:next ex:e ."
    assert validate(g(data), g(chain)).conforms  # plenty of depth
    with pytest.raises(ShapeError):
        validate(g(data), g(chain), max_validation_depth=3)


def test_dedupe_keeps_order_and_skips_trivial_lists():
    items = [URIRef("urn:a"), URIRef("urn:b"), URIRef("urn:a")]
    assert _dedupe(items) == [URIRef("urn:a"), URIRef("urn:b")]
    one = [URIRef("urn:a")]
    assert _dedupe(one) is one
    assert _dedupe(iter(items)) == [URIRef("urn:a"), URIRef("urn:b")]
    assert _dedupe([]) == []


def test_ox_term_caches_are_identity_stable_and_correct():
    """``to_ox`` / ``from_ox`` are the boundary with rdflib terms (rdflib graphs and terms are still accepted as input)."""
    iri, bn = rdflib.URIRef("http://example.org/x"), rdflib.BNode("b1")
    assert to_ox(iri) is to_ox(rdflib.URIRef("http://example.org/x"))
    assert to_ox(iri) == ox.NamedNode("http://example.org/x")
    assert to_ox(bn) == ox.BlankNode("b1")
    assert to_ox(rdflib.URIRef("urn:same")) != to_ox(rdflib.BNode("same")) and to_ox(rdflib.BNode("same")) == ox.BlankNode("same")
    for lit in (rdflib.Literal("x"), rdflib.Literal("1", datatype=rdflib.XSD.integer), rdflib.Literal("a", lang="en")):
        assert from_ox(to_ox(lit)) == lit
    node = ox.NamedNode("http://example.org/y")
    assert from_ox(node) is from_ox(ox.NamedNode("http://example.org/y"))
    assert type(from_ox(node)) is rdflib.URIRef
    assert type(from_ox(ox.BlankNode("z"))) is rdflib.BNode


def test_ox_objects_and_subjects_dedupe_across_graphs():
    store = ox.Store()
    a, p, o = (ox.NamedNode(f"http://example.org/{n}") for n in "apo")
    for graph in (ox.DefaultGraph(), ox.NamedNode("http://example.org/g1"), ox.NamedNode("http://example.org/g2")):
        store.add(ox.Quad(a, p, o, graph))
        store.add(ox.Quad(a, p, ox.Literal("v"), graph))
    view = OxigraphGraph(store)
    A, P, OBJ = URIRef("http://example.org/a"), URIRef("http://example.org/p"), URIRef("http://example.org/o")
    assert sorted(t.value for t in view.objects(A, P)) == ["http://example.org/o", "v"]
    assert list(view.subjects(P, OBJ)) == [A]
    assert sorted(t.value for t in view.objects(A, None)) == ["http://example.org/o", "v"]
    named = OxigraphGraph(store, URIRef("http://example.org/g1"))
    assert len(list(named.objects(A, P))) == 2


def test_sparql_constraint_is_prepared_once_per_run(monkeypatch):
    shapes = g(
        'ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:sparql [ sh:message "bad {$this}" ; '
        'sh:select "SELECT $this WHERE { $this <http://example.org/bad> true }" ] .'
    )
    data = g(" ".join(f"ex:n{i} a ex:T ; ex:bad {'true' if i % 2 else 'false'} ." for i in range(6)))
    from starlayer.shacl_engine.components import sparql_constraints as sc

    calls = []
    real = sc.substitute_path
    monkeypatch.setattr(sc, "substitute_path", lambda text, shape: calls.append(shape.node) or real(text, shape))
    out = validate(data, shapes)
    assert len(out.results) == 3
    assert all("bad http://example.org/n" in text(m) for r in out.results for m in r.messages)
    assert len(calls) == 1  # was one per focus node
