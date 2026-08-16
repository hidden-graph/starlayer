import pytest
from rdflib import Namespace
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starlayergraph.model.triple import TripleTerm
from starshacl import StarShaclValidator

EX = Namespace("http://example.org/")

pyshacl = pytest.importorskip("pyshacl")

# SHACL 1.2 Node Expressions (https://www.w3.org/TR/shacl12-node-expr/) moved
# the node-expression combinator vocabulary to a new namespace, shnex: =
# http://www.w3.org/ns/shacl-node-expr# - distinct from the sh:union/
# sh:intersection/sh:filterShape/sh:path forms pySHACL implements natively
# (covered by test_node_expressions_integration.py). starshacl/
# node_expressions.py adds the shnex: operators on top, without touching
# pySHACL's own handling of the old forms.
#
# Most cases here use sh:expression (SHACL-AF's ExpressionConstraintComponent,
# via validate()): the expression must evaluate to exactly (true) for the
# shape to conform, which is a clean boolean-conformance harness for
# exercising an operator without needing to inspect derived triples. A few
# cases use sh:rule/sh:TripleRule (via apply_rules()) to also exercise the
# OTHER pySHACL call site that resolves node expressions, and to confirm
# RDF-1.2 triple-term values flow through unchanged.

PREFIXES = """
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
    @prefix sparql: <http://www.w3.org/ns/sparql#> .
"""

DATA = """
    @prefix ex: <http://example.org/> .
    ex:alice ex:parent ex:carol , ex:dave ; ex:sibling ex:erin .
    ex:carol ex:age 40 .
    ex:dave ex:age 50 .
    ex:bob a ex:Person .
    ex:PersonShape a ex:UNUSED .
"""


def _expression_conforms(expression_ttl: str, target: str = "ex:alice") -> bool:
    data = StarLayerGraph()
    data.parse(data=DATA, format="turtle")

    shapes = StarLayerGraph()
    shapes.parse(
        data=PREFIXES
        + f"""
        ex:S a sh:NodeShape ;
          sh:targetNode {target} ;
          sh:expression [ shnex:if [ shnex:exists [ {expression_ttl} ] ] ;
                           shnex:then true ; shnex:else false ] .
        ex:PersonShape a sh:NodeShape ; sh:hasValue ex:bob .
        """,
        format="turtle",
    )
    # sh:expression is a SHACL-AF component (ExpressionConstraintComponent) -
    # pySHACL only evaluates it when advanced=True (the default "validation"
    # profile has advanced=False, under which sh:expression is silently
    # never invoked at all, making conforms=True vacuously regardless of the
    # expression's actual content).
    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, advanced=True)
    return result.conforms


def _boolean_expr_conforms(expression_ttl: str, target: str = "ex:alice") -> bool:
    """Like _expression_conforms, but for expressions that already evaluate to
    a boolean (true)/(false) list themselves (e.g. shnex:matchAll, shnex:exists)
    - plugged directly into sh:expression with no extra shnex:exists wrapper,
    since wrapping an already-boolean result in shnex:exists would always see
    a non-empty ``(true)`` or ``(false)`` list and be vacuously true either way.
    """
    data = StarLayerGraph()
    data.parse(data=DATA, format="turtle")

    shapes = StarLayerGraph()
    shapes.parse(
        data=PREFIXES
        + f"""
        ex:S a sh:NodeShape ;
          sh:targetNode {target} ;
          sh:expression [ {expression_ttl} ] .
        ex:PersonShape a sh:NodeShape ; sh:hasValue ex:bob .
        """,
        format="turtle",
    )
    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, advanced=True)
    return result.conforms


def test_pathvalues_basic() -> None:
    assert _expression_conforms("shnex:pathValues ex:parent") is True


def test_pathvalues_with_explicit_focusnode() -> None:
    assert (
        _expression_conforms(
            "shnex:pathValues [ sh:inversePath rdf:type ] ; shnex:focusNode ex:Person", target="ex:alice"
        )
        is True
    )


def test_filtershape_selects_conforming_nodes() -> None:
    assert (
        _expression_conforms(
            "shnex:filterShape ex:PersonShape ; shnex:nodes [ shnex:concat ( [ shnex:pathValues ex:parent ] "
            "ex:bob ) ]"
        )
        is True
    )


def test_var_focusnode() -> None:
    assert _expression_conforms('shnex:var "focusNode"') is True


# sparql: (http://www.w3.org/ns/sparql#) - SPARQL 1.1/1.2 built-in
# functions/operators exposed as node expressions, a wholly separate
# vocabulary from shnex: (starshacl/sparql_node_expressions.py).
# These specifically confirm the *real* validate() entrypoint actually
# reaches sparql_node_expressions.py for a shapes graph that uses ONLY
# sparql: predicates (no shnex: ones at all) - validator.py's own trigger
# condition for wiring in node-expression support originally checked for
# shnex:-namespaced predicates only, so a sparql:-only shapes graph never
# triggered it and fell through to pySHACL's unpatched
# nodes_from_node_expression, which has no idea what a sparql: expression
# is either - confirmed live as a real, separate wiring gap from
# sparql_node_expressions.py's own (correct) implementation, found by
# checking this exact scenario rather than assuming eval_expr()-level
# testing (tests/w3c_shacl12/test_w3c_node_expr.py, which calls eval_expr()
# directly) was sufficient to prove real end-to-end reachability too.


def test_sparql_only_shapes_graph_reaches_sparql_node_expressions() -> None:
    assert _boolean_expr_conforms("sparql:isNumeric ( 42 )") is True


def test_sparql_function_call() -> None:
    assert _boolean_expr_conforms('sparql:greater-than ( [ sparql:strlen ( "hello" ) ] 3 )') is True


def test_distinct_count_value() -> None:
    # distinct(carol, carol, dave) -> {carol, dave}, count 2, not 3 - checked
    # by intersecting the count against each candidate literal and requiring
    # exactly the 2-match to be non-empty.
    count_expr = "shnex:count [ shnex:distinct [ shnex:concat ( ex:carol ex:carol ex:dave ) ] ]"
    assert _expression_conforms(f"shnex:intersection ( [ {count_expr} ] 2 )") is True
    assert _expression_conforms(f"shnex:intersection ( [ {count_expr} ] 3 )") is False


def test_remove_excludes_matching_nodes() -> None:
    assert (
        _expression_conforms(
            "shnex:nodes [ shnex:pathValues ex:parent ] ; shnex:remove ex:carol"
        )
        is True  # dave remains -> non-empty -> exists true
    )


def test_intersection_shnex_namespace() -> None:
    assert (
        _expression_conforms(
            "shnex:intersection ( [ shnex:pathValues ex:parent ] [ shnex:concat ( ex:carol ex:erin ) ] )"
        )
        is True  # {carol, dave} ∩ {carol, erin} = {carol} -> non-empty
    )


def test_concat_preserves_all_including_duplicates() -> None:
    # concat(carol, carol) keeps both -> count 2 (would be 1 if it had
    # deduplicated like shnex:distinct does).
    count_expr = "shnex:count [ shnex:concat ( ex:carol ex:carol ) ]"
    assert _expression_conforms(f"shnex:intersection ( [ {count_expr} ] 2 )") is True
    assert _expression_conforms(f"shnex:intersection ( [ {count_expr} ] 1 )") is False


def test_orderby_limit_offset() -> None:
    # children of alice ordered by age: carol(40), dave(50). limit 1 offset 1 -> [dave]
    assert (
        _expression_conforms(
            "shnex:offset 1 ; shnex:nodes [ shnex:limit 2 ; shnex:nodes [ shnex:orderBy "
            "[ shnex:pathValues ex:age ] ; shnex:nodes [ shnex:pathValues ex:parent ] ] ]"
        )
        is True
    )


def test_orderby_desc() -> None:
    # age-descending (oldest first) top-1 of alice's children (carol=40,
    # dave=50) must be ex:dave, not ex:carol (which is what ascending, the
    # default, would give - see test_orderby_limit_offset).
    top_desc = (
        "shnex:limit 1 ; shnex:nodes [ shnex:orderBy [ shnex:pathValues ex:age ] ; "
        "shnex:desc true ; shnex:nodes [ shnex:pathValues ex:parent ] ]"
    )
    assert _expression_conforms(f"shnex:intersection ( [ {top_desc} ] ex:dave )") is True
    assert _expression_conforms(f"shnex:intersection ( [ {top_desc} ] ex:carol )") is False


def test_flatmap_iterates_per_node() -> None:
    assert (
        _expression_conforms(
            "shnex:nodes [ shnex:pathValues ex:parent ] ; shnex:flatMap [ shnex:pathValues ex:age ]"
        )
        is True
    )


def test_findfirst() -> None:
    assert (
        _expression_conforms(
            "shnex:nodes [ shnex:concat ( ex:carol ex:bob ) ] ; shnex:findFirst ex:PersonShape"
        )
        is True  # bob conforms to PersonShape, carol doesn't -> findFirst returns [bob], non-empty
    )


def test_matchall_true_when_all_conform() -> None:
    assert (
        _boolean_expr_conforms("shnex:nodes ex:bob ; shnex:matchAll ex:PersonShape") is True
    )


def test_matchall_false_when_not_all_conform() -> None:
    assert (
        _boolean_expr_conforms(
            "shnex:nodes [ shnex:concat ( ex:bob ex:carol ) ] ; shnex:matchAll ex:PersonShape"
        )
        is False
    )


def test_count() -> None:
    assert _expression_conforms("shnex:count [ shnex:pathValues ex:parent ]") is True  # count 2, non-empty list


def test_min_max_sum() -> None:
    # alice's children's ages: carol=40, dave=50 -> min 40, max 50, sum 90.
    ages = "shnex:flatMap [ shnex:pathValues ex:age ] ; shnex:nodes [ shnex:pathValues ex:parent ]"
    assert _expression_conforms(f"shnex:intersection ( [ shnex:min [ {ages} ] ] 40 )") is True
    assert _expression_conforms(f"shnex:intersection ( [ shnex:min [ {ages} ] ] 50 )") is False
    assert _expression_conforms(f"shnex:intersection ( [ shnex:max [ {ages} ] ] 50 )") is True
    assert _expression_conforms(f"shnex:intersection ( [ shnex:max [ {ages} ] ] 40 )") is False
    assert _expression_conforms(f"shnex:intersection ( [ shnex:sum [ {ages} ] ] 90 )") is True


def test_instancesof() -> None:
    assert _expression_conforms("shnex:instancesOf ex:Person", target="ex:bob") is True


def test_instancesof_matches_transitive_subclass_instances() -> None:
    # shnex:instancesOf ex:Organization must also match instances of
    # ex:Company (a rdfs:subClassOf descendant of ex:Organization), not
    # just direct ex:Organization instances - matches the W3C SHACL 1.2
    # test suite's instancesOf-base-class fixture.
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:Company rdfs:subClassOf ex:Organization .
            ex:Acme a ex:Company .
            ex:Bystander a ex:Unrelated .
        """,
        format="turtle",
    )

    shapes = StarLayerGraph()
    shapes.parse(
        data=PREFIXES
        + """
        ex:S a sh:NodeShape ;
          sh:targetNode ex:Acme ;
          sh:expression [ shnex:if [ shnex:exists [ shnex:instancesOf ex:Organization ] ] ;
                           shnex:then true ; shnex:else false ] .
        """,
        format="turtle",
    )

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, advanced=True)
    assert result.conforms is True


def test_instancesof_does_not_match_unrelated_class_instances() -> None:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:Company rdfs:subClassOf ex:Organization .
            ex:Bystander a ex:Unrelated .
        """,
        format="turtle",
    )

    shapes = StarLayerGraph()
    shapes.parse(
        data=PREFIXES
        + """
        ex:S a sh:NodeShape ;
          sh:targetNode ex:Bystander ;
          sh:expression [ shnex:if [ shnex:exists [ shnex:instancesOf ex:Organization ] ] ;
                           shnex:then true ; shnex:else false ] .
        """,
        format="turtle",
    )

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, advanced=True)
    assert result.conforms is False


def test_nodesmatching() -> None:
    assert _expression_conforms("shnex:nodesMatching ex:PersonShape") is True  # bob conforms, in the graph


def test_shnex_pathvalues_with_triple_rule_carries_rdf12_triple_term() -> None:
    data = StarLayerGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice ex:claims <<( ex:bob ex:age 42 )>> .
    """, format="turtle12")

    shapes = StarLayerGraph()
    shapes.parse(
        data=PREFIXES
        + """
        ex:R a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:derivedClaim ;
                    sh:object [ shnex:pathValues ex:claims ] ] .
        """,
        format="turtle",
    )
    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    derived = list(result.data_graph.triples((EX.alice, EX.derivedClaim, None)))
    assert len(derived) == 1
    from rdflib import Literal

    assert derived[0][2] == TripleTerm(EX.bob, EX.age, Literal(42))


def test_shnex_and_old_sh_forms_coexist_in_same_validate_call() -> None:
    # Regression check: a shapes graph mixing an old sh:union expression and a
    # new shnex: expression must handle both correctly in one validate() call
    # - the shnex: patch must not break pySHACL's own old-form handling.
    data = StarLayerGraph()
    data.parse(data=DATA, format="turtle")
    shapes = StarLayerGraph()
    shapes.parse(
        data=PREFIXES
        + """
        ex:OldForm a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:expression [ shnex:if [ shnex:exists [ sh:path ex:parent ] ] ;
                           shnex:then true ; shnex:else false ] .
        ex:NewForm a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:expression [ shnex:if [ shnex:exists [ shnex:pathValues ex:sibling ] ] ;
                           shnex:then true ; shnex:else false ] .
        """,
        format="turtle",
    )
    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, advanced=True)
    assert result.conforms is True


# sparql:isTriple/subject over a triple-term value obtained from *real data*
# (not a Turtle constant embedded in the shapes graph) through the actual
# validate() entrypoint - not tests/w3c_shacl12/'s eval_expr()-direct calls,
# which use a hand-built StarLayerGraph as data_graph and so never exercise
# what validate() really hands node-expression evaluation. Found live (via a
# direct user question about whether "rdflib's own SPARQL engine" really
# meant real production usage) that data_graph as received by
# starshacl.node_expressions.eval_expr() in real validate() usage is
# pySHACL's plain, unwrapped RdfLibDataGraph - a triple-term value read from
# it (e.g. via shnex:pathValues) is still in starshacl's own
# flat-encoded urn:starshacl:tt:HASH form, and even after decoding
# that, starlayergraph's own SPARQL engine requires the exact value to
# already be registered in whatever specific graph instance is queried -
# see docs/starlayergraph-upstream-change-log.md's 2026-07-31 entries for the
# full two-part root cause and fix (starshacl/sparql_node_expressions.py).


def test_sparql_istriple_over_real_data_triple_term() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))

    shapes = StarLayerGraph()
    shapes.parse(
        data=PREFIXES
        + """
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:expression [ sparql:isTriple ( [ shnex:pathValues ex:says ] ) ] .
        """,
        format="turtle",
    )
    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, advanced=True)
    assert result.conforms is True


def test_sparql_subject_over_real_data_triple_term() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))

    shapes = StarLayerGraph()
    shapes.parse(
        data=PREFIXES
        + """
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:expression [ sparql:equals ( [ sparql:subject ( [ shnex:pathValues ex:says ] ) ] ex:bob ) ] .
        """,
        format="turtle",
    )
    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, advanced=True)
    assert result.conforms is True
