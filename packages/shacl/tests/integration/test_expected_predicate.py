"""sh:expectedPredicate (SHACL 1.2 SPARQL Extensions section 8.2.7,
"Expected Derived Triples") - both the sh:defaultValue and sh:values halves.

A rule declaring sh:expectedPredicate ex:p expects the *derived* triples for
ex:p - computed via sh:defaultValue/sh:values on every non-deactivated
property shape using ex:p as sh:path - to already be present before it
executes. sh:values here is SHACL 1.2 Core's *validation-time* computed-value
mechanism on an ordinary property shape (sh:select/sh:sparqlExpr/a node
expression - see _compute_sh_values in validator.py) - not the unrelated,
separately-tracked, genuinely unimplemented sh:PropertyRule/sh:values
shorthand (a sh:rule-construction mechanism, see that row in
docs/shacl12-gap-matrix.md's Core changelog table) that happens to share a
predicate name.

**Materialized triples are transient, not permanent** - confirmed 2026-08-15
via the W3C SHACL 1.2 test suite's own expectedPredicate-example fixture,
whose expected result includes only the dependent rule's own conclusions,
never the derived ex:area values themselves. An earlier version of this
feature (and this test file) assumed permanent materialization based on a
plausible but incorrect reading of the spec prose alone - corrected once
concrete fixture evidence was available.

starshacl/validator.py::_materialize_expected_predicates is the
implementation, hooked into the same always-applied
_patch_rules_apply_for_layer_and_run_once wrap item #3 (sh:layer/
sh:runOnce) already installs - see that function's own docstring for why
this lives there rather than as a third wrap of TripleRule.apply/
SPARQLRule.apply.
"""

import pytest
from rdflib import RDF, Literal, Namespace
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl import StarShaclValidator

EX = Namespace("http://example.org/")

pyshacl = pytest.importorskip("pyshacl")


def _rectangle_shapes(*, with_expected_predicate: bool) -> str:
    expected_predicate = "sh:expectedPredicate ex:area ;" if with_expected_predicate else ""
    return f"""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://example.org/> .

        ex:RectangleShape a sh:NodeShape ;
          sh:targetClass ex:Rectangle ;
          sh:property ex:RectangleShape-area ;
          sh:rule ex:Rectangle-computeSmall .

        ex:RectangleShape-area a sh:PropertyShape ;
          sh:path ex:area ;
          sh:defaultValue 1 .

        ex:Rectangle-computeSmall a sh:SPARQLRule ;
          {expected_predicate}
          sh:construct \"\"\"
            PREFIX ex: <http://example.org/>
            CONSTRUCT {{ $this ex:isSmall true . }}
            WHERE {{ $this ex:area ?area . FILTER (?area < 100) }}
          \"\"\" .
    """


def test_expected_predicate_materializes_default_value_before_rule_runs() -> None:
    """No ex:area triple asserted anywhere - the rule's own WHERE clause can
    only match if sh:expectedPredicate correctly materialized
    ex:RectangleShape-area's sh:defaultValue (1) onto ex:rect1 first. The
    materialized ex:area triple itself must NOT survive in the final output
    though - transient, visible only during rule execution (see this file's
    own module docstring for the concrete fixture evidence this is based
    on) - only the rule's own conclusion (ex:isSmall) should persist.
    """
    shapes = StarLayerGraph()
    shapes.parse(data=_rectangle_shapes(with_expected_predicate=True), format="turtle")
    data = StarLayerGraph()
    data.add((EX.rect1, RDF.type, EX.Rectangle))

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert (EX.rect1, EX.area, Literal(1)) not in result.data_graph
    assert (EX.rect1, EX.isSmall, Literal(True)) in result.data_graph


def test_without_expected_predicate_default_value_is_never_materialized() -> None:
    """Same shapes minus sh:expectedPredicate - proves the feature is doing
    real work above, not something that would have happened anyway.
    """
    shapes = StarLayerGraph()
    shapes.parse(data=_rectangle_shapes(with_expected_predicate=False), format="turtle")
    data = StarLayerGraph()
    data.add((EX.rect1, RDF.type, EX.Rectangle))

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert (EX.rect1, EX.area, Literal(1)) not in result.data_graph
    assert (EX.rect1, EX.isSmall, Literal(True)) not in result.data_graph


def test_expected_predicate_does_not_override_an_existing_value() -> None:
    """ex:rect2 already asserts a real (large) ex:area - sh:defaultValue must
    not be materialized on top of it, and the rule must see the real
    asserted value, not the default.
    """
    shapes = StarLayerGraph()
    shapes.parse(data=_rectangle_shapes(with_expected_predicate=True), format="turtle")
    data = StarLayerGraph()
    data.add((EX.rect2, RDF.type, EX.Rectangle))
    data.add((EX.rect2, EX.area, Literal(500)))

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    area_values = set(result.data_graph.objects(EX.rect2, EX.area))
    assert area_values == {Literal(500)}
    assert (EX.rect2, EX.isSmall, Literal(True)) not in result.data_graph


def test_shapes_graph_without_expected_predicate_uses_original_pyshacl_loop() -> None:
    """A shapes graph with an ordinary sh:rule and no sh:expectedPredicate
    anywhere sees zero behavior change - same fallback-safety bar as
    sh:layer/sh:runOnce.
    """
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:PersonShape a sh:NodeShape ;
              sh:targetClass ex:Person ;
              sh:rule [
                a sh:SPARQLRule ;
                sh:construct \"\"\"
                  PREFIX ex: <http://example.org/>
                  CONSTRUCT { $this ex:greeted true . }
                  WHERE { }
                \"\"\" ;
              ] .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.add((EX.alice, RDF.type, EX.Person))

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert (EX.alice, EX.greeted, Literal(True)) in result.data_graph


def test_expected_predicate_prefers_sh_values_over_default_value() -> None:
    """sh:values (sh:sparqlExpr form here) is consulted, and takes priority
    over sh:defaultValue when it produces a result - both a real
    sh:values-computed value distinct from the fallback default (a rule
    depending on the *correct* value, not just "any" value, only fires
    correctly if the real one was actually used) and the fallback-to-default
    behavior for a focus node sh:values can't compute anything for are
    exercised in one fixture, mirroring the SHACL 1.2 SPARQL Extensions
    spec's own ex:RectangleShape-area worked example (sh:values computing a
    real area via sparql:multiply/shnex:pathValues node expressions,
    sh:defaultValue as the fallback) - covered end-to-end against the real
    W3C fixture in tests/w3c_shacl12/ (sparql/rules/expectedPredicate-example),
    this is the narrower unit-level check of the same priority logic.
    """
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:RectangleShape a sh:NodeShape ;
              sh:targetClass ex:Rectangle ;
              sh:property ex:RectangleShape-area ;
              sh:rule ex:Rectangle-computeSmall .

            ex:RectangleShape-area a sh:PropertyShape ;
              sh:path ex:area ;
              sh:defaultValue 1 ;
              sh:values [
                sh:sparqlExpr "999" ;
              ] .

            ex:Rectangle-computeSmall a sh:SPARQLRule ;
              sh:expectedPredicate ex:area ;
              sh:construct \"\"\"
                PREFIX ex: <http://example.org/>
                CONSTRUCT { $this ex:computedArea ?area . }
                WHERE { $this ex:area ?area . }
              \"\"\" .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.add((EX.rect1, RDF.type, EX.Rectangle))

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    # The rule saw sh:values' computed 999, not sh:defaultValue's 1 - proves
    # priority, not just "some value was present." Neither the transient
    # sh:values-computed nor sh:defaultValue's own ex:area triple survives.
    assert (EX.rect1, EX.computedArea, Literal(999)) in result.data_graph
    assert (EX.rect1, EX.area, Literal(1)) not in result.data_graph
    assert (EX.rect1, EX.area, Literal(999)) not in result.data_graph
