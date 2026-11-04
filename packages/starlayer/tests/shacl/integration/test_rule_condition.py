import pytest
from rdflib import Namespace
from starlayer.graph.model.triple import TripleTerm
from starlayer.graph.oxgraph import OxGraph
from starlayer.shacl import RuleError, StarShaclSchema
from starlayer.shacl_engine.terms import from_engine

from ._rdflib_view import rd

EX = Namespace("http://example.org/")

# sh:condition (SHACL 1.2 Inference Rules) restricts which focus nodes a rule
# applies to: a focus node only passes if it conforms to every condition shape.
#
# A condition shape needs a real constraint (sh:class / sh:property) to
# discriminate: sh:targetClass only selects who gets validated by validate()
# and has no effect on a conformance check of one given focus node, so a
# target-only shape trivially conforms for any node regardless of type.


def test_condition_admits_conforming_focus_node_only() -> None:
    data = OxGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Adult ; ex:name "Alice" .
        ex:bob a ex:Child ; ex:name "Bob" .
    """, format="turtle")

    shapes = OxGraph()
    shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
        ex:R a sh:NodeShape ;
          sh:targetSubjectsOf ex:name ;
          sh:rule [
            a sh:TripleRule ;
            sh:condition ex:AdultShape ;
            sh:subject [ shnex:var "focusNode" ] ; sh:predicate ex:eligibleForVoting ; sh:object true ;
          ] .
        ex:AdultShape a sh:NodeShape ; sh:class ex:Adult .
    """, format="turtle")

    result = StarShaclSchema(shacl_graph=shapes).apply_rules(data_graph=data)
    derived = {from_engine(s) for s, _, _ in result.inferred_graph.triples((None, EX.eligibleForVoting, None))}
    assert derived == {EX.alice}


def test_condition_over_rdf12_triple_term_valued_property() -> None:
    data = OxGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice ex:claims <<( ex:bob ex:age 42 )>> .
        ex:carol ex:name "carol" .
    """, format="turtle12")

    shapes = OxGraph()
    shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
        ex:R a sh:NodeShape ; sh:targetSubjectsOf ex:claims, ex:name ;
          sh:rule [
            a sh:TripleRule ;
            sh:condition ex:HasClaimShape ;
            sh:subject [ shnex:var "focusNode" ] ; sh:predicate ex:flagged ; sh:object true ;
          ] .
        ex:HasClaimShape a sh:NodeShape ; sh:property [ sh:path ex:claims ; sh:minCount 1 ] .
    """, format="turtle")

    result = StarShaclSchema(shacl_graph=shapes).apply_rules(data_graph=data)
    derived = {from_engine(s) for s, _, _ in result.inferred_graph.triples((None, EX.flagged, None))}
    assert derived == {EX.alice}

    # The rule's derived triple itself is plain (unrelated to the condition
    # check); the source triple term is base data (not rule output), so it
    # stays in the caller's own, never-mutated data_graph - confirm it's
    # still intact/unflattened there.
    from rdflib import Literal

    claims = list(rd(data).triples((EX.alice, EX.claims, None)))
    assert claims[0][2] == TripleTerm(EX.bob, EX.age, Literal(42))


def test_condition_shape_does_not_need_explicit_typing() -> None:
    """A sh:condition shape needs no explicit `a sh:NodeShape`/`a sh:PropertyShape` typing.

    Covers a single sh:condition value and several (the focus node must conform to all of them).
    """
    data = OxGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Adult, ex:Active ; ex:name "Alice" .
        ex:bob a ex:Child, ex:Active ; ex:name "Bob" .
    """, format="turtle")

    # Single reference, deliberately untyped (no `a sh:NodeShape`).
    shapes = OxGraph()
    shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
        ex:R a sh:NodeShape ; sh:targetSubjectsOf ex:name ;
          sh:rule [
            a sh:TripleRule ;
            sh:condition ex:AdultShape ;
            sh:subject [ shnex:var "focusNode" ] ; sh:predicate ex:eligibleForVoting ; sh:object true ;
          ] .
        ex:AdultShape sh:class ex:Adult .
    """, format="turtle")

    result = StarShaclSchema(shacl_graph=shapes).apply_rules(data_graph=data)
    derived = {from_engine(s) for s, _, _ in result.inferred_graph.triples((None, EX.eligibleForVoting, None))}
    assert derived == {EX.alice}

    # Several sh:condition values: the focus node must conform to all of them; both deliberately untyped.
    list_shapes = OxGraph()
    list_shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
        ex:R a sh:NodeShape ; sh:targetSubjectsOf ex:name ;
          sh:rule [
            a sh:TripleRule ;
            sh:condition ex:AdultShape, ex:ActiveShape ;
            sh:subject [ shnex:var "focusNode" ] ; sh:predicate ex:eligibleForVoting ; sh:object true ;
          ] .
        ex:AdultShape sh:class ex:Adult .
        ex:ActiveShape sh:class ex:Active .
    """, format="turtle")

    result2 = StarShaclSchema(shacl_graph=list_shapes).apply_rules(data_graph=data)
    derived2 = {from_engine(s) for s, _, _ in result2.inferred_graph.triples((None, EX.eligibleForVoting, None))}
    assert derived2 == {EX.alice}


def test_condition_excludes_all_focus_nodes_when_none_conform() -> None:
    data = OxGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Child ; ex:name "Alice" .
    """, format="turtle")

    shapes = OxGraph()
    shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
        ex:R a sh:NodeShape ; sh:targetSubjectsOf ex:name ;
          sh:rule [
            a sh:TripleRule ;
            sh:condition ex:AdultShape ;
            sh:subject [ shnex:var "focusNode" ] ; sh:predicate ex:eligibleForVoting ; sh:object true ;
          ] .
        ex:AdultShape a sh:NodeShape ; sh:class ex:Adult .
    """, format="turtle")

    result = StarShaclSchema(shacl_graph=shapes).apply_rules(data_graph=data)
    derived = list(result.inferred_graph.triples((None, EX.eligibleForVoting, None)))
    assert derived == []


def test_property_rule_sh_values_is_not_implemented() -> None:
    """``sh:PropertyRule`` is not a SHACL 1.2 rule type: an unrecognized rule type is a RuleError.

    SHACL 1.2 Inference Rules defines exactly ``sh:SPARQLRule`` and ``sh:TripleRule``; a rule
    whose type is not a subclass of ``sh:Rule`` must not silently no-op. Update or remove this
    test if the WG reintroduces a similar construct and this project decides to support it.
    """
    data = OxGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Person ; ex:name "Alice" .
    """, format="turtle")

    shapes = OxGraph()
    shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
        ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:rule [
            a sh:PropertyRule ;
            sh:path ex:fullName ;
            sh:values ex:name ;
          ] .
    """, format="turtle")

    with pytest.raises(RuleError):
        StarShaclSchema(shacl_graph=shapes).apply_rules(data_graph=data, meta_shacl=False)
