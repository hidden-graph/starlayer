"""Logical, shape-based, closed, reifier and root-class components of the native SHACL engine."""

from __future__ import annotations

import pytest
from rdflib import Graph
from pyoxigraph import NamedNode as URIRef
from starlayer.graph.oxgraph import OxGraph
from starlayer.shacl_engine import validate
from starlayer.shacl_engine.plan import ShapeError
from starlayer.shacl_engine.terms import SH, lexical, text

PRE = """@prefix ex: <http://example.com/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"""


def run(shapes: str, data: str = ""):
    sg, dg = OxGraph(), OxGraph()
    sg.parse(data=PRE + shapes, format="turtle")
    dg.parse(data=PRE + (data or shapes), format="turtle")
    return validate(dg, sg)


def results(shapes: str, data: str = ""):
    out = run(shapes, data)
    return sorted((text(r.focus).rsplit("/", 1)[-1], text(r.component).rsplit("#", 1)[-1]) for r in out.results)


TARGETS = "ex:S a sh:NodeShape ; sh:targetNode ex:a, ex:b ; "
DATA = "ex:a ex:p 1 ; a ex:A . ex:b ex:p 2 ; a ex:B .\n"


def test_not():
    s = TARGETS + "sh:not [ sh:class ex:A ] . "
    assert results(s + DATA) == [("a", "NotConstraintComponent")]


def test_and_or_xone():
    both = "sh:class ex:A"
    and_ = TARGETS + f"sh:and ( [ {both} ] [ sh:class ex:B ] ) ."
    assert results(and_ + DATA) == [("a", "AndConstraintComponent"), ("b", "AndConstraintComponent")]
    or_ = TARGETS + "sh:or ( [ sh:class ex:A ] [ sh:class ex:C ] ) ."
    assert results(or_ + DATA) == [("b", "OrConstraintComponent")]
    xone = TARGETS + "sh:xone ( [ sh:class ex:A ] [ sh:nodeKind sh:IRI ] ) ."
    assert results(xone + DATA) == [("a", "XoneConstraintComponent")]


def test_empty_lists():
    assert [c for _, c in results(TARGETS + "sh:or () . " + DATA)] == ["OrConstraintComponent"] * 2
    assert results(TARGETS + "sh:and () . " + DATA) == []


def test_value_reported_on_property_shape():
    s = TARGETS + "sh:property [ sh:path ex:p ; sh:not [ sh:in ( 1 ) ] ] . "
    out = run(s + DATA)
    assert [(r.focus, r.value) for r in out.results if r.focus == URIRef("http://example.com/a")][0][1].value == "1"


@pytest.mark.parametrize(
    "bad", ["sh:and ex:notAList", "sh:or [ rdf:first 1 ; rdf:rest ex:x ]", "sh:xone 5", "sh:and ( 1 )", "sh:not 1", "sh:node 1"]
)
def test_malformed_logical(bad):
    with pytest.raises(ShapeError):
        run(TARGETS + bad + " . " + DATA)


def test_node():
    s = TARGETS + "sh:node ex:T . ex:T a sh:NodeShape ; sh:class ex:A . "
    assert results(s + DATA) == [("b", "NodeConstraintComponent")]


def test_recursion_counts_as_conforming():
    s = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:next ; sh:node ex:S ] . "
    assert results(s + "ex:a ex:next ex:a .") == []


QDATA = "ex:h ex:d ex:f1, ex:t1, ex:ft . ex:f1 a ex:F . ex:t1 a ex:T . ex:ft a ex:F, ex:T .\n"
QSHAPES = """ex:H a sh:NodeShape ; sh:targetNode ex:h ;
  sh:property [ sh:path ex:d ; sh:qualifiedValueShape [ sh:class ex:F ] ; sh:qualifiedMinCount %s ; sh:qualifiedMaxCount %s ;
                sh:qualifiedValueShapesDisjoint %s ] ;
  sh:property [ sh:path ex:d ; sh:qualifiedValueShape [ sh:class ex:T ] ; sh:qualifiedMinCount 0 ] .\n"""


def test_qualified_counts():
    assert results(QSHAPES % (2, 2, "false") + QDATA) == []
    assert results(QSHAPES % (3, 3, "false") + QDATA) == [("h", "QualifiedMinCountConstraintComponent")]
    assert results(QSHAPES % (0, 1, "false") + QDATA) == [("h", "QualifiedMaxCountConstraintComponent")]


def test_qualified_disjoint_excludes_siblings():
    # ex:ft conforms to both siblings, so with disjoint it counts for neither: only f1 remains
    assert results(QSHAPES % (2, 2, "true") + QDATA) == [("h", "QualifiedMinCountConstraintComponent")]
    assert results(QSHAPES % (1, 1, "true") + QDATA) == []


def test_qualified_params_without_shape_ignored():
    assert results(TARGETS + "sh:qualifiedMinCount 5 . " + DATA) == []


def test_qualified_bad_count():
    s = TARGETS + "sh:property [ sh:path ex:p ; sh:qualifiedValueShape [ ] ; sh:qualifiedMinCount 1.5 ] ."
    with pytest.raises(ShapeError):
        run(s + DATA)


def test_closed_reports_each_offending_predicate():
    s = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:closed true ; sh:ignoredProperties ( rdf:type ) ; sh:property [ sh:path ex:p ] . "
    out = run(s + "ex:a a ex:A ; ex:p 1 ; ex:q 2 ; ex:r 3 .")
    assert sorted((text(r.path.iri), int(r.value.value)) for r in out.results) == [("http://example.com/q", 2), ("http://example.com/r", 3)]
    assert all(r.path.node == r.path.iri for r in out.results)


def test_closed_false_and_non_plain_paths():
    assert results("ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:closed false . ex:a ex:q 1 .") == []
    s = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:closed true ; sh:property [ sh:path [ sh:inversePath ex:z ] ] . "
    assert results(s + "ex:a ex:q 1 .") == [("a", "ClosedConstraintComponent")]


def test_closed_bad_value():
    with pytest.raises(ShapeError):
        run("ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:closed 7 . ex:a ex:q 1 .")


REIF = """ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property ex:PS . ex:PS sh:path ex:p ; sh:reifierShape ex:R %s .
ex:R a sh:NodeShape ; sh:property [ sh:path ex:ok ; sh:in ( true ) ] .\n"""


def test_reifier_shape():
    bad = 'ex:a ex:p "x" {| ex:ok false |} .'
    good = 'ex:a ex:p "x" {| ex:ok true |} .'
    assert results(REIF % "" + bad) == [("a", "ReifierShapeConstraintComponent")]
    assert results(REIF % "" + good) == []
    assert results(REIF % "" + 'ex:a ex:p "x" .') == []
    assert results(REIF % "; sh:reificationRequired true" + 'ex:a ex:p "x" .') == [("a", "ReifierShapeConstraintComponent")]


def test_reifier_needs_property_shape():
    with pytest.raises(ShapeError):
        run("ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:reificationRequired true . ex:a ex:p 1 .")


def test_root_class():
    s = "ex:S a sh:NodeShape ; sh:targetNode ex:z ; sh:property [ sh:path ex:holds ; sh:rootClass ex:Animal ] . "
    data = "ex:Dog rdfs:subClassOf ex:Animal . ex:z ex:holds ex:Animal, ex:Dog, ex:Car, 3 ."
    out = run(s + data)
    assert sorted(lexical(r.value) for r in out.results) == ["3", "http://example.com/Car"]
    assert {r.component for r in out.results} == {SH.RootClassConstraintComponent}


def test_shapes_graph_plain_rdflib():
    g = Graph()
    g.parse(data=PRE + TARGETS + "sh:not [ sh:class ex:A ] . " + DATA, format="turtle")
    assert not validate(g, g).conforms
