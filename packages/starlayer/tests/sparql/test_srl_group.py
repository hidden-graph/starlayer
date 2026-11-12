"""SPARQL 1.2 Rules (WD 2026-11-09), "Grouping and Aggregation": ``GROUP [BY ?k ...] { pattern } [ ?n := COUNT(*) , ... ]``.

Syntax (productions [22] to [29]), well-formedness (4.2), run-once and closed dependencies (4.1, 4.3), and the evaluation of 6.4 and 6.4
(``evalRuleElements`` for a group element, ``evalAggregate``): a group per key, one group when there are no keys even if the pattern has no
solution, an aggregation error drops the group, the pattern sees only the group keys, and only the keys and the aggregation variables
are in scope afterwards."""

from __future__ import annotations

import pytest
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.sparql.parse_srl import parse_srl
from starlayer.sparql.srl import (
    SRLError,
    SRLParseError,
    parse_ruleset,
    ruleset_to_text,
    srl_parse_to_tree,
    srl_tree_to_text,
    srl_validate,
    tree_to_ruleset,
)
from starlayer.sparql.srl_eval import StratificationError

P = "PREFIX : <http://e/> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"


def _graph(ttl: str = "") -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data="@prefix : <http://e/> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n" + ttl, format="turtle")
    return g


def _infer(rules: str, ttl: str = "") -> set[tuple[str, str, str]]:
    out = parse_ruleset(P + rules).infer(_graph(ttl))
    return {(s.value.rsplit("/", 1)[-1], p.value.rsplit("/", 1)[-1], getattr(o, "value", str(o))) for s, p, o in out.triples((None, None, None))}


COMPONENTS = """
    :frontend rdf:type :Component ; :exposedTo :vuln1 , :vuln2 .
    :db rdf:type :Component ; :exposedTo :vuln1 .
    :logger rdf:type :Component ."""


# ---- the draft's own example 8 ---------------------------------------------------------------------------------------------

def test_example_8_counts_the_vulnerabilities_of_each_component():
    rules = "RULE { ?x :vulnerabilityCount ?n } WHERE { ?x rdf:type :Component . GROUP BY ?x { ?x :exposedTo ?v } [ ?n := COUNT(*) ] }"
    # :logger has no vulnerability, so its group has no solution, there is no group, and no triple is inferred
    assert _infer(rules, COMPONENTS) == {("frontend", "vulnerabilityCount", "2"), ("db", "vulnerabilityCount", "1")}


# ---- evaluation (6.4) ------------------------------------------------------------------------------------------------------

def test_with_no_group_keys_there_is_one_group_even_when_the_pattern_has_no_solution():
    rules = "RULE { :s :n ?n ; :t ?t } WHERE { GROUP { ?s :p ?o } [ ?n := COUNT(*) , ?t := SUM(?o) ] }"
    assert _infer(rules) == {("s", "n", "0"), ("s", "t", "0")}


def test_min_and_max_of_an_empty_group_are_errors_and_the_group_is_dropped():
    assert _infer("RULE { :s :m ?m } WHERE { GROUP { ?s :p ?o } [ ?m := MIN(?o) ] }") == set()
    assert _infer("RULE { :s :m ?m } WHERE { GROUP { ?s :p ?o } [ ?m := MAX(?o) ] }") == set()


def test_one_aggregation_error_drops_the_whole_group_not_just_that_value():
    ttl = ':a :p "text" . :a :q 1 .'
    rules = "RULE { :a :s ?s ; :c ?c } WHERE { GROUP BY ?a { ?a :p ?o } [ ?c := COUNT(*) , ?s := SUM(?o) ] }"
    assert _infer(rules, ttl) == set()  # SUM of a string is an error: ?c is lost with it


def test_count_distinct_and_count_of_a_variable():
    ttl = ":a :p 1, 2 . :b :p 1 . :a :q 1 . :b :q 1 ."
    rules = """
        RULE { :r :values ?n } WHERE { GROUP { ?s :p ?o } [ ?n := COUNT(?o) ] }
        RULE { :r :distinct ?d } WHERE { GROUP { ?s :p ?o } [ ?d := COUNT(DISTINCT ?o) ] }
        RULE { :r :rows ?c } WHERE { GROUP { ?s :p ?o } [ ?c := COUNT(DISTINCT *) ] }"""
    assert _infer(rules, ttl) == {("r", "values", "3"), ("r", "distinct", "2"), ("r", "rows", "3")}


def test_count_distinct_star_counts_distinct_solution_mappings():
    ttl = ":a :p 1 . :b :p 1 ."
    rules = """
        RULE { :r :all ?n } WHERE { GROUP { ?s :p ?o } [ ?n := COUNT(*) ] }
        RULE { :r :values ?n } WHERE { GROUP { ?s :p ?o SET(?c := 1) } [ ?n := COUNT(DISTINCT ?c) ] }
        RULE { :r :distinctMappings ?n } WHERE { GROUP { ?x :p ?o } [ ?n := COUNT(DISTINCT *) ] }"""
    assert _infer(rules, ttl) == {("r", "all", "2"), ("r", "values", "1"), ("r", "distinctMappings", "2")}


def test_sum_min_max_use_sparql_numeric_promotion_and_ordering():
    ttl = ':a :p 1, 2.5 . :a :q "b", "a" . :x :r 3 . :y :r 3 .'
    rules = """
        RULE { :a :sum ?n } WHERE { GROUP { :a :p ?o } [ ?n := SUM(?o) ] }
        RULE { :a :min ?n ; :max ?m } WHERE { GROUP { :a :q ?o } [ ?n := MIN(?o) , ?m := MAX(?o) ] }
        RULE { :a :sumTwice ?n } WHERE { GROUP { ?s :r ?o } [ ?n := SUM(?o) ] }"""
    assert _infer(rules, ttl) == {("a", "sum", "3.5"), ("a", "min", "a"), ("a", "max", "b"), ("a", "sumTwice", "6")}


def test_the_group_pattern_is_correlated_with_the_keys_that_are_already_bound():
    ttl = ":a :p 1, 2 . :b :p 5 . :a rdf:type :T . :b rdf:type :T ."
    rules = "RULE { ?s :total ?n } WHERE { ?s rdf:type :T . GROUP BY ?s { ?s :p ?o } [ ?n := SUM(?o) ] }"
    assert _infer(rules, ttl) == {("a", "total", "3"), ("b", "total", "5")}


def test_a_key_the_pattern_binds_gives_a_group_per_value():
    ttl = ":a :p 1, 2 . :b :p 5 ."
    rules = "RULE { ?s :n ?n } WHERE { GROUP BY ?s { ?s :p ?o } [ ?n := COUNT(*) ] }"
    assert _infer(rules, ttl) == {("a", "n", "2"), ("b", "n", "1")}


def test_variables_bound_before_the_group_but_not_keys_are_not_visible_in_its_pattern():
    # ?o is bound outside; the group pattern's own ?o is a different variable, so it is not constrained to the outer value
    ttl = ":a :p 1, 2 . :a :q 1 ."
    rules = "RULE { ?s :n ?n } WHERE { ?s :q ?o . GROUP BY ?s { ?s :p ?o } [ ?n := COUNT(*) ] }"
    assert _infer(rules, ttl) == {("a", "n", "2")}


def test_filter_and_set_in_a_group_pattern():
    ttl = ":a :p 1, 2, 3 ."
    rules = "RULE { ?s :sum ?n } WHERE { GROUP BY ?s { ?s :p ?o FILTER(?o >= 2) SET(?z := ?o * 10) } [ ?n := SUM(?z) ] }"
    assert _infer(rules, ttl) == {("a", "sum", "50")}


def test_a_blank_node_in_a_group_pattern_acts_as_a_variable():
    ttl = ":a :p [ :q 1 ] , [ :q 2 ] ."
    rules = "RULE { ?s :n ?n } WHERE { GROUP BY ?s { ?s :p [ :q ?v ] } [ ?n := COUNT(*) ] }"
    assert _infer(rules, ttl) == {("a", "n", "2")}


def test_aggregation_values_can_be_used_by_later_elements_of_the_rule():
    ttl = ":a :p 1, 2 . :b :p 9 ."
    rules = "RULE { ?s :big ?n } WHERE { GROUP BY ?s { ?s :p ?o } [ ?n := SUM(?o) ] FILTER(?n > 5) }"
    assert _infer(rules, ttl) == {("b", "big", "9")}


def test_two_group_elements_in_one_rule():
    ttl = ":a :p 1, 2 . :a :q 7 ."
    rules = "RULE { ?s :n ?n ; :t ?t } WHERE { GROUP BY ?s { ?s :p ?o } [ ?n := COUNT(*) ] GROUP BY ?s { ?s :q ?w } [ ?t := SUM(?w) ] }"
    assert _infer(rules, ttl) == {("a", "n", "2"), ("a", "t", "7")}


# ---- run-once and stratification (4.1, 4.3, 4.4) -----------------------------------------------------------------------------

def test_a_rule_with_a_group_element_is_run_once():
    rule = parse_ruleset(P + "RULE { :s :n ?n } WHERE { GROUP { ?s :p ?o } [ ?n := COUNT(*) ] }").rules[0]
    assert rule._is_run_once


def test_the_group_rule_runs_after_the_rules_that_produce_what_its_pattern_matches():
    rules = """
        RULE { ?x :exposedTo ?v } WHERE { ?x :dependsOn ?y . ?y :exposedTo ?v }
        RULE { ?x :count ?n } WHERE { ?x rdf:type :Component . GROUP BY ?x { ?x :exposedTo ?v } [ ?n := COUNT(*) ] }"""
    plan = parse_ruleset(P + rules).plan()
    labels = {(e.source, e.target): e.label for e in plan.edges}
    assert labels[(1, 0)] == "closed"
    assert [[r.index for r in s.run_once] + [r.index for r in s.general] for s in plan.strata] == [[0], [1]]
    ttl = ":web rdf:type :Component ; :dependsOn :app . :app rdf:type :Component ; :dependsOn :db . :db :exposedTo :v1, :v2 ."
    got = _infer(rules, ttl)
    # the count is taken after the recursion has finished: :web and :app inherit the two vulnerabilities of :db
    assert {("web", "count", "2"), ("app", "count", "2")} <= got


def test_a_rule_that_groups_over_its_own_output_is_a_stratification_error():
    rules = "RULE { ?x :n ?n } WHERE { ?x rdf:type :C . GROUP BY ?x { ?x :n ?m } [ ?n := COUNT(*) ] }"
    with pytest.raises(StratificationError):
        parse_ruleset(P + rules).plan()


# ---- syntax (productions [22] to [29]) -------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "RULE {} WHERE { GROUP { ?s ?p ?o } [] }",
        "RULE {} WHERE { GROUP { } [ ] }",
        "RULE {} WHERE { ?a ?b ?c GROUP { ?s ?p ?o } [] FILTER(?c) }",
        "RULE {} WHERE { GROUP BY ?s ?p { ?s ?p ?o } [ ?N := COUNT(*) ] }",
        "RULE {} WHERE { GROUP { ?s ?p ?o } [ ?N := COUNT(DISTINCT *) , ?S := SUM(?o) ] }",
        "RULE {} WHERE { GROUP { ?s ?p ?o } [ ?N := count(distinct ?o) ] }",
    ],
)
def test_the_grammar_accepts(text):
    parse_srl(text)


@pytest.mark.parametrize(
    "text",
    [
        "RULE {} WHERE { GROUP BY ?s [ ?N := COUNT(*) ] }",  # no pattern
        "RULE {} WHERE { GROUP BY ?x { } }",  # no aggregation list
        "RULE {} WHERE { GROUP BY { ?s ?p ?o } [ ?N := COUNT(*) ] }",  # BY without a variable
        "RULE {} WHERE { GROUP BY ?s { ?s :p ?o } [ ?N := COUNT(?s+?o) ] }",  # the argument is a variable, not an expression
        "RULE {} WHERE { GROUP BY ?s { ?s :p ?o } [ ?N := MIN(DISTINCT ?o) ] }",  # DISTINCT only for COUNT
        "RULE {} WHERE { GROUP BY ?s { ?s :p ?o } [ ?N := SUM(*) ] }",  # * only for COUNT
        "RULE {} WHERE { GROUP { ?s ?p ?o } [ ?N := COUNT(*) ?S := SUM(?o) ] }",  # a comma between assignments
        "RULE {} WHERE { GROUP { ?s ?p ?o } [ ?N := COUNT(*) , ] }",  # no trailing comma
        "RULE {} WHERE { GROUP { NOT { ?s ?p ?o } } [] }",  # no negation in a group pattern
        "RULE {} WHERE { GROUP { GROUP { ?s ?p ?o } [] } [] }",  # no nested group
    ],
)
def test_the_grammar_rejects(text):
    with pytest.raises(SRLParseError):
        parse_srl("PREFIX : <http://e/>\n" + text)


# ---- well-formedness (4.2) ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("rules", "kind"),
    [
        ("RULE { :s :p ?n } WHERE { ?n :p ?o GROUP { ?s :q ?v } [ ?n := COUNT(*) ] }", "aggregation_variable_in_scope"),
        ("RULE { :s :p ?n } WHERE { GROUP { ?s :q ?o } [ ?o := COUNT(*) ] }", "aggregation_variable_in_scope"),
        ("RULE { :s :p ?n } WHERE { GROUP { ?s :q ?v } [ ?n := COUNT(*) , ?n := SUM(?v) ] }", "duplicate_aggregation_variable"),
        ("RULE { :s :p ?n } WHERE { GROUP { ?s :q ?v } [ ?n := SUM(?w) ] }", "unbound_aggregation_argument"),
        ("RULE { :s :p ?n } WHERE { GROUP BY ?k { ?s :q ?v } [ ?n := COUNT(*) ] }", "group_key_unbound"),
        ("RULE { :s :p ?v } WHERE { GROUP { ?s :q ?v } [ ?n := COUNT(*) ] }", "unbound_head_variable"),
        ("RULE { :s :p ?n } WHERE { ?a :b ?c GROUP { ?s :q ?v FILTER(?c) } [ ?n := COUNT(*) ] }", "unbound_filter_variable"),
    ],
)
def test_the_well_formedness_conditions(rules, kind):
    with pytest.raises(SRLParseError, match=kind):
        parse_ruleset(P + rules)


def test_a_key_bound_before_the_group_is_visible_in_its_pattern_filter():
    parse_ruleset(P + "RULE { ?s :n ?n } WHERE { ?s :a ?x GROUP BY ?s { ?s :q ?v FILTER(?s != ?v) } [ ?n := COUNT(*) ] }")


# ---- the srl: tree ------------------------------------------------------------------------------------------------------------

TREE_RULES = [
    "RULE { ?x :n ?n } WHERE { ?x rdf:type :C . GROUP BY ?x { ?x :p ?v } [ ?n := COUNT(*) ] }",
    "RULE { :s :n ?n ; :t ?t } WHERE { GROUP { ?s :p ?o } [ ?n := COUNT(DISTINCT ?o) , ?t := SUM(?o) ] }",
    "RULE { ?s :m ?m } WHERE { ?s :q :z GROUP BY ?s { ?s :p ?o FILTER(?o > 1) SET(?z := ?o + 1) } [ ?m := MIN(?z) ] }",
    "RULE { :s :p :o } WHERE { GROUP { ?s :p ?o } [] }",
]


@pytest.mark.parametrize("rules", TREE_RULES)
def test_a_group_survives_text_to_tree_and_back(rules):
    graph, root = srl_parse_to_tree(P + rules)
    assert srl_validate(graph)
    text = srl_tree_to_text(graph, root)
    assert ruleset_to_text(parse_ruleset(text)) == text
    assert tree_to_ruleset(graph, root).rules == parse_ruleset(P + rules).rules


def test_a_group_with_a_malformed_aggregation_does_not_validate():
    from starlayer.sparql.srl import SRL

    graph, _root = srl_parse_to_tree(P + TREE_RULES[1])
    agg = next(graph.subjects(SRL["function"], None))
    graph.remove((agg, SRL["function"], None))
    graph.add((agg, SRL["function"], __import__("pyoxigraph").Literal("AVG")))
    assert not srl_validate(graph)[0] if isinstance(srl_validate(graph), tuple) else not srl_validate(graph)


def test_a_malformed_rule_set_text_is_an_srl_error():
    with pytest.raises(SRLError):
        parse_ruleset(P + "RULE { :s :p :o } WHERE { GROUP { ?s :p ?o } [ ?n := AVG(?o) ] }")
