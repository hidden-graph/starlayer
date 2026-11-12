"""``extract_subgraph()`` and SPARQL-based constraints: the fragment of a conforming node keeps the triples its ``sh:sparql``
constraints and SPARQL-based components depend on, including the ones that exclude a row (``FILTER NOT EXISTS``), so the node
still conforms in its fragment."""

from __future__ import annotations

import pyoxigraph as ox
from starlayer.graph import StarLayerGraph
from starlayer.shacl import extract_subgraph, validate

PREFIXES = """
@prefix ex: <http://example.org/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
"""
A = ox.NamedNode("http://example.org/a")


def _g(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PREFIXES + ttl, format="turtle12")
    return g


def _predicates(fragment) -> set[str]:
    return {p.value.rsplit("/", 1)[-1] for _s, p, _o in fragment}


DATA = """
ex:a a ex:P ; ex:v 1, 2 ; ex:ok 1, 2 ; ex:noise "n" .
ex:b a ex:P ; ex:v 3 ; ex:noise "m" .
"""

SPARQL_CONSTRAINT = """
ex:S a sh:NodeShape ; sh:targetNode ex:a ;
  sh:sparql [ sh:select \"\"\"SELECT $this ?value WHERE {
      $this <http://example.org/v> ?value .
      FILTER NOT EXISTS { $this <http://example.org/ok> ?value } }\"\"\" ] .
"""


def _fragment(shapes: str, data: str = DATA):
    shapes_g, data_g = _g(shapes), _g(data)
    assert validate(data_g, shapes_g, meta_shacl=False).conforms
    fragment = extract_subgraph(data_g, shapes_g)
    assert validate(fragment, shapes_g, meta_shacl=False).conforms
    return fragment


def test_a_sparql_constraint_keeps_the_triples_that_exclude_each_row() -> None:
    fragment = _fragment(SPARQL_CONSTRAINT)
    assert _predicates(fragment) == {"v", "ok"}  # the values, and the ok triples that cleared them; no noise, no type


def test_a_sparql_constraint_does_not_keep_triples_of_other_nodes() -> None:
    fragment = _fragment(SPARQL_CONSTRAINT)
    assert {s for s, _p, _o in fragment} == {A}


def test_a_sparql_based_component_with_a_select_validator() -> None:
    shapes = """
    ex:Covered a sh:ConstraintComponent ;
      sh:parameter [ sh:path ex:covers ] ;
      sh:nodeValidator [ a sh:SPARQLSelectValidator ;
        sh:select \"\"\"SELECT $this ?value WHERE {
            $this <http://example.org/v> ?value . FILTER NOT EXISTS { $this $covers ?value } }\"\"\" ] .
    ex:S a sh:NodeShape ; sh:targetNode ex:a ; ex:covers ex:ok .
    """
    assert _predicates(_fragment(shapes)) == {"v", "ok"}


def test_a_sparql_based_component_with_an_ask_validator() -> None:
    shapes = """
    ex:HasOk a sh:ConstraintComponent ;
      sh:parameter [ sh:path ex:needs ] ;
      sh:validator [ a sh:SPARQLAskValidator ;
        sh:ask \"\"\"ASK { $this $needs $value }\"\"\" ] .
    ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:v ; ex:needs ex:ok ] .
    """
    fragment = _fragment(shapes)
    assert "ok" in _predicates(fragment) and "v" in _predicates(fragment)
    assert "noise" not in _predicates(fragment)


EXPR_PREFIXES = """
@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
@prefix sparql: <http://www.w3.org/ns/sparql#> .
"""


def test_an_expression_constraint_keeps_the_triples_it_reads() -> None:
    shapes = EXPR_PREFIXES + """
    ex:S a sh:NodeShape ; sh:targetNode ex:a ;
      sh:expression [ sparql:equals ( [ shnex:pathValues ex:v ] [ shnex:pathValues ex:ok ] ) ] .
    """
    data = "ex:a ex:v 1 ; ex:ok 1 ; ex:noise 5 ."
    assert _predicates(_fragment(shapes, data)) == {"v", "ok"}


def test_a_node_by_expression_constraint_keeps_the_triples_of_the_computed_shape() -> None:
    shapes = EXPR_PREFIXES + """
    ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property ex:PS .
    ex:PS sh:path ex:next ; sh:nodeByExpression [ shnex:pathValues ex:shapeOf ] .
    ex:NeedsName a sh:NodeShape ; sh:property [ sh:path ex:name ; sh:minCount 1 ] .
    """
    # the shape is computed from the value node's ex:shapeOf, which is read at ex:b
    data = "ex:a ex:next ex:b . ex:b ex:shapeOf ex:NeedsName ; ex:name \"B\" ; ex:noise 1 ."
    fragment = _fragment(shapes, data)
    assert {"next", "shapeOf", "name"} <= _predicates(fragment)
    assert "noise" not in _predicates(fragment)
