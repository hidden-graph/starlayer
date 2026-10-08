import pytest
from rdflib import Namespace
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.graph.model.triple import TripleTerm
from starlayer.shacl import StarShaclSchema

EX = Namespace("http://example.org/")

pyshacl = pytest.importorskip("pyshacl")

# sh:condition (SHACL 1.2 SPARQL Extensions / SHACL-AF rules) restricts which
# focus nodes a sh:rule applies to: pyshacl.rules.shacl_rule.SHACLRule.
# filter_conditions() only lets a focus node through if it conforms to every
# condition shape, checked via the (correctly-formed) SHACLExecutor calling
# convention - this was previously untested anywhere in starShacl, so it was
# unconfirmed whether it worked at all. Live reproduction (this session)
# confirmed it works correctly out of the box, no starShacl-side patch
# needed - these tests lock that in as regression coverage.
#
# The first reproduction attempt used a condition shape with only
# sh:targetClass and no actual constraint - a real SHACL semantics gotcha
# (the same class of mistake as the sh:filterShape investigation elsewhere
# this session): sh:targetClass selects who gets validated when running
# validate() directly, but has no effect on ad-hoc shape.validate(focus=x)
# conformance checks, so a target-only shape trivially "conforms" for any
# node regardless of type. The shapes below use a real constraint
# (sh:class / sh:property) so the condition actually discriminates.


def test_condition_admits_conforming_focus_node_only() -> None:
    data = StarLayerGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Adult ; ex:name "Alice" .
        ex:bob a ex:Child ; ex:name "Bob" .
    """, format="turtle")

    shapes = StarLayerGraph()
    shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:R a sh:NodeShape ;
          sh:targetSubjectsOf ex:name ;
          sh:rule [
            a sh:TripleRule ;
            sh:condition ex:AdultShape ;
            sh:subject sh:this ; sh:predicate ex:eligibleForVoting ; sh:object true ;
          ] .
        ex:AdultShape a sh:NodeShape ; sh:class ex:Adult .
    """, format="turtle")

    result = StarShaclSchema(shacl_graph=shapes).apply_rules(data_graph=data)
    derived = {s for s, _, _ in result.inferred_graph.triples((None, EX.eligibleForVoting, None))}
    assert derived == {EX.alice}


def test_condition_over_rdf12_triple_term_valued_property() -> None:
    data = StarLayerGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice ex:claims <<( ex:bob ex:age 42 )>> .
        ex:carol ex:name "carol" .
    """, format="turtle12")

    shapes = StarLayerGraph()
    shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:R a sh:NodeShape ; sh:targetSubjectsOf ex:claims, ex:name ;
          sh:rule [
            a sh:TripleRule ;
            sh:condition ex:HasClaimShape ;
            sh:subject sh:this ; sh:predicate ex:flagged ; sh:object true ;
          ] .
        ex:HasClaimShape a sh:NodeShape ; sh:property [ sh:path ex:claims ; sh:minCount 1 ] .
    """, format="turtle")

    result = StarShaclSchema(shacl_graph=shapes).apply_rules(data_graph=data)
    derived = {s for s, _, _ in result.inferred_graph.triples((None, EX.flagged, None))}
    assert derived == {EX.alice}

    # The rule's derived triple itself is plain (unrelated to the condition
    # check); the source triple term is base data (not rule output), so it
    # stays in the caller's own, never-mutated data_graph - confirm it's
    # still intact/unflattened there.
    from rdflib import Literal

    claims = list(data.triples((EX.alice, EX.claims, None)))
    assert claims[0][2] == TripleTerm(EX.bob, EX.age, Literal(42))


def test_condition_shape_does_not_need_explicit_typing() -> None:
    """sh:condition's value initially needed explicit `a sh:NodeShape`/
    `a sh:PropertyShape` typing or pySHACL's own lookup_shape_from_node
    crashed with RuleLoadError at rule-execution time (confirmed live) -
    unlike sh:someValue/sh:memberShape/sh:reifierShape, which starShacl
    already auto-types via native_components.SHAPE_EXPECTING_PREDICATES/
    ensure_shape_typed before pySHACL ever runs. sh:condition is now in
    that same list (StarShaclSchema._ensure_native_component_shapes_typed),
    so an untyped condition shape works transparently too - one consistent
    fix strategy, not a special case. Covers both the single-reference and
    SHACL-list forms sh:condition accepts.
    """
    data = StarLayerGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Adult, ex:Active ; ex:name "Alice" .
        ex:bob a ex:Child, ex:Active ; ex:name "Bob" .
    """, format="turtle")

    # Single reference, deliberately untyped (no `a sh:NodeShape`).
    shapes = StarLayerGraph()
    shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:R a sh:NodeShape ; sh:targetSubjectsOf ex:name ;
          sh:rule [
            a sh:TripleRule ;
            sh:condition ex:AdultShape ;
            sh:subject sh:this ; sh:predicate ex:eligibleForVoting ; sh:object true ;
          ] .
        ex:AdultShape sh:class ex:Adult .
    """, format="turtle")

    result = StarShaclSchema(shacl_graph=shapes).apply_rules(data_graph=data)
    derived = {s for s, _, _ in result.inferred_graph.triples((None, EX.eligibleForVoting, None))}
    assert derived == {EX.alice}

    # SHACL-list form, both members deliberately untyped.
    list_shapes = StarLayerGraph()
    list_shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:R a sh:NodeShape ; sh:targetSubjectsOf ex:name ;
          sh:rule [
            a sh:TripleRule ;
            sh:condition ( ex:AdultShape ex:ActiveShape ) ;
            sh:subject sh:this ; sh:predicate ex:eligibleForVoting ; sh:object true ;
          ] .
        ex:AdultShape sh:class ex:Adult .
        ex:ActiveShape sh:class ex:Active .
    """, format="turtle")

    result2 = StarShaclSchema(shacl_graph=list_shapes).apply_rules(data_graph=data)
    derived2 = {s for s, _, _ in result2.inferred_graph.triples((None, EX.eligibleForVoting, None))}
    assert derived2 == {EX.alice}


def test_condition_excludes_all_focus_nodes_when_none_conform() -> None:
    data = StarLayerGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Child ; ex:name "Alice" .
    """, format="turtle")

    shapes = StarLayerGraph()
    shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:R a sh:NodeShape ; sh:targetSubjectsOf ex:name ;
          sh:rule [
            a sh:TripleRule ;
            sh:condition ex:AdultShape ;
            sh:subject sh:this ; sh:predicate ex:eligibleForVoting ; sh:object true ;
          ] .
        ex:AdultShape a sh:NodeShape ; sh:class ex:Adult .
    """, format="turtle")

    result = StarShaclSchema(shacl_graph=shapes).apply_rules(data_graph=data)
    derived = list(result.inferred_graph.triples((None, EX.eligibleForVoting, None)))
    assert derived == []


def test_property_rule_sh_values_is_not_implemented() -> None:
    """``sh:PropertyRule`` has no implementation anywhere - not in pySHACL
    0.40.0 (``pyshacl.rules.shacl_rule`` only dispatches ``sh:TripleRule``/
    ``sh:SPARQLRule``; there is no ``PropertyRule`` module) and not in
    starShacl's own code.

    **Note (2026-09-28): the spec construct this test was originally written
    against no longer exists.** `sh:PropertyRule` was previously described in
    `docs/shacl12-gap-matrix.md` as a `sh:rule` shorthand (SHACL 1.2 Core
    changelog's "new sh:values") - re-fetching both `shacl12-inference-rules`
    and `shacl12-core` directly and searching for "PropertyRule" found zero
    occurrences in either current document; `shacl12-inference-rules`'s
    "Built-in Rule Types" section defines exactly `sh:SPARQLRule` and
    `sh:TripleRule`, and Core's own `sh:values` is now defined purely as a
    validation-time/computed-property feature with no connection to
    `sh:rule` at all (see `docs/shacl12-gap-matrix.md`'s "Not Covered /
    Deferred" table for the full account). This test still exercises real,
    useful coverage regardless - an unrecognized rule type correctly raises
    `RuleLoadError` rather than silently no-opping - so it's kept, just no
    longer citing a real spec gap as its reason. Update or remove it if the
    WG reintroduces a similar construct and this project decides to support
    it.
    """
    from pyshacl.errors import RuleLoadError

    data = StarLayerGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Person ; ex:name "Alice" .
    """, format="turtle")

    shapes = StarLayerGraph()
    shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:rule [
            a sh:PropertyRule ;
            sh:path ex:fullName ;
            sh:values ex:name ;
          ] .
    """, format="turtle")

    with pytest.raises(RuleLoadError):
        StarShaclSchema(shacl_graph=shapes).apply_rules(data_graph=data, meta_shacl=False)
