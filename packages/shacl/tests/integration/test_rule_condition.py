import pytest
from rdflib import Namespace
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starlayergraph.model.triple import TripleTerm
from starshacl import StarShaclValidator

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

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes)
    derived = {s for s, _, _ in result.data_graph.triples((None, EX.eligibleForVoting, None))}
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

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes)
    derived = {s for s, _, _ in result.data_graph.triples((None, EX.flagged, None))}
    assert derived == {EX.alice}

    # The rule's derived triple itself is plain (unrelated to the condition
    # check), but confirm the source triple term is still intact/unflattened.
    from rdflib import Literal

    claims = list(result.data_graph.triples((EX.alice, EX.claims, None)))
    assert claims[0][2] == TripleTerm(EX.bob, EX.age, Literal(42))


def test_condition_shape_does_not_need_explicit_typing() -> None:
    """sh:condition's value initially needed explicit `a sh:NodeShape`/
    `a sh:PropertyShape` typing or pySHACL's own lookup_shape_from_node
    crashed with RuleLoadError at rule-execution time (confirmed live) -
    unlike sh:someValue/sh:memberShape/sh:reifierShape, which starShacl
    already auto-types via native_components.SHAPE_EXPECTING_PREDICATES/
    ensure_shape_typed before pySHACL ever runs. sh:condition is now in
    that same list (StarShaclValidator._ensure_native_component_shapes_typed),
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

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes)
    derived = {s for s, _, _ in result.data_graph.triples((None, EX.eligibleForVoting, None))}
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

    result2 = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=list_shapes)
    derived2 = {s for s, _, _ in result2.data_graph.triples((None, EX.eligibleForVoting, None))}
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

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes)
    derived = list(result.data_graph.triples((None, EX.eligibleForVoting, None)))
    assert derived == []


def test_property_rule_sh_values_is_not_implemented() -> None:
    """``sh:PropertyRule``/``sh:values`` (SHACL 1.2 Core changelog: "new
    sh:values") has no implementation anywhere - not in pySHACL 0.40.0
    (``pyshacl.rules.shacl_rule`` only dispatches ``sh:TripleRule``/
    ``sh:SPARQLRule``; there is no ``PropertyRule`` module, and
    ``pyshacl.consts`` has no ``SH_values`` at all) and not in starShacl's own
    code (grepped ``starshacl/`` - ``sh:values``/``SH.values`` appear only in
    a docstring and a meta-shapes comment, never as an actual predicate
    handled anywhere).

    ``docs/shacl12-gap-matrix.md`` marks the row containing this feature
    "done" (for the node-expression extension point and the generalized
    sh:targetNode/sh:deactivated/sh:defaultValue parts, which genuinely are
    done), but its own notes already flag sh:values itself as "not separately
    verified" - this test confirms that hedge is actually hiding a real gap,
    not just a missing test: using it raises ``RuleLoadError`` rather than
    silently no-opping or producing wrong output, so at least a caller gets a
    clear failure instead of a silent miss. This is a locked-in regression
    marker for the current (unsupported) state, not coverage of a working
    feature - update or remove this test if ``sh:PropertyRule``/``sh:values``
    support is ever added.
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
        StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)
