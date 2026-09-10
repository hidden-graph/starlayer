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
    @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
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


def _boolean_expr_conforms(expression_ttl: str, target: str = "ex:alice", fmt: str = "turtle") -> bool:
    """Like _expression_conforms, but for expressions that already evaluate to
    a boolean (true)/(false) list themselves (e.g. shnex:matchAll, shnex:exists)
    - plugged directly into sh:expression with no extra shnex:exists wrapper,
    since wrapping an already-boolean result in shnex:exists would always see
    a non-empty ``(true)`` or ``(false)`` list and be vacuously true either way.

    ``fmt`` selects the shapes-graph parse format - "turtle12" for cases that
    need an RDF 1.2 dir-lang-string literal constant (``"x"@en--ltr``), which
    plain "turtle" doesn't parse.
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
        format=fmt,
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


def test_conformstoshape_true_when_all_nodes_conform() -> None:
    # Zero starshacl-owned coverage before this test - only the W3C suite
    # exercised shnex:conformsToShape at all.
    assert (
        _boolean_expr_conforms("shnex:conformsToShape ( ex:bob ex:PersonShape )") is True
    )


def test_conformstoshape_false_when_a_node_does_not_conform() -> None:
    assert (
        _boolean_expr_conforms("shnex:conformsToShape ( ex:carol ex:PersonShape )") is False
    )


def test_conformstoshape_over_expression_yielding_multiple_nodes() -> None:
    # shnex:conformsToShape requires ALL results of the first argument's node
    # expression to conform - bob conforms to PersonShape, carol does not, so
    # concat(bob, carol) must be false even though bob alone would be true.
    assert (
        _boolean_expr_conforms(
            "shnex:conformsToShape ( [ shnex:concat ( ex:bob ex:carol ) ] ex:PersonShape )"
        )
        is False
    )


def test_conformstoshape_over_empty_result_is_not_vacuously_true() -> None:
    # Confirmed live: shnex:conformsToShape's implementation returns [] (not
    # [true]) when its node-expression argument yields zero nodes - unlike
    # shnex:matchAll (all() over an empty n_list -> True, a real boolean),
    # an empty *list of results* here means "unbound", which
    # _boolean_expr_conforms's sh:expression harness treats as non-conforming
    # (ExpressionConstraintComponent requires exactly (true), not "no value
    # at all"). Documents the actual, not assumed, behavior.
    assert (
        _boolean_expr_conforms(
            "shnex:conformsToShape ( [ shnex:filterShape ex:PersonShape ; shnex:nodes ( ex:carol ) ] ex:PersonShape )"
        )
        is False
    )


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


# ---------------------------------------------------------------------------
# sparql: (http://www.w3.org/ns/sparql#) namespace - full pipeline coverage.
#
# Before this class, only 5 of the 77 sparql: functions/operators
# (strlen, isTriple, subject, equals, greater-than) were ever exercised
# through the real validate()/apply_rules() entrypoint - the other 72 had
# coverage only via tests/w3c_shacl12/test_w3c_node_expr.py, which calls
# eval_expr()/eval_sparql_expr() directly against a hand-built
# StarLayerGraph, never through pySHACL's real dispatch. That gap is exactly
# how the two real bugs already on record in this file's docstring
# (real-data triple-term flat-encoding, and the shapes-graph-only-uses-
# sparql:-wiring gap) were both missed by unit-level coverage and only found
# by testing the real entrypoint - see test_sparql_only_shapes_graph_reaches_
# sparql_node_expressions and test_sparql_istriple_over_real_data_triple_term
# above.
#
# Building this comprehensive table found two more, previously undocumented:
# 1. sparql:now/sparql:rand were entirely absent from starshacl/
#    sparql_node_expressions.py's dispatch table - not "wired but broken",
#    genuinely missing - so a shapes graph using either crashed the whole
#    validate() call with an unguarded StopIteration (not registered in
#    _ALL_PREDICATES at all, so is_sparql_expr() never routed them here; they
#    fell through to pySHACL's own expression evaluator, which doesn't
#    understand them either). Fixed by adding SPARQL.now/SPARQL.rand to
#    _FUNCTION_CALLS ("NOW"/"RAND") - both are ordinary niladic SPARQL 1.1
#    builtins, no special-casing needed.
# 2. sparql:hasLangdir/langdir/strlangdir silently gave wrong answers
#    (hasLangdir always false, langdir always "") for a DirLangString value
#    reaching this module through the real pipeline - by the time pySHACL's
#    node-expression dispatch hands a DirLangString here, it has already been
#    flat-encoded to a plain Literal (starlayergraph's internal dirlang
#    datatype-URI convention), exactly the same flattening
#    _decode_triple_term() above already works around for triple terms.
#    sparql_node_expressions.py's own _eval_dirlang_form()._decode() only
#    ever checked isinstance(value, DirLangString), which is never true for
#    real pipeline data - only for the W3C suite's eval_expr()-direct harness,
#    which never encodes anything. Fixed by also trying
#    starshacl.adapters._try_decode_dirlangstring() (the same decoder
#    starshacl.adapters itself already uses).
#
# Each entry evaluates to a boolean directly (comparison/predicate functions)
# or is wrapped in sparql:equals/sparql:isX against a known expected value
# (value-returning functions) so every case can share the one
# _boolean_expr_conforms() harness. Nested sparql: calls need [ ] blank-node
# wrapping around each nested call, same as shnex: nesting elsewhere in this
# file (a bare `sparql:f ( sparql:g (...) )` is not valid Turtle - the nested
# call must itself be `[ sparql:g (...) ]`, confirmed live: omitting the
# brackets raised "too many values to unpack" out of _defining_predicate()).
SPARQL_FUNCTION_PIPELINE_CASES = [
    ("strlen", 'sparql:equals ( [ sparql:strlen ( "hello" ) ] 5 )', "turtle"),
    ("ucase", 'sparql:equals ( [ sparql:ucase ( "abc" ) ] "ABC" )', "turtle"),
    ("lcase", 'sparql:equals ( [ sparql:lcase ( "ABC" ) ] "abc" )', "turtle"),
    ("substr", 'sparql:equals ( [ sparql:substr ( "hello" 2 3 ) ] "ell" )', "turtle"),
    ("contains", 'sparql:contains ( "hello" "ell" )', "turtle"),
    ("strstarts", 'sparql:strstarts ( "hello" "he" )', "turtle"),
    ("strends", 'sparql:strends ( "hello" "lo" )', "turtle"),
    ("strbefore", 'sparql:equals ( [ sparql:strbefore ( "hello" "l" ) ] "he" )', "turtle"),
    ("strafter", 'sparql:equals ( [ sparql:strafter ( "hello" "l" ) ] "lo" )', "turtle"),
    ("encode", 'sparql:equals ( [ sparql:encode ( "a b" ) ] "a%20b" )', "turtle"),
    ("concat", 'sparql:equals ( [ sparql:concat ( "foo" "bar" ) ] "foobar" )', "turtle"),
    ("langMatches", 'sparql:langMatches ( "en" "en" )', "turtle"),
    ("regex", 'sparql:regex ( "hello" "^h" )', "turtle"),
    ("replace", 'sparql:equals ( [ sparql:replace ( "hello" "l" "L" ) ] "heLLo" )', "turtle"),
    ("abs", 'sparql:equals ( [ sparql:abs ( -5 ) ] 5 )', "turtle"),
    ("ceil", 'sparql:equals ( [ sparql:ceil ( 4.2 ) ] 5 )', "turtle"),
    ("floor", 'sparql:equals ( [ sparql:floor ( 4.8 ) ] 4 )', "turtle"),
    ("round", 'sparql:equals ( [ sparql:round ( 4.5 ) ] 5 )', "turtle"),
    ("year", 'sparql:equals ( [ sparql:year ( "2024-01-15"^^xsd:date ) ] 2024 )', "turtle"),
    ("month", 'sparql:equals ( [ sparql:month ( "2024-01-15"^^xsd:date ) ] 1 )', "turtle"),
    ("day", 'sparql:equals ( [ sparql:day ( "2024-01-15"^^xsd:date ) ] 15 )', "turtle"),
    ("hours", 'sparql:equals ( [ sparql:hours ( "2024-01-15T10:20:30"^^xsd:dateTime ) ] 10 )', "turtle"),
    ("minutes", 'sparql:equals ( [ sparql:minutes ( "2024-01-15T10:20:30"^^xsd:dateTime ) ] 20 )', "turtle"),
    ("seconds", 'sparql:equals ( [ sparql:seconds ( "2024-01-15T10:20:30"^^xsd:dateTime ) ] 30 )', "turtle"),
    ("tz", 'sparql:equals ( [ sparql:tz ( "2024-01-15T10:20:30Z"^^xsd:dateTime ) ] "Z" )', "turtle"),
    (
        "timezone_is_bound",
        # TIMEZONE() returns an xsd:dayTimeDuration - checked for boundedness
        # rather than an exact value (duration lexical form varies), unlike
        # tz's plain-string result above.
        'sparql:bound ( [ sparql:timezone ( "2024-01-15T10:20:30Z"^^xsd:dateTime ) ] )',
        "turtle",
    ),
    ("md5", 'sparql:equals ( [ sparql:md5 ( "abc" ) ] "900150983cd24fb0d6963f7d28e17f72" )', "turtle"),
    ("sha1", 'sparql:equals ( [ sparql:sha1 ( "abc" ) ] "a9993e364706816aba3e25717850c26c9cd0d89d" )', "turtle"),
    (
        "sha256",
        'sparql:equals ( [ sparql:sha256 ( "abc" ) ] '
        '"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad" )',
        "turtle",
    ),
    (
        "sha384",
        'sparql:equals ( [ sparql:sha384 ( "abc" ) ] '
        '"cb00753f45a35e8bb5a03d699ac65007272c32ab0eded1631a8b605a43ff5bed8086072ba1e7cc2358baeca134c825a7" )',
        "turtle",
    ),
    (
        "sha512",
        'sparql:equals ( [ sparql:sha512 ( "abc" ) ] '
        '"ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a2192992a274fc1a836ba3c23a3feebbd'
        '454d4423643ce80e2a9ac94fa54ca49f" )',
        "turtle",
    ),
    ("isIRI", "sparql:isIRI ( ex:alice )", "turtle"),
    ("isURI", "sparql:isURI ( ex:alice )", "turtle"),
    ("isBlank_false_for_iri", "sparql:logical-not ( [ sparql:isBlank ( ex:alice ) ] )", "turtle"),
    ("isLiteral", 'sparql:isLiteral ( "x" )', "turtle"),
    ("isNumeric", "sparql:isNumeric ( 42 )", "turtle"),
    ("bnode", "sparql:isBlank ( [ sparql:bnode () ] )", "turtle"),
    ("iri", 'sparql:equals ( [ sparql:iri ( "http://example.org/alice" ) ] ex:alice )', "turtle"),
    ("uri", 'sparql:equals ( [ sparql:uri ( "http://example.org/alice" ) ] ex:alice )', "turtle"),
    ("strdt", 'sparql:equals ( [ sparql:strdt ( "42" xsd:integer ) ] 42 )', "turtle"),
    (
        "strlang_via_lang_roundtrip",
        'sparql:equals ( [ sparql:lang ( [ sparql:strlang ( "hello" "en" ) ] ) ] "en" )',
        "turtle",
    ),
    ("uuid", "sparql:isIRI ( [ sparql:uuid () ] )", "turtle"),
    ("struuid", "sparql:equals ( [ sparql:strlen ( [ sparql:struuid () ] ) ] 36 )", "turtle"),
    ("str", 'sparql:equals ( [ sparql:str ( 42 ) ] "42" )', "turtle"),
    ("lang", 'sparql:equals ( [ sparql:lang ( "hi"@en ) ] "en" )', "turtle"),
    ("datatype", "sparql:equals ( [ sparql:datatype ( 42 ) ] xsd:integer )", "turtle"),
    ("sameTerm", "sparql:sameTerm ( ex:alice ex:alice )", "turtle"),
    (
        "triple_chain_subject",
        "sparql:equals ( [ sparql:subject ( [ sparql:triple ( ex:s ex:p ex:o ) ] ) ] ex:s )",
        "turtle",
    ),
    (
        "triple_chain_predicate",
        "sparql:equals ( [ sparql:predicate ( [ sparql:triple ( ex:s ex:p ex:o ) ] ) ] ex:p )",
        "turtle",
    ),
    (
        "triple_chain_object",
        "sparql:equals ( [ sparql:object ( [ sparql:triple ( ex:s ex:p ex:o ) ] ) ] ex:o )",
        "turtle",
    ),
    ("isTriple_of_constructed_triple", "sparql:isTriple ( [ sparql:triple ( ex:s ex:p ex:o ) ] )", "turtle"),
    (
        "now_returns_a_dateTime",
        "sparql:equals ( [ sparql:datatype ( [ sparql:now () ] ) ] xsd:dateTime )",
        "turtle",
    ),
    ("rand_is_numeric", "sparql:isNumeric ( [ sparql:rand () ] )", "turtle"),
    ("sameValue_cross_type_numeric", "sparql:sameValue ( 1 1.0 )", "turtle"),
    ("not-equals", "sparql:not-equals ( 1 2 )", "turtle"),
    ("less-than", "sparql:less-than ( 1 2 )", "turtle"),
    # greater-than itself is already covered by test_sparql_function_call
    # above - included here too so the coverage-guard test below (and this
    # table's own self-containment) doesn't depend on that older test.
    ("greater-than", "sparql:greater-than ( 2 1 )", "turtle"),
    ("less-than-or-equal", "sparql:less-than-or-equal ( 1 1 )", "turtle"),
    ("greater-than-or-equal", "sparql:greater-than-or-equal ( 1 1 )", "turtle"),
    ("plus", "sparql:equals ( [ sparql:plus ( 1 2 ) ] 3 )", "turtle"),
    ("subtract", "sparql:equals ( [ sparql:subtract ( 5 2 ) ] 3 )", "turtle"),
    ("multiply", "sparql:equals ( [ sparql:multiply ( 2 3 ) ] 6 )", "turtle"),
    ("divide", "sparql:equals ( [ sparql:divide ( 6 2 ) ] 3 )", "turtle"),
    ("logical-and", "sparql:logical-and ( true true )", "turtle"),
    ("logical-or", "sparql:logical-or ( false true )", "turtle"),
    ("logical-not", "sparql:logical-not ( false )", "turtle"),
    ("unary-plus", "sparql:equals ( [ sparql:unary-plus ( 5 ) ] 5 )", "turtle"),
    ("unary-minus", "sparql:equals ( [ sparql:unary-minus ( 5 ) ] -5 )", "turtle"),
    ("bound_true", "sparql:bound ( 1 )", "turtle"),
    (
        "bound_false_for_empty_coalesce",
        "sparql:logical-not ( [ sparql:bound ( [ sparql:coalesce () ] ) ] )",
        "turtle",
    ),
    (
        "coalesce_skips_unbound_first_arg",
        "sparql:equals ( [ sparql:coalesce ( [ sparql:coalesce () ] 5 ) ] 5 )",
        "turtle",
    ),
    ("if_true_branch", "sparql:equals ( [ sparql:if ( true 1 2 ) ] 1 )", "turtle"),
    ("hasLang_matching_tag", 'sparql:hasLang ( "hi"@en "en" )', "turtle"),
    ("hasLangdir_true_for_dirlangstring", 'sparql:hasLangdir ( "hello"@en--ltr )', "turtle12"),
    ("langdir_extracts_direction", 'sparql:equals ( [ sparql:langdir ( "hello"@en--ltr ) ] "ltr" )', "turtle12"),
    (
        "strlangdir_via_langdir_roundtrip",
        'sparql:equals ( [ sparql:langdir ( [ sparql:strlangdir ( "hello" "en" "ltr" ) ] ) ] "ltr" )',
        "turtle",
    ),
]


@pytest.mark.parametrize("name,expression_ttl,fmt", SPARQL_FUNCTION_PIPELINE_CASES, ids=[c[0] for c in SPARQL_FUNCTION_PIPELINE_CASES])
def test_sparql_function_through_real_pipeline(name: str, expression_ttl: str, fmt: str) -> None:
    assert _boolean_expr_conforms(expression_ttl, fmt=fmt) is True


def test_sparql_function_pipeline_cases_cover_every_registered_predicate() -> None:
    # Regression guard for the table above itself: fails loudly if a future
    # sparql: addition (or a rename) isn't reflected here, rather than
    # silently leaving the new predicate at zero pipeline coverage.
    from starshacl.sparql_node_expressions import _ALL_PREDICATES

    registered_local_names = {str(p).rsplit("#", 1)[-1] for p in _ALL_PREDICATES}
    # Every registered predicate's own local name must appear as at least
    # one case's expression text (looser than exact-match on the synthetic
    # test id, which freely adds descriptive suffixes like "_true"/"_via_...").
    joined_exprs = " ".join(expr for _name, expr, _fmt in SPARQL_FUNCTION_PIPELINE_CASES)
    missing = {name for name in registered_local_names if f"sparql:{name} " not in joined_exprs + " "}
    assert not missing, f"sparql: predicates with no pipeline test case: {sorted(missing)}"
