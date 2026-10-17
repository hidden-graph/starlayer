"""RDF 1.2 triple terms (``<<( s p o )>>``) in SRL rules: in rule bodies, rule
heads and DATA blocks - parsing, rendering, the RDF encoding, evaluation and the
well-formedness checks."""

from __future__ import annotations

import pytest
from rdflib import Graph, Literal, URIRef, Variable
from starlayer.graph import StarLayerGraph
from starlayer.graph.model.triple import TripleTerm
from starlayer.sparql import srl
from starlayer.sparql.srl import SRLParseError, parse_ruleset

EX = "http://example.org/"
RDF_REIFIES = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")
P = f"PREFIX ex: <{EX}>\n"


def _u(local):
    return URIRef(EX + local)


def _base():
    g = StarLayerGraph()
    g.parse(
        data=f"""
        @prefix ex: <{EX}> .
        ex:alice ex:believes <<( ex:bob ex:age 130 )>> ; ex:name "Alice" .
        ex:carol ex:believes <<( ex:dan ex:age 40 )>> ; ex:name "Carol" .
        ex:bob ex:name "Bob" .
        """,
        format="turtle12",
    )
    return g


def _tt(s, p, o):
    return TripleTerm(s, p, o)


# --- evaluation ---------------------------------------------------------------


def test_a_triple_term_in_a_body_pattern_binds_its_inner_variables():
    rules = parse_ruleset(
        P
        + "RULE { ?w ex:doubts ?p } WHERE { ?w ex:believes <<( ?p ex:age ?n )>> . FILTER(?n > 100) }"
    )
    inferred = rules.infer(_base())
    assert {tuple(t) for t in inferred} == {(_u("alice"), _u("doubts"), _u("bob"))}


def test_a_ground_triple_term_in_a_body_pattern_matches_only_that_triple_term():
    rules = parse_ruleset(
        P
        + "RULE { ?w ex:knowsBob ex:yes } WHERE { ?w ex:believes <<( ex:bob ex:age 130 )>> }"
    )
    assert {tuple(t) for t in rules.infer(_base())} == {
        (_u("alice"), _u("knowsBob"), _u("yes"))
    }


def test_a_triple_term_pattern_joins_with_the_other_patterns():
    rules = parse_ruleset(
        P
        + "RULE { ?w ex:isAbout ?name } WHERE { ?w ex:believes <<( ?p ex:age ?n )>> . ?p ex:name ?name }"
    )
    # only bob has a name among the people believed about
    assert {tuple(t) for t in rules.infer(_base())} == {
        (_u("alice"), _u("isAbout"), Literal("Bob"))
    }


def test_a_head_triple_term_is_created_in_the_output():
    rules = parse_ruleset(
        P
        + "RULE { ?w ex:says <<( ?p ex:age ?n )>> } WHERE { ?w ex:believes <<( ?p ex:age ?n )>> }"
    )
    inferred = rules.infer(_base())
    assert isinstance(inferred, StarLayerGraph)
    assert (
        _u("alice"),
        _u("says"),
        _tt(_u("bob"), _u("age"), Literal(130)),
    ) in inferred
    assert len(inferred) == 2


def test_a_nested_triple_term_is_matched_and_created():
    base = StarLayerGraph()
    base.parse(
        data=f"@prefix ex: <{EX}> . ex:a ex:p <<( ex:b ex:q <<( ex:c ex:r ex:d )>> )>> .",
        format="turtle12",
    )
    rules = parse_ruleset(
        P
        + "RULE { ?x ex:found ?c } WHERE { ?x ex:p <<( ?b ex:q <<( ?c ex:r ex:d )>> )>> }"
    )
    assert {tuple(t) for t in rules.infer(base)} == {(_u("a"), _u("found"), _u("c"))}


def test_not_with_a_triple_term_pattern():
    rules = parse_ruleset(
        P
        + "RULE { ?x ex:noBelief ex:yes } "
        + "WHERE { ?x ex:name ?n . NOT { ?x ex:believes <<( ?p ex:age ?a )>> } }"
    )
    assert {t[0] for t in rules.infer(_base())} == {_u("bob")}


def test_where_data_with_a_triple_term_matches_only_the_base_graph():
    rules = parse_ruleset(
        P
        + "DATA { ex:erin ex:believes <<( ex:bob ex:age 130 )>> . }\n"
        + "RULE { ?w ex:fromBase ex:yes } WHERE DATA { ?w ex:believes <<( ex:bob ex:age 130 )>> }\n"
        + "RULE { ?w ex:fromAny ex:yes } WHERE { ?w ex:believes <<( ex:bob ex:age 130 )>> }"
    )
    inferred = rules.infer(_base())
    assert {t[0] for t in inferred.triples((None, _u("fromBase"), None))} == {
        _u("alice")
    }
    assert {t[0] for t in inferred.triples((None, _u("fromAny"), None))} == {
        _u("alice"),
        _u("erin"),
    }


def test_a_data_block_triple_term_is_in_the_output_and_matched_by_rules():
    rules = parse_ruleset(
        P
        + "DATA { ex:erin ex:believes <<( ex:bob ex:age 7 )>> . }\n"
        + "RULE { ?w ex:thinksAbout ?p } WHERE { ?w ex:believes <<( ?p ex:age ?n )>> }"
    )
    inferred = rules.infer(StarLayerGraph())
    assert (
        _u("erin"),
        _u("believes"),
        _tt(_u("bob"), _u("age"), Literal(7)),
    ) in inferred
    assert (_u("erin"), _u("thinksAbout"), _u("bob")) in inferred


def test_a_plain_rdflib_base_graph_works_when_the_rules_use_triple_terms():
    rules = parse_ruleset(P + "DATA { ex:erin ex:believes <<( ex:bob ex:age 7 )>> . }")
    plain = Graph()
    assert len(rules.infer(plain)) == 1


def test_a_starlayer_base_graph_with_triple_terms_works_with_rules_that_do_not_use_them():
    """Before triple-term support this raised ``AssertionError: ... must be an rdflib term``."""
    rules = parse_ruleset(P + "RULE { ?x ex:known ex:yes } WHERE { ?x ex:name ?n }")
    assert {t[0] for t in rules.infer(_base())} == {_u("alice"), _u("carol"), _u("bob")}


def test_a_head_triple_term_that_would_be_invalid_rdf_is_skipped():
    """A literal cannot be the subject of a triple term (RDF 1.2), so no triple is created."""
    base = StarLayerGraph()
    base.parse(data=f"@prefix ex: <{EX}> . ex:a ex:age 130 .", format="turtle12")
    rules = parse_ruleset(
        P + "RULE { ex:x ex:says <<( ?n ex:p ex:o )>> } WHERE { ?w ex:age ?n }"
    )
    assert len(rules.infer(base)) == 0


def test_query_with_a_goal_pattern_containing_a_triple_term():
    rules = parse_ruleset(P + "RULE { ?w ex:flag ex:yes } WHERE { ?w ex:name ?n }")
    goal = srl.TriplePattern(
        subject=Variable("w"),
        predicate=_u("believes"),
        object=_triple_term_node(Variable("p"), _u("age"), Variable("n")),
    )
    rows = rules.query(_base(), goal)
    assert {
        (r[Variable("w")], r[Variable("p")], r[Variable("n")].toPython()) for r in rows
    } == {
        (_u("alice"), _u("bob"), 130),
        (_u("carol"), _u("dan"), 40),
    }


def _triple_term_node(s, p, o):
    from starlayer.sparql.triple_term import TripleTermNode

    return TripleTermNode("TripleTerm", subject=s, predicate=p, object=o)


# --- text and RDF forms --------------------------------------------------------

_TEXT = (
    P
    + "DATA { ex:alice ex:believes <<( ex:bob ex:age 30 )>> . }\n"
    + "RULE { ?w ex:says <<( ?p ex:age ?n )>> } WHERE { ?w ex:believes <<( ?p ex:age ?n )>> . FILTER(?n > 1) }"
)


def test_a_rule_set_with_triple_terms_round_trips_through_text():
    rules = parse_ruleset(_TEXT)
    text = srl.ruleset_to_text(rules)
    assert "<<(" in text and ")>>" in text
    assert srl.ruleset_to_text(parse_ruleset(text)) == text


def test_a_rule_set_with_triple_terms_round_trips_through_rdf_and_conforms_to_the_shapes():
    rules = parse_ruleset(_TEXT)
    graph, root = srl.ruleset_to_tree(rules)
    assert srl.srl_validate(graph)[0] is True
    assert srl.ruleset_to_text(srl.tree_to_ruleset(graph, root)) == srl.ruleset_to_text(
        rules
    )


# --- well-formedness and planning -----------------------------------------------


def test_a_variable_bound_only_inside_a_body_triple_term_counts_as_bound():
    # ?n is bound only inside the triple term, yet is used by FILTER and in the head
    parse_ruleset(
        P
        + "RULE { ?w ex:n ?n } WHERE { ?w ex:believes <<( ?p ex:age ?n )>> . FILTER(?n > 1) }"
    )


def test_a_head_variable_that_nothing_binds_inside_a_triple_term_is_rejected():
    with pytest.raises(SRLParseError, match="unbound_head_variable"):
        parse_ruleset(
            P
            + "RULE { ?w ex:says <<( ?p ex:age ?z )>> } WHERE { ?w ex:believes <<( ?p ex:age ?n )>> }"
        )


@pytest.mark.parametrize(
    "text",
    [
        "RULE { ?x ex:r ?y } WHERE { <<( ?a ex:p ?b )>> ex:q ?y . ?x ex:s ?a }",
        "RULE { <<( ?a ex:p ?b )>> ex:q ?y } WHERE { ?a ex:p ?b . ?x ex:s ?y }",
        "DATA { <<( ex:a ex:p ex:b )>> ex:q ex:c . }",
    ],
)
def test_a_triple_term_as_a_subject_is_rejected(text):
    with pytest.raises(SRLParseError, match="triple_term_in_subject"):
        parse_ruleset(P + text)


def test_a_body_triple_term_depends_on_the_rule_that_can_produce_it():
    plan = parse_ruleset(
        P
        + "RULE { ?w ex:says <<( ?p ex:age ?n )>> } WHERE { ?w ex:src ?p . ?p ex:age ?n }\n"
        + "RULE { ?w ex:heard ex:yes } WHERE { ?w ex:says <<( ex:bob ex:age 130 )>> }"
    ).plan()
    assert {(e.source, e.target, e.label) for e in plan.edges} == {(1, 0, "open")}


def test_a_head_triple_term_containing_a_variable_makes_a_run_once_rule():
    plan = parse_ruleset(
        P
        + "RULE { ?w ex:says <<( ?p ex:age ?n )>> } WHERE { ?w ex:believes <<( ?p ex:age ?n )>> }"
    ).plan()
    assert [r.index for r in plan.strata[0].run_once] == [0]


# --- the rest of the SPARQL 1.2 triple syntax: object lists, reified triples, annotations ---


def _annotated_base():
    g = StarLayerGraph()
    g.parse(
        data=f"""
        @prefix ex: <{EX}> .
        ex:a ex:p ex:b1 , ex:b2 .
        ex:a ex:says ex:b1 {{| ex:certainty 0.9 |}} .
        ex:a ex:says ex:b2 {{| ex:certainty 0.2 |}} .
        """,
        format="turtle12",
    )
    return g


def test_a_comma_separated_object_list_in_the_body_and_the_head():
    rules = parse_ruleset(
        P + "RULE { ?x ex:r ?y , ex:fixed } WHERE { ?x ex:p ?y , ex:b2 }"
    )
    inferred = {tuple(t) for t in rules.infer(_annotated_base())}
    assert inferred == {
        (_u("a"), _u("r"), _u("b1")),
        (_u("a"), _u("r"), _u("b2")),
        (_u("a"), _u("r"), _u("fixed")),
    }


def test_an_annotation_block_in_a_body_pattern_matches_the_reifier_of_that_triple():
    rules = parse_ruleset(
        P
        + "RULE { ?x ex:strong ?y } WHERE { ?x ex:says ?y {| ex:certainty ?c |} . FILTER(?c > 0.5) }"
    )
    assert {tuple(t) for t in rules.infer(_annotated_base())} == {
        (_u("a"), _u("strong"), _u("b1"))
    }


def test_a_reified_triple_in_a_body_pattern():
    rules = parse_ruleset(
        P
        + "RULE { ?x ex:strong ?y } WHERE { << ?x ex:says ?y >> ex:certainty ?c . FILTER(?c > 0.5) }"
    )
    assert {tuple(t) for t in rules.infer(_annotated_base())} == {
        (_u("a"), _u("strong"), _u("b1"))
    }


def test_an_annotation_block_in_a_head_creates_the_triple_its_reifier_and_the_annotation():
    rules = parse_ruleset(
        P + "RULE { ?x ex:knows ?y {| ex:since 2020 |} } WHERE { ?x ex:p ?y }"
    )
    inferred = rules.infer(_annotated_base())
    assert (_u("a"), _u("knows"), _u("b1")) in inferred
    assert {o for _r, _p, o in inferred.triples((None, RDF_REIFIES, None))} == {
        _tt(_u("a"), _u("knows"), _u("b1")),
        _tt(_u("a"), _u("knows"), _u("b2")),
    }
    assert len(list(inferred.triples((None, _u("since"), Literal(2020))))) == 2


def test_a_reified_triple_in_a_data_block():
    rules = parse_ruleset(P + "DATA { << ex:a ex:p ex:b >> ex:certainty 0.9 . }")
    inferred = rules.infer(StarLayerGraph())
    assert (
        len(list(inferred.triples((None, RDF_REIFIES, _tt(_u("a"), _u("p"), _u("b"))))))
        == 1
    )
    assert len(list(inferred.triples((None, _u("certainty"), None)))) == 1


def test_a_blank_node_property_list_and_a_collection():
    rules = parse_ruleset(
        P
        + "RULE { ?x ex:r [ ex:a ?y ; ex:n 1 ] } WHERE { ?x ex:p ?y }\nDATA { ex:a ex:list ( 1 2 ) . }"
    )
    inferred = rules.infer(_annotated_base())
    assert (
        len(list(inferred.triples((None, _u("n"), Literal(1))))) == 2
    )  # one fresh blank node per solution
    assert any(p == _u("list") for _s, p, _o in inferred)


def test_a_variable_in_a_data_block_is_rejected():
    with pytest.raises(SRLParseError, match="variable_in_data"):
        parse_ruleset(P + "DATA { ?x ex:p ex:o . }")
