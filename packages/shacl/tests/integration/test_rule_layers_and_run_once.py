"""sh:layer / sh:runOnce (SHACL 1.2 SPARQL Extensions section 8.2.4/8.2.6).

pySHACL's own rule loop (``pyshacl.rules.apply_rules``) processes shapes
*sequentially* - one shape's rules reach their own independent fixpoint,
then the next shape's rules run, in ``shape.order`` order. The spec's layer
model is a *global* fixpoint across every rule in a layer regardless of
which shape it's attached to, which that per-shape loop cannot express.
``starshacl/validator.py::_patch_rules_apply_for_layer_and_run_once``
replaces the loop, but only when a shapes graph actually declares
``sh:layer``/``sh:runOnce`` - see that function's docstring.
"""

import pytest
from rdflib import Literal, Namespace, RDF

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayer_graph import StarLayerGraph

from ._shape_loader import load_shape

EX = Namespace("http://example.org/")

pyshacl = pytest.importorskip("pyshacl")


def test_cross_shape_layering_orders_by_layer_not_by_shape_order() -> None:
    """ShapeA's rule (layer 0) must produce ex:stage1 before ShapeB's rule
    (layer 1) can produce ex:stage2 from it. ShapeA is deliberately given a
    *higher* sh:order (10) than ShapeB (0) - under pySHACL's original
    per-shape-sequential loop, shapes are processed in ascending shape.order,
    so ShapeB (order 0) would run to its own fixpoint *first*, see no
    ex:stage1 yet, produce nothing, and never be revisited once ShapeA
    (order 10) runs afterward - ex:stage2 would never appear. Only a real
    cross-shape, layer-ordered fixpoint gets this right.
    """
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:ShapeA a sh:NodeShape ;
              sh:targetNode ex:start ;
              sh:order 10 ;
              sh:rule [
                a sh:SPARQLRule ;
                sh:layer 0 ;
                sh:construct \"\"\"
                  PREFIX ex: <http://example.org/>
                  CONSTRUCT { $this ex:stage1 true . }
                  WHERE { }
                \"\"\" ;
              ] .

            ex:ShapeB a sh:NodeShape ;
              sh:targetNode ex:start ;
              sh:order 0 ;
              sh:rule [
                a sh:SPARQLRule ;
                sh:layer 1 ;
                sh:construct \"\"\"
                  PREFIX ex: <http://example.org/>
                  CONSTRUCT { $this ex:stage2 true . }
                  WHERE { $this ex:stage1 true . }
                \"\"\" ;
              ] .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.add((EX.start, EX.marker, Literal(True)))

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert (EX.start, EX.stage1, Literal(True)) in result.data_graph
    assert (EX.start, EX.stage2, Literal(True)) in result.data_graph


def test_run_once_rule_fires_exactly_once_despite_minting_fresh_blank_nodes() -> None:
    """A rule that mints a fresh blank node every execution would, if
    (mis)treated as an ordinary iterating rule, keep producing a "new" triple
    every pass forever - hitting pySHACL's own 100-iteration cap and raising
    ReportableRuntimeError. Marking it sh:runOnce must make it fire exactly
    once and let the call succeed.
    """
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:MarkerShape a sh:NodeShape ;
              sh:targetNode ex:start ;
              sh:rule [
                a sh:SPARQLRule ;
                sh:layer 0 ;
                sh:runOnce true ;
                sh:construct \"\"\"
                  PREFIX ex: <http://example.org/>
                  CONSTRUCT { ?bn a ex:Marker . }
                  WHERE { BIND(BNODE() AS ?bn) }
                \"\"\" ;
              ] .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.add((EX.start, EX.marker, Literal(True)))

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    markers = list(result.data_graph.subjects(RDF.type, EX.Marker))
    assert len(markers) == 1


def test_sh_order_within_a_layer_is_compared_globally_not_per_shape() -> None:
    """Two run-once rules, same layer, on two different shapes: the
    precursor (sh:order 1) is on a shape with a *higher* shape.order (10)
    than the dependent rule's shape (sh:order 2 on a shape with order 0).
    Run-once rules fire exactly once, in sh:order sequence, with no
    fixpoint re-try - so if the implementation accidentally grouped/sorted
    by shape.order first (the old per-shape nesting) rather than comparing
    every rule's own sh:order globally within the layer, the dependent rule
    would run before the precursor and never see its output.
    """
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:ShapeP a sh:NodeShape ;
              sh:targetNode ex:start ;
              sh:order 10 ;
              sh:rule [
                a sh:SPARQLRule ;
                sh:layer 0 ;
                sh:runOnce true ;
                sh:order 1 ;
                sh:construct \"\"\"
                  PREFIX ex: <http://example.org/>
                  CONSTRUCT { $this ex:precursor true . }
                  WHERE { }
                \"\"\" ;
              ] .

            ex:ShapeQ a sh:NodeShape ;
              sh:targetNode ex:start ;
              sh:order 0 ;
              sh:rule [
                a sh:SPARQLRule ;
                sh:layer 0 ;
                sh:runOnce true ;
                sh:order 2 ;
                sh:construct \"\"\"
                  PREFIX ex: <http://example.org/>
                  CONSTRUCT { $this ex:dependent true . }
                  WHERE { $this ex:precursor true . }
                \"\"\" ;
              ] .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.add((EX.start, EX.marker, Literal(True)))

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert (EX.start, EX.dependent, Literal(True)) in result.data_graph


def test_shapes_graph_without_layer_or_run_once_uses_original_pyshacl_loop() -> None:
    """No regression: a shapes graph using ordinary sh:rule with no
    sh:layer/sh:runOnce anywhere must still produce the correct result via
    pySHACL's own original per-shape loop (the patch delegates straight
    through, unmodified) - reuses the existing reach-fixpoint fixture
    already covered by test_rule_iteration.py, through apply_rules() this
    time rather than validate() directly, to exercise the actual patched
    call site.
    """
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rules_reach_sparql.ttl"), format="turtle")

    data = StarLayerGraph()
    data.add((EX.a, EX.reach, EX.b))
    data.add((EX.b, EX.reach, EX.c))
    data.add((EX.c, EX.reach, EX.d))

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert (EX.a, EX.reach, EX.c) in result.data_graph
    assert (EX.a, EX.reach, EX.d) in result.data_graph
    assert (EX.b, EX.reach, EX.d) in result.data_graph
